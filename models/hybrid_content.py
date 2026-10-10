import json, random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence

class Model(nn.Module):
    def __init__(self, public, config):
        super().__init__(); self.config=config
        with np.load(Path(public)/'features.npz',allow_pickle=False) as data:
            ids=data['ids'].tolist(); vectors=np.asarray(data['vectors'],dtype=np.float32)
        self.index={(n.decode() if isinstance(n,bytes) else str(n)):i+1 for i,n in enumerate(ids)}
        self.register_buffer('features',torch.cat([torch.zeros(1,128),F.normalize(torch.from_numpy(vectors),dim=-1)]))
        self.project=nn.Linear(128,128,bias=False); nn.init.eye_(self.project.weight)
        self.gru=nn.GRU(128,128,batch_first=True)
        self.temperature=nn.Parameter(torch.tensor(1.4))
        self.recency=nn.Parameter(torch.tensor(-2.0))
        self.scale=nn.Parameter(torch.tensor(1.7))
        self.mean_scale=nn.Parameter(torch.tensor(0.0))
        self.sequence_scale=nn.Parameter(torch.tensor(0.0))
        self.raw_scale=nn.Parameter(torch.tensor(0.0))
        self.dropout=nn.Dropout(0.15)
        self.prior=nn.Sequential(nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))
    def tensors(self, rows, candidates):
        histories=[[self.index.get(n,0) for n in r['history'][-80:]] for r in rows]
        lengths=[max(1,len(h)) for h in histories]; width=max(lengths)
        hi=torch.tensor([h+[0]*(width-len(h)) for h in histories],dtype=torch.long)
        short=[h[-20:] for h in histories]; sl=[max(1,len(h)) for h in short]
        si=torch.tensor([h+[0]*(max(sl)-len(h)) for h in short],dtype=torch.long)
        cw=max(1,max(map(len,candidates)))
        ci=torch.tensor([[self.index.get(n,0) for n in c]+[0]*(cw-len(c)) for c in candidates],dtype=torch.long)
        mask=torch.arange(cw)[None,:]<torch.tensor([len(c) for c in candidates])[:,None]
        age=(torch.tensor(lengths)[:,None]-1-torch.arange(width)[None,:]).clamp_min(0).float()
        return hi,ci,age,mask,si,sl
    def logits(self, rows, candidates):
        hi,ci,age,mask,si,sl=self.tensors(rows,candidates)
        rawh=self.features[hi]; rawc=self.features[ci]
        h=F.normalize(self.project(rawh),dim=-1)
        c=F.normalize(self.project(rawc),dim=-1)
        hm=hi!=0; sim=torch.bmm(c,h.transpose(1,2))
        energy=self.temperature.exp().clamp(max=20)*sim-F.softplus(self.recency)*torch.log1p(age)[:,None,:]
        weights=energy.masked_fill(~hm[:,None,:],-1e4).softmax(-1)*hm[:,None,:]
        weights=weights/weights.sum(-1,keepdim=True).clamp_min(1e-8)
        matched=(weights*sim).sum(-1)
        mean=(h*hm[:,:,None]).sum(1)/hm.sum(1,keepdim=True).clamp_min(1)
        global_sim=(c*F.normalize(mean,dim=-1)[:,None,:]).sum(-1)
        sh=self.dropout(F.normalize(self.project(self.features[si]),dim=-1))
        packed=pack_padded_sequence(sh,sl,batch_first=True,enforce_sorted=False)
        seq=F.normalize(self.gru(packed)[1][0],dim=-1)
        sequence_sim=(c*seq[:,None,:]).sum(-1)*hm.any(1)[:,None]
        rawmean=(rawh*hm[:,:,None]).sum(1)/hm.sum(1,keepdim=True).clamp_min(1)
        raw_sim=(rawc*F.normalize(rawmean,dim=-1)[:,None,:]).sum(-1)
        scores=self.scale.exp().clamp(max=30)*matched+F.softplus(self.mean_scale)*global_sim
        scores=scores+F.softplus(self.sequence_scale)*sequence_sim+F.softplus(self.raw_scale)*raw_sim+self.prior(rawc).squeeze(-1)
        return scores.masked_fill(~mask,-1e9)
    def fit(self, rows, output_dir):
        rng=random.Random(self.config['seed']); opt=torch.optim.Adam(self.parameters(),lr=0.001,weight_decay=1e-5)
        for epoch in range(self.config['epochs']):
            order=list(rows); rng.shuffle(order); losses=[]; self.train()
            for offset in range(0,len(order),self.config['batch_size']):
                batch=order[offset:offset+self.config['batch_size']]; cs=[]
                for r in batch:
                    neg=[n for n in r['candidates'] if n!=r['positive']]
                    cs.append([r['positive']]+rng.sample(neg,min(4,len(neg))))
                loss=F.cross_entropy(self.logits(batch,cs),torch.zeros(len(batch),dtype=torch.long))
                opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(self.parameters(),5); opt.step(); losses.append(loss.item())
            print(json.dumps({'epoch':epoch+1,'loss':float(np.mean(losses))}),flush=True)
        torch.save(self.state_dict(),Path(output_dir)/'checkpoint.pt')
    def score(self, rows):
        self.eval(); out=[]
        with torch.no_grad():
            for start in range(0,len(rows),32):
                batch=rows[start:start+32]; cs=[r['candidates'] for r in batch]; scores=self.logits(batch,cs)
                for i,c in enumerate(cs):
                    values=scores[i,:len(c)].tolist()
                    if not np.isfinite(values).all(): raise ValueError('Nonfinite scores')
                    out.append(values)
        return out

def build(public_path, config): return Model(public_path,config)

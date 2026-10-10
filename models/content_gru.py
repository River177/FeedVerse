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
        with np.load(Path(public)/'features.npz', allow_pickle=False) as data:
            ids=data['ids'].tolist(); vectors=np.asarray(data['vectors'],dtype=np.float32)
        self.index={(n.decode() if isinstance(n,bytes) else str(n)):i+1 for i,n in enumerate(ids)}
        v=F.normalize(torch.from_numpy(vectors),dim=-1)
        self.register_buffer('features',torch.cat([torch.zeros(1,128),v]))
        self.project=nn.Linear(128,128,bias=False)
        nn.init.eye_(self.project.weight)
        self.gru=nn.GRU(128,128,batch_first=True)
        self.mix=nn.Parameter(torch.tensor(-1.0))
        self.scale=nn.Parameter(torch.tensor(2.0))
        self.prior=nn.Sequential(nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))
    def tensors(self, rows, candidates):
        histories=[[self.index.get(n,0) for n in r['history'][-50:]] for r in rows]
        lengths=[max(1,len(h)) for h in histories]; width=max(lengths)
        hi=torch.tensor([h+[0]*(width-len(h)) for h in histories],dtype=torch.long)
        cw=max(1,max(map(len,candidates)))
        ci=torch.tensor([[self.index.get(n,0) for n in c]+[0]*(cw-len(c)) for c in candidates],dtype=torch.long)
        mask=torch.arange(cw)[None,:]<torch.tensor([len(c) for c in candidates])[:,None]
        return hi,ci,lengths,mask
    def logits(self, rows, candidates):
        hi,ci,lengths,mask=self.tensors(rows,candidates)
        h=F.normalize(self.project(self.features[hi]),dim=-1)
        c=F.normalize(self.project(self.features[ci]),dim=-1)
        hm=(hi!=0).float().unsqueeze(-1)
        mean=(h*hm).sum(1)/hm.sum(1).clamp_min(1)
        packed=pack_padded_sequence(h,lengths,batch_first=True,enforce_sorted=False)
        recurrent=self.gru(packed)[1][0]
        user=F.normalize(mean+torch.sigmoid(self.mix)*recurrent,dim=-1)
        scores=self.scale.exp().clamp(max=30)*(c*user[:,None,:]).sum(-1)+self.prior(self.features[ci]).squeeze(-1)
        return scores.masked_fill(~mask,-1e9)
    def fit(self, rows, output_dir):
        rng=random.Random(self.config['seed'])
        opt=torch.optim.Adam(self.parameters(),lr=0.001,weight_decay=1e-5)
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
                batch=rows[start:start+32]; cs=[r['candidates'] for r in batch]
                scores=self.logits(batch,cs)
                for i,c in enumerate(cs):
                    values=scores[i,:len(c)].tolist()
                    if not np.isfinite(values).all(): raise ValueError('Nonfinite scores')
                    out.append(values)
        return out

def build(public_path, config): return Model(public_path,config)

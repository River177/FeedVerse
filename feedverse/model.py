"""Frozen baseline; candidates receive an independent copy of this file."""
import json, random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence

class Model(nn.Module):
    def __init__(self, public, config):
        super().__init__(); self.config=config
        self.seen=json.loads((Path(public)/'seen.json').read_text()); self.index={n:i+1 for i,n in enumerate(self.seen)}
        self.embedding=nn.Embedding(len(self.seen)+1,64)
        self.gru=nn.GRU(64,64,batch_first=True)
    def encode(self, rows):
        lengths=[max(1,len(r['history'])) for r in rows]
        h=torch.tensor([[self.index.get(n,0) for n in r['history']]+[0]*(max(lengths)-len(r['history'])) for r in rows],dtype=torch.long)
        packed=pack_padded_sequence(self.embedding(h),lengths,batch_first=True,enforce_sorted=False)
        return self.gru(packed)[1][0]
    def logits(self, rows, candidates):
        ids=torch.tensor([[self.index.get(n,0) for n in c] for c in candidates],dtype=torch.long)
        return (self.encode(rows).unsqueeze(1)*self.embedding(ids)).sum(-1)/8
    def fit(self, rows, output):
        rng=random.Random(self.config['seed']); opt=torch.optim.Adam(self.parameters(),lr=0.001)
        for epoch in range(self.config['epochs']):
            order=list(rows); rng.shuffle(order); losses=[]; self.train()
            for offset in range(0,len(order),self.config['batch_size']):
                batch=order[offset:offset+self.config['batch_size']]
                cs=[[r['positive']]+rng.sample([n for n in r['candidates'] if n!=r['positive']],min(4,len(r['candidates'])-1)) for r in batch]
                loss=nn.functional.cross_entropy(self.logits(batch,cs),torch.zeros(len(batch),dtype=torch.long))
                opt.zero_grad(); loss.backward(); opt.step(); losses.append(loss.item())
            print(json.dumps({'epoch':epoch+1,'loss':float(np.mean(losses))}),flush=True)
        torch.save(self.state_dict(),Path(output)/'checkpoint.pt')
    def score(self, rows):
        self.eval(); out=[]
        with torch.no_grad():
            for r in rows: out.append(self.logits([r],[r['candidates']])[0].tolist())
        return out

def build(public, config): return Model(public,config)

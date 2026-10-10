import math
from collections import Counter
import numpy as np

def rankings(rows,scores):
    if len(rows)!=len(scores): raise ValueError('Score row count mismatch')
    ranked=[]
    for r,s in zip(rows,scores):
        if len(set(r['candidates']))!=len(r['candidates']): raise ValueError('Duplicate candidates')
        if len(s)!=len(r['candidates']) or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in s): raise ValueError('Invalid scores')
        if r['positive'] not in r['candidates']: raise ValueError('Positive absent from candidates')
        # Deterministic, candidate-order tie resolution, never labels.
        ranked.append(sorted(range(len(s)),key=lambda i:(-s[i],i)))
    return ranked

def metrics(rows,scores,seen):
    ranks=rankings(rows,scores); seen=set(seen)
    def group(indices):
        if not indices: return {'count':0,'Recall@5':None,'Recall@10':None,'NDCG@5':None,'NDCG@10':None,'MRR':None,'article_coverage':None,'exposure_hhi':None}
        positions=[next(j+1 for j,i in enumerate(ranks[k]) if rows[k]['candidates'][i]==rows[k]['positive']) for k in indices]
        m={'count':len(indices),'MRR':float(np.mean([1/p for p in positions]))}
        for cutoff in (5,10):
            m[f'Recall@{cutoff}']=float(np.mean([p<=cutoff for p in positions]))
            m[f'NDCG@{cutoff}']=float(np.mean([1/math.log2(p+1) if p<=cutoff else 0 for p in positions]))
        exposure=Counter(rows[k]['candidates'][i] for k in indices for i in ranks[k][:10]); catalogue={n for k in indices for n in rows[k]['candidates']}
        m['article_coverage']=len(exposure)/len(catalogue); total=sum(exposure.values()); m['exposure_hhi']=sum((v/total)**2 for v in exposure.values())
        return m
    return {'overall':group(list(range(len(rows)))),'cold':group([i for i,r in enumerate(rows) if r['positive'] not in seen])}

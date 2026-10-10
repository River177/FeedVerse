"""Independent pure-Python metric recomputation from saved full-candidate scores."""
import json, math,time
from collections import Counter
from .data import sha,dump

def independently_compute(rows,scores,seen):
    result={}
    for name,indices in [('overall',list(range(len(rows)))),('cold',[i for i,r in enumerate(rows) if r['positive'] not in seen])]:
        if not indices:
            result[name]={'count':0,**{k:None for k in ['MRR','Recall@5','Recall@10','NDCG@5','NDCG@10','article_coverage','exposure_hhi']}}; continue
        totals={k:0.0 for k in ['MRR','Recall@5','Recall@10','NDCG@5','NDCG@10']}; exposure=Counter(); catalogue=set()
        for i in indices:
            r=rows[i]; s=scores[i]; ordered=sorted(zip(r['candidates'],s,range(len(s))),key=lambda x:(-x[1],x[2])); assert len({n for n,_,_ in ordered})==len(r['candidates'])
            rank=[n for n,_,_ in ordered].index(r['positive'])+1; totals['MRR']+=1/rank
            for k in [5,10]:
                if rank<=k: totals[f'Recall@{k}']+=1; totals[f'NDCG@{k}']+=math.log(2)/math.log(rank+1)
            exposure.update(n for n,_,_ in ordered[:10]); catalogue.update(r['candidates'])
        result[name]={'count':len(indices),**{k:v/len(indices) for k,v in totals.items()},'article_coverage':len(exposure)/len(catalogue),'exposure_hhi':sum(v*v for v in exposure.values())/sum(exposure.values())**2}
    return result

def audit(b):
    data_hash=b.check_data(); m=json.loads((b.frozen/'manifest.json').read_text()); seen=set(json.loads((b.public/'seen.json').read_text()))
    for path,h in m['sources'].items(): assert sha(path)==h,'Raw source changed'
    train=json.loads((b.public/'train.json').read_text()); valid=json.loads((b.frozen/'validation.json').read_text()); held=json.loads((b.frozen/'heldout.json').read_text())
    assert not {r['user'] for r in valid}&{r['user'] for r in held}
    for rows in [train,valid,held]:
        for r in rows: assert 3<=len(r['history'])<=50 and len(r['candidates'])>=20 and r['candidates'].count(r['positive'])==1 and len(set(r['candidates']))==len(r['candidates'])
    assert seen=={n for r in train for n in r['history']+[r['positive']]}
    selection=json.loads((b.root/'selection.json').read_text()); reports=[]
    for p in sorted(b.variants.iterdir()):
        for split in ['validation','heldout']:
            f=p/(split+'-evaluation.json')
            if not f.exists(): continue
            report=json.loads(f.read_text()); scores_path=p/('score-'+split)/'scores.json'; assert sha(scores_path)==report['scores_sha256']
            identity=b.identity(p.name); assert all(report['identity'].get(k)==v for k,v in identity.items()); assert sha(p/'artifacts/checkpoint.pt')==report['identity']['checkpoint_sha256']
            inputs=json.loads((p/('score-'+split)/'input.json').read_text()); assert all('positive' not in r for r in inputs)
            rows=valid if split=='validation' else held; assert [{k:v for k,v in r.items() if k!='positive'} for r in rows]==inputs
            scores=json.loads(scores_path.read_text()); assert len(scores)==len(rows)
            assert all(len(s)==len(r['candidates']) and all(math.isfinite(x) for x in s) for r,s in zip(rows,scores))
            recomputed=independently_compute(rows,scores,seen)
            for group in recomputed:
                for key,value in recomputed[group].items():
                    recorded=report['metrics'][group][key]
                    assert recorded is None if value is None else abs(value-recorded)<1e-12,(p.name,split,group,key)
            if split=='heldout': assert report['variant'] in ['baseline',selection['selected']]
            reports.append({'variant':p.name,'split':split,'metrics':recomputed,'report_sha256':sha(f),'identity':report['identity']})
    assert any(r['variant']==selection['selected'] and r['split']=='heldout' for r in reports)
    assert len([p for p in b.variants.iterdir() if p.name!='baseline'])<=3
    for v,h in selection['reports_sha256'].items(): assert sha(b.path(v)/'validation-evaluation.json')==h
    result={'passed':True,'time':time.time(),'data_manifest_sha256':data_hash,'selection':selection,'checks':['raw source hashes','frozen file hashes','eligibility and unique positive','validation/heldout user isolation','training-only cold definition','checkpoint/source/config identity','label-free scoring inputs','canonical scores/rankings','pure-Python independent metrics','selection frozen before heldout','three-candidate limit'],'reports':reports}
    dump(b.root/'audit.json',result); return result

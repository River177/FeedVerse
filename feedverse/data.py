import hashlib, json, random
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

SEED = 42

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
    return h.hexdigest()

def dump(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def eligible(path):
    rows=[]
    for line in Path(path).read_text().splitlines():
        iid, uid, time, history, impressions = line.split('\t')
        pairs=[x.rsplit('-',1) for x in impressions.split()]
        pos=[n for n,l in pairs if l=='1']; candidates=[n for n,l in pairs]
        if len(history.split())>=3 and len(pos)==1 and len(candidates)>=20:
            assert len(set(candidates))==len(candidates)
            rows.append(dict(id=iid,user=uid,time=time,history=history.split()[-50:],candidates=candidates,positive=pos[0]))
    return rows

def prepare(raw, root):
    root=Path(root); frozen=root/'frozen'; public=root/'public'
    if (frozen/'manifest.json').exists():
        manifest=json.loads((frozen/'manifest.json').read_text())
        for rel,h in manifest['outputs'].items():
            if sha(root/rel)!=h: raise ValueError('Frozen data changed: '+rel)
        return manifest
    raw=Path(raw); rng=random.Random(SEED)
    sources={str(raw/split/name):sha(raw/split/name) for split in ['MINDsmall_train','MINDsmall_dev'] for name in ['news.tsv','behaviors.tsv']}
    train=rng.sample(eligible(raw/'MINDsmall_train/behaviors.tsv'),20000)
    dev=eligible(raw/'MINDsmall_dev/behaviors.tsv'); users=sorted({r['user'] for r in dev}); rng.shuffle(users)
    vu=set(users[:len(users)//2]); valid=rng.sample([r for r in dev if r['user'] in vu],1000); held=rng.sample([r for r in dev if r['user'] not in vu],1000)
    assert not {r['user'] for r in valid}&{r['user'] for r in held}
    seen=sorted({n for r in train for n in r['history']+[r['positive']]}); seen_set=set(seen)
    # Training-side article text only: includes logged train candidates, never dev-only articles.
    fit_ids=sorted({n for r in train for n in r['history']+r['candidates']})
    news={}
    for split in ['MINDsmall_train','MINDsmall_dev']:
        for line in (raw/split/'news.tsv').read_text().splitlines():
            p=line.split('\t'); news.setdefault(p[0],dict(category=p[1],subcategory=p[2],title=p[3],abstract=p[4]))
    ids=sorted({n for r in train+valid+held for n in r['history']+r['candidates']})
    def text(n): return news[n]['title']+' '+news[n]['abstract']+' '+news[n]['category']
    tf=TfidfVectorizer(max_features=20000, min_df=2, dtype=np.float32)
    x=tf.fit_transform([text(n) for n in fit_ids]); svd=TruncatedSVD(n_components=128,random_state=SEED)
    svd.fit(x)
    features=svd.transform(tf.transform([text(n) for n in ids])).astype('float32')
    public.mkdir(parents=True,exist_ok=True); frozen.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(public/'features.npz',ids=np.array(ids),vectors=features)
    import pickle
    with open(frozen/'text-transform.pkl','wb') as f: pickle.dump((tf,svd),f)
    dump(public/'articles.json',{n:news[n] for n in ids}); dump(public/'seen.json',seen); dump(public/'train.json',train)
    for split,rows in [('validation',valid),('heldout',held)]:
        dump(frozen/(split+'.json'),rows)
    dump(public/'validation-input.json',[{k:v for k,v in r.items() if k!='positive'} for r in valid])
    coverage={s:sum(r['positive'] not in seen_set for r in rows) for s,rows in [('validation',valid),('heldout',held)]}
    files=list(public.glob('*'))+list(frozen.glob('*'))
    manifest=dict(protocol='feedverse-mind-cold-v1',seed=SEED,sources=sources,counts={'train':len(train),'validation':len(valid),'heldout':len(held)},cold_positive_counts=coverage,train_seen_articles=len(seen),feature_fit_articles=len(fit_ids),feature_fit_ids_sha256=hashlib.sha256('\n'.join(fit_ids).encode()).hexdigest(),sample_ids={s:[r['id'] for r in rows] for s,rows in [('train',train),('validation',valid),('heldout',held)]},outputs={str(p.relative_to(root)):sha(p) for p in files})
    dump(frozen/'manifest.json',manifest)
    return manifest

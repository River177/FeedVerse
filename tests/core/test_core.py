import json, math, tempfile, time, unittest, os, signal
from pathlib import Path
import numpy as np
import torch
from feedverse.data import eligible,dump,sha
from feedverse.evaluation import metrics,rankings
from feedverse.backend import Backend
from feedverse.sandbox import probe

class ProtocolTests(unittest.TestCase):
    def test_labels_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'behaviors.tsv'; cs=' '.join(f'N{i}-{int(i==3)}' for i in range(20))
            p.write_text(f'1\tu\tt\tN1 N2 N4\t{cs}\n2\tu\tt\tN1\t{cs}\n3\tu\tt\tN1 N2 N3\tN1-1 N2-1\n')
            r=eligible(p); self.assertEqual(len(r),1); self.assertEqual(r[0]['positive'],'N3'); self.assertEqual(len(r[0]['candidates']),20)
    def test_metrics_independent(self):
        rows=[{'positive':'a','candidates':['a','b','c']},{'positive':'b','candidates':['a','b','c']}]
        scores=[[3,2,1],[3,2,1]]; m=metrics(rows,scores,['a'])
        self.assertEqual(m['overall']['MRR'],.75); self.assertAlmostEqual(m['cold']['NDCG@10'],1/math.log2(3)); self.assertEqual(m['cold']['count'],1)
        self.assertIsNone(metrics(rows,scores,['a','b'])['cold']['MRR'])
    def test_invalid(self):
        r=[{'positive':'a','candidates':['a','b']}]
        for s in [[[float('nan'),0]],[[1]],[],[[float('inf'),1]]]:
            with self.assertRaises(ValueError): rankings(r,s)
        with self.assertRaises(ValueError): rankings([{'positive':'a','candidates':['a','a']}],[[1,1]])
        with self.assertRaises(ValueError): rankings([{'positive':'c','candidates':['a','b']}],[[1,1]])
    def test_unknown_empty_and_reload(self):
        from feedverse.model import build
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); dump(p/'seen.json',['a']); config={'seed':42,'epochs':1,'batch_size':1}
            torch.manual_seed(42); m=build(p,config)
            r=[{'history':[],'candidates':['unseen','a']}]; scores=m.score(r)
            self.assertTrue(np.isfinite(scores).all()); torch.save(m.state_dict(),p/'checkpoint.pt'); m2=build(p,config); m2.load_state_dict(torch.load(p/'checkpoint.pt',weights_only=True))
            self.assertEqual(scores,m2.score(r)); self.assertEqual(m.index.get('unseen',0),0)
    def test_mcp_hides_heldout(self):
        from feedverse.mcp import dispatch
        with tempfile.TemporaryDirectory() as d:
            b=Backend(d)
            listing=dispatch(b,{'id':1,'method':'tools/list'})['result']['tools']
            self.assertEqual(len(listing),10); self.assertFalse(any('heldout' in t['name'] for t in listing))
            for name,args in [('evaluate_variant',{'variant':'baseline','split':'heldout'}),('heldout',{'variant':'baseline'})]:
                result=dispatch(b,{'id':2,'method':'tools/call','params':{'name':name,'arguments':args}})
                self.assertTrue(result['result']['isError'])
    def test_sandbox(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'local') as d:
            self.assertTrue(all(probe(d)['blocked'].values()))

class JobsTests(unittest.TestCase):
    def test_cancel_resume_identity_and_freeze(self):
        # Separate tiny fixture, never part of the scientific candidate count.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'local') as d:
            b=Backend(d); row={'id':'1','user':'u','history':['a']*3,'candidates':['a','b'],'positive':'a'}
            dump(b.public/'train.json',[row]); dump(b.public/'seen.json',['a']); dump(b.public/'articles.json',{}); dump(b.public/'validation-input.json',[{k:v for k,v in row.items() if k!='positive'}]); dump(b.frozen/'validation.json',[row]); dump(b.frozen/'heldout.json',[row]);
            dump(b.frozen/'manifest.json',{'outputs':{str(p.relative_to(b.root)):sha(p) for p in list(b.public.glob('*'))+list(b.frozen.glob('*'))}})
            b.create_variant('baseline',None); p=b.path('baseline'); model=p/'source/model.py'
            model.write_text(model.read_text().replace("rng=random.Random(self.config['seed']);", "import time; time.sleep(3); rng=random.Random(self.config['seed']);"))
            dump(p/'artifacts/config.json',{'seed':42,'threads':1,'epochs':1,'batch_size':1})
            first=b.train_variant('baseline'); self.assertEqual(b.train_variant('baseline')['id'],first['id']); time.sleep(.8); self.assertEqual(b.cancel(first['id'])['state'],'cancelled')
            resumed=b.train_variant('baseline'); self.assertNotEqual(first['id'],resumed['id']); self.assertTrue((p/'attempts'/first['id']/'job.json').exists())
            time.sleep(1); os.kill(resumed['pid'],signal.SIGKILL)
            for _ in range(40):
                interrupted=b.get_job_status(resumed['id'])
                if interrupted['state']=='interrupted': break
                time.sleep(.1)
            self.assertEqual(interrupted['state'],'interrupted')
            lost_id=resumed['id']; resumed=b.train_variant('baseline'); self.assertNotEqual(resumed['id'],lost_id)
            deadline=time.time()+30
            while time.time()<deadline:
                result=b.get_job_status(resumed['id'])
                if result['state'] not in ['queued','running']: break
                time.sleep(.25)
            self.assertEqual(result['state'],'completed',result)
            self.assertEqual(b.train_variant('baseline')['id'],resumed['id']); self.assertTrue((p/'attempts'/resumed['id']/'checkpoint.pt').exists())
            report=b.evaluate_variant('baseline'); self.assertEqual(report['metrics']['overall']['count'],1)
            with self.assertRaises(ValueError): b.patch_source('baseline','x=1')
            b.create_variant('one'); b.create_variant('two'); b.create_variant('three')
            good=b.read_source('one').replace('import time; time.sleep(3); ','')
            bad=good.replace('return out','return [[float("nan") for _ in r["candidates"]] for r in rows]')
            b.patch_source('one',bad); dump(b.path('one')/'artifacts/config.json',{'seed':42,'threads':1,'epochs':1,'batch_size':1})
            def finish(job):
                limit=time.time()+15
                while time.time()<limit:
                    status=b.get_job_status(job['id'])
                    if status['state'] not in ['queued','running']: return status
                    time.sleep(.1)
                self.fail('Test job did not finish')
            self.assertEqual(finish(b.train_variant('one'))['state'],'completed')
            with self.assertRaises(RuntimeError): b.evaluate_variant('one')
            self.assertTrue((b.path('one')/'validation-failure.json').exists())
            b.patch_source('one',good); self.assertEqual(finish(b.train_variant('one'))['state'],'completed'); b.evaluate_variant('one')
            with self.assertRaises(ValueError): b.patch_source('one',good+'\n# cannot edit validated model\n')
            with self.assertRaises(ValueError): b.create_variant('four')
            with self.assertRaises(FileNotFoundError): b.evaluate_variant('baseline','heldout')
            selection=b.select(); self.assertEqual(selection['selected'],'baseline'); b.evaluate_variant('baseline','heldout')
            with self.assertRaises(ValueError): b.patch_source('one','x=1')
            model.write_text(model.read_text()+'\n# changed\n')
            with self.assertRaises(ValueError): b.evaluate_variant('baseline')
if __name__=='__main__': unittest.main()

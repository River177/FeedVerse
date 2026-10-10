"""Copied into sandbox; only public inputs, candidate source and artifacts are visible."""
import importlib.util,json,sys,random
from pathlib import Path
import numpy as np
import torch
mode,source,public,artifacts,inputs=sys.argv[1:]
config=json.loads((Path(artifacts)/'config.json').read_text())
random.seed(config['seed']); np.random.seed(config['seed']); torch.manual_seed(config['seed']); torch.set_num_threads(config['threads'])
spec=importlib.util.spec_from_file_location('candidate',source); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
model=module.build(public,config)
if mode=='train':
    model.fit(json.loads((Path(public)/'train.json').read_text()),artifacts)
else:
    model.load_state_dict(torch.load(Path(artifacts)/'checkpoint.pt',weights_only=True,map_location='cpu'))
    rows=json.loads(Path(inputs).read_text()); scores=model.score(rows)
    Path(artifacts,'scores.json').write_text(json.dumps(scores,allow_nan=False))

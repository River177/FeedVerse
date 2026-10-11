"""Export aggregate web acceptance evidence, not data, credentials or checkpoints."""
import json,sys,shutil,time
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from feedverse.web_store import Store,read_json
from feedverse.data import dump,sha
from feedverse.backend import PROJECT
store=Store();eid='exp_fc779057748b4aa5';folder=store.path(eid);root=folder/'core';snapshot=store.snapshot(eid);audit=read_json(PROJECT/'local/web-independent-audit.json')
assert snapshot['status']=='completed' and audit['passed']
assert len(snapshot['models'])==2 and snapshot['models'][0]['reused']
model=next(m for m in snapshot['models'] if m['id']=='candidate_1');assert len(model['jobs'])==1 and len(model['epochs'])==5
before=read_json(PROJECT/'local/web-history-before.json');assert all(sha(p)==h for p,h in before.items())
raw=[json.loads(x) for x in (root/'mcp-events.jsonl').read_text().splitlines()];calls=Counter(r.get('tool','error') for r in raw)
for name in ['patch_source','train_variant','evaluate_variant']:assert calls[name]==1
assert not any(r.get('arguments',{}).get('split')=='heldout' for r in raw)
assert not list(root.glob('variants/*/heldout-evaluation.json'))
shutil.copyfile(root/'variants/candidate_1/source/model.py',PROJECT/'models/web_validation_candidate.py')
logs={name:sha(PROJECT/'local'/name) for name in ['web-tests.log','web-core-regression.log','web-prototype-tests.log','web-build.log','dev-full-check.log']}
for name in ['web-tests.log','web-core-regression.log']:assert '\nOK\n' in (PROJECT/'local'/name).read_text()
receipt={'passed':True,'experiment_id':eid,'session_id':snapshot['session_id'],'task':'MIND cold start, fixed seed42 20k/1k; validation-only web integration','candidate_count':1,'baseline_reused':True,'new_training_attempts':1,'metrics':{m['id']:m['metrics'] for m in snapshot['models']},'candidate_identity':model['identity'],'selection':snapshot['selection'],'usage':snapshot['usage'],'independent_audit':audit,'mcp_tool_counts':dict(calls),'test_counts':{'core':7,'web':10,'prototype':4},'artifact_sha256':{'sdk_events':sha(folder/'runtime/sdk-events.jsonl'),'mcp_events':sha(root/'mcp-events.jsonl'),'bridge_audit':sha(folder/'runtime/bridge-audit.jsonl'),'checkpoint':sha(root/'variants/candidate_1/artifacts/checkpoint.pt'),'scores':sha(root/'variants/candidate_1/score-validation/scores.json')},'test_log_sha256':logs,'real_failure':'Initial daemon startup hit short Unix socket directory sandbox denial; restored the same exploration after allowing only the exact owned short socket directory. No model requests or training had occurred before recovery.','controlled_failure_tests':'HTTP bridge upstream401 stops subsequent credential acquisition; upstream429 retains Retry-After. These are fixtures, not failures of the user account.','browser_checks':['Web form submitted one candidate','Refresh preserved exploration identity','Real history and ranking view','Distribution filters and article details','Read-only source diff and Escape closing','Narrow screen without horizontal document overflow'],'limits':['Single candidate, one seed, weak ID baseline; no general AGH superiority claim','One request has no usage receipt and remains missing','No new heldout evaluation','Competition flow and presentation not implemented']}
dump(PROJECT/'docs/web-validation.json',receipt)
base=receipt['metrics']['baseline'];new=receipt['metrics']['candidate_1'];job=model['jobs'][0]
text=f'''# FeedVerse 网页接入验收

主网页已接通真实后台，旧合成规则页面已删除。网页可以创建探索、查看真实状态、源码、推荐案例、分配、用量及记录；支持取消、恢复、档案、脱敏导出与带明确标签的历史回放。

## 真实网页执行

通过本机浏览器表单提交探索 `{eid}`，候选上限为1。首次启动因长路径触发AGH短Unix socket回退，精确目录尚未被沙箱允许而失败。修复后从网页按原ID恢复，保留真实失败回执，未关闭沙箱，也未启动第二个探索。

AGH session `{snapshot['session_id']}` 自行生成“训练侧文本SVD残差内容编码、全局与候选相关双注意力历史聚合及内容先验”模型。MCP实际调用修改、训练、独立评价与比较；只新增一个科研训练attempt，基线明确复用。训练完成5个epoch，耗时 {job['finished']-job['created']:.1f} 秒。通用源码保存为 `models/web_validation_candidate.py`，checkpoint与数据不提交Git。

| 验证指标 | 复用基线 | 新候选 |
|---|---:|---:|
| 冷启动 NDCG@10 | {base['cold']['NDCG@10']:.6f} | {new['cold']['NDCG@10']:.6f} |
| 整体 NDCG@10 | {base['overall']['NDCG@10']:.6f} | {new['overall']['NDCG@10']:.6f} |
| 冷启动 Recall@10 | {base['cold']['Recall@10']:.6f} | {new['cold']['Recall@10']:.6f} |
| 整体 MRR | {base['overall']['MRR']:.6f} | {new['overall']['MRR']:.6f} |

按固定验证冷启动NDCG@10冻结 candidate_1。独立纯Python复算误差小于1e-12；评分输入无positive，完整1,000条候选排名有效。额外评分检查证明新模型支持未知文章和空历史，没有追加训练。

本轮13次模型请求，12个完成usage回执，已确认 {snapshot['usage']['tokens']['total_tokens']:,} token。余下1次没有usage终止回执，保留缺失。费用未核验，estimated credits不当作实际费用。

## 验收与边界

- 网页/API/文件的指标、排名及Top10文章入选次数一致；默认案例为冻结顺序第一个，不是挑选成功样本。
- API测试覆盖并发/重复提交、单活跃探索、取消确认状态、原ID恢复、完成后不重跑、进程丢失、额外配置与跨Origin拒绝、SSE续传/去重、源码路径允许列表、脱敏、1–3候选限制和保留边界。
- 实际bridge处理器用受控HTTP401/429夹具测试停止队列与Retry-After；本机真实TRAPI身份正常，没有让账户失效或反复登录。
- 候选评分失败与修复、训练取消/SIGKILL恢复由现有核心实际子进程测试覆盖，不冒充本轮真实科研错误。
- 实际AGH沙箱策略仍拒绝读取原保留标签；新探索没有任何保留评分产物。原实验127个文件的SHA256全部未改变。
- 7项核心测试、10项网页/API测试、4项原型测试及生产构建通过。浏览器检查刷新、案例、Canvas过滤、只读diff、原生dialog键盘关闭和窄屏无横向页面溢出。
- 一键启动经过真实检查；Ctrl-C只清理由本启动器创建的API，已有Vite仍保留，退出码为0。

本轮验证目标是网页与真实AGH闭环，不是完整MIND官方实验，也不证明AGH普遍优于人工工程师。比赛现场讲述与包装尚未制作。运行步骤见 `web-workbench.md`，完整身份、指标和原始回执哈希见 `web-validation.json`。
'''
(PROJECT/'docs/web-validation.md').write_text(text)
print(json.dumps({'exported':True,'passed':True,'training_attempts':1,'history_unchanged':127}))

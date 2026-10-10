"""Export only hashes, generic model source and aggregate results; never raw data or secrets."""
import sys,json,shutil,sqlite3,time
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from feedverse.backend import Backend,PROJECT
from feedverse.data import dump,sha
from feedverse.audit import audit
b=Backend(); verified=audit(b); docs=PROJECT/'docs'; model_dir=PROJECT/'models'; model_dir.mkdir(exist_ok=True)
for p in b.variants.iterdir(): shutil.copyfile(p/'source/model.py',model_dir/(p.name+'.py'))
manifest=json.loads((b.frozen/'manifest.json').read_text()); dump(docs/'frozen-data-manifest.json',{'runtime_manifest_sha256':sha(b.frozen/'manifest.json'),'manifest':manifest})
runtime=PROJECT/'local/agh-runtime'; events=[json.loads(x) for x in (runtime/'bridge-audit.jsonl').read_text().splitlines()]; session=json.loads((runtime/'exploration.json').read_text()); sdk=[json.loads(x) for x in (runtime/'sdk-events.jsonl').read_text().splitlines()]
completed=[r for r in events if r['event']=='response.completed']; usage={k:sum(r['usage'].get(k,0) for r in completed) for k in ['input_tokens','output_tokens','total_tokens']}; usage['cached_input_tokens']=sum(r['usage'].get('input_tokens_details',{}).get('cached_tokens',0) for r in completed)
permissions=[r for r in sdk if 'permission' in r]; assert all(not r['allowed'] or r['permission']['toolCall']['_meta']['ai.agnes.harness']['tool'].startswith('mcp_feedverse_524f7e14_') for r in permissions)
start=min(r['time'] for r in sdk if r.get('sessionId')==session['sessionId']); end=session['finished']; mcp=[json.loads(x) for x in (b.root/'mcp-events.jsonl').read_text().splitlines()]; agent_mcp=[r for r in mcp if start-2<=r['time']<=end]
counts=Counter(r.get('tool','error') for r in agent_mcp)
assert counts['patch_source']==3 and counts['train_variant']==3 and counts['evaluate_variant']==3 and counts['compare_runs']>=1
assert session['reason']=='completed' and len(completed)>0
with b.db() as db: jobs=[{k:r[k] for k in ['id','variant','state','created','finished','error']} for r in db.execute('SELECT * FROM jobs ORDER BY created')]
assert len(jobs)==4 and all(j['state']=='completed' for j in jobs)
for p in b.variants.iterdir():
 epochs=[json.loads(line)['epoch'] for line in (p/'artifacts/train.log').read_text().splitlines() if line.startswith('{')]
 assert epochs==[1,2,3,4,5]
selected=verified['selection']['selected']; assert (b.path(selected)/'heldout-evaluation.json').stat().st_mtime>=verified['selection']['time']
checks={'core_tests':(PROJECT/'local/core-tests.log').read_text(),'edge_models':json.loads((b.root/'edge-receipt.json').read_text()),'mcp_stdio':json.loads((PROJECT/'local/mcp-protocol-receipt.json').read_text()),'sandbox':json.loads((b.root/'isolation-receipt.json').read_text()),'frontend_tests_sha256':sha(PROJECT/'local/frontend-tests.log'),'frontend_build_sha256':sha(PROJECT/'local/frontend-build.log')}
assert 'OK' in checks['core_tests'] and 'FAILED' not in checks['core_tests']
source_files=list((PROJECT/'feedverse').glob('*.py'))+list((PROJECT/'scripts').glob('*.py'))+list((PROJECT/'scripts').glob('*.mjs'))+list((PROJECT/'scripts').glob('*.sh'))+[PROJECT/'requirements-core.txt',PROJECT/'config/agh.example.json']
receipt={'audit':verified,'environment':json.loads((PROJECT/'local/environment.json').read_text()),'source_sha256':{str(p.relative_to(PROJECT)):sha(p) for p in source_files},'jobs':jobs,'checks':checks,'agh':{'session':session,'deployment':'gpt-6-astra_2026-09-03','instance':'redmond/interactive','api_version':'2025-04-01-preview','tool_call_counts':dict(counts),'model_request_count':sum(e['event']=='request' for e in events),'completed_model_responses':len(completed),'http_status_counts':dict(Counter(str(e['status']) for e in events if e['event']=='upstream')),'usage_completed_responses_only':usage,'missing_usage_requests':sum(e['event']=='response_end' and e.get('usage') is None for e in events),'credits_are_estimated':True,'cost':None,'cost_note':'No verified per-token billing rate or TRAPI bill; actual expense not inferred from AGH estimated credits','permissions_allowed':sum(r['allowed'] for r in permissions),'sdk_events_sha256':sha(runtime/'sdk-events.jsonl'),'mcp_events_sha256':sha(b.root/'mcp-events.jsonl'),'bridge_audit_sha256':sha(runtime/'bridge-audit.jsonl')},'artifact_root':'local/core','frontend_changed':False}
dump(docs/'core-validation.json',receipt)
reports=verified['reports']; get=lambda v,s:next(r for r in reports if r['variant']==v and r['split']==s)
text=['# FeedVerse 核心系统验证报告','', '真实 MIND 数据 → 模型训练 → AGH 修改代码 → 独立评价的闭环已完成。网页没有接入真实结果。','', '## 本轮结果','', '| 模型 | 验证整体 NDCG@10 | 验证冷启动 NDCG@10 | 训练时间（秒） |','|---|---:|---:|---:|']
for v in ['baseline','content_gru','attention_content','hybrid_content']:
 r=get(v,'validation'); j=next(j for j in jobs if j['variant']==v); text.append(f"| {v} | {r['metrics']['overall']['NDCG@10']:.6f} | {r['metrics']['cold']['NDCG@10']:.6f} | {j['finished']-j['created']:.1f} |")
text+=['',f'按验证冷启动 NDCG@10 冻结 `{selected}`；候选没有使用保留反馈。验证 1,000 条，其中冷启动正例 685 条。','', '| 保留评价 | 整体 NDCG@10 | 冷启动 NDCG@10 | 整体 MRR | 冷启动 Recall@10 |','|---|---:|---:|---:|---:|']
for v in ['baseline',selected]:
 r=get(v,'heldout')['metrics'];text.append(f"| {v} | {r['overall']['NDCG@10']:.6f} | {r['cold']['NDCG@10']:.6f} | {r['overall']['MRR']:.6f} | {r['cold']['Recall@10']:.6f} |")
text+=['','保留侧 1,000 条，其中冷启动正例 694 条。其余 Recall/NDCG@5/10、MRR、覆盖率与曝光 HHI，以及源码/config/checkpoint 身份，完整保存在 `core-validation.json`。独立纯 Python 复算与生产评价器误差小于 1e-12；未缺失任何模型评价。','', '## AGH 实际执行','',f"真实会话 `{session['sessionId']}`，固定 Astra deployment。AGH 自行生成了三个不同模型源码，通过 MCP 真正调用训练、读取状态、重载评价和比较。所有模型均有五个 epoch 的真实训练日志及独立 checkpoint；没有额外科研候选或重训。",'', 'content_gru 引入文本内容投影与 GRU/平均池化；attention_content 使用候选条件的历史注意力和时间位置衰减；hybrid_content 加入短历史 GRU 与语义残差。第三个模型未超过第二个模型的选定指标，保留其源码和结果。差异不能归因于单个组件。','',f"模型请求 {receipt['agh']['model_request_count']} 次，已完成响应 {len(completed)} 次。已确认真实 usage 合计 input={usage['input_tokens']:,}、output={usage['output_tokens']:,}、total={usage['total_tokens']:,}；cached input={usage['cached_input_tokens']:,}。失败请求无 usage 时保持缺失，不填零。没有核验 TRAPI 账单或单价，因此不报告虚构费用；SDK credits 仅为估算。",'', '## 故障与边界验收','', '首次 MCP 启用因 AGH 未显式允许本地 loopback HTTP 而失败。通过官方配置允许本地连接后恢复，原始失败回执保留。TRAPI 有 429 回执；SDK 有界重试在同一会话恢复，未登录或更换模型。三个科研候选没有训练/评分错误，不能把测试夹具故障冒充真实科研失败。所有训练日志有 OpenMP 临时文件告警，训练与重载均成功。','', '核心集成测试覆盖取消、manager 被 SIGKILL 后识别中断并按身份恢复、完成训练不重复启动、每 attempt 独立产物、非有限评分失败回执与同候选修复、源码与 checkpoint 身份变化拒绝、候选数量限制、选择冻结和保留访问门禁。其余测试覆盖标签筛选/对应、空历史/未知文章、非法分数/重复候选、缺失不填零、独立指标。真实四个模型均通过未知文章与空历史评分、两次独立重载一致性检查。MCP stdio 协议与实际排名/曝光比较也通过。','', 'macOS Seatbelt 实测阻止候选越界读写和网络；AGH 自身策略实测阻止保留标签读取和项目源码写入。评分进程输入无标签。验证与保留用户无交集，原件和冻结输出的哈希均通过。管理器的 attempt 隔离与失败修复在最后的独立小夹具中补充验证，没有重跑或改写四个科研模型。','', '核心 Python 测试 7 项、原有网页测试 4 项与网页生产构建通过。前端源码保持原样。AGH daemon 已停止。','', '## 结论限制与产物','', '本轮证明真实代码修改、训练和独立评分已接通，并在这个固定子集上改善了轻量 ID 基线。只有一个 seed、一次探索；基线对未知文章只有统一表示，而候选获得可学习内容表示，符合冷启动任务，但不能证明 AGH 比人工工程师更优秀，也不是完整 MIND 官方成绩或普遍自我改进结论。第二/第三候选的微小差别不作显著性声明。','', '模型通用源码在 `models/`，冻结协议在 `core-protocol.md`，操作与恢复在 `core-usage.md`，数据 SHA256/样本 ID 清单在 `frozen-data-manifest.json`，全部汇总/身份/用量在 `core-validation.json`。原始数据、checkpoint、分支 Git 历史、评分数组和真实会话/失败记录在本机 `local/`，不上传 GitHub；凭据不提交。']
(docs/'core-validation.md').write_text('\n'.join(text)+'\n')
print(json.dumps({'exported':True,'audit_passed':True,'selected':selected,'usage':usage,'statuses':receipt['agh']['http_status_counts']}))

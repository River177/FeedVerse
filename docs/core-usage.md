# 本地核心系统

在仓库根目录运行；推荐使用已核验的 /Users/river/miniforge3/bin/python3.13。依赖版本见 requirements-core.txt。macOS 的 /usr/bin/sandbox-exec 必须存在并通过探针，禁止无沙箱降级。

```sh
python -m feedverse.cli prepare /absolute/path/to/recprompt_repro/dataset
python -m feedverse.cli train baseline
python -m feedverse.cli status JOB_ID
python -m feedverse.cli evaluate baseline
python -m feedverse.cli create candidate
python -m feedverse.cli source candidate
python -m feedverse.cli patch candidate /absolute/path/to/model.py
python -m feedverse.cli train candidate
python -m feedverse.cli cancel JOB_ID
python -m feedverse.cli compare baseline candidate
python -m feedverse.cli case candidate 0
python -m feedverse.cli select
python -m feedverse.cli heldout baseline
python -m feedverse.cli heldout SELECTED_VARIANT
python -m feedverse.cli audit
```

全局 --root /absolute/path 可用于新的独立探索；默认 local/core。一个 root 冻结后不能继续修改候选。不要删除 selection.json 来反复用保留结果调参。失败或取消后用 train 同一个候选恢复，完成身份不会重跑。

## MCP / AGH

scripts/mcp_server.py 是共享后端的 MCP 服务，默认 stdio；--http 18778 提供 loopback Streamable HTTP。它只提供计划中的十个工具，拒绝额外参数/任意路径和保留评价。

AGH 源码/依赖放在 local/agh-pinned（不提交），固定 commit 的归档可从 https://codeload.github.com/AgnesAI-Labs/agnes-harness/tar.gz/a39272bb6bcb3109584e1bd3abac595789ae365d 获取。解压后用 pnpm10.34.5 install --frozen-lockfile 和 pnpm --filter @agnes/cli build:local。固定归档/lockfile 哈希见本轮 environment 清单，源码不作项目修改。网络代理按机器已有配置设置，不写入凭据。

```sh
python scripts/mcp_server.py --http 18778
python scripts/trapi_bridge.py --root local/agh-runtime --config config/agh.example.json
python scripts/agh_local.py start
python scripts/agh_local.py setup
python scripts/agh_local.py explore
python scripts/agh_local.py stop
```

桥接配置在 config/agh.example.json；运行前应冻结该文件哈希。SDK setup 验证模型目录、配置账号，再登记/信任/启用 FeedVerse MCP。explore 将真实 session ID 写入 local/agh-runtime/exploration.json，未完成时恢复同一 session；完成后拒绝重新启动。需要另一轮研究时建立新 root 和独立 home/config，不能复用保留反馈。

local/ 是本机运行产物，不提交 Git。它包含完整冻结样本、SQLite、模型、分支历史、失败日志、AGH 轨迹和 bridge usage。docs/ 的清单和报告只保留协议、哈希、汇总及不含数据/凭据的模型代码。原始 MIND 与 checkpoint 不上传。

```sh
python -m unittest discover -s tests/core -v
npm test
npm run build
```

# AGH-RSI 项目交接

交接时间：2026-10-09 23:26（Asia/Shanghai）。本文是新 Codex 项目的工作起点。

## 1. 用户已确认的方向

项目正式命名为 **AGH-RSI**。目标是做一个有实际科研用途、不过于复杂、能够根据运行反馈改进自身执行策略的系统。

核心不是预先挑一两道题做固定演示，也不是单纯增加报错重试、堆多个 Agent 或以人工求助为主要创新。用户明确认可的是：

> 通过 AGH 执行科研任务；在 benchmark 上反复运行、分析失败、提出通用策略修改、验证修改，逐步取得更好的结果。

采用两个循环：

- **内层任务执行**：规划 → 探索数据 → 写程序 → 实际执行 → 自检与修复 → 提交最终程序。
- **外层策略改进**：运行开发任务 → 独立评价 → 分析失败轨迹 → 提出一个通用策略修改 → 重测 → 接受或回退。

第一版只允许外层修改一份 `strategy.md`，不自动修改 AGH 核心、模型版本、benchmark 数据或评价器。该文件作为任务提示的一部分传入 AGH；正式 Skill 封装可以后续再做。

用户允许在本地写代码、调用 API 做测试。本次请求只要求写交接文档；尚未启动 AGH-RSI 开发或 benchmark 实验。用户准备自行在 Codex 中打开新项目继续工作。

## 2. 当前完成与未完成

### 已完成

1. 阅读比赛要求、AGH 官方仓库、ScienceAgentBench 论文与工程文档。
2. 在 `gcr-a100` 上从源码构建 AGH。
3. 实时确认 TRAPI Astra 部署可见，且直接 Chat Completions、Responses 均可调用。
4. 配置 AGH 通过本机 OAuth 转接服务调用 Astra。
5. AGH CLI 对话成功。
6. AGH 工具闭环成功：读 CSV → 写 Python → shell 执行 → 读回结果。
7. 独立核验结果正确，并导出完整会话；不含凭据的证据已备份到本地。
8. 核对 AGH 原生 subagent 实现；尚未实际测试子任务的 Astra 调用链路。

### 未完成

- 本地 AGH 构建和本地 TRAPI 认证尚未验证。
- ScienceAgentBench 完整数据、verified 配套评价器尚未安装和实际运行。
- 尚未冻结任务划分、调用预算、并发、reasoning 设置和迭代轮数。
- 尚无 AGH-RSI 代码、开发集基线、策略改进实验或 SOTA 结果。
- 没有运行过 102 个任务，更没有 102/102 通过的结果。

## 3. 现有 AGH + Astra 环境

### GCR 安装身份

| 项目 | 已验证的值 |
|---|---|
| SSH alias / hostname | `gcr-a100` / `GCRAZGDL1681` |
| 安装根目录 | `/datadisk/agh-astra-smoke` |
| AGH 源码 | `/datadisk/agh-astra-smoke/agnes-harness` |
| AGH commit | `a39272bb6bcb3109584e1bd3abac595789ae365d` |
| Node.js / pnpm | `24.10.0` / `10.34.5` |
| AGH_HOME / profile | `/datadisk/agh-astra-smoke/home` / `local-dev` |
| 测试工作区 | `/datadisk/agh-astra-smoke/workspace` |
| CLI wrapper | `/datadisk/agh-astra-smoke/agh` |
| AGH catalog model ID | `gpt-6-astra` |
| TRAPI instance / deployment | `redmond/interactive` / `gpt-6-astra_2026-09-03` |
| Responses API version | `2025-04-01-preview` |
| 直接 Chat smoke API version | `2024-10-21` |
| 测试设置 | `thinking=low`，`contextWindow=32768` |

源码未修改；Node 下载归档已验证官方 SHA256。构建成功，notice 生成器有少数第三方依赖缺少 LICENSE 文件的警告，见 `build.log`。

远端使用方法：

```bash
ssh gcr-a100
cd /datadisk/agh-astra-smoke/workspace
/datadisk/agh-astra-smoke/agh -p '只读查看当前目录并概括'
/datadisk/agh-astra-smoke/agh sessions --json
```

`agh` wrapper 检查并按需启动 bridge；CLI 连接或启动独立 daemon。普通 CLI 保留默认工具审批。

### OAuth 转接

AGH 内置 OpenAI provider 使用 Responses。现有 bridge：

```text
AGH OpenAI Responses adapter
  → http://127.0.0.1:18777/v1
  → AzureCliCredential 获取 api://trapi/.default token
  → TRAPI redmond/interactive 的 Astra Responses endpoint
```

bridge 只映射模型名与转接请求，保留流式响应；实际模型仍是上述 Astra deployment，不是 mock 或其他模型。它提供 `/v1/models` 和 `/v1/responses`，仅监听回环地址，使用独立本机凭据。Azure token 不写入 AGH 提示或公开日志。

这是 smoke 接入，不是已经验收的长期/高并发生产网关。尚未测试 token 过期场景、长期流式连接、断线恢复、高 reasoning 和完整用量汇总。正式实验需要补足响应完成标记、用量、请求标识及错误分类记录。

### 本地现有文件

绝对目录：`/Users/river/Documents/Projects/tmp/agh-gcr-setup`。

- `README.md`：远端安装与使用说明。
- `trapi_bridge.py`：OAuth Responses bridge。
- `configure.mjs`：通过 AGH SDK 配置服务保存模型；没有手工修改 configuration.json。
- `tool_smoke.mjs`：通过 SDK 执行工具测试、接收事件、进行单次指定命令授权。
- `env.sh`、`agh`、`start-bridge.sh`：远端启动脚本。
- `evidence/`：日志、导出会话、输入、生成程序、结果与独立核验。
- `evidence.tar.gz`：不含凭据的证据归档。

归档 SHA256：`a9d358192d3a6cbc4d6bfc51480ab97752aa8119ea2b46a9a8f519b521698142`。

**这些脚本含有远端绝对路径，不可直接当作可移植的本地程序运行。** 本地实现应将安装根目录、AGH_HOME、SDK 路径、Python 路径、监听端口等改为配置项。

工具 smoke 的证据：

- session：`agnes:local:local-dev:cli:workspace:1b21c37cf9f54ac1`。
- 最终状态：`completed`。
- 独立结果：`count=3`，`mean_temperature_c=12`，`sample_sd_temperature_c=2`。
- SDK 仅为 `python3 analyze.py` 提供单次执行授权，没有全局关闭审批。
- `credits` 是 AGH 的 estimated 值，不能直接当作 TRAPI 实际美元费用。

GCR 的 platform doctor 对完整 sandbox 边界仍报告 awaiting probe；shell 成功不等于已验证全部隔离边界。

GCR 技能记录预约截止为 **2026-10-10 15:00（Asia/Shanghai）**，本次未实时核验续期。不要把远端机器当作唯一成果存储。

## 4. 本地开发和 API 路线

用户允许优先本地开发与小规模 API 测试，GCR 环境是可复用参照。

建议顺序：

1. 检查本地 Node、pnpm、Python、Azure CLI、Docker 与剩余磁盘。
2. 使用当前会话提供的 `trapi` 技能，先运行 helper 的 `status`，再确认 live models。不要假定远端 Azure 登录在本地也可用。
3. 若认证失败，按技能处理 `az login --scope api://trapi/.default`，不手工获取/粘贴 token。
4. 构建相同 AGH commit，或明确记录选择的新 commit；使用独立 home。
5. 将 bridge 与 SDK 配置脚本参数化，在本地重做一个最小工具闭环。
6. 若本地认证不可用但 GCR 可用，可在本地写代码并远端执行；不要为了接入偷偷替换 Astra。

macOS 构建要求 Node >=24.10、pnpm 10.34.5、Xcode Command Line Tools。源码构建命令：

```bash
pnpm install --frozen-lockfile
pnpm --filter @agnes/cli build:local
node packages/cli/dist/local/agnes.mjs --help
```

Node SDK 已使用以下真实接口跑通：`createClient`、`client.initialize()`、`client.config.test/save`、`client.session.new({cwd})`、`session.onPermissionRequest()`、`session.prompt()`、`client.close()`。参考现有 `configure.mjs` 和 `tool_smoke.mjs`，继续核对目标 commit 的接口。

CLI 可用于手工使用；任务适配器优先 SDK，以便管理会话、事件、审批和结束状态。为每次 attempt 创建独立输出目录，不让上一轮产物被误当成本轮成功结果。

## 5. ScienceAgentBench 身份与评测边界

主 benchmark 是 **ScienceAgentBench**，不是 Terminal-Bench-Science。

- 102 个任务，来自 44 篇同行评审论文，四个科研学科。
- 输入包括任务说明、数据、目录/内容预览、可选专家知识。
- 最终交付独立 Python 程序，生成指定产物后由官方评价器评分。
- 主指标 Success Rate：任务是否达到验收标准；另有执行有效率、CodeBERTScore、费用。
- 部分图表任务用模型 Judge，评分并非全部确定性测试。
- 原论文使用过每题三次独立运行再按最终评分取最好；不能与单次成功率混比。
- 2026-04 更新要求使用 **verified split** 和 **benchmark_verified.zip**。先冻结 HF revision、数据及评分文件 hash。
- 旧 `run_infer.py` 仍可含 `split="validation"`；不要盲用旧默认。官方脚本的删除输出目录、按日志行数恢复等行为也应核对，适配器使用明确任务 ID 和 attempt 身份。
- 完整解压数据不应重新公开；按官方要求说明数据获取和复现方式。

官方 2025 Docker 更新在 16 核、32GB 内存机器上报告全量已有程序评测：串行约90分钟、8 worker约22分钟。这不是 Agent 生成和反复调试的时间，也不是当前 verified 版本的实测保证。官方容器创建没有 GPU 透传，CPU 可以起步；复杂训练的耗时应实测。

数据划分尚未冻结。已提出的方案是约20题开发、其余保留测试，**按论文/数据源分组**，最终题数以实际分组为准。DILI #18/#19/#40/#41 等相关任务应放在同一侧。

- 开发集用于评分反馈和策略改进。
- 保留集不暴露给策略改进器，冻结最终策略后再运行。
- 如反复使用全量102题开发，必须如实称为开发后全量成绩，不能伪装成独立测试。
- SOTA 是待验证目标；未经同版本、同条件、强基线比较，不作该结论。
- 不把人提供答案/改代码后的成绩与自主 Agent 成绩混报。

初始单题候选：#18 DILI 随机森林（明确要求5折CV及参数搜索），#3 材料体积模量随机森林回归。它们只是接入/展示候选，不是已冻结的唯一科研场景。用户的核心兴趣是整个自我改进系统。

## 6. 第一版设计

### 固定与可变部分

固定：AGH commit、Astra deployment、模型参数、官方任务/数据/评价器、工具权限、计算预算和数据划分。

外层可变：一份通用 `strategy.md`，约束模型的数据探索、任务拆解、计算验证、输出检查和纠错方法。

内层可变：该任务的分析代码和合法中间产物。

第一版不引入多 Agent 编队、复杂 UI、自动改工具实现、自动改评价器、模型微调或任意搜索任务答案。

### 内层运行器

接收任务公开输入及策略，创建独立 workspace/session，通过 AGH 完成真实执行。仅向任务 Agent 暴露任务允许的数据、运行日志及自身检查结果。最终提交后，评价器在独立环境执行。

保存稳定 run/attempt 身份和状态：`pending/running/submitted/evaluated/infra_error/cancelled` 等。失败、评分不通过和技术缺失分别记账；任何汇总都说明分母和完整覆盖情况。恢复时按任务ID、策略hash、配置hash与attempt查找，不按日志行数猜进度。

### 策略改进器

读取当前策略、开发集评分、允许公开的失败轨迹，提出 **一个共性问题和一个最小通用修改**：

```json
{
  "problem": "多个任务存在预测行与输入样本不对应的问题",
  "evidence": [{"task_id": "development-task", "trace_ref": "..."}],
  "hypothesis": "提交前检查样本ID可以减少对齐错误",
  "change": "新增样本ID覆盖、唯一性与对应关系检查",
  "expected_effect": "输出对齐错误减少"
}
```

候选策略不能写入特定任务答案、隐藏标签、参考实现或从评价器获取的真实答案。评价器错误日志也可能含 expected 值，应使用允许字段构成改进反馈包，不能直接全量转发。

### 接受与回退

候选在同一开发集、同模型和预算下重测。第一版提出的保守规则：

1. 成功数增加。
2. 原本成功任务没有退步。
3. 未超过预算约束。

通过则保存新版本，否则保留拒绝候选证据并继续使用旧版。较小提升需要针对相关任务复跑，排除随机波动。规则仍需在首轮实验前具体冻结。

不修改数据或评分条件来消除退步，不根据隐藏测试选择候选。缺少证据或任务覆盖不完整时不能自动宣布改进成功。

### 推荐文件结构（尚未实现）

```text
AGH-RSI/
├── HANDOFF.md
├── config/
├── strategy/initial.md
├── strategy/versions/
├── tasks/split_manifest.json
├── src/run_task.mjs
├── src/evaluate.py
├── src/improve.py
├── src/evolve.py
└── runs/
```

每条任务记录至少含 task/run/attempt ID、策略hash、模型deployment/API版本/reasoning、环境与预算、session ID、时间戳、最终程序hash、轨迹位置、评分、错误类型、token usage和费用来源。AGH estimated credits 与实际价格分别记录。

## 7. 下一步执行顺序与验收

1. **本地接入**：参数化 bridge/SDK 路径，完成小请求和真实工具闭环。失败时明确是认证、模型、AGH还是环境问题。
2. **单题适配**：获取 verified 数据，隔离答案与评价器，跑一道科研任务；AGH 程序与官方评分产物都可复核。
3. **冻结开发协议**：按来源分组划分任务，确定预算、并发、thinking、专家知识条件、接受规则、重复统计方式。
4. **开发集初始基线**：记录初始策略的完整覆盖、成功、失败、技术错误和用量。
5. **一轮自动改进**：系统提出候选，自动重测并产生接受/回退回执，不由人手工改答案冒充自动改进。
6. **有限迭代**：曾建议先试三轮；尚未批准为正式实验规模。小请求与单题测试可以先做，扩大到持续付费或全量运行前落实预算。
7. **冻结最终策略后测试**：报告开发曲线和保留任务结果，比较固定初始策略与进化后策略；其他强基线在必要时按相同条件补充。

第一阶段成功标准：任务能通过AGH执行、官方评价器可用、轨迹可导出、输出独立核验；第二阶段成功标准：实际完成一轮有证据的候选验证与接受/回退。即使候选没有提升，机制仍需如实交付，不保证涨分或100%通过。

新项目可以直接开始落实前两步，不必再次讨论宏观选题。遇到必须由用户完成的认证或缺少费用预算，再提出具体问题。

## 8. Subagent 状态

AGH 已实现 `subagent_fork/spawn/collect/cancel`。基础 preset 默认深度1、fan-out4、worktree隔离；非Git工作区可能退回shared。doctor为只读检查，repair在当前版本禁用。

已确认源码支持，未实测完整子任务链路。第一版外层改进器可用独立模型调用实现，暂时没有使用子智能体的必要，不要把它当成创新本身。

## 9. 比赛要求与交付

用户提供的原始赛事文本：
`/Users/river/.codex/attachments/8667df44-fd12-43a5-b916-3d35f8b59278/已粘贴的文本.txt`。

- AGH 必须承担核心任务流程，不可仅生成文案或做外围辅助。
- 作品需要实际运行、外部能力调用、任务规划、反馈调整、验证及异常处理。
- 提交可核查的AGH执行记录，以及正常、边界、失败三类案例。
- 3–5分钟演示视频，以实际操作为主。
- 报名截止2026-10-10 12:00，提交截止2026-10-15 12:00（按用户提供赛事文本）。用户是否报名尚不清楚。
- 获奖后有开源要求；依赖、素材和数据来源应说明，凭据不公开。

适合的展示：初始策略失败 → 自动归纳一个共性问题 → 生成通用策略修改 → 重测与接受/回退 → 展示对保留任务的影响。

## 10. 原始来源

- AGH：https://github.com/AgnesAI-Labs/agnes-harness
- AGH 安装：https://github.com/AgnesAI-Labs/agnes-harness/blob/main/docs/guide/install.zh-CN.md
- AGH CLI/配置：https://github.com/AgnesAI-Labs/agnes-harness/blob/main/docs/guide/quickstart.zh-CN.md
- SAB 仓库：https://github.com/OSU-NLP-Group/ScienceAgentBench
- SAB verified 数据：https://huggingface.co/datasets/osunlp/ScienceAgentBench
- SAB 论文：https://arxiv.org/abs/2410.05080
- SAB Docker与耗时：https://github.com/OSU-NLP-Group/ScienceAgentBench/blob/main/docs/20250110_docker/README.md
- TRAPI 技能（本机）：`/Users/river/.agents/skills/trapi/SKILL.md`
- GCR 技能（本机）：`/Users/river/.codex/skills/gcr-a100/SKILL.md`

## 11. 新 Codex 项目的启动消息

可以向新项目发送：

> 请先阅读 HANDOFF.md，继续开发 AGH-RSI。方向已经确认：AGH 执行科研任务，外层根据 ScienceAgentBench 开发任务的失败轨迹自动改进一份通用策略，并通过独立评测接受或回退。先复用已验证的 AGH/TRAPI Astra 接入代码，改成可配置的本地版本，完成本地小规模工具测试，再打通一道 verified 科研任务。第一版保持简单，不先增加多Agent或复杂界面。保留执行记录、版本身份与独立验证；持续付费或全量运行前明确预算。

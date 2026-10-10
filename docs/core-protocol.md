# FeedVerse 核心协议 v1

网页仍为规则原型。真实系统通过 Python CLI / MCP 独立运行；没有接入网页，也没有现场演示包装。

## 数据与目标

原始 MIND-small 文件只读。种子 42，历史至少 3 条且截取最后 50 条、当前 impression 恰有一个点击、候选至少 20 且不重复。官方 train 按行抽取 20,000 条；官方 dev 将排序后打乱的用户均分两侧，各抽取 1,000 条。验证与保留用户不重叠。它是日志候选集上的单点击预测子集，不是全库召回或官方完整成绩。

训练历史与训练正例的并集定义 seen。冷启动指标的分母是正例不在 seen 的 impression；不推断发布时间。文章覆盖率为 top10 中不同文章数 / 相应评测组候选文章并集大小。曝光集中度为 top10 文章曝光份额的 HHI。排名按分数降序，同分按原始候选顺序，绝不按标签打破同分。

所有文章的标题、摘要、类别是允许输入。TF-IDF 的词表/IDF 与 128 维 SVD 仅拟合固定训练样本历史和日志候选所含的文章；然后用同一变换处理其余文章。冷文章可能出现在训练负例，这符合“未在历史和正例出现”的固定定义。训练侧与验证/保留的用户未要求彼此完全不同；只有 dev 两侧按用户隔离。

## 模型和固定训练

基线使用 64 维 ID embedding、单层 GRU、点积评分。seen 之外的文章映射到共享未知项。PyTorch CPU，固定种子 42、6 个线程、batch128、5 epoch。基线 Adam lr0.001。每个训练样本包含唯一正例和最多 4 个日志负例，评测使用完整候选。候选修改自己的 model.py，build(public_path, config) 返回具有 fit(rows, artifact_dir) 和 score(rows) 的 nn.Module；fit 保存 state_dict 至 checkpoint.pt。候选可以改变可执行特征/模型/历史编码，不能改 worker、划分、评价器或训练配置。

训练工作区只有公开训练输入、文章特征、独立候选源码及其产物。评分是新的受限 Python 进程，重新 build 并 weights_only=True 加载 checkpoint。评分输入没有 positive。评分进程无网络，不能访问独立评价进程的标签或其它候选。沙箱必须先通过真实 PyTorch、隐藏文件读写和网络拒绝探针；失败即停止。macOS Seatbelt 限制 regular-file 读取到允许输入与运行时/系统库、写入到候选产物及 /dev。目录遍历元数据供加载器使用，受保护文件内容仍不可读。AGH 本身另有文件沙箱，只允许固定 AGH 源码/依赖、独立 home/workspace、系统运行时及系统临时目录；可信 MCP HTTP 服务在沙箱外执行后端。

整体与冷组分别报告 Recall@5/10、NDCG@5/10、MRR、覆盖、HHI。没有冷样本时保留 null。有效候选均保留。最多 3 个候选目录，失败修复留在原分支；通过训练和验证的候选不能再通过 patch_source 改写；训练或评分失败有独立回执，可以在原候选修复，重新按新源码身份训练。验证冷 NDCG@10 严格高于基线才替换基线；不设整体下降门槛。同分保留当前方案，结果不能填零。

selection.json 冻结验证报告哈希与选定模型身份后，可信 CLI 才能评价保留侧，限基线和选定模型。MCP 不暴露选择或保留评价方法。保留反馈不送入 AGH。独立审计以单独的纯 Python 实现重算所有指标、核验用户分组、源文件/输出/源码/config/checkpoint 身份及 label-free 评分输入。

## 执行与恢复

SQLite 保存 queued/running/completed/failed/cancelled/interrupted 状态。每次训练身份包含候选源码 commit、源码/worker/config SHA256 及冻结数据清单 SHA256。同一身份的已完成训练直接返回，不重复运行。失败/取消/中断可按同一候选显式再 train；返回新的 attempt ID，并保留数据库回执。每个新 attempt 在独立目录执行，只有状态仍为 running 且身份一致时，可信 manager 才将 checkpoint 发布到候选目录；失去 manager 的旧子进程不能冒充新产物。训练限 30 分钟；评分限 5 分钟。取消终止该 manager 的进程组，不以返回成功冒充模型完成。

AGH 固定源码 commit a39272bb6bcb3109584e1bd3abac595789ae365d、pnpm10.34.5。本地独立 home，Node SDK 创建并保存真实 session ID；未完成会话按 ID 恢复。TRAPI 原有 Azure CLI 身份获取/刷新 token，Astra deployment 固定 gpt-6-astra_2026-09-03。认证 401/403 停止 bridge 请求队列，不替换模型。bridge 记录请求 ID、上游 ID、完成/失败事件、真实 token usage 和异常类型；不把 AGH estimated credits 当成真实 token 或费用。服务只监听 127.0.0.1。AGH 的 arbitrary shell/非本工具审批被拒绝。

本轮只有一个 seed 和一次 AGH 探索，不能据此作普遍改进、显著性或 SOTA 声明。成功标准是真实可执行的编辑、训练、独立评价和诚实结果，无需 AGH 获胜。

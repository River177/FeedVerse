# FeedVerse 真实实验工作台

主页面读取真实 MIND 模型和执行产物，浏览器不连接 TRAPI/MCP。旧的合成规则模拟在 `/prototype`，与真实数据和实验状态分开。

## 启动与使用

```sh
# 在具备 PyTorch 的 Python 环境安装网页依赖；本机已核验 miniforge3/python3.13
python -m pip install -r requirements-web.txt
npm install
npm run dev:full
```

默认网页 http://127.0.0.1:5173/，API http://127.0.0.1:18779。脚本优先使用 FEEDVERSE_PYTHON 指定的解释器，其次查找项目虚拟环境、本机 miniforge3 和当前解释器。启动时实际验证沙箱。已有同项目 API/Vite 可复用；退出只终止本启动器创建的服务。若本启动器创建了 API，Ctrl-C 会先请求取消当前探索，等待独立 manager 释放 AGH/bridge/MCP，再停止 API。

生产本地使用：`npm run build`，再运行 `python -m uvicorn feedverse.web_api:app --host 127.0.0.1 --port 18779`。API 同时服务构建后的网页和 `/prototype`。原始 MIND 和 local/core 的冻结基线须已准备；原有核心 CLI 仍可使用。

默认打开已核验历史实验，比较 baseline 和 attention_content。新建探索可填写方向并选择 1–3 个候选，默认 3；同时只能执行一个探索。方向不能覆盖数据、seed42、CPU、batch128、5 epoch、最多4负例或评价边界。点击已有效候选可切换比较模型；源码和差异为只读。

网页 URL 保存 experiment ID。刷新、关闭标签页不会停止独立 runner；重启网页 API 可以重新读取状态。API 检测 manager 丢失时标记中断，按原 ID 和 session 恢复。取消先进入停止中，只有 AGH、训练和本轮服务均停止后才进入已取消。完成的探索不能重复恢复执行。

## 数据与展示边界

- 模型比较使用原始验证报告；缺失结果为 null，不补零。基线导入有完整身份和“复用模型”标签，不创建虚构的新训练记录。
- 案例默认按冻结样本顺序，覆盖1,000个验证样本。实际点击由可信网页API提供，仅用于浏览；模型score及AGH的recommend_case仍无标签。
- 推荐分布是完整验证候选文章集合上的Top10入选次数。散点图对数坐标、类别/冷文章/搜索筛选与明细表共享数据，点击点会定位表格并打开文章详情。它不是线上曝光或用户满意度。
- 冷文章指未在训练历史及正例出现，不代表发布时间。跨模型主要比较排名，原始分数不是校准点击概率。
- 训练日志没有独立时间戳时，记录时间使用日志文件修改时间并标记log_mtime，不推断更精确的epoch结束时间。
- 已完成探索可回放真实记录时间；回放有明确标签，仅改变记录显示，不伪造训练状态或评分。
- 历史保留成绩只展示旧冻结报告；新探索不运行保留评价，MCP没有网页报告或标签接口。

## 运行目录与接口

网页注册表与事件在 `local/web/web.sqlite`。每轮 `local/web/explorations/<id>/` 含独立core/runtime、AGH home/workspace、源码分支、attempt、评分、事件和服务日志。公开数据与可信评价材料共享冻结目录；候选代码与AGH进程不能读取评价材料。基线只复制源码Git身份、config/checkpoint、验证报告与评分数组，不导入历史候选或保留成绩。

Unix socket超过103字节时，固定AGH版本会在 `/private/tmp/agnes-<uid>-<dataDir哈希>` 使用短目录。启动器只创建并允许这个精确目录，校验所有者与0700模式；不扩大到整个/tmp，不关闭沙箱。

主要API：

| 路由 | 行为 |
|---|---|
| GET /api/health、/api/experiments | 本地状态和实验档案 |
| POST /api/explorations | title、instruction、candidate_limit、request_key；重复或并发提交返回已有探索 |
| GET /api/experiments/{id} | 模型、状态、验证指标、选择、身份及用量 |
| GET /api/experiments/{id}/events | SSE，支持Last-Event-ID/after断线续传 |
| GET /api/experiments/{id}/event-log | 按seq分页获取完整事件 |
| POST /api/explorations/{id}/cancel、/resume | 停止及原身份恢复 |
| GET /api/experiments/{id}/models/{model}/source | 允许模型的完整源码、diff与SHA256 |
| GET /api/experiments/{id}/cases、/cases/{index} | 分页验证案例及完整候选排名 |
| GET /api/experiments/{id}/distribution、/articles/{article} | 文章分配与详情 |
| GET /api/experiments/{id}/export | 脱敏快照、身份和全部执行事件 |

JSON写入请求禁止额外字段，包括path、command、训练参数。外部Origin写入被拒绝，服务只绑定loopback。导出屏蔽凭据和本机路径。SDK/MCP/bridge原始日志保留于local，不提交Git。用量按request ID去重，只累加真实usage；无终止回执的请求也记为缺失，不把estimated credits当费用。

## 测试

```sh
python -m unittest discover -s tests/core -v
python -m unittest discover -s tests/web -v
npm test
npm run build
```

浏览器验收包括网页提交真实单候选、刷新恢复、源码弹窗键盘操作、推荐案例、分布过滤、历史回放、档案切换、旧原型，以及窄屏溢出。网页接入验收结果见 web-validation.md。比赛讲述与现场流程暂未制作。

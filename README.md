# FeedVerse · 推荐平行世界

本地推荐实验系统：真实 MIND 数据、可训练的历史推荐模型、AGH 修改模型代码、独立评价。

核心系统与网页分开运行。主网页已接入真实 AGH 探索、训练状态、模型评分、新闻排名和推荐分配。比赛现场流程尚未制作。

## 核心系统

协议见 [docs/core-protocol.md](docs/core-protocol.md)，运行与恢复见 [docs/core-usage.md](docs/core-usage.md)。Python 实现在 `feedverse/`，AGH SDK、TRAPI bridge 和 MCP 启动器在 `scripts/`。原始数据、凭据、模型和会话轨迹仅保存于被 Git 忽略的 `local/`；源码和汇总报告可提交私有仓库。

```sh
python -m feedverse.cli prepare /absolute/path/to/recprompt_repro/dataset
python -m feedverse.cli train baseline
python -m feedverse.cli status JOB_ID
python -m feedverse.cli evaluate baseline
python -m unittest discover -s tests/core -v
```

## 真实网页运行

```bash
npm install
npm run dev:full
```

打开终端给出的本地网址，默认是 `http://127.0.0.1:5173/`。无需远端服务器。新探索通过后台复用现有 TRAPI 身份，浏览器不持有模型凭据。字体随应用打包。完整使用和恢复方法见 [docs/web-workbench.md](docs/web-workbench.md)。

```bash
npm test       # 真实网页 API、生命周期与结果一致性
npm run build # TypeScript 检查和生产构建
npm run preview
```

## 历史

旧 RSI 项目保存在 Git 标签 `archive/agh-rsi-before-feedverse`。旧实验记录在被忽略的 `runs/` 目录中，与当前推荐实验工作台无关。

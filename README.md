# FeedVerse · 推荐平行世界

本地推荐实验系统：真实 MIND 数据、可训练的历史推荐模型、AGH 修改模型代码、独立评价。

核心系统与网页分开运行。主网页已接入真实 AGH 探索、训练状态、模型评分、新闻排名和推荐分配。原合成规则原型保留在 `/prototype`；比赛现场流程尚未制作。

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
npm test       # 可复现性、曝光守恒、指标定义和输入边界
npm run build # TypeScript 检查和生产构建
npm run preview
```

## 规则原型（/prototype）

- 两个共享用户、创作者和随机事件的世界，以蓝色基线和橙色干预并排展示。
- 点击创作者星图，比较其曝光、独立触达、点击和逐轮经历；可搜索全部创作者。
- 播放、暂停、逐轮前后查看、拖动时间轴、调速和回到起点。
- 调整探索、新作者扶持和多样性权重，重新计算两个世界。
- 选择三个预设目标，自定义验收阈值，查看达标、取舍或未找到方案。
- 一键运行本地演示流程：观察 → 分叉 → 尝试 → 比较 → 调整 → 新种子复验。
- 展开工具输入输出；在会话档案中重新打开方案；导出含全部轨迹的 JSON。
- 查看当前手写排序规则；按曝光变化排序创作者明细，比较正负变化和独立触达。
- 桌面和手机布局、键盘操作、弹窗焦点限制及减少动态效果支持。

首次打开会载入种子 42 的 60 轮预计算轨迹，时间轴停在第 36 轮。当前设置保存在本机浏览器；实验档案在本次页面会话中保存，长期留存请导出 JSON。

## 引擎与边界

默认世界有 480 位用户、72 位创作者和六类内容。每位用户每轮获得一次推荐；用户兴趣与内容池固定，累计曝光会影响后续推荐。模拟包含内容质量、兴趣匹配、重复疲劳、2% 的共同背景探索率，以及可调整的策略。

新创作者的初始声望较低，扶持权重随其曝光增长而衰减。满意度、新作者曝光份额、用户类别熵和前 10% 创作者的曝光占比均有明确计算定义。两组使用相同的随机源，便于重现和比较。

这是一组公开假设下的机制模拟，不直接代表真实平台因果效果。演示控制器按所选预设与数值约束执行；顶部自然语言内容作为实验备注。不同种子的复验可能失败，界面如实呈现结果。

主要代码：`src/engine.ts` 为独立模拟函数，`src/App.tsx` 管理交互与演示流程，`src/components.tsx` 提供星图、详情和记录组件。真实后端不会使用该合成引擎作为模型评价器；后续网页将展示独立训练/评价结果。

## 历史

旧 RSI 项目保存在 Git 标签 `archive/agh-rsi-before-feedverse`。旧实验记录在被忽略的 `runs/` 目录中，与 FeedVerse 原型无关。

# 本地环境检查

检查日期：2026-10-09（Asia/Shanghai）。以下为本次本地实测，后续运行前应复查。

## 项目和 GitHub

- 本地目录：`/Users/river/Documents/Projects/AGH-RSI`。
- 远端：`https://github.com/River177/AGH-RSI`。
- GitHub API 已确认 `visibility=PRIVATE`，默认分支为 `main`。
- 初始化提交已推送，远端 `main` 与本地提交相同。

## 环境

| 项目 | 实测结果 | 对下一步的影响 |
| --- | --- | --- |
| 系统 | macOS 27.0.1，arm64 | 本地构建需兼容 Apple Silicon |
| 内存 | 64 GiB | 环境盘点值，未进行任务容量测试 |
| 磁盘可用 | 约 89 GiB，卷使用率 91% | 下载 benchmark 前核对实际数据与解压空间 |
| Node.js | 24.21.0 | 满足交接记录的最低版本 24.10 |
| pnpm | 11.25.0，来自 Codex fallback runtime | 与交接要求的 10.34.5 不同，构建前核对目标源码的 packageManager 并使用匹配版本 |
| 默认 Python | Homebrew Python 3.14.7 | 缺少 openai、azure-identity、requests |
| 现有可用 Python | `/Users/river/miniforge3/bin/python3.13`，3.13.12 | 三个 TRAPI helper 依赖已存在，helper 已成功运行 |
| Azure CLI | 2.90.0 | 可获取 TRAPI scope token |
| Docker | PATH 中无命令，常见 Docker.app/OrbStack.app 路径未找到 | 官方容器评测环境尚不可用 |
| Git / GitHub CLI | 2.54.0 / 2.100.0 | 仓库创建和推送成功 |
| Xcode | `/Applications/Xcode.app/Contents/Developer`，Apple clang 21.0.0 | 开发工具可调用；尚未构建 AGH |
| AGH | `agh`、`agnes` 未在 PATH 中找到 | 尚未验证本地安装或执行能力 |

## TRAPI 实测

默认 Python 运行 helper 时因依赖缺失退出；改用现有 Miniforge Python 后：

- `status`：token 获取成功，`/tmds/deployments` 返回 HTTP 200。
- `models --instance redmond/interactive --filter gpt-6-astra`：返回 `gpt-6-astra_2026-09-03`。
- 本次仅检查认证和模型列表，未发起模型推理，未验证 Chat/Responses、本地 bridge 或 AGH 工具闭环。
- 未将 token 或其他凭据保存到仓库。

复查命令：

```bash
/Users/river/miniforge3/bin/python3.13 /Users/river/.agents/skills/trapi/scripts/trapi.py status
/Users/river/miniforge3/bin/python3.13 /Users/river/.agents/skills/trapi/scripts/trapi.py models --instance redmond/interactive --filter gpt-6-astra
```

## 可复用材料与后续准备

`/Users/river/Documents/Projects/tmp/agh-gcr-setup` 中的 README、bridge、SDK 配置、工具测试和启动脚本均存在。它们包含远端路径，尚未复制进项目或运行。

下一步开发需要核对目标 AGH commit 和包管理器版本，参数化接入脚本并完成本地工具闭环。官方 benchmark 容器还需要可用的 Docker 环境，并核对 Apple Silicon 与官方镜像的兼容性。本次没有安装软件、构建 AGH、下载 benchmark 或启动实验。

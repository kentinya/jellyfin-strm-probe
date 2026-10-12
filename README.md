# Jellyfin STRM Probe Optimizer

按 STRM 中的 URL、内容 SHA-1 和字节大小判断是否需要远程探测，复用 Jellyfin 已保存的媒体流；内容相同而 URL 改变时，只更新播放地址。

项目名称：`Jellyfin.Plugin.StrmProbeOptimizer`。目标语言：C#。插件状态库：SQLite。媒体流仍由 Jellyfin 原生数据库保存。

**当前只有开发基线文件，插件尚未实现。** Jellyfin 目标版本、.NET SDK、服务包装、探测成功信号和路径持久化需要先通过 Slice 1 验证。当前环境没有 `dotnet`，未运行任何插件构建或实机测试。

## 本次范围

本次建立开发流程、需求、架构、测试矩阵、Slice／Task 合同和 Git 初始化工具。后续产品开发限于 Jellyfin 插件及其隔离测试。

**本次开发不包括 STRM 生成程序。** 插件读取现有 STRM，不生成、改写或删除 STRM，不请求 OpenList 元数据 API。生成程序与 JellyfinProxy 均为外部系统；参见 [范围说明](docs/scope.md)。

## 从这里开始

1. 阅读原始 [V3.0 方案](<Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md>) 和 [范围说明](docs/scope.md)。
2. 阅读 [AGENTS.md](AGENTS.md) 和 [开发流程](docs/development-workflow.md)。
3. 查看 [当前 Slice](SLICE.md)、[当前 Task](TASK.md) 和 [路线图](docs/roadmap.md)。

核心规则：URL 改变且没有新旧两个有效且相同的 SHA-1 时，必须要求探测；大小相同不能豁免。修改时间不参与判断。`allowMediaProbe=false` 时保留待探测状态，不能自行启动 ffprobe。

## 当前仓库检查与初始化历史

原规划环境的 `.git` 曾为只读文件系统。正常目录可写后，本地 Git 基线与 Slice 1 合同已初始化，首个 Task 在合同提交后计划；未配置远程或推送。

当前已初始化仓库运行：

```bash
git status --short --branch
python3 scripts/check_governance.py
python3 -m unittest discover -s tests -v
```

测试只验证开发治理，不代表插件构建或 Jellyfin 播放通过。最新流程包含分阶段测试、证据复用、用户明确要求的冻结／恢复和关闭后停止规则；来源版本见 [references.md](docs/references.md)。

以下是原始基线的一次性初始化方式，留作历史说明；当前仓库不要重新执行。历史 `bootstrap-manifest.json` 保存初始化时的清单与摘要，不随后续维护重新生成。

初始化前检查规划文件：

```bash
python3 scripts/check_governance.py --bootstrap
```

在运行环境允许写入 `.git` 后，执行：

```bash
python3 scripts/bootstrap_repository.py --author-name '你的名字' --author-email '你的邮箱'
python3 scripts/check_governance.py
git status --short --branch
git log --oneline
```

脚本创建 `main`，依次提交原始方案基线、Slice 1 合同及开发文件、Task 1.1 计划，自动填入真实 Base SHA。它仅加入明确的文件清单，不配置远程或推送；已有仓库或文件偏离本次基线时会停止，避免覆盖后续工作。作者参数只用于这些提交，不写全局 Git 配置；省略时使用 `Codex <codex@localhost>`。

初始化前的 `--bootstrap` 只验证规划文件，不能代替提交后的治理检查，更不代表产品验收。

## 文档导航

| 文件 | 用途 |
|---|---|
| [requirements.md](docs/requirements.md) | 稳定需求编号与业务判断 |
| [product-experience.md](docs/product-experience.md) | 管理员与播放用户的完整旅程 |
| [architecture.md](docs/architecture.md) | CURRENT／TARGET 分离、模块与状态边界 |
| [compatibility.md](docs/compatibility.md) | 目标版本和三个接入风险的验证清单 |
| [test-matrix.md](docs/test-matrix.md) | T01～T28 与补充测试，全部尚未运行 |
| [progress.md](docs/progress.md) | Slice 关闭记录与当前开发指针 |
| [references.md](docs/references.md) | mediaflow 流程来源、版本和适配说明 |
| [A 经验](docs/agent-experience/slice-owner-architect-final-reviewer.md) | Slice 规划、合同变更与最终审查的方法 |
| [B 经验](docs/agent-experience/task-planner-reviewer.md) | Task 规划、测试安排与停止规则的方法 |
| [Developer 经验](docs/agent-experience/developer-implementation-role.md) | 本项目可复用的实施经验，目前暂空 |

仓库中尚无 `.sln`、`.csproj`、插件安装包或 Docker 部署配置。Task 1.1 在核实 Jellyfin 版本和依赖后创建真实可构建项目，不先填入未经验证的包版本。

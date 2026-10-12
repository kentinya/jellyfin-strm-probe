# 参考来源

最新读取日期：2026-10-13。引用外部流程并针对本项目重新编写；没有复制 mediaflow 的媒体整理实现、Storage／Recognition 架构或“禁止 FFprobe”产品规则。

## 原始方案

文件：[Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md](<../Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md>)。

原文件 SHA-256：`d236cab6b3992636b524f30bbe49a91adb9ef5d6b7010ed5695cae7d65f228ae`。初始化前校验此值，原文保持不变。生成程序排除项由 [scope.md](scope.md) 明确记录。

## mediaflow 开发流程

仓库：[kentinya/mediaflow](https://github.com/kentinya/mediaflow)。本次读取时 main 提交：[`ba6b4f92f278950a5e0346d7dfa1387fafac2fca`](https://github.com/kentinya/mediaflow/commit/ba6b4f92f278950a5e0346d7dfa1387fafac2fca)，提交时间 2026-10-12 11:42:48 UTC，tree 为 `c4c29366968ef33ec1dc1e8d4d9173a3d8fca588`。

| 来源 | 读取文件的 Git blob SHA | 本项目适配 |
|---|---|---|
| [development-workflow.md](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/docs/development-workflow.md) | `84072c1fac4a76f7f8fdd368adc83a7350db8848` | 测试阶段、证据复用、用户冻结／恢复、合同变更与关闭后停止 |
| [Task/TEMPLATE.md](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/Task/TEMPLATE.md) | `18e9ff82b9d28c03e72e3163ba3f537d07855cf1` | 四部分测试计划、证据索引与可选经验候选 |
| [check_governance.py](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/scripts/check_governance.py) | `28ab299e43fd359f0cea04cc0e495276dcc543f3` | 接受已提交 PLANNED／无活动 Task；拒绝 PLANNED 下活动 Task，保留本项目祖先与原文校验 |
| [AGENTS.md](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/AGENTS.md) | `572d2be874e2fa724027e45f32d7835ed39e2fb2` | 按职责阅读经验，稳定需求规范与原始参考分工 |
| [A 经验](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/docs/agent-experience/slice-owner-architect-final-reviewer.md) | `6dc344e9e62548194542d6fedccdd59a6e6b72bc` | 适用方法明确标为外部参考 |
| [B 经验](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/docs/agent-experience/task-planner-reviewer.md) | `cb760a3a34155d39a270c3121f6d9a6d83e21faa` | 适用方法明确标为外部参考 |
| [Developer 经验](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/docs/agent-experience/developer-implementation-role.md) | `83da6992a97120650affcebeb08d09c5c989d485` | 仅借鉴维护格式；本项目尚无插件实施经验，清单暂空 |
| [quality.yml](https://github.com/kentinya/mediaflow/blob/ba6b4f92f278950a5e0346d7dfa1387fafac2fca/.github/workflows/quality.yml) | `da541a1848576b9885e46daeaf03eb950159e0dc` | 更新 checkout／setup-python 版本，补治理回归；不复制 Python／Web 产品门槛 |

还读取了 AGENTS、CLAUDE、SLICE、TASK 和 Roadmap，了解文档职责与当前合同格式。本项目没有继承这些文件中的产品规则和历史验收结果，没有配置该仓库为本项目远程。

首次基线参考版本 `df4391bd2ff351cbcfc34d24f193aff5abb59dbc` 保留在 Git 历史。此次流程同步没有移动本项目 Slice／Task Base、改变业务验收或开始插件实现。

### 本地参考检出

终端 clone 因 GitHub DNS 解析失败，改用 GitHub 连接读取固定提交及递归 tree，核验 blob／tree／commit 对象后构建浅层稀疏 Git 检出：`/tmp/jf-strm-probe-mediaflow-latest`。包含流程、角色经验、模板、检查脚本、CI、当前合同及导航等 16 个文件，HEAD 为上述 main 提交；其 origin 仅属于独立参考目录。

这是本次会话的流程参考检出，未下载全部源码 blob 或历史；目录位于 `/tmp`，不是持久证据。可核验的来源由以上固定提交链接保存。本项目保留适用于 C# Jellyfin 插件的独立治理实现，不能拿参考仓库测试结果作为本项目验收。

## Jellyfin 源码定位

| 来源 | 目的 |
|---|---|
| [v10.11.8 标签](https://github.com/jellyfin/jellyfin/tree/v10.11.8) | 对应提交 `2c62d40f0d13926874eef9118a95be0dcee4e659`，候选兼容版本 |
| [v10.11.8 global.json](https://github.com/jellyfin/jellyfin/blob/2c62d40f0d13926874eef9118a95be0dcee4e659/global.json) | 已读取 SDK 9.0.0／latestMinor；不是插件已构建证据 |
| [v12.2 标签提交](https://github.com/jellyfin/jellyfin/commit/ca0f16eb7c195f720a1493ed469a27c4657db0c6) | 确认原方案标签存在，仍需目标服务器验证 |
| [MediaSourceManager.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/Emby.Server.Implementations/Library/MediaSourceManager.cs) | 原方案提出的 GetPlaybackMediaSources 接入位置，Task 1.1 核实 |
| [ProbeProvider.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs) | 原方案提出的 STRM 注释／URL 读取位置，Task 1.1 核实 |
| [BaseItem.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Controller/Entities/BaseItem.cs) | 原方案提出的 ShortcutPath 和持久化位置，Task 1.1 核实 |

后三项是待核实定位，当前没有据此宣布接口或二进制已兼容。不读取 OpenList API 或生成程序实现，因为本次范围已经排除。

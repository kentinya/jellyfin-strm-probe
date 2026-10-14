# 参考来源

最新补充日期：2026-10-14；原流程参考读取日期为 2026-10-13。引用外部流程并针对本项目重新编写；没有复制 mediaflow 的媒体整理实现、Storage／Recognition 架构或“禁止 FFprobe”产品规则。

## 当前原始方案与历史

文件：[Jellyfin STRM Probe Optimizer V4.3 开发方案.md](<../Jellyfin STRM Probe Optimizer V4.3 开发方案.md>)。

当前 V4.3 SHA-256：`ce3d1bcb74bf56da6be566283adc162f57d174e5e36d4c9a5bcb86e265ab31fc`。按用户授权仅修改扫描方式和版本标识，治理继续校验完整内容。V4.2 原文及 SHA-256 `4dc8e6aa4ebd16fa4ca32b35a6f58ac9e48932e334ac772f5c0f431a39ae32e2` 保留于 `fdcd3fc5576a1eba7835c9e9ff261ac6844a2e96`。

V3.0 已从工作区移除，其原文 SHA-256 为 `d236cab6b3992636b524f30bbe49a91adb9ef5d6b7010ed5695cae7d65f228ae`，原文件、旧合同与旧 Task 可从 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485` 读取。历史 bootstrap 清单不重生成；当前校验不再要求已被用户删除的旧文件。版本取舍与生成器排除见 [scope.md](scope.md)。

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

首次基线参考版本 `df4391bd2ff351cbcfc34d24f193aff5abb59dbc` 保留在 Git 历史。此前 mediaflow 流程同步没有移动本项目 Slice／Task Base 或改变业务验收；本轮 V4.2 重规划另行记录实质合同变更，不开始插件实现。

### 本地参考检出

终端 clone 因 GitHub DNS 解析失败，改用 GitHub 连接读取固定提交及递归 tree，核验 blob／tree／commit 对象后构建浅层稀疏 Git 检出：`/tmp/jf-strm-probe-mediaflow-latest`。包含流程、角色经验、模板、检查脚本、CI、当前合同及导航等 16 个文件，HEAD 为上述 main 提交；其 origin 仅属于独立参考目录。

这是本次会话的流程参考检出，未下载全部源码 blob 或历史；目录位于 `/tmp`，不是持久证据。可核验的来源由以上固定提交链接保存。本项目保留适用于 C# Jellyfin 插件的独立治理实现，不能拿参考仓库测试结果作为本项目验收。

## Jellyfin 源码定位

| 来源 | 目的 |
|---|---|
| [v10.11.8 标签](https://github.com/jellyfin/jellyfin/tree/v10.11.8) | 对应提交 `2c62d40f0d13926874eef9118a95be0dcee4e659`，候选兼容版本 |
| [v10.11.8 global.json](https://github.com/jellyfin/jellyfin/blob/2c62d40f0d13926874eef9118a95be0dcee4e659/global.json) | 已读取 SDK 9.0.0／latestMinor；不是插件已构建证据 |
| [v12.2 标签提交](https://github.com/jellyfin/jellyfin/commit/ca0f16eb7c195f720a1493ed469a27c4657db0c6) | 确认原方案标签存在，仍需目标服务器验证 |
| [v12.2 发布页](https://github.com/jellyfin/jellyfin/releases/tag/v12.2) | 2026-10-13 浏览时标为最新稳定版本；发布源码提交为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`，不代表插件兼容已验证 |
| [MediaSourceManager.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/Emby.Server.Implementations/Library/MediaSourceManager.cs) | 原方案提出的 GetPlaybackMediaSources 接入位置，Task 1.1 核实 |
| [ProbeProvider.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs) | 原方案提出的 STRM 注释／URL 读取位置，Task 1.1 核实 |
| [BaseItem.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Controller/Entities/BaseItem.cs) | 原方案提出的 ShortcutPath 和持久化位置，Task 1.1 核实 |
| [MediaBrowser.Controller.csproj at v12.2](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Controller/MediaBrowser.Controller.csproj) | 本轮源码页面显示目标框架 `net10.0`；未取得固定 SDK、镜像 digest 或本项目依赖组合 |

后三项是待核实定位，当前没有据此宣布接口或二进制已兼容。不读取 OpenList API 或生成程序实现，因为本次范围已经排除。

## V4.2 计划任务定位

2026-10-13 读取 [官方 v12.2 发布页](https://github.com/jellyfin/jellyfin/releases/tag/v12.2)，页面标示发布版本 12.2；这不是插件实机支持证据。本轮通过 GitHub 源码页面检视 `MediaSourceManager.cs`、`ProbeProvider.cs` 和 `MediaBrowser.Controller.csproj`，没有本地检出 Jellyfin 源码；详细定位及环境限制见 [compatibility.md](compatibility.md)。

| V4.2 引用／候选源码 | 本轮读取结论 |
|---|---|
| [IScheduledTask.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Model/Tasks/IScheduledTask.cs) | 网页及 raw 读取 Cache miss，未取得源码；Task 1.1 固定源码核实 |
| [IConfigurableScheduledTask.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Model/Tasks/IConfigurableScheduledTask.cs) | raw 读取 Cache miss，未取得源码；核实是否适合任务注册 |
| [ILibraryPostScanTask.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Controller/Library/ILibraryPostScanTask.cs) | raw 读取 Cache miss，未取得源码；仅候选定位，首版明确排除 |
| [`MediaSourceManager.GetPlaybackMediaSources`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Library/MediaSourceManager.cs#L2479-L2513) | 已由官方源码页面确认 `.strm` 且 `allowMediaProbe=true` 会触发 `FullRefresh`，随后重读静态媒体源；DI 替换和实际播放行为仍 NOT RUN |
| [`ProbeProvider.FetchVideoInfo`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs#L1498-L1601) | 已确认路径上会调用原生 `ProbeVideo` 并读取 STRM 地址；成功信号、失败保留、地址持久化和重启结果仍 NOT RUN |

V4.2 的“已核对源码”是用户方案陈述；本项目仍须独立验证目标版本 API、注册、默认无触发时间、取消与进度，不把本轮不可读取的定位写成通过。

## A 开发环境准备来源

2026-10-13 通过浏览工具读取 [目标源码 global.json](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/global.json) 的 `10.0.0`／`latestMinor`，以及 [Microsoft .NET 10 官方发布元数据](https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/10.0/releases.json) 中具体 SDK `10.0.401` 的 Linux x64 URL／SHA-512。本地固定与工具见 [环境交接](development-environment.md)；网页能读元数据不意味着终端可以下载 SDK。

隔离安装方式参考 [Jellyfin 官方容器文档](https://jellyfin.org/docs/general/installation/container/) 和 [Microsoft 手动安装文档](https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual)。没有取得实际 Docker manifest digest，未拉取镜像或安装 SDK；固定候选输入不声明二进制兼容。

### 权限解除后的实测补充

同日用户恢复权限后，终端重新读取 Microsoft 官方 release metadata 并核对固定 SDK 的 URL／SHA-512，成功安装 SDK。Jellyfin 源码已本地检出至 `artifacts/dev-env/source`，HEAD 为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`；官方镜像已拉取并记录 digest，实际 Public Info 为 `12.2.0`。已实际恢复 `Jellyfin.Controller`／`Jellyfin.Model` `12.2.0`，两包 nuspec 的 repository commit 与该源码一致，引用样例 Release 编译运行 PASS。此前“没有检出／未安装／未取得 digest”是前轮历史诊断，不是当前环境状态。

源文件、镜像身份、包来源和原始运行日志保留于 [环境交接](development-environment.md) 所指本机证据目录；镜像未提供 revision 标签，不能仅凭版本号证明镜像整体构建源码。Task 的插件接入／成功信号／地址持久化及 T4 产品门槛仍须独立验证。

## 所选库候选 ID 与分批读取参考

2026-10-14 源码调研后，用户授权 A 采用候选 ID 集合＋分批对象读取；该授权及合同边界见 [scope.md](scope.md#用户授权的批量读取替代)。下列固定源码仅作为接入与设计参考，不代表本项目批量、内存、取消、兼容或停止验收 PASS。

| 固定来源 | 已读取的做法及本项目取舍 |
|---|---|
| [Meilisearch ReindexTask](https://github.com/Shadowghost/jellyfin-plugin-meilisearch/blob/6279d1559b991b792fc9af45c5f182df93f1d5f3/Jellyfin.Plugin.Meilisearch/Tasks/ReindexTask.cs#L179) | 先 `GetItemIds`，再按 ID 批次 `GetItemList`，避免滑动 offset；借鉴候选身份与对象分批分离，不引入其索引交换、同步暂停或持久化队列。它的一次获取 ID 成本需要本项目独立观测。 |
| [Intro Skipper SeasonResolver](https://github.com/intro-skipper/intro-skipper/blob/e167e74bcf0b6b1f6772e88bebb3c65fa25f6388/IntroSkipper/Manager/SeasonResolver.cs#L105) | 用 `GetVirtualFolders`／库 ItemId、`ParentId`／Recursive 查库内项目；其无分页对象列表不照搬为本项目整库对象缓存。 |
| [TheIntroDB 范围判断](https://github.com/TheIntroDB/jellyfin-plugin/blob/daa0a9b3054edc35adcde0eda7dadec7213a935d/TheIntroDB/Providers/TheIntroDbSegmentProvider.cs#L402) | 选定库 ID 与 `ItemIds＋AncestorIds` 重核范围；不照搬空选择扩大范围或依靠媒体片段扫描的运行模式。 |
| [固定 Jellyfin LibraryManager](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Library/LibraryManager.cs) 与 [GetItemIdsList](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Server.Implementations/Item/BaseItemRepository.Querying.cs#L22) | 本地固定源码已核对 ID 投影／原生库过滤入口；同步接口无调用 token，停止检查放在调用前后，不承诺查询中断。多库、alternate、对象批次和实际运行分配尚未实测。 |

后续用户授权将方案扫描文字最小修订为 V4.3，已同步文件名和完整内容摘要；V4.2 原文仍由上述 Git 快照保留，ID 集合合同与 Task 范围不变。

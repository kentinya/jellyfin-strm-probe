# NO ACTIVE IMPLEMENTATION TASK

Task 3.2 已由 B 审查 PASS，当前不再创建实施 Task；以下保留最近完成的计划、报告与审查，供独立 Slice Final 及 A 交接。Next: B RUNS SLICE FINAL。

# Task 3.2 — 完整管理员配置与操作恢复旅程

范围 authority 为已提交的 [Slice 3](SLICE.md)，遵循 [开发流程](docs/development-workflow.md)；规划／审查读 [B 经验](docs/agent-experience/task-planner-reviewer.md)，实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 3.2
Parent Slice: 3
Status: PASS
Task Base: 2f74aa83f15707df56c4b15409ba1538a488f83a
Contract Checkpoint: 2b515f35db7fc8e85d8ac1a8085dd9b8ccc62ef3
Difficulty: Medium
Test Level: T3
Planner / Reviewer: B
```

## Goal

管理员在 Jellyfin 原生插件配置入口打开完整页面，加载并保存启用、播放自动检查、最大并发、批量媒体库范围和详细日志五项配置；能区分保存成功、加载／保存失败、空或失效库选择，并理解生效时机。从页面说明可找到原生「STRM 媒体信息检查」入口与故障恢复方法，使用已交付后端完成“配置 → 原生任务运行 → 查看反馈／恢复”的完整旅程。

闭合 RO-7、RO-2 的范围选择页面及 AC-1／Required Surfaces 的配置页与浏览器操作证据。一个 Task 完成页面注册、交互、错误路径、操作说明和隔离浏览器验收，不按字段、HTML／脚本文件或测试拆分。Task PASS 后 B 再核对全部 RO；满足即停止创建 Task，单独运行完整 Slice Final 并提交 Closure Packet 给 A。

## 实际基线、规划检查与复用

2026-10-15，B 先读必读清单、B 经验及已提交 Slice，初始工作区干净。Task 3.1 已在 Task Base 检查点经 B PASS，完整计划／Developer 报告／Reviewed Range／AC 与证据保留于 `2f74aa83f15707df56c4b15409ba1538a488f83a:TASK.md`。接受产品实现 `3209bc699544f26ffe7a5e100941edda0b0d275d`，原 Task 3.1 Base `b86d9c17d7f915108072f54ee098f0f5543fe093` 保持在该快照，不重设历史。

规划前治理 PASS，已提交 Slice／Roadmap／稳定需求／流程与 Task 3.1 合同一致；Slice 3 仍 ACTIVE、Base `6da90ab6bd8995d8204ae0b7faf786c823699fe6` 不变。RO-1～RO-6 批量表面及 RO-7 范围后端已交付；完整 HTML／浏览器旅程未实现，全部 Slice RO 尚未满足，不提交 Closure Packet、不宣布关闭。

已有能力必须复用：

- `Plugin.cs` 的 UpdateConfiguration、原子保存、有效配置发布与启动并发快照；`PluginConfiguration.cs` 的值域与库 ID 校验；`PluginPlaybackSettings` 的动态配置及启动值。批量范围由 BatchAllLibraries＋BatchLibraryIds 表示一个用户配置项，不新造存储或第二套保存接口。
- `LibraryIdProvider`／目标 Jellyfin 原生媒体库查询、稳定库 ID 和已交付的范围解析。页面展示库名称、内部使用原生 ID；范围在下一轮批量生效，不能把页面编辑混入正在运行的固定范围。
- 原生计划任务、进度／历史与脱敏日志；页面只引导用户进入原生任务管理，不提供第二套运行／停止／时间入口。
- 现有 `scripts/run_isolated_plugin_integration.py`／`run_isolated_batch_integration.py` 的专用实例识别、部署、认证、本地媒体、配置／触发器备份恢复、重启与验证。Task 3.1 的 B 索引 `.git/validation-evidence/3209bc699544f26ffe7a5e100941edda0b0d275d/b-review8-20261015/INDEX.md`；B 聚焦132／独立28、真实 stop／sharing 通过，全套173 C#／54 Python及其他实机门槛经匹配原始证据复用。

当前实际缺口：Plugin 未实现标准插件页面导出，csproj 无配置 HTML 嵌入资源，仓库没有配置页面；`docs/core-configuration.md` 仍只说明四项 API，没有完整管理员旅程。固定源码 DashboardController 通过 IHasWebPages.GetPages 与 EmbeddedResourcePath 读取页面，可使用此既有机制；源码可行性不是页面实测通过。

本机尚无 Playwright／Node／Chromium／Firefox，浏览器验证仍 NOT RUN。准备隔离测试浏览器属于本 Task 的验证工作，不能用页面源码、HTML 字符串测试或 API-only 请求替代真实交互。实现者选择并锁定浏览器测试依赖及浏览器版本，优先 Python Playwright 或等效工具；保存在忽略的工具目录／隔离测试容器，不增加插件生产依赖。提供明确可复现的准备命令，必要工具回归归入现有 Python discover，不另开环境 Task。

## 实施范围与边界

1. 通过固定 Jellyfin 标准插件页面导出与嵌入资源提供完整配置页；优先复用原生网页端表单、ApiClient／认证及现有配置通道。部署后从真实插件管理入口可以找到和打开，资源路径正确，无额外网站／独立配置服务。
2. 五项可编辑配置加载正确，保存完整候选且不丢失其他已保存项。页面展示全部／选定库，原生库名称与稳定 ID 对应；旧配置缺少范围字段默认全部。明确选定却未选库、已保存库失效或库列表暂不可读时给出可操作反馈，不静默扩成全部；加载未完成／失败不得用默认表单覆盖有效配置。
3. 加载、保存、重读及失败恢复形成完整交互。合法保存后确认有效值，返回页面／重启后读回一致；校验拒绝、网络失败或服务器保存异常有明确反馈，不显示假成功，不把错误响应原文／堆栈直接展示为秘密或私有路径。错误可通过重试／修正后保存恢复；后端继续保持原子保存失败保护，不为 UI 重做配置层。
4. 说明 Enabled、PlaybackAutoCheck、DetailedLog 的下一检查请求语义，并区分禁用后批量未开始拒绝／已开始收尾；关闭播放检查仍可独立批量。并发默认2、1～8、仅下次 Jellyfin 启动生效；范围保存只对下轮生效。固定判断规则、首次信任与只按需批量作为说明，不能新增可关闭开关。
5. 从页面可找到原生「控制台 → 计划任务 → STRM 媒体信息检查」的准确导航或链接、默认无自动触发、手动／停止／定时／进度所在位置，以及单项修复重跑、状态库不可用修复后重启的说明。不要从页面自动清空数据库、自动修复、安排默认时间或触发检查。
6. 新增真实浏览器隔离验收入口 `scripts/run_isolated_configuration_integration.py`，复用现有服务和恢复工具；保留脱敏交互／截图或等效浏览器原始证据。更新 `docs/core-configuration.md` 中本 Task 交付的页面操作、第五项范围与恢复说明；不改稳定需求、合同或替 A 做关闭协调。

允许文件：Plugin／csproj 的页面导出／资源接入、插件项目内配置 HTML／必要页面脚本、相关现有测试、浏览器验收／必要测试工具与隔离工具依赖记录、上述操作说明、TASK 完成报告。页面不得包含服务器源码路径、认证常量或完整签名媒体 URL。

当前是 T3：页面接入及保存已有后端，不改变决策、Coordinator、原生刷新、指纹提交、范围获取／停止语义。发现必须修改这些已接受核心行为时先交 B 重新评估 T4；普通页面错误修正留在同一 Task，不默改合同或重新拆任务。

## 验收条件

- [x] **AC-U1 页面入口／完整加载**：固定隔离 Jellyfin 部署后，管理员从原生插件入口打开页面，五项有效值及真实库列表正确，无未处理页面异常；旧配置默认全部，普通页面打开不启动探测／任务。
- [x] **AC-U2 合法保存／持久化**：经实际浏览器编辑五项组合并保存，页面反馈、配置 API／文件、重新打开及真实重启后读回一致；并发保存时提示下次启动，不伪报已热生效。编辑某一项不重置其他已保存值。
- [x] **AC-U3 范围安全／恢复**：全部与显式部分可切换，至少两库；选定空集合、失效库、读取库列表失败有清楚反馈，未成功加载／保存不得扩大范围或覆盖已有值。修正并重试可恢复；保存部分范围后由原生任务验证只处理选定库。
- [x] **AC-U4 错误反馈／原子保护**：并发越界、服务端拒绝、页面请求失败和保存失败控制反馈准确；失败不变更有效配置／旧文件，不假成功。页面错误可重试；不泄 token／Cookie／签名 URL／私有路径。物理保存故障可复用既有隔离控制，浏览器需证明对应失败响应确实被展示并可恢复。
- [x] **AC-U5 完整操作旅程**：用户能按页面说明找到原生任务及真实运行／停止／定时／结果；固定规则和识别限制以说明展示。经页面关闭播放检查仍可运行批量，经页面禁用插件不启动新批量探测；正常再启用／修复后可重试。已接受的极窄并发控制无需在页面 Task 再造实现。
- [x] **AC-U6 验证／边界交接**：T3 指定候选门槛、真实浏览器交互及重启／恢复有匹配证据；测试实例前后配置、触发器、媒体／地址与临时条目恢复，已有播放／批量核心回归保持。准确标记外部联调／大库／保存故障实机等未运行限制，不声明 Slice 已关闭。

## 必要测试

工作目录 `/opt/jf-strm-probe`，固定 SDK10.0.401／net10.0／Jellyfin12.2.0 组合与现有锁文件。执行阶段与证据复用遵循开发流程；本 Task 的浏览器验收入口和浏览器工具是待交付内容，当前没有该命令的 PASS。

### 开发／修正反馈

```bash
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~ConfigurationTests|FullyQualifiedName~CoreServiceRegistrationTests'
python3 -m unittest discover -s tests -v
python3 scripts/run_isolated_configuration_integration.py
```

先准备锁定的浏览器工具，首次或依赖变化先 locked restore；按新增页面／失败路径聚焦反馈，保留首次失败。浏览器脚本可明确调用隔离工具环境中的解释器／浏览器，但以上仓库入口必须可直接运行，缺工具时明确报不可用和准确准备命令，不悄悄跳过交互。

### 最终 Task 候选门槛

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/run_isolated_configuration_integration.py
python3 scripts/check_governance.py
git diff --check
```

- 本 T3 要求 C# 全套的原因：修改插件公开页面导出／嵌入资源和配置载体，需要确认核心注册／委托与已接受的173项配置、播放、批量、并发／持久化边界仍成立；全套已包含聚焦则不机械重复。Python 全套保护共用隔离部署／恢复工具。
- 浏览器入口默认完整运行 AC-U1～U5，实际打开并操作页面，记录交互、页面 console、脱敏截图／结果、有效配置及请求状态；覆盖成功、范围错误、请求失败／保存拒绝与恢复，实际重启读回。不是只直接调用 API 后截图静态 HTML。失败反馈可在浏览器网络层控制响应，不能把它说成服务器磁盘故障注入；物理原子保存保护引用匹配 C# 控制。
- 浏览器保存的范围／启停结果通过真实原生任务作代表性端到端核对，复用既有 native API 与本地手写夹具，测试不新增产品按钮。运行前后保存配置／触发器／夹具身份，finally 恢复文件、有效内存配置、触发器和原生地址并清除临时条目，未恢复不得 PASS。
- 本 Task 不要求机械重跑已无输入变化的完整播放／七场景 batch suite；变更触及核心或实际回归时重评门槛。页面 Task PASS 后若全部 RO 满足，B 必须另跑当前 Slice 的完整 T4 Final：既有默认播放、批量默认 suite、新浏览器入口、全部构建／测试／质量／治理与恢复，不能以本 Task／旧 Task 日志代替 Final。
- 操作说明本地链接／锚点与相关事实检查，资源与部署 DLL 身份核对。不得宣称兼容其他版本、外部代理或发布包已验证。

### B 独立验证

审阅真实 Task Base..Developer Head、页面资源／导出／实际保存路径与浏览器原始证据；独立执行 `python3 scripts/run_isolated_configuration_integration.py`，核对真实页面入口、五项读写、部分／失效范围、错误反馈与重试、重启持久化及全部恢复。独立配置／注册聚焦；匹配的完整门槛允许原始证据核验后复用，缺失或输入不符须重跑。不把 API-only 或模拟DOM当真实浏览器 PASS。

### 证据与重跑规则

每个候选保留 `.git/validation-evidence/<source-sha>/<run-id>/INDEX.md` 及原始产物，包含准确源码／工作区内容、浏览器工具／版本／依赖锁、SDK／镜像／配置／夹具／部署身份、命令／cwd／退出码／耗时、失败／重跑／跳过与交互／截图的脱敏证据；仅本机可读如实说明。页面／脚本／依赖／测试／工具变化均是可执行输入变化，最终候选重跑相关门槛，不能把 HTML 当普通报告后继。测试实例的私有配置文件、认证材料和触发器备份不进入普通提交；截图只保留可公开的页面配置值和假库名称，不暴露任何秘密或私有路径。

## 非目标

- 修改 Slice、Roadmap、稳定需求或 A 的最终审查／关闭协调；本轮只规划，不实施插件。
- 重做 Task 3.1 的候选获取、源身份／决策、Coordinator、原生刷新、停止收尾或指纹机制；不补独立调度／运行／停止／时间 UI，不热调并发。
- 生成程序、OpenList API／远程哈希、代理改造、全库强制探测、状态机／新指纹字段、自动删库修复、生产操作。
- Slice 4 的十万真实库／完整扫描压力、外部代理联调、广泛客户端／媒体格式和发布 ZIP。当前 Slice 必需的页面与完整 Final 不延期。

## Developer Completion Report

- Changed Files（相对 Task Base `2f74aa83f15707df56c4b15409ba1538a488f83a`）：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Plugin.cs`：新增 `IHasWebPages`，导出一个 `StrmProbeOptimizer` 页面描述符。
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Jellyfin.Plugin.StrmProbeOptimizer.csproj`：嵌入 `Configuration/configPage.html`。
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Configuration/configPage.html`：新配置页（五项读写、库范围、失败反馈、说明）。
  - `scripts/configuration_page_driver.mjs`、`scripts/run_isolated_configuration_integration.py`、`scripts/prepare_browser_tools.py`：真实浏览器隔离验收入口与工具准备。
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ConfigurationPageTests.cs`、`tests/test_isolated_configuration_integration.py`：页面导出与工具守卫测试。
  - `docs/core-configuration.md`：补充配置页、第五项范围与恢复说明。
- Implemented：管理员从原生插件入口打开完整配置页，加载／编辑／保存启用、播放自动检查、最大并发、详细日志、批量范围五项；展示真实媒体库名称并保存稳定库 ID；空选择／失效库／列表不可读／加载失败／保存拒绝均有可操作反馈且不静默扩大或覆盖；页面说明原生任务入口、固定规则、首次信任、仅按需处理、停止收尾与状态库恢复。并发只提示下次启动生效。页面无第二套运行／停止／时间入口。
- Tests and Results（完整 SHA `dac695e45f8619b6ebcc24327e515fd9413240a1`，索引 `.git/validation-evidence/dac695e45f8619b6ebcc24327e515fd9413240a1/developer-20261015-01/INDEX.md`）：
  - `restore --locked-mode` PASS；`build` PASS（0 警告 0 错误）；C# `test` PASS 178/178（原 173 + 新增 5）；`format --verify-no-changes` PASS。
  - `python3 -m unittest discover -s tests -v` PASS 61/61（原 54 + 新增 7）。
  - `python3 scripts/run_isolated_configuration_integration.py` PASS：真实 Chromium 140（chromium-1187／Playwright 1.55.0）覆盖 AC-U1～U5，含页面加载、五项编辑保存、部分范围、真实重启读回、空选择拒绝、库列表读取失败、保存拒绝、加载失败，以及页面保存的部分范围驱动原生任务库选择；结束后配置与全部触发器已恢复并核对。
  - `python3 scripts/run_isolated_plugin_integration.py` PASS（同一候选，既有默认播放／失败／竞态／重启回归未回退，夹具与地址已恢复）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` PASS。
- Decisions：复用现有配置保存通道、`ILibraryIdProvider`／原生库查询与原生任务；未改决策、Coordinator、原生刷新、指纹提交或范围／停止语义，故维持 T3，无需升 T4。浏览器工具仅测试依赖，放忽略目录。
- Remaining In-Slice Work：本 Task 全部验收后由 B 核对全部 RO；满足则单独 Slice Final 与 Closure Packet。
- Risks / Deviations：本机浏览器工具与系统库属宿主测试依赖，不是插件生产依赖；真实外部代理、真实大库与保存故障实机注入仍 NOT RUN，留 Slice 4／其他 Task。两次默认插件集成早失败源于此前中断运行留下的夹具／指纹库／配置污染，重置后同一候选通过，且该失败在 Task Base 独立复现，与本 Task 改动无关。
- Head SHA：`dac695e45f8619b6ebcc24327e515fd9413240a1`。

少量经验候选留待 Slice 收尾，不以流水账或新增经验条数作为通过门槛。

## Developer Fix Report（FR-U1／FR-U2／FR-U3）

- 修正 Head SHA：`dd5acfa19984955c8730eab5f212d485a65780c9`（Task Base 与 Task ID 不变，未改合同、范围或测试门槛）。
- Changed Files（相对 Task Base `2f74aa83f15707df56c4b15409ba1538a488f83a`）：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Configuration/configPage.html`：失效库可见并阻止保存、保存反馈区分拒绝与未确认、新增「重新读取」、表单 `novalidate` 以让页面自身给出并发越界反馈。
  - `scripts/configuration_page_driver.mjs`：每场景独立会话与结果，新增失效范围、丢失响应、提交前失败、拒绝保存、并发越界、空范围恢复、加载／库列表失败恢复、旧配置缺字段，以及页面保存值驱动原生任务的场景；固定浏览器 `locale: 'zh-CN'`。
  - `scripts/run_isolated_configuration_integration.py`：每场景独立证据目录；断言失效范围 0 POST、未确认反馈不承诺回滚、并发越界不改有效值、真实原生任务终态与指纹行；原生任务旅程由页面保存值驱动。
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ConfigurationPageTests.cs`、`tests/test_isolated_configuration_integration.py`：新增页面与守卫断言。
  - `docs/core-configuration.md`：补充失效范围、重新读取与保存反馈区分说明。
- FR-U1：失效库保留为「已失效媒体库」并阻止保存，未修正前保存 0 POST；取消失效项后保存只写入有效库 ID（场景 04）。
- FR-U2：服务器已提交但响应丢失时页面提示「保存结果未确认」，不再承诺「未被更改」；重新读取显示真实有效值（场景 05、06）。
- FR-U3：补齐原计划缺项与端到端旅程；B 复现的 `scrollHandler`／locale 失败经定位为 Jellyfin 自身 web 组件竞态与宿主 POSIX locale，分别按精确 bundle／消息归类与固定浏览器 locale 处理（见证据 `development-feedback/`）。
- Tests and Results（完整 SHA `dd5acfa19984955c8730eab5f212d485a65780c9`，索引 `.git/validation-evidence/dd5acfa19984955c8730eab5f212d485a65780c9/developer-20261016-01/INDEX.md`）：
  - `restore --locked-mode` PASS；`build` PASS（0 警告 0 错误）；C# `test` PASS 181/181（0 skipped）；`format --verify-no-changes` PASS。
  - `python3 -m unittest discover -s tests -v` PASS 63/63。
  - `python3 scripts/run_isolated_configuration_integration.py` PASS：真实 Chromium（chromium-1187／Playwright 1.55.0）17 个场景覆盖 AC-U1～U5 及 FR-U1／FR-U2，含真实重启读回、失效范围、响应丢失、拒绝／网络失败恢复、并发越界、旧配置缺字段，以及页面保存值驱动的原生任务部分／全部范围、关闭播放检查仍批量、禁用不新增探测、再启用恢复；结束后配置与全部触发器恢复并核对。
  - `python3 scripts/run_isolated_plugin_integration.py` PASS（同一候选，既有默认播放／失败／竞态／重启回归未回退）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` PASS。
- Decisions：仍复用现有配置保存通道、`ILibraryIdProvider`／原生库查询与原生任务；未改决策、Coordinator、原生刷新、指纹提交或范围／停止语义，维持 T3。
- Remaining In-Slice Work：本 Task 全部验收后由 B 核对全部 RO；满足则单独 Slice Final 与 Closure Packet。
- Risks / Deviations：真实外部代理、真实大库与保存故障实机注入仍 NOT RUN，留 Slice 4／其他 Task。证据仅本机可读，未推送。

## Developer Fix Report（FR-U4）

- 修正 Head SHA：`5580492a5cacbdc0772dd2f14f9b527ab3851746`（Task Base 与 Task ID 不变，未改合同、范围或测试门槛）。
- Changed Files（相对 Task Base `2f74aa83f15707df56c4b15409ba1538a488f83a`）：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Configuration/configPage.html`：新增 `readConcurrencyValue()`，用 `valueAsNumber`（带 `Number(...)` 回退）读取完整数值；`validateBeforeSave()` 要求 `Number.isInteger` 且 1～8，返回校验后的数值对象；保存 POST 复用同一已校验值，移除两处 `parseInt` 截断。
  - `scripts/configuration_page_driver.mjs`：新增 `numeric_boundary_invalid`／`numeric_boundary_valid` 两个独立会话场景，覆盖 `2.5`、`8.9`、`1e1`、空值、`0`、`9` 及合法 `1`／`8`／`2`。
  - `scripts/run_isolated_configuration_integration.py`：新增 `scenario_numeric_boundary`，断言非法输入 0 POST、有效配置与配置文件不变，合法值页面／有效配置一致。
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ConfigurationPageTests.cs`：新增 `PageValidatesTheWholeConcurrencyNumberWithoutTruncating`（要求 `valueAsNumber`、`Number.isInteger`，禁止 `parseInt(concurrencyInput`）。
  - `tests/test_isolated_configuration_integration.py`：守卫断言新增 numeric boundary 场景与 0 POST 断言。
  - `docs/core-configuration.md`：补充并发按完整数值校验、小数／指数／空值／越界均拒绝且不截断保存的说明。
- FR-U4：并发输入按完整数值判定，`2.5`、`8.9`、`1e1`、空值、`0`、`9` 均拒绝且 0 POST，有效配置与旧文件不变；合法 `1`／`8`／`2` 保存后页面与有效配置一致（场景 18／19）。不再有 `parseInt` 截断把 `2.5` 存为 2、`1e1` 存为 1。
- Tests and Results（完整 SHA `5580492a5cacbdc0772dd2f14f9b527ab3851746`，索引 `.git/validation-evidence/5580492a5cacbdc0772dd2f14f9b527ab3851746/developer-20261016-02/INDEX.md`）：
  - `restore --locked-mode` PASS；`build` PASS（0 警告 0 错误）；C# `test` PASS 182/182（0 skipped）；`format --verify-no-changes` PASS。
  - `python3 -m unittest discover -s tests -v` PASS 63/63。
  - `python3 scripts/run_isolated_configuration_integration.py` PASS：真实 Chromium（chromium-1187／Playwright 1.55.0）19 个场景覆盖 AC-U1～U5 及 FR-U1／FR-U2／FR-U4，含新增数值边界非法 0 POST／有效值不变与合法 1／8／2 保存读回；结束后配置与全部触发器恢复并核对。
  - `python3 scripts/run_isolated_plugin_integration.py` PASS（同一候选，既有默认播放／失败／竞态／重启回归未回退）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` PASS。
- Decisions：仍复用现有配置保存通道、`ILibraryIdProvider`／原生库查询与原生任务；未改决策、Coordinator、原生刷新、指纹提交或范围／停止语义，维持 T3。
- Remaining In-Slice Work：本 Task 全部验收后由 B 核对全部 RO；满足则单独 Slice Final 与 Closure Packet。
- Risks / Deviations：真实外部代理、真实大库与保存故障实机注入仍 NOT RUN，留 Slice 4／其他 Task。证据仅本机可读，未推送。

## B Review Result

```text
Reviewed: 2f74aa83f15707df56c4b15409ba1538a488f83a..5580492a5cacbdc0772dd2f14f9b527ab3851746
Report Checkpoint: c22531c194cfe687345d2234e6345a7caa513e54
Decision: PASS
P0/P1 Blockers: NONE
Slice Required Outcomes all satisfied: YES
Next: RUN SLICE FINAL; NO NEW TASK
```

2026-10-16，B 完成必读、治理与真实完整范围／本次 `dd5acfa..5580492` 差异审查；初始工作区干净。报告后继只修改 TASK.md，53 个可执行／测试／工具／依赖输入及构建身份已记录；独立实机部署 DLL 与 Developer 候选 SHA-256 均为 `8487db03ef7444d6c207ab2e31c448c8bb308d22f521e5b9c37df100869fac44`。Task ID、Base、Goal、Scope、T3 和原门槛不变，未修改已接受的决策／协调／原生刷新／提交／停止核心。前轮反例与决定保留于 `b7c5957e3aa110e78adc57b4d434f5a786aff0ce:TASK.md` 及其本机证据，不把历史 FAIL 改为 PASS。

### 修正与验收

FR-U4 已修正：页面读取完整 valueAsNumber，明确检查 Number.isInteger 与 1～8，将同一已校验数值用于 POST。独立真实浏览器六项非法输入 `2.5`／`8.9`／`1e1`／空值／0／9 全部拒绝、0 POST，旧文件与有效配置不变；合法 1／8／2 各保存并读回一致。旧 FR-U1／U2 的失效范围与未确认保存／重读再次通过；原缺失旅程和稳定证据目录已补齐。

| Task 验收 | 决定与证据 |
|---|---|
| AC-U1 | PASS：原生插件入口、真实库列表与五项加载、旧配置默认全部、加载失败禁止保存及恢复；浏览器 01／10／12。 |
| AC-U2 | PASS：五项保存、有效值／配置文件／重启读回一致、修改单项保留其他项、并发下次启动说明；02／03／18／19。 |
| AC-U3 | PASS：两库部分／全部、失效／空范围阻止保存与修正、库列表失败及恢复、页面值驱动原生任务范围；04／09／11／13／14。 |
| AC-U4 | PASS：失去响应不承诺未变、提交前失败／拒绝／重读、严格数值范围与零 POST；05～08／18／19。物理原子保存保护由匹配 ConfigurationTests 控制支持，不声称实机磁盘故障注入。 |
| AC-U5 | PASS：准确原生任务与恢复说明；页面关闭播放检查仍可批量、禁用后原生 Cancelled 且新项目无指纹、再启用完成；13～17。原生停止／定时完整事实由已接受 Task 3.1 支持。 |
| AC-U6 | PASS：最终 T3 门槛输入与日志可核验、独立浏览器及重启恢复通过，外部联调／真实大库／实机数据库保存故障仍分别 NOT RUN；未作 Slice 关闭声明。 |

### 独立验证与证据复用

本机索引 `.git/validation-evidence/5580492a5cacbdc0772dd2f14f9b527ab3851746/b-review-20261016-03/INDEX.md`，仅本机可读。

- B 独立配置／注册／页面聚焦 22 passed、0 failed、0 skipped（2.509 秒），使用匹配候选已有构建 `--no-build`；验收工具守卫 9 passed、0 failed（0.216 秒）。原始日志、TRX、命令与耗时保存。
- B 独立指定配置页入口 19 场景 PASS，255.531 秒、退出 0；包括六项非法数值、三项合法数值、失效范围、提交后响应丢失、失败恢复、旧配置、真实重启和页面保存值驱动的原生任务部分／全部／播放关闭／禁用／恢复。每场景保留脱敏参数、console／响应、POST、截图与原始结果；配置及全部触发器 restored and verified。
- 审阅并复用 Developer 同候选原始 locked restore／build（0 警告 0 错误）／182 项 C#（0 skipped）／format／63 项 Python／19 场景浏览器／默认播放回归／治理与差异日志及退出码／耗时。源码与锁输入一致，二进制摘要与部署一致；不声称 B 重跑这些完整门槛。Slice Final 将另行运行全部指定门槛，旧 Task 运行不代替 Final。
- 证据表述边界：07-rejected-save 为浏览器合成 400，非真正服务器校验拒绝；允许用于页面错误反馈，后端保护由独立配置控制支持。源码按完整数值判断，数学上合法的指数写法可被接受，不能泛称所有指数写法都拒绝；不影响 1～8 整数规则，属于非阻塞说明精度。

### Slice 全部 Required Outcomes／Surfaces 重核与停止决定

| Slice 结果 | 当前覆盖 |
|---|---|
| RO-1 | Task 3.1：原生发现、无默认触发、手动／停止／定时／重启触发器；原生任务导出与生命周期 Surface。 |
| RO-2 | Task 3.1：候选 ID／去重／分批／范围／多版本与模拟成本；Task 3.2：两库范围页面／保存／失效恢复。原生查询与范围 Surface 完整。 |
| RO-3 | Task 3.1：共用源级决策、原生探测、五字段 SQLite 条件提交与失败／竞态保护；相关共用执行与持久化 Surfaces 完整。 |
| RO-4 | Task 3.1：实际开始共享、全局上限及播放权限；Task 3.2：并发页面校验／生效说明。 |
| RO-5 | Task 3.1：开始边界停止、仅撤销未开始、已开始收尾／再次运行、真实手动／定时竞争。 |
| RO-6 | Task 3.1：原生状态／进度／统计／错误隔离与状态库恢复；Task 3.2：配置失败和恢复可操作。原生结果／日志／实机入口 Surface 完整。 |
| RO-7 | Task 3.2：五项完整页面、加载／保存／拒绝／未确认／重读、旧配置与说明，关闭最后一个页面 Surface 缺口。 |

Task 3.1 PASS 完整快照 `2f74aa83f15707df56c4b15409ba1538a488f83a:TASK.md`。七个 RO 和六类 Required Surfaces 的实施义务均已覆盖，停止创建 Task。下一步在当前合同上执行单独 T4 Slice Final：原定全部构建／测试／质量／治理，加 `python3 scripts/run_isolated_plugin_integration.py`、`python3 scripts/run_isolated_batch_integration.py`（默认七场景 suite）和 `python3 scripts/run_isolated_configuration_integration.py`（19 场景）。Final 成功后形成一份 Closure Packet 交 A；本决定不宣布 Slice 关闭、不选择 Slice 4，也不提前改 CURRENT／Roadmap／稳定需求。

经验候选供收尾评估：配置传输失败不等同服务端回滚，应独立核对“已提交但响应丢失”；关闭原生表单校验时须对完整数值而非前缀做验证，适用于自有表单校验。

# Task 3.2 — 完整管理员配置与操作恢复旅程

范围 authority 为已提交的 [Slice 3](SLICE.md)，遵循 [开发流程](docs/development-workflow.md)；规划／审查读 [B 经验](docs/agent-experience/task-planner-reviewer.md)，实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 3.2
Parent Slice: 3
Status: FIX REQUIRED
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

- [ ] **AC-U1 页面入口／完整加载**：固定隔离 Jellyfin 部署后，管理员从原生插件入口打开页面，五项有效值及真实库列表正确，无未处理页面异常；旧配置默认全部，普通页面打开不启动探测／任务。
- [ ] **AC-U2 合法保存／持久化**：经实际浏览器编辑五项组合并保存，页面反馈、配置 API／文件、重新打开及真实重启后读回一致；并发保存时提示下次启动，不伪报已热生效。编辑某一项不重置其他已保存值。
- [ ] **AC-U3 范围安全／恢复**：全部与显式部分可切换，至少两库；选定空集合、失效库、读取库列表失败有清楚反馈，未成功加载／保存不得扩大范围或覆盖已有值。修正并重试可恢复；保存部分范围后由原生任务验证只处理选定库。
- [ ] **AC-U4 错误反馈／原子保护**：并发越界、服务端拒绝、页面请求失败和保存失败控制反馈准确；失败不变更有效配置／旧文件，不假成功。页面错误可重试；不泄 token／Cookie／签名 URL／私有路径。物理保存故障可复用既有隔离控制，浏览器需证明对应失败响应确实被展示并可恢复。
- [ ] **AC-U5 完整操作旅程**：用户能按页面说明找到原生任务及真实运行／停止／定时／结果；固定规则和识别限制以说明展示。经页面关闭播放检查仍可运行批量，经页面禁用插件不启动新批量探测；正常再启用／修复后可重试。已接受的极窄并发控制无需在页面 Task 再造实现。
- [ ] **AC-U6 验证／边界交接**：T3 指定候选门槛、真实浏览器交互及重启／恢复有匹配证据；测试实例前后配置、触发器、媒体／地址与临时条目恢复，已有播放／批量核心回归保持。准确标记外部联调／大库／保存故障实机等未运行限制，不声明 Slice 已关闭。

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

## B Review Result

```text
Reviewed: 2f74aa83f15707df56c4b15409ba1538a488f83a..dd5acfa19984955c8730eab5f212d485a65780c9
Report Checkpoint: 5c176e9eb46e7d7eff82a0b1e51039d1199ac213
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER FIXES THE SAME TASK 3.2
```

2026-10-16，B 重新完成必读、治理与完整 Task Base..Developer Head 范围核对；初始工作区干净。相对上次候选另审 `dac695e45f8619b6ebcc24327e515fd9413240a1..dd5acfa19984955c8730eab5f212d485a65780c9` 的页面／浏览器工具／测试／操作文档差异。报告后继只改变 TASK.md，可执行输入与候选一致，既有构建 DLL SHA-256 与 Developer 实机部署记录一致。未改决策、Coordinator、原生刷新、提交或停止核心，仍为同一 Task／Base／Goal／Scope／T3，不变更合同、不创建新 Task。上轮决定与指导保留于 `3c25af09c15f6d607264962c5b65d7396262b355:TASK.md`。

### 上轮修正核对

- **FR-U1 已修正并独立通过**：失效 ID 在真实页面可见；未修正保存为 stale，0 POST；取消失效项后只提交真实库。独立重用已审阅的实机控制入口复现，原始结果／截图完整保留。
- **FR-U2 已修正并独立通过**：真实隔离服务器 POST 返回 204 后丢弃响应，页面为 save-unconfirmed，不声称配置未变；重新读取显示已经生效的值。提交前失败／重读等原始场景亦已审阅。
- **FR-U3 的资料及原缺失旅程已补齐**：Developer 提供最终候选逐门槛原始日志、耗时、17 个独立浏览器场景目录和页面保存值直接驱动的原生任务结果；旧配置、范围修正、重读恢复和启停链均有证据。保留失败反馈过程，没有把旧日志缺失补造成旧 PASS。并发校验本次新增的缺陷见 FR-U4；不把原 17 场景 PASS 标签当作所有输入已验证。

### 当前产品阻塞（P1）

**FR-U4：关闭原生表单校验后，parseInt 把非法并发输入截断并保存为另一值（AC-U2／AC-U4／RO-7）。**

`Configuration/configPage.html:11` 新增 novalidate，但 `validateBeforeSave`（第 274 行）和构造 POST（第 350 行）仍使用 parseInt，只检查截断后的结果。B 在真实浏览器打开原生插件页面、使用正常输入和保存按钮，观察到：

| 用户输入 | 页面反馈／保存后显示 | 实际 POST、有效配置与文件 |
|---|---|---|
| `2.5` | 保存成功，输入框仍为 `2.5` | `MaxConcurrentProbes = 2` |
| `1e1`（数值 10） | 保存成功，输入框仍为 `1e1` | `MaxConcurrentProbes = 1` |

两次均实际到达隔离服务器，不是修改 DOM 有效性或截获伪造成功。后端只收到合法整数，因此无法拒绝用户原本输入的小数或越界数。这破坏“1～8 整数”校验与保存值确认；并发仍按原合同在下次启动生效，本轮没有误称热生效。

**最小修正指导：**

1. 用 number 输入的 `valueAsNumber`（或完整数值转换）取得数值，明确检查 `Number.isInteger(value)` 且 `1 <= value <= 8`；空值／非数／小数／越界均拒绝，不再用 parseInt 截断校验或组装请求。
2. 保存开始时取得并校验一次候选值，后续 POST 使用同一个已校验数值，避免校验和发送各自重新转换。可以继续使用 novalidate 与页面错误提示，不需改后端或核心并发机制。
3. 将真实浏览器回归补入现有并发场景：至少覆盖 `2.5`、`8.9`、`1e1`、空值及 0／9，拒绝时 0 POST、有效配置和旧文件不变；修正为合法值后可保存。合法 1／2／8 的页面、请求和重读值应一致。指数输入应按完整数值判定，不能把 10 截成 1；无需另建测试 Task 或只增加 HTML 字符串断言。
4. 按原定反馈／最终候选门槛验证新候选，更新真实实现 SHA 和完成报告后重新交 B。原范围、T3、验收及完整门槛不删减。

### B 独立验证与证据

本机索引：`.git/validation-evidence/dd5acfa19984955c8730eab5f212d485a65780c9/b-review-20261016-02/INDEX.md`，仅本机可读，未推送。

- **PASS**：配置／注册／页面聚焦 21 passed、0 failed、0 skipped（3.976 秒，`focused.log`／TRX）；验收工具守卫 9 passed、0 failed（0.413 秒，`python-focused.log`）。聚焦使用当前候选已有构建的 `--no-build`，DLL 与源码／报告输入身份记录在 `inputs.json`，未更换被测二进制。
- **PASS**：上轮两项关键实机复核（56.688 秒，`key-checks.log`、`review-keys.json` 及分场景原始证据）。配置文件逐字节及有效值恢复一致，触发器恢复后重启核对。
- **FAIL（产品行为）**：数值边界的两次真实页面保存复现 FR-U4（49.463 秒，`numeric-boundary.log`／`numeric-boundary.json`／`numeric/`）。控制脚本正常退出不代表产品 PASS；API／文件／POST 均核对，结束后配置逐字节、有效值和触发器恢复。
- **FAIL（指定默认浏览器入口）**：使用既有 Node PATH 运行，80.645 秒、退出 1；load 阶段捕获 Jellyfin 首页的 `[Home] failed to get tab controller` 异常，后续场景未执行，配置／触发器恢复成功（`browser-retry.log`）。调用栈指向原生 hometab，console 来源为 home bundle，未被现有工具分类接受；没有据此另判产品回归，也不忽略后声称全套通过。此前一次计时包装因宿主没有 `/usr/bin/time` 未启动测试，原日志保留；随后用 Python 记录准确耗时。
- **原始证据已审阅，未独立重跑**：Developer 同一候选 locked restore／build（0 警告 0 错误）／181 项 C#／format／63 项 Python／17 场景浏览器／默认播放回归及治理／差异日志。只作为匹配候选的已有证据，不能覆盖本轮新反例或把本轮默认入口 FAIL 改成 PASS。修正后的 HTML 属可执行输入，仍须按原计划重跑最终门槛；环境／原生噪声须有可核验归因和精确处理，不泛化忽略异常。
- 事实校正：Developer 的 07-rejected-save 实际采用浏览器合成 400 响应，`mutate_invalid` 模式未被该场景使用；不能称为真正到达服务器的校验拒绝。该控制符合原计划允许的页面失败反馈验证，后端保护另由已有配置测试支持，下轮报告须按真实控制方式说明。

### Slice 停止规则与交接

当前 Task 未 PASS，RO-7 的合法输入与准确保存仍不满足，不执行 Slice Final、不提交 Closure Packet。Task 3.1 已接受的 RO-1～RO-6 核心事实保留；Slice／Roadmap／稳定需求不改动，不代替 A 关闭。Developer 在同一 Task 修正 FR-U4、取得新候选完整证据后重新交审；PASS 后 B 再核对全部 RO／Surfaces，满足才停止创建 Task 并运行完整 Slice Final。

经验候选保留供 Slice 收尾评估：请求失败不能等同服务端回滚；用“已提交但响应丢失”的传输控制核对有效值与反馈，适用于配置持久化页面审查。

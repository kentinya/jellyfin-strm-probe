# Task 3.2 — 完整管理员配置与操作恢复旅程

范围 authority 为已提交的 [Slice 3](SLICE.md)，遵循 [开发流程](docs/development-workflow.md)；规划／审查读 [B 经验](docs/agent-experience/task-planner-reviewer.md)，实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 3.2
Parent Slice: 3
Status: READY FOR B REVIEW
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
Reviewed: 2f74aa83f15707df56c4b15409ba1538a488f83a..dac695e45f8619b6ebcc24327e515fd9413240a1
Report Checkpoint: 047fc9444c51807ab7e766cfff0808952b1a27d9
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER FIXES THE SAME TASK 3.2
```

2026-10-16，B 完成必读、治理及真实 Base..Head 审查，开始时工作区干净。报告后继仅改变 TASK.md，可执行源码与上述 Developer Head 一致。页面导出／嵌入资源、已有配置通道复用及产品文件范围合法，未修改已接受的决策／协调／刷新／提交核心；维持 T3。以下都是当前合同内的阻塞，保留 Task ID、Base、Goal、Scope、验收和测试计划，不另建修正 Task，不交 A 改合同。

### 当前阻塞（P1）

1. **FR-U1：失效库选择被静默丢弃（AC-U3／RO-7）**。`configPage.html:167–196` 只渲染当前库，没有比较已保存 ID 与可用 ID 的差集；加载仍显示“已加载当前配置”。B 通过真实页面的配置 GET 响应控制提供“一个真实库＋一个已失效 ID”的已保存范围，未编辑范围直接保存，捕获 POST 发现仅剩真实库 ID，页面报告成功。该控制不修改真实库或服务器范围；它证明页面会静默改写已保存选择，不能当作失效库反馈已经验收。须明确标识失效选择并给出修正路径；在用户明确修正前不能因保存其他字段而静默丢弃。补真实浏览器失效选择／修正重试回归。
2. **FR-U2：响应丢失时错误承诺配置未变（AC-U4／RO-7）**。`configPage.html:257–263` 将保存请求错误统一解释为“已保存的有效配置未被更改”。B 在真实隔离服务器已处理 POST 并返回 204 后，于浏览器网络层丢弃响应：页面显示该错误，API 读回 `DetailedLog` 却已从 false 变为 true。须区分可确认的拒绝与结果未知，必要时重读有效值；不能对网络中断承诺回滚。补提交前网络失败、提交后响应丢失及恢复／重试的浏览器证据，不要求改变后端原子保存合同。
3. **FR-U3：验收覆盖和证据不足（AC-U1～U6）**。现有默认浏览器入口只检查了部分指定行为：缺失失效库、旧配置缺范围字段的页面加载、浏览器并发越界、失败后的实际重试恢复，以及由页面关闭播放检查仍能批量／禁用后无新批量探测／再启用恢复的端到端核对。`scenario_native_task_scope` 在运行前用 API 把 Enabled／PlaybackAutoCheck 都改回 true，又用 API 切全部范围，不能声称这些任务由相应页面保存值驱动；`run_native_task` 还须核对实际终态／结果而非仅等 Idle。完成现有计划要求的浏览器操作后直接运行原生任务并核对真实结果，不能用 API 重写被验收值代替页面旅程。

   Developer 索引只有标签与两个摘要 JSON，没有 restore／build／178 项 C#／format／61 项 Python／治理／差异门槛的原始日志；浏览器截图仍引用 `/tmp`，各场景同名截图相互覆盖，console／响应的原始结果被摘要丢弃，已声明的首次失败／Base 复现也无相应产物。本轮不能据此复用完整候选门槛。须在稳定忽略目录为修正候选保存准确输入／工具／锁／部署产物身份、每条门槛命令／退出码／耗时／计数及原始日志，浏览器每场景独立保存交互／截图／console／响应与恢复证据；历史缺失如实说明，不补造旧日志。修正涉及 HTML／脚本等可执行输入，按原计划重新完成最终候选门槛。

### Developer 简明修复指导

2026-10-16，按用户要求补充以下实施建议。它细化上述三个阻塞，不改变原验收／测试门槛；继续 Task 3.2、原 Base 和 T3，本次只补指导，不实施插件修正。

**第一步：让失效库可见，并由用户明确修正。** 修改 `Configuration/configPage.html`：

- 仅在显式选择模式且库列表读取成功时，计算“已保存 ID－当前有效库 ID”。把失效项保留为勾选项，标注“已失效媒体库”，显示提示“请取消失效项并选择有效库，或明确切换为全部媒体库”。不能加载时直接过滤丢弃。
- 只要仍勾选失效项，就阻止保存并说明原因；用户取消失效项、保留至少一个有效库后可保存，也可主动切换为全部。这样修改日志等其他字段不会顺便改掉范围。
- 库列表读取失败时保留原选择，不把未知判断成已失效；显式范围在成功重读前不能保存，不自动改为全部。旧配置没有范围字段仍按已有默认全部处理。

**第二步：保存反馈准确表达已知结果。** 继续用现有配置 API：

- 有明确成功响应时显示保存成功及现有生效时机。明确校验拒绝可提示“输入被拒绝，请修正后重试”。网络错误、超时或无法确认的服务器错误统一提示“保存结果未确认，请重新读取当前配置后核对”，删除这类路径中“有效配置未被更改”的承诺。
- 增加一个简单的“重新读取”配置操作，复用库列表／配置加载函数。失败时先保留编辑内容；用户主动重读成功后，用服务器有效值回填，再决定是否编辑重试。重读失败继续显示无法确认，不报成功，不声称回滚，不自动重复 POST。
- 加载和保存期间禁用保存以避免重叠请求；加载失败继续保留已有禁止保存保护。无需新增后端接口、持久化状态或事务机制。

**第三步：补真实浏览器验收，直接验证页面到任务。** 扩展现有 driver／runner：

- 先覆盖两个已复现反例：一个有效库＋一个失效库，未经修正不能静默保存，修正后成功；服务器已保存但响应被丢弃时不误报未更改，重新读取能看到真实有效值。B 的 `boundary-driver.mjs`／`run_boundaries.py` 可参考，产品回归用例归入现有验收入口。
- 补原计划缺项：旧配置缺范围字段、并发越界、提交前请求失败、加载／库列表／保存失败后的重试恢复。每项核对页面反馈、有效配置和适用的文件保护，不能只匹配提示文字。
- 用浏览器保存部分范围后直接运行原生任务，核对范围内／外结果；再由浏览器切全部并核对。分别经页面关闭播放检查、禁用、再启用后运行原生任务，验证可批量、无新增插件探测、恢复可运行。夹具准备可用现有工具，但运行前不能用 API 改写正在验收的配置值；检查原生终态及本次结果。
- 在测试工具中明确 Node 路径和浏览器 locale，定位已捕获的页面异常，保留首次失败和修正证据。不能用宽泛忽略页面异常换取 PASS；不要求重做批量核心或增加产品运行按钮。

**第四步：保留可交接证据，再重新交审。** 每个场景使用独立目录保存截图、交互、console／响应原始结果；统一放入 `.git/validation-evidence/<新实现完整SHA>/<run-id>/`，保留脱敏和恢复核对。先跑聚焦反馈，修正稳定后执行本 Task 原定的最终候选门槛，记录准确命令、退出码、耗时、计数、输入及部署产物身份；更新完成报告和真实新实现 SHA，交回 `READY FOR B REVIEW`。历史缺失日志如实标记，不补造。B 审查 PASS 前不进入 Slice Final。

### B 独立验证与证据

本机证据根目录：`.git/validation-evidence/dac695e45f8619b6ebcc24327e515fd9413240a1/b-review-20261016/`，索引 `INDEX.md`。该目录仅本机可读，未推送。

- 配置／注册／页面聚焦：18 passed、0 failed、0 skipped，原始 `focused.log`、`b-focused.trx`；验收工具守卫：7 passed、0 failed，`python-focused.log`。这些通过不证明上述遗漏旅程。
- 真实浏览器独立边界：`boundaries.json`、`boundaries.log`、控制脚本及三张独立截图，复现 FR-U1／U2；FR-U1 为真实页面的受控读取／截获保存，FR-U2 为真实服务器提交后的传输失败，不冒充物理磁盘故障。配置文件与有效值恢复均核对一致，触发器恢复并重启验证。
- 指定浏览器入口首次因 shell PATH 缺 Node 未执行交互，退出 1，保留 `configuration-integration.log`；补入已安装 Node 的 PATH 后重跑仍退出 1：load 场景通过，save_valid 捕获 `t.scrollHandler is not a function` 和 `Invalid language tag: en-us@posix` 页面错误，见 `configuration-integration-retry.log`。错误来源尚未判定，不据此另宣称产品回归，也不忽略异常标 PASS；两次实例配置／触发器均恢复成功。修正交审须提供可复现的工具／locale 环境及匹配门槛结果。
- 未独立重跑完整 restore／build／C#／format／Python／默认播放／完整批量套件；已有 P1，且本候选完整证据不满足复用规则，均不作为本轮 PASS。修正后的候选仍须通过原计划全部门槛。未执行 Slice Final 或 A Final Review。

### Slice 停止规则核对

Task 3.1 已接受的 RO-1～RO-6 核心事实和审查快照保留；本次变更未重做这些核心行为。RO-7、RO-2 的范围页面及配置交互／证据 Surface 尚不满足，AC-U3／U4 已有反例，U1／U2／U5／U6 的完整证据仍缺。不创建新 Task，不提交 Closure Packet，不改变 Slice／Roadmap／稳定需求，也不宣布 Slice 关闭。Developer 在同一 Task 修正并重新交审；PASS 后 B 再核对全部 RO／Surfaces，满足才执行完整 Slice Final 并提交 A。

供 Slice 收尾评估的一条经验候选：请求失败被误当作服务端回滚 → 用“服务端已提交、客户端丢失响应”的传输控制核对有效值与反馈 → 适用于配置保存等有持久化副作用的页面审查；不是新增验收或经验条数门槛。

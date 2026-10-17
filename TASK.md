# Task 4.1 — 单版本安装包与完整安装恢复旅程

必读：[Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。原计划由用户明确授权 A 规划，后续 B 根据固定方案规划并独立审查；当前为 B 审查后的同 Task 修正交接，具体决定见文末。

```text
Task ID: 4.1
Parent Slice: 4
Status: FIX REQUIRED
Task Base: ae265d0dba02aa1c5599871602d4350072b7155f
Contract Checkpoint: ae265d0dba02aa1c5599871602d4350072b7155f
Difficulty: High
Test Level: T4
Planner / Reviewer: A (user-authorized planning) / B (independent Task Review)
Implementation Head: c1fb5ee57272f158c2ea7abd7545980d1f11337d
```

## Goal

完成 Slice 4 RO-1 的单版本交付：管理员取得固定 Jellyfin 12.2.0／Linux x64 ZIP，按说明在干净实例安装、配置、播放、运行原生任务并重启；替换已接受 Slice 3 测试安装时保留配置／可信指纹，禁用／移除后恢复原生，重新安装／启用后继续检查。对应 AC-1／AC-2 和 AC-8 的包、身份、恢复部分。MP4／MKV 与原生 Web 实际播放在本 Task 交付。

## 真实准入与缺口

- 初始 `main` 工作区干净；已提交合同及 Roadmap 均 ACTIVE，Task 规划前治理 PASS。上方 Base 是先行提交固定方案后的真实完整 SHA；Slice Base `03169b07d110964562f7da31d2c3d7add82e5ff5` 保持不变，后续报告／计划不移动 Task Base。
- 已核对现有 `.sln`、产品 `.csproj`、`Plugin.cs`、`Packaging/meta.json`、开发环境工具及三个实机入口。产品固定 net10.0、SDK 10.0.401、Jellyfin Controller／Model 12.2.0；已有 SQLite 托管依赖和 `libe_sqlite3.so` 的开发部署路径，但没有经过验收的发布 ZIP／安装入口。
- `scripts/run_isolated_plugin_integration.py:deploy_plugin()` 从本地 bin／Release 复制 DLL／deps／native 文件；批量和配置页入口也调用它。因此直接执行这些工具不能证明只从 ZIP 安装，必须显式区分开发部署和归档消费。
- `Packaging/meta.json` 与 `Plugin.Description` 仍描述原型；GUID 为 `b061643e-d17d-4c6e-8ba2-6b57e286bd20`，当前程序集／元数据版本 0.1.0.0，targetAbi 12.2.0.0。修订说明时不能夸大尚未验证的大库、代理或跨版本支持。
- 现有 `development_environment.py` 的 WORK、project、端口和集成脚本的配置／指纹路径固定指向共享隔离实例，不能仅改一个端口就宣称新实例独立。安装验收需要明确独立的 config／cache／媒体／STRM／状态路径、project、网络与本机端口，写操作前核验归属。
- SDK 与现有隔离容器可用是此前只读观察；已有 Playwright 包不证明当前 Node／Chromium 可执行链可用。开工重新核对并准备仓库内固定测试依赖；本次尚未安装、部署或运行产品验收。

## 实施范围

### 可重复打包与负载验证

交付一个仓库内本地打包入口，从固定 Release 输出／锁定依赖建立 Linux x64 ZIP、完整文件／依赖／适用许可清单、每文件及归档 SHA-256、真实源码／构建输入身份。默认产物路径约定为 `artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，旁置摘要／清单；内部版本来自一致的程序集和元数据，允许沿用 0.1.0.0，不为本 Task 修改 GUID 或 schema。

包含插件 DLL／需要的 deps 信息、实际 SQLite 托管与 Linux x64 native 负载，按真实运行验证解析路径；不机械打包整个 bin、不夹带 Jellyfin 核心 DLL、其他平台 runtime、FFmpeg、SDK、源码／测试、运行状态或凭据。已存在的原生运行时由 Jellyfin 提供。缺 native／必需依赖、元数据冲突、负载摘要不符、非法归档路径或符号链接须在部署前明确拒绝，不能覆盖旧有效安装后再报错。

按实际元数据和已验证能力更新原型描述、安装／支持／备份与恢复说明。可增加构建／打包属性及相关测试；不引入自动更新／上架系统，不宣称 ZIP 已公开发布或支持其他版本／平台。

### 仅消费 ZIP 的真实隔离验收

新增专用包验收入口，复用已固定镜像、归属检查和无部署副作用的现有 API／断言；仅为本 Task 增加必要的实例参数／小型共用函数，不建立通用环境框架。安装服务器容器无源码、SDK、NuGet、bin／obj 挂载；初始插件目录为空，插件负载完全来自待测 ZIP。测试宿主可构建基线、准备合成媒体和浏览器，不能借此补给待测插件依赖。

分别覆盖干净安装和已有安装替换：升级起点使用 Slice 3 接受实现 `7c64eb5dcad6e5f20fb7eb41819be2521f65484d` 的可核验构建／负载，在专用实例准备有效配置、可信指纹和未完成变化。若需重建旧基线，隔离获取该提交并使用固定 SDK／锁及原 SourceRevisionId，记录实际摘要；不修改主工作区、不把新候选复制一份冒充旧版本。旧基线准备与候选安装分阶段记录，候选安装阶段仅使用 ZIP。

通过真实页面和原生入口完成五项配置加载／保存／生效提示、原生任务唯一／无默认触发、手动检查、MP4／MKV 原生 Web 实际播放、URL 变化后的最新地址／主流／指纹及重启、替换后未变复用和未完成变化重试。现有完整回归保护定时、共享、停止和失败语义；本 Task 不重建扫描／大库／代理场景。

按说明验证禁用、移除插件负载后的原生播放及重装／启用恢复；配置／SQLite 备份与保留可核对，不删除媒体库或自动删状态库。所有部署、移除、重启和清理仅限核验归属后的专用验收实例；不能触碰宿主生产 Jellyfin 或无关服务。后续若在现有共享隔离实例运行旧回归，独立记录前后输入及恢复，串行执行。

### 实施边界与必要修复

主要涉及 `scripts/` 打包／包验收／必要测试环境与浏览器入口、`dev/` 专用隔离配置、产品 Packaging／描述／必要构建属性、相应 Python／C# 测试、安装与支持文档。允许修复直接阻止本 Task 必要结果、且保持合同的真实缺陷，记录触发、范围和 T4 证据；不为目录整齐或未来功能重构。

决策、权限、取消、Coordinator、指纹 schema／提交和原生保存关联以已接受行为为基线，不新增规则或状态。若发现必须改变义务／接入成功边界或当前范围验收含义，停止依赖该变化的实施，先交 A 修订合同、B 重判合法性；不能以打包修复名义扩张。

开工时附资源／SDK／浏览器可用性和真实代理来源缺失清单，供 4.3／4.4 后续 B 计划使用。这里只读摸底，不实施代理或十万夹具；代理尚未固定不妨碍本 Task 对 RO-1 独立验收。

## 验收条件

- [ ] AC-1：一个命令产出可交接 ZIP 与清单／摘要，GUID／版本／ABI／来源／依赖／许可准确；负载满足最小 Linux x64 运行需求，无秘密、数据或无关核心库。缺失／损坏／非法路径包在部署前拒绝，保留已有有效文件。
- [ ] AC-1：新建干净专用隔离实例，仅解包安装候选后插件 Active；进程加载负载摘要匹配 ZIP，未调用开发部署补文件，正常完成原生 SQLite 创建／读写／重启恢复。
- [ ] AC-1：真实 HTML 配置页五项操作与错误反馈、生效时机正确；仅一个原生任务且默认无触发，手动任务可运行并报告真实进度／结果。首次已有主流信任和未变复查零插件探测，信任不计成功探测。
- [ ] AC-1：MP4／MKV 在原生 Web 客户端实际播放，记录所测封装／codec、原生播放路径和媒体时间／视频帧推进证据，不只看 HTTP 200。同 SHA-1／Size 换 URL 后实际探测，最新地址／主流／指纹一致，重启仍正确。
- [ ] AC-2：从上述 Slice 3 接受构建替换安装，配置和可信指纹保留，未变复用，待处理变化可重试；不假造旧版本／旧数据。备份／恢复、禁用／移除／重装／启用按交付说明可操作，原生播放与恢复检查正确。
- [ ] AC-8 对应部分：清单、部署文件、源码／构建及测试身份可核验；必要负向用例、全部既有回归／实机和本 Task 包验收通过，失败和重跑保留。专用实例／原共享隔离实例的配置、全部触发器、媒体／STRM、库条目和恢复／清理有记录。
- [ ] 支持声明限定固定组合及实测格式／客户端，README／安装说明／兼容性／矩阵按真实结果同步；RO-2／RO-3／RO-4 保持未完成，既有安全及隐私边界不变。

## 必要测试

Test Level 为 High／T4：本 Task 跨打包依赖、全新启动接入、SQLite、配置／升级恢复和真实播放。开发反馈先聚焦新工具和安装失败，最终候选保留完整门槛；本轮只规划，所有产品测试结果均 NOT RUN。

### 开发／修正反馈

开发反馈命令，从仓库根运行（含本 Task 待新增的工具测试）：

```bash
python3 -m unittest discover -s tests -p 'test_*package*.py' -v
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~ConfigurationTests|FullyQualifiedName~ConfigurationPageTests'
```

第一条对应本 Task 待新增的工具测试，当前尚无这些文件、不是已执行证据；实现后必须列出实际发现／执行数，零测试不能通过。第二条用于产品配置／页面／描述或相关构建变更的反馈；完整最终 C# 已覆盖时不重复。尚未 restore 时先 locked restore／build。

新增工具测试聚焦实际风险：负载最小完整性、缺 native／依赖／元数据不一致／摘要损坏拒绝、归档路径越界／符号链接、拒绝外部实例／目录和失败不覆盖旧文件、候选包摘要与安装负载一致、恢复失败不能输出 PASS。可复用或补充现有环境／配置工具测试，不写镜像实现的空断言。

以下是本 Task 必须交付的 CLI 约定，当前脚本未实现，状态 NOT RUN；不是已存在的工具或产品通过证据：

```bash
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all
```

包验收入口应另支持 `--scenario clean`／`upgrade`／`recovery`／`invalid` 作为开发反馈；`all` 覆盖全部且保留失败／恢复结果。B 若根据实际工具设计调整接口，先在同一 Task 计划记录新准确命令和等价覆盖，不删验收。

### 最终检查点门槛

先处理已知失败，再对准备提交的最终候选从 `/opt/jf-strm-probe` 执行：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py --scenario suite
python3 scripts/run_isolated_configuration_integration.py --scenario all
python3 scripts/check_governance.py
git diff --check
```

另检查全部维护 Markdown 的本地文件／锚点与 CURRENT／TARGET，不改变 V4.3 原文／稳定需求。新增两条脚本仍是待实现门槛；不能因其当前不存在改写为 PASS。包验收和三个既有实机入口串行执行、分别索引；后者开发部署不计入 ZIP 安装证明。全套 C#／Python 已覆盖聚焦测试时记录覆盖关系。

### B 独立验证

B 审查完整 `ae265d0dba02aa1c5599871602d4350072b7155f..Implementation Head`，核验新增依赖和实际包清单／归档／部署摘要，阅读原始安装、浏览器、SQLite、升级／重启、移除／原生恢复和既有实机日志，不能只读完成报告。

独立使用同一已记录候选 ZIP 复现：干净实例只从归档启动与主流／播放、缺 native 或摘要损坏部署前拒绝且不损伤有效安装、Slice 3 基线替换保留配置／可信指纹、禁用／移除／重装恢复。至少核验一次实际 Web 媒体推进及变化地址重启，不允许调用开发部署弥补负载。独立运行如已完整覆盖 `all` 则不再机械逐场景重复。

其余完整回归／实机可在核对源码、锁、工具、运行配置／夹具和包／负载身份完全匹配、阅读原始产物后明确复用；证据缺失／不匹配时重跑对应门槛。B 的独立审查不由实施者代签，也不代替 A 最终 Slice 审查。

### 证据与重跑规则

每个候选在 `.git/validation-evidence/<source-sha>/<run-id>/INDEX.md` 或稳定 CI 产物保留完整输入／源码 SHA、工作区准确差异、SDK／锁／镜像／Node／Playwright／Chromium、基线来源与产物、配置／夹具、精确命令／cwd／退出／耗时／计数、原始日志／浏览器交互、包／文件／部署 SHA-256、配置／指纹保护和恢复结果。私有凭据不进入索引或归档，对外地址仅记录脱敏身份。

构建候选和打包负载身份可核验后才执行安装验收；源码／工具／锁／元数据／配置／夹具变化后，重新生成包并重跑相应最终门槛。T4 可执行输入变更仍需全套指定门槛；纯报告后继提交核对输入、重跑消费文档的治理／链接，不虚构新实机。保留首败与所有重跑；环境／依赖不足标 BLOCKED／NOT RUN，不用零测试、skip、放宽超时或人工补文件制造 PASS。

## 非目标与剩余 Slice 工作

- 4.2 的完整扫描重叠／有限扰动收敛、4.3 的真实十万库与成本、4.4 的实际 JellyfinProxy／OpenList 专有行为，本 Task 不提前宣称通过；只读依赖摸底不是这些结果的验收。
- 不发布／推送／上架、不开发生成器、远程哈希、OpenList 元数据 API、代理／缓存改造、独立调度／按钮／状态机或跨平台支持。
- 不改变决策／权限／取消规则、并发生效语义、媒体源身份、schema／指纹门槛或不相关产品结构；不改生产媒体／生产运行实例及其他服务。

## Developer Completion Report

- Changed Files：`scripts/package_plugin.py`、`scripts/package_environment.py`、`scripts/run_isolated_package_integration.py`、`scripts/package_playback_driver.mjs`（新增）；`scripts/run_isolated_plugin_integration.py`、`dev/compose.yaml`、`src/.../Jellyfin.Plugin.StrmProbeOptimizer.csproj`、`src/.../Packaging/meta.json`、`src/.../Plugin.cs`、`src/.../packages.lock.json`、`tests/test_package_plugin.py`、`tests/test_isolated_package_integration.py`、`docs/package-installation.md`（新增）；后续文档提交更新 README 与 CURRENT 事实指针。
- Implemented：
  - 打包：`package_plugin.py` 从 `dotnet publish`（Release／linux-x64／framework-dependent）与已锁依赖构造最小负载（插件程序集、deps、托管与 linux-x64 native SQLite、`meta.json`、`THIRD-PARTY-NOTICES.txt`），写确定性 ZIP 及清单／SHA-256，并独立验证归档（单顶层目录、GUID／ABI、汇编白名单、native 声明、拒绝越界路径与符号链接）。
  - 隔离实例：`package_environment.py` 自建 Compose project（`jf-strm-probe-package-*`）、端口 `18097`、工作区 `artifacts/package-env`，服务器容器仅挂载 config／cache／strm／media，不挂源码／SDK／NuGet／bin；用固定 Jellyfin 镜像的 FFmpeg 生成 MP4／MKV 合成媒体；向导／库／凭证自建。
  - 包验收：`run_isolated_package_integration.py` 仅消费归档，覆盖 clean（首次信任／未变／换 URL／重启／配置页／原生任务／MP4／MKV 原生 Web 播放）、upgrade（从 Slice 3 接受提交 `7c64eb5d…` 构建替换，保留配置与指纹并重检）、recovery（禁用／移除／重装）、invalid（损坏／缺 native／GUID／ABI／越界／符号链接拒绝且不损伤有效安装）。
  - 元数据／描述与 `RuntimeIdentifiers`（`linux-x64`，使 locked restore 与 RID publish 一致，并新增 `net10.0/linux-x64` 锁段）。
- Tests and Results：
  - `bash scripts/dotnet-local restore … --locked-mode` PASS；`build --configuration Release --no-restore` 0 警告／0 错误；`test` 202/202 PASS；`format --verify-no-changes` PASS。
  - `python3 -m unittest discover -s tests -v` 92/92 PASS（原 63 项加本 Task 29 项工具回归）。
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases --source-revision 4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2` PASS；归档 SHA-256 `643c02082a19e94f122fa3a3675ccd96c2a818de52f16f1a9354db068dadfaf0`，来源 SHA `4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2`。
  - `python3 scripts/run_isolated_package_integration.py --package … --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all` PASS（clean／upgrade／recovery／invalid 均通过；MP4／MKV 视频时间与解码画面推进；负向包在部署前拒绝且有效安装保留）。
  - 既有隔离回归：`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` PASS。二者恢复与清理均验证。`run_isolated_configuration_integration.py --scenario all` 首次运行在 `reload_after_restart` 因 Jellyfin Web 客户端 `hometab` 无害噪声被现有分类器误判而 FAIL，三次立即重跑均完整 19 场景 PASS；该脚本与 Task Base 字节一致，非本 Task 引入，如实保留首败与重跑，交 B 判断。
  - 原始证据索引：`.git/validation-evidence/4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2/dev-final-1/INDEX.md`（最终候选，仅本工作区可读）；早期候选 `492b37da…`／`6574122b…` 的证据集均已标 SUPERSEDED，因后续可执行输入变化。
- Decisions：
  - 归档采用框架依赖发布布局（托管 DLL 置根、native SQLite 置根并显式列入白名单／deps），已在隔离实例实证加载与 SQLite 读写；不夹带 Jellyfin 核心库或另一套 FFmpeg。
  - 包实例使用独立 project／端口／工作区；为让 `JellyfinApi` 支持包实例凭证，给基类构造器增加可选 `credentials_path`（默认不变）。
  - 首次信任前置改为在插件禁用下由 Jellyfin 原生播放建立主流；库扫描本身不探测 STRM 内容。
  - `verify_archive` 以内容哈希比较部署负载，仅对 Jellyfin 会重写的 `meta.json` 按身份字段比较。
  - HLS.js 非致命告警按 Jellyfin 自有 bundle 与 `Fatal: false` 精确白名单，致命或其他来源错误仍失败。
- Remaining In-Slice Work：RO-2（真实十万库／成本）、RO-3（完整扫描重叠）、RO-4（实际 JellyfinProxy）及最终独立 Slice Final。
- Risks / Deviations：浏览器执行链依赖仓库内固定 Playwright／Chromium（已在包实例实测）；升级基线需隔离 worktree 重建（本次实际使用 `7c64eb5d…`，记录了其发布文件摘要）；真实代理来源与十万库资源仍是后续 Task 风险，不在本 Task 扩大。
- Head SHA：`4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2`（功能检查点 `492b37da25222a7dd1f7071d27c84cbb3f65825d`；本报告在后续文档提交记录，不预填自身 SHA）。

### Developer 修正报告（2026-10-17，BR-41-1～4）

- 修正提交：`c1fb5ee57272f158c2ea7abd7545980d1f11337d`（`fix: enforce package integrity, ownership and real upgrade/restore acceptance`），在 Task Base `ae265d0d…` 之后追加，未改写已审查历史。
- Changed Files：`scripts/package_plugin.py`、`scripts/package_environment.py`、`scripts/run_isolated_package_integration.py`、`tests/test_package_plugin.py`、`tests/test_isolated_package_integration.py`、`docs/package-installation.md`。未改产品决策／权限／取消／Coordinator／SQLite schema／指纹门槛。
- BR-41-1：`verify_archive` 现与已发布旁置清单比对归档 SHA-256 及每个负载文件摘要，并校验依赖完整性、meta／deps 版本一致、汇编白名单与实际 `AssemblyVersion`（从 CLI 元数据读取）、允许负载集合与固定 ABI；`--verify` 与 `deploy_archive`／`unpack_archive` 默认读取同名 `.manifest.json`，缺清单或任何不符即在部署前拒绝。B 的四类反例与缺清单均被拒且不损伤有效安装；结构检查与摘要比较相互独立（缺托管依赖／版本冲突／额外核心库由结构检查独立拒绝，`changed_native_payload` 由摘要拒绝）。
- BR-41-2：`scenario_upgrade` 新增一个未变项目（替换后零探测复用）与一个待处理变化项目；新增真实恢复：停止服务器 → 备份配置／指纹 → 通过正常 API 改动配置 → 再停止 → 恢复备份 → 重启 → 读回核对配置、指纹与播放；新增恢复失败拒绝控制（缺失备份目录）。复制文件不再被当作恢复 PASS。
- BR-41-3：`package_environment.require_owned_path` 在部署、基线、备份、恢复、移除与清理的所有写入口前校验路径与父链归属及符号链接；`config/plugins` 为符号链接或目标逃出工作区即拒绝，外部 sentinel 保持原样；Docker 归属查询非零退出即停止。`main()` 的 finally 记录前后配置／指纹／媒体／STRM 对账，`--cleanup` 仅删除确认本轮所有的输入，收尾失败使总体失败。
- BR-41-4：打包把 `SourceRevisionId` 显式传给 `publish`，并在发布后从程序集读回构建标识核对；`--source-revision` 现要求为真实可达且等于当前 HEAD 的提交，拒绝全零／虚构 SHA；清单记录锁文件摘要、构建输入摘要与准确构建命令。两次独立 publish 产出同一 DLL 摘要，与清单条目一致。
- Tests and Results（候选 `c1fb5ee5…`，工作区干净）：restore PASS；build 0 警告／0 错误；`dotnet test` 202/202 PASS；format PASS；`python3 -m unittest discover -s tests -v` 106/106 PASS；`package_plugin.py` 产出 ZIP SHA-256 `1a8b32c58b4dfabac3fba4671fd5751b8ce3e6673d7b9922e7d5c1951e6ac1d5`；`run_isolated_package_integration.py --scenario all` PASS（clean／upgrade／recovery／invalid）；`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` 首败（见下）后重跑 PASS；`run_isolated_configuration_integration.py --scenario all` PASS；governance／`git diff --check`／Markdown 本地链接与锚点 PASS。
- 首败与重跑：batch 首次 FAIL `The current round must have exactly one Execute entry, found 42`；诊断为既有测试夹具的“一天内日志”秒过滤缺陷，`--tail 8000` 含前一日 `15:xx` 行（41 行）被计入当前 `00:27` 轮次；`run_isolated_batch_integration.py` 与产品源码与本 Task Base 及被审查实现头字节一致。重建隔离容器清除跨日日志后，同一字节一致脚本 PASS。两次结果均保留，交 B 判断。
- 证据索引：`.git/validation-evidence/fix-41/developer-20261017-01/INDEX.md`（本地可读）。
- Remaining In-Slice Work：RO-2、RO-3、RO-4 与最终 Slice Final 未变，仍 NOT RUN。
- Head SHA：`c1fb5ee57272f158c2ea7abd7545980d1f11337d`（本报告在后续文档提交记录，不预填自身 SHA）。

## B Review Result

### 当前复审决定（2026-10-17，修正候选）

```text
Reviewed: ae265d0dba02aa1c5599871602d4350072b7155f..c1fb5ee57272f158c2ea7abd7545980d1f11337d
Correction Delta: 4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2..c1fb5ee57272f158c2ea7abd7545980d1f11337d
Review Start HEAD: cd45ea91663af315999cdc77bfab65dcde4ee7ed
Reviewer: B
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — RO-1 has the remaining blockers below; RO-2/3/4 remain NOT RUN
Next: Developer corrects the same Task 4.1; no Task 4.2 is activated
```

起始 `main` 工作区干净；完成必读、已提交合同／固定方案核对和治理 PASS。核对 Base..Head 的 25 文件范围、修正差异和后继报告；61 项源码／工具／测试／依赖／环境输入均与 `c1fb5ee5…` 字节一致，后继 `cd45ea91…` 仅修改 TASK。未修改产品实现、Slice、Roadmap 或稳定需求，未操作运行中的 Jellyfin／Docker。

读取 Developer 修正索引、包验收原始 JSON、既有实机与构建／测试日志、批量首败及重跑。实际 ZIP SHA-256 为 `1a8b32c58b4dfabac3fba4671fd5751b8ce3e6673d7b9922e7d5c1951e6ac1d5`；旁置清单及 DLL 嵌入的构建 revision 均为修正提交。旧坏包四反例、外部 plugins 目录链接及虚构来源 SHA 的回归在 B 本机执行均拒绝，原有效安装保留；43/43 打包工具测试 PASS、0 失败／0 跳过，正确包 CLI 校验 PASS。BR-41-4 的来源传递／真实提交约束和本候选产物身份已有修正；BR-41-2 已增加未变复用及实际配置备份／恢复／重启步骤，保留 Developer 观察，不把它们冒充 B 独立实机通过。

B 在临时目录独立增加三项反例，确认以下原有义务仍未完成。原 ZIP 未改动；备份反例只覆盖临时外部 sentinel，清理反例的 Docker 调用被 mock；它们是工具边界证据，不能推导普通观影或标准安装已经损坏。反例脚本退出 0 表示缺陷复现，三项保护结果均为 FAIL。

| 当前 P1 阻塞 | 证据与必要修正 |
|---|---|
| **BR-41-1（剩余）— 主插件版本一致性仍未验证，AC-1／AC-8** | `scripts/package_plugin.py:442` 只比较目录与 meta；第 482 行在 deps 无 `assemblyVersion` 时跳过检查，而主插件 runtime 条目实际为 `{}`。把真实候选的目录和 meta 同时改为 `9.9.9.9`，保留 DLL 的 `0.1.0.0` 和 deps 的项目 `0.1.0`，结构校验及匹配重算清单的校验均接受。原发布清单仍会拒绝被改包，这不否定摘要修正；缺口在构建器本身同样消费的结构校验。应独立读取主插件实际 AssemblyVersion，核对 meta／目录／deps 项目版本（按 .NET 三段与四段版本明确归一化），不依赖可选字段；构建与消费共用检查，补“目录＋meta 同改”和“deps 项目版本冲突”负例。坏包在写出／替换有效安装前拒绝。 |
| **BR-41-3a（剩余）— 备份文件写入可越出隔离区，AC-8／不变量 11** | `scripts/package_environment.py:497` 只校验备份目录，随后第 507 行 `copy2` 跟随已有目标文件链接。临时 `WORK/backup/Jellyfin.Plugin.StrmProbeOptimizer.xml` 链接到 WORK 外 sentinel 时，`backup_state` 不拒绝，并把 sentinel 覆盖为配置内容。此外 `require_owned_path` 先 resolve 再检查父链，会漏掉指向 WORK 内其他目录的链接。应在任何写入前校验完整原始路径链及最终文件，不能只校验目录；核对已有部署／基线／备份／恢复／媒体与 STRM 写入口使用情况，补最终文件和父目录链接的拒绝／外部文件不变测试。只修现有小型归属检查，不建立通用环境框架。 |
| **BR-41-3b（剩余）— 收尾记录没有落实恢复／清理，AC-8** | `capture_instance_state` 未获取全部任务触发器／原生库条目；`reconcile_instance_state` 第 571 行无条件返回 RECORDED，`main` 不判断差异。Developer 原始结果顶层 PASS，但只记录新增 `Upgrade Unchanged.strm`、变化的指纹 DB，未给 cleanup／恢复结果。B 临时修改预存 STRM 后同样仅 RECORDED、不恢复；调用 `cleanup_instance`（mock stop）又删除了预存 STRM／配置等整个目录。目录在 WORK 内不足以证明内容属于本轮。应使用明确本轮归属的干净实例输入，或保存并恢复已有隔离输入；对全部触发器／库条目／配置／媒体／STRM 进行前后核对，成功与异常路径均核验收尾，仅清理本轮创建项，收尾失败必须总体 FAIL。可采用拒绝非本轮输入的简单前置约束，不能以可选 `--cleanup` 或一份差异列表代替必要结果。 |

本机证据：[B 复审索引](.git/validation-evidence/c1fb5ee57272f158c2ea7abd7545980d1f11337d/b-rereview-20261017/INDEX.md)，含输入摘要、审查起点快照、原始命令／输出、反例脚本及结果；仅本工作区可读。已发现明确 P1，按开发流程提前拒绝：B 独立包实机／Web／升级恢复、可复建发布及其余完整 T4 重跑本轮均 NOT RUN，未签发任何整体产品 PASS。下一候选仍须完整原计划及 B 独立实机门槛；原始运行可否复用需按输入及证据完整性再次判断。

批量首败 `found 42` 与后续 PASS 均保留；跨日日志过滤为既有工具限制，未据本轮结果另造产品阻塞，也不把首败改写为 PASS。下一轮长验收须按合同保留完整日期／会话关联，不能仅凭一段 PASS 标签或清空日志省略来源证据。

**合法性：同一 Task 4.1 继续修正。** 三项均为既定包版本／隔离／收尾义务，Contract 可满足，无需 A 改合同。保留 ID、Task Base、Goal、Scope、验收和 High／T4 全部门槛；追加修正提交，先复现／修正上述工具反例，再对最终候选重建 ZIP、运行原完整门槛并提交准确报告。不得借此修改播放规则、取消、Coordinator、SQLite schema 或推进 4.2～4.4。

重新核对四个 RO／全部 Surfaces：RO-1 的包版本及恢复清理 Surface 仍阻塞；RO-2 真实十万库／成本、RO-3 完整扫描重叠与 RO-4 实际代理均未完成。本轮不创建下一 Task、不运行 Slice Final、不提交 Closure Packet、不宣布 Slice 关闭。经验候选：文件写入的归属检查须覆盖最终目标及原始父链；收尾差异应与恢复／本轮归属断言联动。留待 A 收尾择要合并，不改角色经验文件或增加合同义务。

### 上轮审查及修正指导（历史，当前决定以上方复审为准）

```text
Reviewed: ae265d0dba02aa1c5599871602d4350072b7155f..4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2
Review Start HEAD: b48afd1dec64d958d354c496995e3d0d3a46306e
Reviewer: B
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — RO-1 has the blockers below; RO-2/3/4 remain NOT RUN
Next: Developer corrects Task 4.1; retain Task ID, Base, Goal, Scope, acceptance and T4 gates
```

### 审查范围、证据与合法性

2026-10-17，B 起始工作区干净，已完成必读、已提交合同／固定方案核对及治理检查。审查上述完整范围，核对 25 个改变文件及后继报告；61 项当前源码／工具／测试／依赖／环境输入与 Implementation Head 字节一致。没有修改 Slice、Roadmap、稳定需求或产品实现，也没有操作运行中实例。

读取 Developer 最终索引、包安装／升级／恢复原始 JSON、C#／Python 日志和配置页首败／三次重跑。候选 ZIP SHA-256 确为 `643c02082a19e94f122fa3a3675ccd96c2a818de52f16f1a9354db068dadfaf0`，当前归档／文件与旁置清单相符；已有干净安装、主流／指纹及 MP4／MKV Web 媒体推进的 Developer 观察保留。它们不足以证明下列缺失行为。

B 独立运行 `python3 -m unittest discover -s tests -p 'test_*package*.py' -v`：29/29 PASS、0 失败／0 跳过；另在临时目录对同一候选 ZIP 制造反例，四类非法包均被接受并替换临时有效安装，另复现一项外部目录写入。复现脚本退出 0 表示反例得到确认，五项预期保护均为 FAIL，不是产品 PASS。全部临时数据自动删除，未修改原候选包。

本机完整索引：[B Review INDEX](.git/validation-evidence/4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2/b-review-20261017/INDEX.md)，含复现脚本、原始结果、61 项输入摘要和审查起点合同／Task 快照；仅本工作区可读。已发现明确阻塞，本轮干净实机／升级／恢复的 B 独立运行及其余完整 T4 重跑均 NOT RUN，不据 Developer 标签签发 PASS。修正候选仍须原完整门槛和 B 独立实机验证。

### 上轮 Task 阻塞项（P1，修正进展见当前复审）

1. **BR-41-1 — 部署前校验没有落实包完整性合同（AC-1／AC-8）。** `scripts/package_plugin.py:verify_archive()` 重新计算摘要后直接返回，没有与已发布清单／预期摘要比对；托管依赖仅按可被修改的 `meta.json.assemblies` 查存在性，也不核对版本目录／程序集／元数据的一致性。B 保留原旁置清单，分别重写 native 为无效内容、删除 `Microsoft.Data.Sqlite.dll` 并从 assemblies 删除但保留 deps 声明、将 meta 版本改为 `9.9.9.9`、添加 `Jellyfin.Controller.dll`：四包均通过 `verify_archive`，随后 `unpack_archive` 覆盖临时有效安装。修正须在任何有效安装替换前核验可信预期摘要、完整依赖与允许的负载／元数据；补对应真实拒绝与旧文件保留测试，不能只测 ZIP 截断／CRC 或缺 native。若准确 CLI 需要显式 manifest／expected digest，由 B 先在本 Task 记录等价接口；不得删减验收。

2. **BR-41-2 — 升级与备份恢复缺少必要执行（AC-2）。** `scripts/run_isolated_package_integration.py:scenario_upgrade()` 只对有待处理 URL 变化的项目执行替换后检查，没有已接受且未变项目的零探测复用；第 567～572 行在服务器运行时复制配置／SQLite 后即返回 `backup_restore` 路径，没有按说明停止、备份、实际恢复、重启和读回核对，也没有恢复失败的拒绝测试。补齐这两条真实旅程，核对配置／可信指纹／原生主流和地址、未变零探测及待处理变化可重试；失败或缺失不能仍输出总体 PASS。保留当前已观察的替换与变化重试事实，不把复制文件解释为恢复已通过。

3. **BR-41-3 — 隔离写入与收尾边界未完成（AC-8／安全不变量 11）。** `scripts/package_environment.py:deploy_archive()` 不检查 `config/plugins` 的符号链接／实际归属，`unpack_archive()` 会沿该链接删除并替换目标。B 用两个临时目录模拟 owned／foreign，外部有效目录的 sentinel 被删除且写入候选负载。所有部署、基线、备份、移除／清理的必要写入口均须在写入前核验归属，外部路径失败保持原样，Docker 归属查询失败不能作为无容器继续；增加相应拒绝测试。另 `main()` 的 finally 仅保存／打印结果，包验收无自身配置／全部触发器／媒体／STRM／临时库条目的前后对账与恢复／清理结果；补成功及失败路径的可核验收尾，保留必要原始证据，只清理确认本轮所有的输入，不扩大为通用环境框架。

4. **BR-41-4 — 源码与构建身份无法按报告复建（AC-1／AC-8）。** 清单声明来源 `4bad6eb43e3b8bb87ce9df9bc0aa1adb952044f2`，归档 DLL 与 RID AssemblyInfo 实际嵌入 `d157e0ddbd5710c9036fff93123c5420316db056`；两提交可执行输入一致，B 不认定为混入不同产品代码，但当前未记录真实构建 revision／SourceRevisionId 的区别。`--source-revision` 也只校验字符串格式，独立调用接受不存在的全零 SHA，且未传给 publish／验证工作区内容；清单缺锁／构建输入摘要和准确构建命令。修正须关联真实可达源码、被测输入和实际构建标识，拒绝不匹配／虚构来源，记录锁／SDK／命令，证明固定输入及原 SourceRevisionId 下产物可复建；纯文档后继可按流程核验复用，不以改标签代替溯源。

以上均属于原 Task 安装／升级／恢复／身份／隔离义务，Contract 可以满足，**无需 A 改合同；当前 Task 继续同 ID／Base 修正**。修正追加提交，重建 ZIP，保留首败和全部重跑；T4 可执行输入变化后仍执行原指定全套，不重用本次旧候选的 PASS 替代新候选门槛。Developer 同步安装／支持／矩阵中的事实标签，未完成部分不能继续写成已验证。

配置回归首败原文定位到 Jellyfin Home 的 `hometab` 堆栈，原脚本与 Task Base 相同，三份后续完整输出为 PASS；本轮保留这组真实结果，不将首败改写为 PASS，也不据此另造当前 Task 阻塞或削减修正候选门槛。

### Developer 简单修复方案（2026-10-17，B 补充）

保持 Task 4.1 的 ID、Base、Goal、Scope、验收和 T4 门槛，按下表顺序修正。主要改现有打包／隔离验收脚本、对应测试和安装说明；复用已有原生 API、浏览器与证据入口。当前问题包含工具缺陷和验收缺口，尚未证明正常播放失败；不据此改播放决策、Coordinator、取消或 SQLite schema，不展开 4.2～4.4。

| 顺序 | 最小改法 | 完成判断 |
|---|---|---|
| 1．包校验（BR-41-1） | `--verify` 和包验收部署默认读取 ZIP 同目录、同名的 `.manifest.json`，比对归档及全部文件摘要；缺清单或不匹配即拒绝。补齐 deps 所需托管／native 文件、目录／meta／实际程序集版本、固定 ABI 及允许负载检查。打包内部先检查布局、写出清单，再用同一消费校验验证最终产物；全部校验和暂存完成后才替换有效安装。 | B 的四类异常包、缺清单／依赖和元数据冲突均在部署前拒绝，旧安装摘要不变；正确包通过。结构检查要独立于摘要比较验证，不能只靠摘要不符使所有负例通过。 |
| 2．隔离写入与收尾（BR-41-3） | 在现有 `package_environment.py` 加小型共用归属检查，覆盖部署、基线、备份、移除与清理的目标及父目录，拒绝逃出专用工作区的路径／符号链接；Docker 查询非零退出即停止。`finally` 记录并核对本轮配置／全部触发器／媒体／STRM／库条目，恢复原有输入、清理确认本轮创建的临时项，保留原始证据；收尾失败使总体失败。 | 临时目录中的外部 sentinel 保持原样；正常与失败运行都有收尾结果。符号链接反例是辅助函数的边界测试，不声称已证明标准 CLI 或普通观影会越界。不建立通用环境管理框架。 |
| 3．升级和恢复（BR-41-2） | 在真实 Slice 3 基线上准备一个未变项目、一个待处理变化项目；替换后分别检查零探测复用及变化重试。按说明停止服务器后备份配置／插件 SQLite，通过正常操作改变测试配置／指纹，再停止、恢复备份、重启并读回；补一项恢复失败控制。 | 原配置／可信指纹／地址／主流保留，未变零探测，变化只按需探测；实际恢复后的值与备份一致、播放／检查可用。复制出备份文件不能当作恢复 PASS，恢复失败不能输出总体 PASS。 |
| 4．构建身份（BR-41-4） | 发布候选从当前干净 HEAD 构建；`--source-revision` 若保留，本轮仅允许等于该完整 SHA。将同一 SHA 显式传给 publish 的 `SourceRevisionId`，清单记录它、SDK、锁文件／实际构建输入摘要与准确命令；固定输入再次构建比较产物摘要。 | 清单与实际 DLL 构建标识一致，虚构或不匹配 SHA 被拒绝；可复建。纯文档后继按流程核对输入并复用既有包，不为改报告重标产物来源。 |
| 5．安装说明与事实同步 | 修正 `docs/package-installation.md` 的摘要命令工作目录，并同步安装／支持／矩阵中的实测事实。该路径错误已在仓库根目录复现失败、归档目录复现成功，属同 Task 文档修正，不另开 Task。 | 从仓库根目录照抄说明即可校验正确包；未完成验证仍写 NOT RUN／待复审，保留旧失败。 |

B 在此明确以上默认清单读取行为；现有打包与包验收 CLI 参数不变，属于原完整性验收的落实，不增加发布签名、自动安装器或新的产品机制。以下校验接口目前已存在，但修正后的行为仍待实施／验证：

```bash
python3 scripts/package_plugin.py --verify artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip
(cd artifacts/releases && sha256sum -c Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip.sha256)
```

开发时先跑 `python3 -m unittest discover -s tests -p 'test_*package*.py' -v` 及相关 `invalid`／`upgrade`／`recovery` 场景，确认反例已修正、恢复已真正执行，再对最后修正候选重建包并执行上文“最终检查点门槛”全部命令；实机串行。准确测试数、包／部署摘要、原始失败与每次重跑、恢复／清理结果写入新证据索引。随后追加实现提交及完成报告，交为 READY FOR B REVIEW；B 独立复审后才决定 PASS。本轮仅补充指导，未实施修复、未运行新的产品验收，FIX REQUIRED 保持。

### Slice 重核与经验候选

RO-1／安装、升级恢复及包身份 Surfaces 未通过本次 B 审查；RO-2 的真实十万库／成本、RO-3 的完整扫描重叠、RO-4 的真实代理及相应 Surfaces 均未完成。固定交付方案的 Task 4.2 依赖 4.1 B PASS，本轮不创建下一 Task，不运行 Slice Final、不提交 Closure Packet、不宣布 Slice 关闭。

供 A 收尾时择要合并的经验：校验工具能列出新摘要不等于核验已发布输入 → 对重写 ZIP、依赖／元数据不一致构造反例并检查有效安装保留 → 用于包交接；恢复报告容易只证明备份文件存在 → 实际执行恢复／重启和业务读回，并记录失败收尾 → 用于升级与恢复审查。此处不改角色经验文件或增加验收义务。

NEXT ACTION: DEVELOPER CORRECTS TASK 4.1 (BR-41-1 REMAINDER / BR-41-3a / BR-41-3b)

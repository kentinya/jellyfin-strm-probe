# Task 4.1 — 单版本安装包与完整安装恢复旅程

必读：[Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。用户已明确授权本次直接规划 Task；后续 B 根据固定方案规划，独立审查责任保留。本轮仅提交计划，不启动实施。

```text
Task ID: 4.1
Parent Slice: 4
Status: READY FOR B REVIEW
Task Base: ae265d0dba02aa1c5599871602d4350072b7155f
Contract Checkpoint: ae265d0dba02aa1c5599871602d4350072b7155f
Difficulty: High
Test Level: T4
Planner / Reviewer: A (user-authorized planning) / B (independent Task Review)
Implementation Head: 6574122be9e2b931fa0acd5d7a6c389da7096c87
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
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases --source-revision 6574122be9e2b931fa0acd5d7a6c389da7096c87` PASS；归档 SHA-256 `15b4d570b6669b5555c1646c7fe959a0538f11fe72a88c5c95649b18eb5621c4`，来源 SHA `6574122be9e2b931fa0acd5d7a6c389da7096c87`。
  - `python3 scripts/run_isolated_package_integration.py --package … --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all` PASS（clean／upgrade／recovery／invalid 均通过；MP4／MKV 视频时间与解码画面推进；负向包在部署前拒绝且有效安装保留）。
  - 既有隔离回归：`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` PASS；`run_isolated_configuration_integration.py --scenario all` PASS。三者恢复与清理均验证。
  - 原始证据索引：`.git/validation-evidence/6574122be9e2b931fa0acd5d7a6c389da7096c87/dev-final-1/INDEX.md`（最终候选，仅本工作区可读）；早期候选 `492b37da25222a7dd1f7071d27c84cbb3f65825d` 的证据集已标 SUPERSEDED，因死代码清理改变可执行输入。
- Decisions：
  - 归档采用框架依赖发布布局（托管 DLL 置根、native SQLite 置根并显式列入白名单／deps），已在隔离实例实证加载与 SQLite 读写；不夹带 Jellyfin 核心库或另一套 FFmpeg。
  - 包实例使用独立 project／端口／工作区；为让 `JellyfinApi` 支持包实例凭证，给基类构造器增加可选 `credentials_path`（默认不变）。
  - 首次信任前置改为在插件禁用下由 Jellyfin 原生播放建立主流；库扫描本身不探测 STRM 内容。
  - `verify_archive` 以内容哈希比较部署负载，仅对 Jellyfin 会重写的 `meta.json` 按身份字段比较。
  - HLS.js 非致命告警按 Jellyfin 自有 bundle 与 `Fatal: false` 精确白名单，致命或其他来源错误仍失败。
- Remaining In-Slice Work：RO-2（真实十万库／成本）、RO-3（完整扫描重叠）、RO-4（实际 JellyfinProxy）及最终独立 Slice Final。
- Risks / Deviations：浏览器执行链依赖仓库内固定 Playwright／Chromium（已在包实例实测）；升级基线需隔离 worktree 重建（本次实际使用 `7c64eb5d…`，记录了其发布文件摘要）；真实代理来源与十万库资源仍是后续 Task 风险，不在本 Task 扩大。
- Head SHA：`6574122be9e2b931fa0acd5d7a6c389da7096c87`（功能检查点 `492b37da25222a7dd1f7071d27c84cbb3f65825d`；本报告在后续文档提交记录，不预填自身 SHA）。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO — RO-1 implemented and pending independent review; RO-2/3/4 await implementation/evidence
Next: B reviews Task 4.1 Base..Implementation Head and independently reproduces the key package behaviors
```

B PASS 后重核全部 RO；仍按固定方案进入 4.2 时才规划下一 Task。全部 RO 满足则单独 Slice Final 并形成 Closure Packet；不在此关闭 Slice。

NEXT ACTION: B REVIEWS TASK 4.1

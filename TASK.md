# Task 5.1 — 干净检出的 Python 3.11 质量回归与 CI 修复

受已提交的 [Slice 5](SLICE.md) 约束，以 [开发流程](docs/development-workflow.md) 为准。实施前阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 5.1
Parent Slice: 5
Status: FIX REQUIRED
Task Base: 2111e20488ba5afbf46cfe8af8782cf4a63379fb
Contract Checkpoint: 2111e20488ba5afbf46cfe8af8782cf4a63379fb
Difficulty: Medium
Test Level: T3
Planner / Reviewer: B
```

## Goal

完成 RO-4／AC-5 的质量反馈闭环：干净检出在 Python 3.11 下执行全部 Python 测试，修复 CI-F1～CI-F3，不依赖开发机忽略夹具／镜像锁／数据库或运行中的 Docker 服务，保留隔离及不可变锁拒绝规则；取得匹配修复候选的远端 Repository quality 成功结果。RO-1～RO-3 留待本 Task 通过后规划，不以 CI 绿灯宣称播放正确。

## 实际缺口与实施范围

规划前工作区干净，main 比 origin/main 超前三个文档提交；治理检查通过。HEAD 的 Slice 5／Roadmap 已提交为 ACTIVE，无活动 Task。默认 Python 为 3.13.5，PATH 未发现 python3.11，实施须先准备并记录真实 3.11 解释器及补丁版本，不以 3.13 代替。

| 缺口 | 真实代码及修复边界 |
|---|---|
| CI-F1 | `tests/test_isolated_batch_integration.py::BatchScriptGuardTests.test_temporary_fixture_refuses_to_overwrite_and_writes_a_versioned_manifest` 在真实 artifacts 目录先 unlink，再调用读取 `batch.FIXTURE` 的 `temporary_fixture`。改为临时目录自备源并注入路径，保留版本、URL、字段及拒绝覆盖断言；不得删写开发夹具。 |
| CI-F2 | `tests/test_isolated_package_integration.py::PackageEnvironmentTests.test_compose_uses_a_separate_project_port_and_no_source_mount` 只替换 WORK，`write_compose` 仍读取真实镜像锁。提供合法确定性临时锁或注入加载边界，保留专用端口／项目、内部网络及无源码挂载断言；真实缺锁、可变 tag、错误仓库／spec 仍拒绝。 |
| CI-F3 | `tests/test_isolated_large_library_integration.py::PreparedLibraryReuseTests.test_reuse_full_scenario_verifies_copy_and_delegates_without_rebuilding` 有 21 个同层 with 上下文，触及 3.11 静态嵌套限制；相邻非空指纹拒绝用例也须检查。用 ExitStack 等保持全部 patch 生命周期、调用及断言，不删用例或仅升级 Python。 |

主要修改限这三个测试文件，必要时小改 `.github/workflows/quality.yml` 的语法覆盖；工作流已固定 3.11，不要求形式性修改。只在无法隔离现有边界时，才可对 `scripts/run_isolated_batch_integration.py`、`scripts/package_environment.py` 作最小可测性调整，记录理由，不改变部署、归属、锁验证或探测行为。T3 因跨工具导入／共享模块／隔离保护；全 Python discovery 用于检验模块间 patch 泄漏和导入次序，三个聚焦函数不能代替。

## 验收条件

- [x] 在独立干净 Base 检出和真实 Python 3.11 下保留三处原失败，区分历史远端 FAIL 与本轮复现；未复现则报告差异，不虚填。（Developer 原始日志保留；B 另在独立干净 Base 经既有入口复现全部三处。）
- [x] 修复保持原行为和拒绝条件，输入／清理仅限测试自备临时目录，不触碰现存 artifacts、1004 项准备库或用户文件。（B 已审查真实差异并通过干净候选全量核验，现存准备库未操作。）
- [x] 干净候选完整 Python discovery 无 error／failure，记录发现数、执行数及所有 skip 原因；两个现有发布归档缺失 skip 单列、不计 PASS，不新增 skip 掩盖失败。（B 独立新跑：264 项、262 通过、2 个既有发布归档缺失 skip，无失败／错误；skip 不计 PASS。）
- [x] 全 scripts／tests Python 语法、治理、差异检查通过；完整 C# 门槛由 B 承担或核验匹配证据，不交回 Developer。（B 已完成 Python 静态检查及 C# locked restore／Release build／202 项测试／format；首次 format 预算中止与补跑通过分别保留。）
- [x] 不需要启动 Jellyfin／容器／数据库、拉镜像或读取本地凭据，原生锁及隔离保护仍有效。（B 全量含 Compose CLI config 解析，无需 Docker 服务／容器／镜像拉取／凭据；Developer 关于未运行 CLI 子检查的说法见下方纠正。）
- [ ] 匹配候选远端 Repository quality 必要步骤全部成功；未获发布授权或没有远端结果时记 BLOCKED／NOT RUN，不能签 Task PASS。（BLOCKED / NOT RUN：本轮未推送、未触发 workflow。）
- [x] Developer 提交真实实现 SHA、聚焦证据及省略项；B 审查完整 Task Base..Head，不修改 Slice 合同或插件成功判定。（B 已审查完整 Base..`2291ee2` 与报告后继 `a23037c`。）

## 必要测试

### 开发／修正反馈（Developer）

从检出根目录执行；python3.11 须为经版本核验的真实解释器，若用绝对路径，报告逐字记录实际命令。

```bash
python3.11 --version
python3.11 -m unittest discover -s tests -p test_isolated_batch_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_package_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_large_library_integration.py -v
python3.11 -m py_compile tests/test_isolated_batch_integration.py tests/test_isolated_package_integration.py tests/test_isolated_large_library_integration.py
python3 scripts/check_governance.py
git diff --check
```

先在新的干净 Base 检出运行对应命令保留首败，不在带开发夹具的主工作区运行旧 F1。新增／修改测试随上述模块执行；若改到许可工具，补其直接受影响模块并说明覆盖。Developer 只运行受影响验证，报告完整 Python／C#、远端及实机未运行项。

### 最终检查点门槛（B）

B 固定 Developer 已提交的完整实现 SHA，另建隔离干净检出，记录 tree、无用户改动及无忽略产物的起点，不清理当前工作区。只准备解释器和工具，不复制 artifacts／凭据／数据库。B 执行：

```bash
python3.11 --version
python3.11 scripts/check_governance.py
python3.11 -m unittest discover -s tests -v
python3.11 -m compileall -q scripts tests
git diff --check
git show --format= --check HEAD
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
```

C# 使用 SDK 10.0.401；B 可在固定候选主检出执行四项或核验匹配的完整原始证据，不能改为 Developer 必跑。完整 Python 已含聚焦模块，通过后不机械重跑。现有 `test_real_compose_config_is_isolated` 只调用 Docker Compose CLI 的 config 解析，不启动服务；记录 CLI 版本，不为测试拉镜像或启动服务。实际发现其他运行服务依赖时保留失败，在同 Task 修复隔离，不跳过模块。

远端步骤前先完成可审阅候选、本地门槛及索引。当前未授权新推送，本计划不自动 push、触发 workflow 或改远端；到该步骤再呈交准确候选和动作。授权后核验 push／PR 原生触发的 Repository quality 的 head SHA、工作流、Python 版本和每步日志，不能借其他提交绿灯。远端欠项留在本 Task，不另造补 CI Task。

### B 独立验证

1. 审查固定 `2111e20488ba5afbf46cfe8af8782cf4a63379fb..Head` 的全部差异，包括断言、skip、patch 范围和额外文件；核验没有插件源码／依赖／成功判定变化。
2. 独立核验并按需复现 Base 三个真实失败入口，在干净候选运行完整 discovery／compileall；F1 核对不触碰开发夹具，F2 核对合法临时锁和真实缺锁／错误锁拒绝，F3 核对所有 patch 生效与恢复、完整委派及非空指纹拒绝断言。通过既有函数／测试入口复现，不臆造 HTTP 参数或不可达产品路径。
3. 本 Task 不改播放链，不运行播放矩阵或操作现存实例；包／扫描／1004 项实机不是本 Task 的新通过声明。必要改动若影响这些链路，先由 B 重评同 Task 测试计划；合同范围问题交 A，产品修复仍待用户决定。
4. 阅读匹配候选全量原始证据并承担欠缺门槛，不采信标签代替日志。远端欠项或当前 Task 阻塞给 FIX REQUIRED，修正继续同一 Task。

### 证据、预算与重跑规则

使用 `.git/validation-evidence/<完整源码SHA>/<run-id>/`，含 INDEX、源码／tree／候选、解释器／SDK／Compose、工作流／锁摘要、干净检出证明、逐条命令／退出码／计数／耗时、Base 首败与重跑；原始资料不上传，远端结果授权后补入。纯文档后继比较输入并重跑治理；可执行输入变化重取受影响结果，不复用失配证据，不机械重跑不相关 Final。

每轮从开始检查起记录实际总用时与测试累计时间，严格满足用户要求的测试占比小于 50%。失败／重试、构建／静态门槛和等待远端测试计入测试；重叠区间按墙钟并集计，同时保留逐命令耗时，不靠并发隐藏。初始上限：Developer 每轮总预算 30 分钟、测试 10 分钟；B 每轮总预算 40 分钟、测试 12 分钟，均不要求耗满。启动测试前用已实际发生的非测试工作量留足余量；实际比例仍须小于 50%，不能拿计划预算作分母。接近上限停止启动新测试，保留结果和余项，不空等凑比例、不降低门槛、不将未跑写 PASS；环境准备另记实耗。

## 非目标

不实施 RO-1～RO-3 播放夹具／浏览器矩阵，不改插件诊断或 returnedPrimaryMatchesProbe，不建新框架，不操作生产／现存实例／准备库，不验证 JellyfinProxy，不移动 Base、不改写历史或自动推送。后续播放 Task 须固定真实已有入口、音频支持、全部展开行和截图实际查看，不假造尚不存在的矩阵命令。

## Developer Completion Report

- Changed Files：`tests/test_isolated_batch_integration.py`、`tests/test_isolated_package_integration.py`、`tests/test_isolated_large_library_integration.py`（仅此三个；插件源码、`scripts/`、依赖、工作流与成功判定未改）。
- Implemented：CI-F1 改为在测试自备临时目录中写版本化 STRM 并注入 `ROOT`／`FIXTURE`，仍调用真实 `temporary_fixture`，保留版本／URL／字段及二次写入 `FileExistsError` 拒绝，并断言未在仓库 `artifacts/` 留下文件；CI-F2 从临时根目录注入确定性不可变镜像锁后调用 `write_compose`，保留专用端口／项目、内部网络与无源码挂载断言，新增 `test_compose_refuses_a_missing_mutable_or_foreign_image_lock` 保留缺锁／可变 tag／错误 spec／错误仓库的真实拒绝；CI-F3 将 21 项 patch 链与相邻非空指纹拒绝用例改为单个 `ExitStack`，patch 集合、顺序、生命周期与全部断言不变。`.github/workflows/quality.yml` 经评估后未改（改动会被既有治理测试拒绝，且非必需）。
- Tests and Results：真实 Python 3.11.10（`/opt/py311/python/bin/python3.11`，python-build-standalone 20241016 归档，自备解包；主机默认 3.13.5 未用于门槛）。干净 Base `2111e20` 复现三处原始失败（206 tests，3 errors，2 skips；F1 缺 `artifacts/dev-env/strm/Environment Fixture.strm`，F2 缺不可变镜像锁，F3 导入期 `SyntaxError: too many statically nested blocks`）。干净候选 `2291ee2`（无 `artifacts/`）：完整 discovery 264 tests `OK (skipped=2)` EXIT=0；聚焦三模块 24／31／58 全 OK；`py_compile`、`compileall scripts tests`、`check_governance.py` PASS、`git diff --check`、`git show --format= --check HEAD` 全部 EXIT=0。两个 skip 均为 `'the published release archive is not present'`（`test_package_plugin.PackageIntegrityTests` 两项），单列且不计 PASS，未新增 skip。证据：`.git/validation-evidence/2291ee21a989cc5c905fc945bd8936aaa23a2673/dev-implementation-20261021T0008Z/INDEX.md`。
- Decisions：F1 保留对真实写入函数的覆盖而非改测 `temporary_fixture_in`；F2 选择在测试侧注入临时 `ROOT` 与合法锁，未改 `load_image_lock`／`write_compose` 的产品边界，从而不触碰锁验证语义；F3 用 `ExitStack` 而非拆用例或升级解释器。未使用 Docker、容器、镜像拉取、数据库或本地凭据。
- Remaining In-Slice Work：RO-1～RO-3 全部（P01～P08 真实播放矩阵、ColorRange 返回主流误判回归）；RO-4 的远端 Repository quality 成功结果仍未取得。
- Risks / Deviations：Python 3.11 为自备 standalone 解释器（3.11.10），与 CI 的 `setup-python 3.11` 具体补丁版本可能不同，B 若要求精确对齐须自行确认；远端 workflow 未推送、未触发，记 BLOCKED / NOT RUN，不据此签 PASS；两个发布归档缺失 skip 未消除；未运行完整 C# 门禁、Docker Compose CLI `config` 子检查、任何 Jellyfin／容器／1004 项实机回归（按分工交 B）；本 Task 未改播放链与 `returnedPrimaryMatchesProbe`，产品误判仍待用户决定。
- Head SHA：`2291ee21a989cc5c905fc945bd8936aaa23a2673`（tree `1b9df66b8678753c1cf6d8faedf32011e16676df`）。
- Timing：本轮从 00:03:50Z 开始实现，候选提交 00:07:39Z，证据收尾至 00:08:34Z；测试累计约 60 秒（聚焦三模块 ≈1.7s、完整 discovery 主工作区 ≈10.5s、干净候选 ≈6.7s、Base 复现 ≈6.7s 及各模块），占本轮实际用时远低于 30%。

## B Review Result

```text
Reviewed: 2111e20488ba5afbf46cfe8af8782cf4a63379fb..2291ee21a989cc5c905fc945bd8936aaa23a2673
Report Checkpoint Reviewed: a23037cba585d14fde77d4a6dd5623ff81b25382
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: COMPLETE THE REMOTE REPOSITORY QUALITY GATE IN TASK 5.1 AFTER EXPLICIT PUBLICATION AUTHORIZATION
```

B 于 2026-10-21 独立审查完整 Task Base..实现候选及其报告后继；三个测试修复未发现需改代码的阻塞，插件、工具、依赖、工作流与成功判定未改。**当前阻塞 B5.1-1：缺少匹配候选的远端 Repository quality 成功结果（BLOCKED / NOT RUN）**。GitHub 只读查询实现 SHA 返回 422／No commit found，未推送或触发远端运行；本地通过不能代替 AC-5。保留同一 Task ID／Base／Goal／Scope，未获授权不推送、不开始下一 Task。

- B 新跑：独立干净 Base 通过既有 unittest 入口复现 F1／F2／F3 原失败；独立干净候选 Python 3.11.10 完整 discovery 共 264 项，262 通过、2 个既有发布归档缺失 skip（不计 PASS），无失败／错误；完整套件包含全部聚焦用例及真实 Compose CLI config，无需重复跑聚焦模块。compileall、治理、差异和提交空白检查通过。
- B 承担 C# 完整门禁：SDK 10.0.401 locked restore／Release build／202 项 C# 测试通过；format 首次因本轮测试预算中止（19.08 秒、EXIT=124），保留首次记录；相同命令补跑 27.30 秒、EXIT=0。未将全量交回 Developer。
- 归属：Python 干净候选为 `2291ee21a989cc5c905fc945bd8936aaa23a2673`；C# 在主检出 `a23037cba585d14fde77d4a6dd5623ff81b25382` 执行，已逐字节核对全部 69 个非 Markdown 跟踪输入与候选一致，后继仅改 Task 报告。Developer 原始证据仅作佐证，本轮全量和关键复现由 B 独立执行。Developer 报告所称未运行 Compose CLI 子检查需纠正：完整 discovery 实际已执行 `test_real_compose_config_is_isolated`；它仅解析配置，不启动服务。
- B 证据：`.git/validation-evidence/2291ee21a989cc5c905fc945bd8936aaa23a2673/b-review-20261021T0015Z/INDEX.md`，包含准确命令、退出码、耗时、首败、跳过、输入摘要、远端只读结果和收尾；只在本机可读，不上传原始资料。
- 时间：截至 00:20:26Z，本轮实际 307.13 秒、保守累计测试 88.15 秒（含 Base 失败、首次 format 中止、补跑及静态门槛），占 28.70%，低于 50%；无空等补时。两个本轮自建 worktree 已核验后移除，日志持续保留。
- 后续只补本 Task 的远端欠项：授权后普通推送可审阅 main 检查点到现有 origin，核验原生 push 触发的同 head workflow／Python／逐步骤日志。纯报告后继比较可执行输入并重跑治理后复用匹配全量，不机械重跑 Final。若远端失败，修正仍留在 Task 5.1。
- 全部 RO 尚未满足：RO-1～RO-3 真实播放矩阵／ColorRange 仍 NOT RUN，RO-4 尚缺远端门槛；不生成 Closure Packet，不返回 SLICE READY FOR A REVIEW，不自行关闭 Slice。本 Task 不操作现存 Jellyfin 或全部 1004 项准备库。

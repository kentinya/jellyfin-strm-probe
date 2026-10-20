# Task 5.1 — 干净检出的 Python 3.11 质量回归与 CI 修复

受已提交的 [Slice 5](SLICE.md) 约束，以 [开发流程](docs/development-workflow.md) 为准。实施前阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 5.1
Parent Slice: 5
Status: PLANNED
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

- [ ] 在独立干净 Base 检出和真实 Python 3.11 下保留三处原失败，区分历史远端 FAIL 与本轮复现；未复现则报告差异，不虚填。
- [ ] 修复保持原行为和拒绝条件，输入／清理仅限测试自备临时目录，不触碰现存 artifacts、1004 项准备库或用户文件。
- [ ] 干净候选完整 Python discovery 无 error／failure，记录发现数、执行数及所有 skip 原因；两个现有发布归档缺失 skip 单列、不计 PASS，不新增 skip 掩盖失败。
- [ ] 全 scripts／tests Python 语法、治理、差异检查通过；完整 C# 门槛由 B 承担或核验匹配证据，不交回 Developer。
- [ ] 不需要启动 Jellyfin／容器／数据库、拉镜像或读取本地凭据，原生锁及隔离保护仍有效。
- [ ] 匹配候选远端 Repository quality 必要步骤全部成功；未获发布授权或没有远端结果时记 BLOCKED／NOT RUN，不能签 Task PASS。
- [ ] Developer 提交真实实现 SHA、聚焦证据及省略项；B 审查完整 Task Base..Head，不修改 Slice 合同或插件成功判定。

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

- Changed Files：NOT SET。
- Implemented：NOT RUN。
- Tests and Results：NOT RUN；交接时补聚焦证据、首败／重跑、实际时间比例及省略项。
- Decisions：NOT SET。
- Remaining In-Slice Work：RO-1～RO-3 全部；RO-4 待本 Task 验收，远端须届时授权。
- Risks / Deviations：需准备 Python 3.11；远端未授权；产品误判不能借本 Task 修改。
- Head SHA：NOT SET。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER IMPLEMENTS TASK 5.1
```

当前仅规划，尚无实现候选，不签发产品 PASS／FIX REQUIRED。交回后 B 只给 PASS 或 FIX REQUIRED，修正沿用同一 Task；每次 PASS 重查所有 RO，全部满足后提交 Closure Packet 并返回 SLICE READY FOR A REVIEW，由 A 最终审查，B 不自行关闭。

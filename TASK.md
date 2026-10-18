# NO ACTIVE IMPLEMENTATION TASK

## Task 4.2 — 完整扫描与播放／批量并发下的正确性

本检查点保留 Task 4.2 的完整计划、历史审查和 B 补证 PASS；没有活动实施任务。下一步由 B 按已提交 Slice／固定方案规划 4.3，本轮不启动后续实施。

必读：[Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。本计划只细化已提交合同的 RO-3；4.1 已独立 PASS，审查原文保留于 `git show 0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`，不修改 Slice／Roadmap／稳定需求。

```text
Task ID: 4.2
Parent Slice: 4
Status: PASS
Task Base: 0e7b26b381ed5f71781e75d317275afa51d791e9
Contract Checkpoint: ae265d0dba02aa1c5599871602d4350072b7155f
Difficulty: High
Test Level: T4
Planner / Reviewer: B
Implementation Head: 86946cc4ef5c0648b71aafc00aa666f2a2bb20c5
```

## Goal

交付 Slice 4 RO-3：在最终 ZIP 安装的固定 Jellyfin 12.2.0／Linux x64 隔离实例中，完整原生库扫描与批量检查、播放的实际探测重叠。有限增删、移库、URL／内容变化与独立强制刷新不造成越范围探测、过期指纹或错误地址；扰动停止后下一轮重新查询并收敛，停止收尾、再运行及重启正确。对应 Slice AC-5、AC-6 和 AC-8 的扫描、共同控制及证据／恢复部分。

## 实际基线与缺口

- 规划前工作区干净，已读已提交合同、固定方案、真实实现／测试与 4.1 原始证据，治理 PASS。Slice Base 仍为 `03169b07d110964562f7da31d2c3d7add82e5ff5`。本 Task Base 是上一 Task 的 B PASS 检查点，不是旧实现或未来提交。
- 4.1 已提供 `package_plugin.py`、`package_environment.py`、`run_isolated_package_integration.py`：可重复最小 ZIP、独立实例、当前轮工作区归属、只从归档安装、页面／Web 播放／升级恢复。使用已有能力，不另建环境框架。实例写入及清理沿用“当前进程实际取得＋磁盘 token 一致”，旧非空工作区即使带旧标记也拒绝。
- `Services/BatchLibraryScope.cs` 的 `LibraryBatchCandidateSource` 已使用原生候选 ID 查询和当前范围的分批读取；`BatchCheckRunner` 每批上限 128、消费者最多 8。播放／批量已有共同 Coordinator、保存关联和条件指纹提交。保持这些机制及五字段 schema。
- 现有 `run_isolated_batch_integration.py` 覆盖多于一批的夹具、原生多版本、运行中增删、双向共享、停止和故障；但没有完整原生扫描 Running 区间与两入口实际执行相交的证据，不能当作 RO-3 已完成。
- `JellyfinApi.refresh_library()` 只提交 `/Library/Refresh`，不证明扫描已开始或结束。固定 Jellyfin 原生全库扫描任务 Key 为 `RefreshLibrary`，插件任务 Key 为 `StrmProbeOptimizerBatchCheck`；按 Key／本轮运行身份识别，不能依赖本地化名称。
- 旧实机入口会 `deploy_plugin()` 并使用共享开发路径；新扫描验收不能直接调用其 main／部署。旧日志辅助按日内时间筛选，不能拿来关联本次完整日期／容器／轮次。实际原生强制刷新、源读取和 PlaybackInfo API 可复用，涉及路径／实例的函数须显式接收当前上下文。
- RO-2 的十万真实库与分层成本、RO-4 的实际代理仍 NOT RUN；本 Task 不提前实施。4.1 的旧包 PASS 也不能替代本 Task 最后候选的包／扫描验收。

## 实施范围与简单实施顺序

按以下顺序完成一个完整行为，不按文件／字段另拆 Task。先得到可重复失败或缺口证据，再做必要产品修复。

### 1．复用隔离环境，建立扫描验收入口

新增 `scripts/run_isolated_scan_integration.py` 和相应 `tests/test_isolated_scan_integration.py`。只增加本行为需要的上下文／小型共用函数；复用 `package_environment` 的新工作区选择、镜像锁、Compose 归属检查、ZIP 校验／部署、鉴权、媒体准备、对账和清理。该入口只消费指定 ZIP，不调用开发部署、不在验收期间补 DLL 或重建包。

CLI 为本 Task **待实现接口，当前 NOT RUN**：

```bash
python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/scan-all
```

`--scenario overlap`／`stop`／`recovery` 可用于反馈；`all` 包括全部和共同控制。若实际设计必须改接口，先交 B 在同 Task 登记准确命令及等价覆盖，不删验收。证据保存在工作区以外，默认清理本轮临时实例；包验收／扫描验收及三个旧实机入口串行运行，不同时使用相同 project／端口／鉴权身份。

场景开始前等原生扫描和插件任务空闲，记录全部任务触发器，暂时关闭会干扰场景的自动触发，测试定时场景除外；结束恢复并核验。每轮以本次开始时间／终态关联，不能沿用上轮扫描结果。

开工记录当前资源、SDK 10.0.401、Node／Chromium／Playwright 实际路径与版本、镜像 digest、输入配置和 ZIP／部署文件摘要。先在部署前拒绝坏包、旧工作区或错误归属；finally 必须有对账、恢复／清理结果，任何收尾失败使整轮 FAIL。不能碰宿主生产 Jellyfin、现有代理或其他 Docker 服务。

### 2．准备可核对的小型多库／多版本夹具

使用两个不重叠的原生库根：一个在插件所选范围内，一个在范围外。复用合成 MP4／MKV 和受控 HTTP 后端；在所选库先准备约 160 个受支持 STRM，使原生候选实际跨越 128 对象批次，另列少量普通／旧输入与范围外对照。文件只由验收工具在本轮专用目录写入；插件仍只读 STRM。

批量所选库只约束批量入口；范围外对照不主动发起播放请求。播放仍按已有播放开关和权限处理，不能新增“按批量所选库过滤播放”的规则。

通过原生扫描／刷新获取当前项目 ID、媒体源、有效主流及库关系，再通过插件建立可信基线；准备原生媒体流的探测与本轮插件探测分开计数。禁止直接写 Jellyfin 数据库、伪造主流或成功保存信号。用原生 MergeVersions API 准备至少一个有两个不同媒体源的项目，验证选源及不同源独立，不手写数据库关系。

输出夹具清单：逻辑名称、当前原生 ID／MediaSourceId、范围、物理文件身份、URL 摘要／内容哈希／Size、原生主流与可信基线。清单跟踪后续变化；移库／扫描可能产生新 ID，按当前原生身份对账，不要求旧 ID 永存，也不为本 Task增加孤儿指纹清理机制。

### 3．证明真实三方重叠，再执行有限变化

使用现有可控延迟媒体路由与唯一请求标识，让一个批量探测和一个不同源的播放探测实际开始并保持在执行中。观察真实编码器／后端请求开始，不能把排队、获取许可或 POST 返回当成已开始。随后触发原生完整库扫描，轮询原生任务本轮开始时间、Running 和终态，记录扫描与两个实际探测区间的交集。

所有事件用完整 UTC 日期、单调耗时、本轮 UUID、容器 ID／启动身份、任务运行身份和源身份关联；Docker 日志使用带日期时间的输出和明确 since 边界。保留扫描开始／结束、文件变化、实际探测开始／结束、保存／提交和任务结算时序。扫描过快而未观察到交集时本场景 FAIL；不得用串行执行或单纯 sleep 假造重叠。开发反馈可调整受控夹具／有限延迟以形成真实窗口，保留每次失败和配置变化，最终固定输入后重跑。

在已观察到的重叠窗口执行以下有限序列；一次变化后记录原生观察结果，停止扰动后再做第 5 步的收敛验证：

| 变化 | 操作与必须核验的结果 |
|---|---|
| 新增／删除 | 在候选固定后新增一个 STRM，删除一个尚未实际开始的候选。当前集合不宣称事务快照；新增最迟下一轮发现，消失项安全结算，不能遗漏后仍虚报成功。 |
| 移库／范围 | 将一个尚未开始的源移出所选库，并将一个源移入；用原生扫描更新关系，执行前重新核对当前范围。范围外源零批量主动探测，下一轮准确处理新范围。独立播放／原生全库扫描自身的探测单列，不冒充批量越界。 |
| 探测期间 URL 再变 | 对有可信 A 基线的源换 URL 为 B（SHA-1／Size 相同仍必须探测），确认 B 的实际探测开始后将 STRM 改为 C。B 即使原生完成也不能成为 C 的可信指纹；有效旧基线保留，重新读取后 C 成功保存才能提交。后续 PlaybackInfo／主流／重启最终指向 C。 |
| 内容与信息变化 | 对另一源保持 URL、改变有效内容 SHA-1；另设 SHA-1 不可比且有效 Size 改变的对照，核验按既有规则探测。保留未变／相同有效 SHA-1＋Size 变化、信息不足等完整既有决策回归，不增规则。 |
| 独立强制刷新／多版本 | 使用原生 `Items/{id}/Refresh` FullRefresh 及正确 MediaSourceId 的播放，保留本版本原生行为。事件或刷新返回不是指纹成功证据；不能强求原生手动刷新必定探测 STRM，也不能更新另一个版本的指纹／地址。 |

如失败是测试编排或原生任务未实际运行，先修工具／准备；如发现产品真实缺陷，在同 Task 增加最小修复与有效回归，再重跑最终 T4。不能通过降低断言、伪造 ID／提交或新建持久化状态绕过。若需要改变合同、核心成功／保存边界或业务规则，交 A 判定，B 重判后再继续。

### 4．在同一安装候选验证共同控制、停止与恢复

复用现有 API／断言和场景思路，最少参数化当前实例／状态路径；不能为复用而复制整个旧脚本或偷偷开发部署。`all` 在所记录 ZIP 安装的实例取得以下真实结果，旧开发部署回归另外执行：

- 原生手动运行与真实定时触发、唯一任务、默认无触发；保存和恢复全部任务触发器。
- 同源的批量先开始→播放加入、播放先开始→批量加入两方向共享，各只有一次实际插件探测；不同源独立，混合场景的插件实际主动探测不超过本轮启动配置（默认 2）。原生扫描／独立强制刷新发起的探测另列，不能用全进程 ffprobe 总数判断插件池越限。
- 批量有已开始和未开始工作时原生停止：停止后不再获取后续候选／批次或启动未开始探测；已开始及已加入工作继续完成，可在全部成功条件满足后提交。旧轮收尾、统计和资源释放完成前下一轮不得实际运行；随后原生再运行可收敛。记录 Running／Cancelling／终态、进度及实际源结算，不把 Cancelled 写 Completed／100%。
- 单项媒体失败保留旧基线、不妨碍其他合格项，修复后可重试；插件 SQLite 全局故障停止优化并尽可能原生委托，不能因末项跳过而伪报成功。隔离恢复状态库并重启后正常，不删库重建、不注入物理 Jellyfin 数据库故障。
- 原调用 false 权限、禁用、普通／旧输入、有效／无效 SHA-1、解析错误和必要脱敏的既有控制保持。固定版本 PlaybackInfo 使用 None token，不新增“客户端停止取消已开始探测”测试或取消源；false 权限实机沿用既有经验证的原生入口，不能编造 PlaybackInfo 查询参数。

### 5．停止变化后收敛、重启并交接证据

结束所有文件扰动，等本轮所有实际执行结算，再完成一轮原生扫描和一轮全新候选批量检查。以原生当前稳定库重新生成预期集合，逐源核对在范围／消失／移入移出／新增／多版本结果，检查实际地址、必要主流和指纹，统计等式与进度／终态一致，无持续残留工作。随后未变复查零额外插件探测；重启并重新鉴权，PlaybackInfo 返回稳定新地址／正确选源，指纹不倒退。

更新测试矩阵、兼容性／环境说明及必要事实指针，只写本 Task 已测固定组合与限制。保留 RO-2／RO-4 NOT RUN，不提前写 Slice PASS／关闭或改 Roadmap。恢复共享开发实例原配置、全部触发器、STRM／媒体与原生地址，删除并核验本轮临时库项；专用扫描实例核对本轮变更清单并清理。失败和中断也不能跳过 finally 或丢失外置证据。

## 验收条件

- [x] AC-5：完整原生扫描 Running 区间与已实际开始的批量、播放执行有可核验交集；有限增删／移库／URL／内容变化和独立强制刷新都有时序与结果证据，不以 API 排队或串行场景替代。
- [x] AC-5：候选集合与当前范围符合既有规则，消失项正确结算、新增下一轮发现；不越范围、不接受探测期间变化的过期指纹，不串多版本，最终最新地址／主流／指纹及重启一致。
- [x] AC-6：最终 ZIP 安装候选上手动／定时、双向共享、不同源与混合并发、停止收尾／再运行、单项失败、SQLite 故障／修复重启真实通过；false 权限及禁用／普通／旧输入、末项全局故障等既有控制通过。无新取消语义或产品状态机制。
- [x] AC-6：首次信任、可靠成功／跳过／未完成／撤销等统计准确，检查与需要等式成立，进度／终态不虚报；扫描自身与插件探测成本分别记录。
- [x] AC-8 对应部分：当前源码／包／部署／镜像／配置／夹具身份、精确命令和原始证据一致；完整 T4 门槛、归档安装与新增扫描验收通过。恢复／清理失败不能输出 PASS；签名 URL／凭据不泄露。
- [x] 改动仅限本行为的验收入口／必要共用帮助、相关测试／事实文档及实际阻碍 RO-3 的最小产品修复；没有改变 Slice／稳定需求或引入排除机制。RO-2／RO-4 和单独 Slice Final 明确未完成。

## 必要测试

High／T4：实际扫描、播放、并发和条件持久化，保留完整指定门槛。所有新增扫描接口／产品结果当前 NOT RUN。

### 开发／修正反馈

先跑新增工具用例、已知失败及直接受影响回归，再跑小型实机 `overlap`／`stop`／`recovery`；尚无还原结果时先 locked restore。新工具测试必须实际发现且数量非零，优先验证缺失真实交集不能 PASS、跨日／旧会话不会混入、范围／过期版本对账失败被拒及异常收尾／旧工作区保护，避免只镜像字段实现。

```bash
python3 -m unittest discover -s tests -p 'test_isolated_scan_integration.py' -v
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~BatchCheckTests|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~PlaybackOptimizerTests|FullyQualifiedName~MediaSourceManagerProxyTests'
```

上述 Python 文件待新增，第二条为现有测试。完整最终套件已覆盖的聚焦用例无需机械重跑；涉及保存／核心接入修复仍须补相应原生链路证据。

### 最终检查点门槛

在准备提交的完整候选，从 `/opt/jf-strm-probe` 依次执行，所有实机串行。打包来源须为真实干净实现提交；必要时先提交实现、再对该候选验证、后提交纯报告。下面扫描命令待本 Task 实现，其他入口已存在。

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/package-all
python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/scan-all
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py --scenario suite
python3 scripts/run_isolated_configuration_integration.py --scenario all
python3 scripts/check_governance.py
git diff --check
```

路径中的 `<source-sha>`／`<run-id>` 是运行前替换的完整源码 SHA／唯一运行 ID 占位符，不照抄 shell 重定向。另做本地 Markdown 文件／锚点及事实协调检查并记录准确命令；配置浏览器原始输出用现有 `STRM_CONFIG_EVIDENCE_DIR` 指向稳定外置目录。新扫描入口与包验收必须使用同一个记录摘要的最终 ZIP；旧实机明确标为开发部署证据。不得在最后可执行输入变化后沿用旧最终证据。

### B 独立验证

审查 Task Base..Implementation Head 的真实代码／测试及完整原始结果；独立复现三方实际交集、URL 探测期间再变保护、当前范围／稳定集合收敛、停止结算和重启关键路径。独立检验没有真实交集／收尾失败不能 PASS 的工具控制。核验最后 ZIP 与加载负载、所有共同控制和恢复结果；输入匹配、原始记录完整的全量／昂贵门槛可明确复用，缺失或矛盾的对应门槛须重跑。B PASS 后再核对全部 RO／Surfaces，仍有缺口才规划下一 Task。

### 证据与重跑规则

证据索引放 `.git/validation-evidence/<完整源码SHA>/<唯一run-id>/` 或稳定 CI 产物；只有本机证据就注明本机可读。记录完整源码／审查 SHA、工作区准确内容身份、SDK／锁／镜像／浏览器、ZIP／部署、脱敏配置／夹具、准确命令／cwd／退出码／计数／耗时、串行及重试设置。每个场景有原生任务状态、完整 UTC 事件表、实际插件与原生探测计数、原生保存／指纹／地址／主流、范围与统计对账及 finally 结果。

保留首次失败、每次重跑及原因；超时、无真实重叠、依赖不可用、恢复失败均不算 PASS。源码／工具／测试／锁／运行配置／夹具改变后重跑受影响证据；最终可执行输入改变后完整 T4 门槛重新取得。纯报告后继比较输入后才复用，重跑消费文档的治理／链接检查。跨目录字节重建等额外性质不隐含承诺，构建版本与固定输入／原路径产物身份须准确。

## 非目标

RO-2 的十万原生候选／成本验收（后续 4.3）、RO-4 的真实代理（后续 4.4）、单独 Slice Final／Closure Packet、本轮远程推送／上架；不开发生成器／OpenList 客户端，不改代理、不下载媒体算 SHA-1、不增加 FFmpeg。无新调度器／队列／持久化运行状态、schema／规则／取消语义变更、并发热调整、首版扫描后自动触发或通用环境框架。普通 P2 措辞与无关重构不是本 Task 工作。

## Developer Completion Report

- Changed Files：`scripts/run_isolated_scan_integration.py`（新增）、`tests/test_isolated_scan_integration.py`（新增）；本 Task 后继续以纯报告更新 `TASK.md`、`docs/test-matrix.md`、`docs/compatibility.md`、`docs/development-environment.md`、`README.md`、`docs/roadmap.md`、`docs/progress.md` 的 CURRENT 事实指针。没有修改产品源码、schema、业务规则或既有工具。
- Implemented：
  - 新增 `scripts/run_isolated_scan_integration.py`，只消费指定 ZIP 并部署到 4.1 的独立包实例（Compose project `jf-strm-probe-package-*`、端口 `18097`、工作区 `artifacts/package-env`），不调用 `deploy_plugin()`、不在验收期间补 DLL 或重建包；复用 `package_environment` 的新工作区选择、镜像锁、Compose 归属检查、ZIP 校验／部署、鉴权、媒体准备、对账与清理。
  - 真实三方重叠：在所选 STRM 库放 130 个受支持 STRM（跨 128 对象批次），另有范围外本地库对照。插件禁用时用原生探测持久化主流，启用后首轮批量对全部候选零插件探测首次信任；随后让一个批量探测（所选库源）和一个播放探测（范围外不同源）实际开始并保持执行，再触发原生 `RefreshLibrary` 全库扫描任务，用原生 `LastExecutionResult` 的 UTC Running 区间与真实后端请求开始时间断言交集（缺失交集不能 PASS）。
  - 有限变化：URL 探测期间再变（B→C，B 不得成为可信指纹、旧基线保留、后续 C 提交）；同 URL 内容 SHA-1 变化探测；SHA-1 不可比且有效 Size 变化探测；移出所选库不批量探测、移入下轮发现；新增下轮发现、消失安全结算；多版本经原生 `MergeVersions` 合并后按共享 project／独立 source_key 校验、显式 `MediaSourceId` 选源返回各自地址；独立 `Items/{id}/Refresh` FullRefresh 不改任一版本指纹；稳定集合重跑与未变复查零插件探测、重启后地址稳定。
  - 停止：原生停止已开始与未开始工作的批量，已开始源结算并提交、未开始源撤销；提交／撤销按持久指纹而非时序日志分类；下一轮收敛。
  - 共同控制（在 ZIP 安装实例）：真实定时触发持久化与触发、双向同源共享各只一次真实探测、不同源混合并发峰值按插件运行计数归因（默认 2）。
  - 恢复：普通媒体／旧 STRM 委托原生且无插件事件；禁用后不发起新探测；SQLite 全局故障失败且不探测、恢复重启后正常。
  - 收尾：finally 恢复并核验全部原生任务触发器与插件配置，对账实例输入，默认清理本轮临时实例；旧非空工作区即使带旧标记也拒绝。
- Tests and Results（候选 Implementation Head `4837cb6d98ebbc60281ab3a66c888588a1120110`，证据索引 `.git/validation-evidence/4837cb6d98ebbc60281ab3a66c888588a1120110/run-20261017T102059Z-f765f3d7/`，本机可读）：
  - `bash scripts/dotnet-local restore … --locked-mode` PASS（2s）；`build --configuration Release --no-restore` 0 警告／0 错误（6s）；`test` 202/202 PASS（8s）；`format --verify-no-changes` PASS（15s）。
  - `python3 -m unittest discover -s tests -v` 141/141 PASS（3s），其中本 Task 新增 `tests/test_isolated_scan_integration.py` 19 项。
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases` PASS；归档 SHA-256 `58a0e22c26827c1ce2b6ff65b6ece3468b837f63a5cd589f4c9a7ab6d6793353`，来源 SHA `4837cb6d…`，与当前 HEAD 一致。
  - `python3 scripts/run_isolated_package_integration.py --package … --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all` PASS；消费归档 SHA-256 与上一致；clean／upgrade／recovery／invalid 全过，实例对账 CLEAN、清理 CLEANED。
  - `python3 scripts/run_isolated_scan_integration.py --package … --scenario all` PASS；消费同一归档 SHA-256；overlap／controls／stop／recovery 全过，`trigger_restoration` = restored and verified，实例对账 CLEAN、清理 CLEANED。三方交集实测：扫描 `10:34:19.376947Z`–`10:34:21.755303Z`，批量探测 `10:34:19.107135Z`–`10:34:39.134173Z`，播放探测 `10:34:19.106805Z`–`10:34:39.136686Z`，两次真实插件探测开始。有限变化均按预期：URL 再变 B 拒绝／C 提交、内容／Size 变化探测、移入发现／移出不探测、新增发现／删除结算、多版本共享 project 与独立 source_key 且显式选源正确、FullRefresh 不改指纹、稳定集合与未变复查 `actual probe calls 0`、重启地址稳定。停止轮：2 提交／1 撤销、`Cancelled`、下一轮收敛。共同控制：定时触发持久化且触发、双向共享各 1 次后端探测（batch_first `actual probe calls 1`、playback_first `0`）、混合峰值 `peak_running_probes 2` 且播放开始 `running 2`。
  - 既有开发部署回归（另列，明确不是归档安装证据）：`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` PASS（fixture／state restoration 均验证）。`run_isolated_configuration_integration.py --scenario all` 首次在浏览器场景因 Jellyfin Web `hometab` 无害噪声被现有分类器误判 FAIL（与 Task 4.1 已记录的同脚本 flake 一致），首次立即重跑又因 Chromium `headless_shell` SIGSEGV FAIL，第二次重跑完整 19 场景 PASS；该脚本与 Task Base／Slice Base 字节一致，非本 Task 引入，首败与两次重跑原始日志均保留，交 B 判断。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` 无输出；本地 Markdown 链接／锚点检查 25 文件 0 断链。
- Decisions：只新增扫描验收入口与对应工具回归，未改产品源码／schema／规则／取消语义。复用 4.1 的包实例与既有 `package_environment`／`package_plugin`／包验收 API；不新建环境框架。三方交集以原生任务 `LastExecutionResult` 区间与真实后端请求开始／完成时间判定，不以排队或 POST 返回冒充。停止提交／撤销按持久指纹分类，避免时序窗口误判。
- Remaining In-Slice Work：RO-2 真实十万原生库与分层成本（后续 4.3）、RO-4 实际 JellyfinProxy 联调（后续 4.4）、单独 Slice Final／Closure Packet 尚未完成。
- Risks / Deviations：RO-3 已在固定 ZIP 安装候选的代表性多库／多版本夹具上取得；未覆盖真实十万库或完整生产扫描压力，也未使用实际代理。audio-only 实机、物理 Jellyfin 数据库保存故障注入与通用 FullRefresh 性能证明沿用已接受限制，未新增。首败配置回归为既有 flake，未自行豁免，交 B 判定。
- Head SHA：`4837cb6d98ebbc60281ab3a66c888588a1120110`。

### Developer 修正报告（2026-10-17，BR-42-1～4）

- 修正提交：`d534be0`（强化扫描验收控制与证据）后续 `2d850a8`、`e4eb780`、`85cf051`、`97981cd`、`a33bad8`、`5247632`、`c798e02`、`8377d37`、`eac764d` 逐项修复；均在 Task Base 之后追加，未改写已审查历史，未改产品源码／schema／规则／取消语义。
- BR-42-1（真实窗口内变化）：新增 `require_change_in_window`／`require_captured`；`overlap_round` 先让批量与播放探测实际开始并保持执行，再触发原生 `RefreshLibrary` 并轮询到 Running 后才发出有限变化（B→C、内容 SHA-1、Size），并要求每个变化操作时间落在原生扫描 Running 区间内；`scope_change_round` 在已固定的 130 候选集合上删除／移出已捕获候选、集合固定后新增／移入，并要求全部落在 Running 区间内。删除／移出目标必须实际属于捕获集合，否则工具 FAIL。
- BR-42-2（逐源／选源／成功）：`require_completed_execution` 统一要求本轮自身身份、完整起止与 Completed，拒绝 Failed／Cancelled／超时／缺结果；`summary_fields_complete` 要求全部计数器存在（缺失即硬失败，不再经 `or 0` 变零）；重叠用实际后端开始与新增 `PROBE_MEDIA_REQUEST_FINISHED` 观测结束，不用配置延时推算；B→C 要求 A 原样保留而非仅“≠B”；`_require_selected_source` 校验请求的 MediaSourceId 与返回源 Id、Path 一致，拒绝未筛选多源／错版本；两个合并版本改为不同 URL 并保留同内容哈希／Size 对照；独立 FullRefresh 观察原生实际处理后再读两源；停止后从当前原生库生成稳定预期集合并逐源核对范围、指纹、地址、主流，重启覆盖 URL 变化源与显式选源。
- BR-42-3（停止与恢复）：`scenario_stop` 改用跨 128 批次夹具（130 候选、小改动子集），记录 Running→Cancelling→终态、Cancelling 期间进度必须 <100%、已开始工作提交／未开始工作撤销、停止后不再读取后续批次或启动新探测；旧轮收尾期间经原生入口再次运行不得实际进入新轮。`scenario_recovery` 增加 ZIP 上单项媒体失败隔离（失败保留完整旧基线、健康变化源仍成功）；禁用／故障前先制造应探测的变化，按插件编码器开始与所有后端路由（普通／delay 开始／完成／媒体请求）归因，不能只看 delay 计数。
- BR-42-4（证据）：新增 `EvidenceRecorder`，在外置 `--evidence-dir` 增量记录每轮完整 UTC／单调时间、容器启动身份、任务运行身份、源／文件／URL 摘要、变更操作与结果，保留脱敏原始任务轮询、后端与插件日志、保存／指纹快照；`events.jsonl` 追加式、`rounds/` 逐轮快照、`INDEX.md` 与 `result.json`；finally 在删除实例前采集失败片段与恢复／清理结果，收尾／清理失败使总体 FAIL，`--evidence-dir` 缺省落到工作区外。所有 URL／token／path 仅存 SHA-256 摘要。
- 反例控制（`tests/test_isolated_scan_integration.py`，37 项）：缺失交集、窗口外变化、删除目标不在固定集合、Failed／Cancelled／缺区间执行、缺失摘要计数器、错 MediaSourceId／错地址、Cancelling 期间 100%、收尾期间新轮／新探测、禁用或故障仍活动、证据在外置目录留存且收尾失败总体 FAIL 均被拒绝。原 B 四项控制（串行扰动、失败扫描被接受、失败任务且缺摘要宣称收敛、错误选源被接受）在当前候选已不再成立（对应 API 已改或断言已加）。
- Tests and Results（候选 Implementation Head `eac764d9b32a1b13f8ac963f8c14888fd50db4a3`，证据索引 `.git/validation-evidence/eac764d9b32a1b13f8ac963f8c14888fd50db4a3/run-20261017T143741Z-92b89989/`，本机可读）：
  - `bash scripts/dotnet-local restore … --locked-mode` PASS；`build --configuration Release --no-restore` 0 警告／0 错误；`test` 202/202 PASS；`format --verify-no-changes` PASS。
  - `python3 -m unittest discover -s tests -v` 158/158 PASS，其中本 Task 新增／重写 `tests/test_isolated_scan_integration.py` 37 项。
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases` PASS；归档 SHA-256 `62ae0669f4aadecaaaf7efc1d007fd4310765c70f47c99de17418ab97e946f0d`，来源 SHA `eac764d9…`，与当前 HEAD 一致。
  - `python3 scripts/run_isolated_package_integration.py --package … --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all` PASS；消费同一归档 SHA-256；clean／upgrade／recovery／invalid 全过。
  - `python3 scripts/run_isolated_scan_integration.py --package … --scenario all` PASS；消费同一归档 SHA-256；overlap／controls／stop／recovery 全过，`trigger_restoration` = restored and verified，实例对账 CLEAN、清理 CLEANED。三方交集实测：扫描 `14:41:43.558950Z`–`14:41:46.033613Z`，批量后端 `14:41:43.260801Z`–`14:42:03.262608Z`，播放后端 `14:41:43.261928Z`–`14:42:03.263115Z`；B→C／内容／Size 三个变化均在 Running 窗口内。有限变化：A 保留／B 拒绝／C 提交、内容与 Size 探测、移入发现／移出不批量探测、新增下轮发现／删除结算、多版本不同 URL 且显式选源正确、FullRefresh 不改指纹、稳定集合 136 源逐一对账且未变复查 `actual probe calls 0`、重启后 URL 变化源与多版本显式选源地址稳定。停止轮：130 候选跨批、`Cancelled`、已开始 2 提交／未开始 4 撤销、Cancelling 期间进度 96.9% < 100%、收尾期无新轮／新探测、再运行被拒、下一轮收敛。恢复：单项失败保留基线且健康源成功、禁用零探测、SQLite 故障 Failed 且零探测、恢复重启后正常。共同控制：定时触发持久化且触发、双向共享各 1 次真实后端探测、混合峰值 `peak_running_probes 2` 且播放开始 `running 2`。
  - 既有开发部署回归（另列，不是归档安装证据）：`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` PASS（fixture／state restoration 均验证）；`run_isolated_configuration_integration.py --scenario all` PASS（19 场景，`STRM_CONFIG_EVIDENCE_DIR` 指向外置目录）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` 无输出；本地 Markdown 链接／锚点检查 25 文件 162 链接 0 断链。
- Decisions：只改扫描验收入口／工具测试与合成媒体服务的观测标记，未改产品源码。重叠以原生任务 `LastExecutionResult` 的 Completed 起止与后端实际开始／结束判定，不以排队或 POST 返回冒充，也不再用配置延时推算结束。停止提交／撤销按停止轮自身摘要（`reliable_success`／`revoked`）分类，避免把收尾后重跑提交误当作停止轮结果。合成媒体服务仅新增 `PROBE_MEDIA_REQUEST_FINISHED` 观测标记，现有路由／计数不变。
- Remaining In-Slice Work：RO-2 真实十万原生库与分层成本（后续 4.3）、RO-4 实际 JellyfinProxy 联调（后续 4.4）、单独 Slice Final／Closure Packet 尚未完成。
- Risks / Deviations：RO-3 已在固定 ZIP 安装候选的代表性多库／多版本夹具上取得；未覆盖真实十万库或完整生产扫描压力，也未使用实际代理。audio-only 实机、物理 Jellyfin 数据库保存故障注入与通用 FullRefresh 性能证明沿用已接受限制，未新增。扫描验收要求提供外置 `--evidence-dir`（缺省落到工作区外），不再把证据留在会被清理的实例工作区内。
- Head SHA：`eac764d9b32a1b13f8ac963f8c14888fd50db4a3`。

## B Review Result

```text
Reviewed: 0e7b26b381ed5f71781e75d317275afa51d791e9..86946cc4ef5c0648b71aafc00aa666f2a2bb20c5
Report Checkpoint: 03f62bc8fafcd3e3b50bf4a21e35c12135f7eaa1
Decision: PASS
Slice Required Outcomes all satisfied: NO — RO-1/RO-3 B PASS; RO-2/RO-4 NOT RUN
Next: B plans Task 4.3 under the committed Slice; no further Task 4.2 Developer correction
```

### 本轮独立复审与证据（2026-10-17）

B 已核对完整 Task Base..Implementation Head、上一轮拒绝后的追加提交、报告后继差异和已提交 Slice／固定交付方案。初始 `main` 工作区干净，治理 PASS。产品 C#／测试、SDK、锁文件未变；本 Task 的可执行变化为新增扫描验收／工具测试及合成媒体服务的两个观测标记。报告后继只改文档。未发现需要改变合同的事实；Task ID、Base、Goal、Scope、High／T4 和全部最终门槛保持不变。

B 证据索引：`.git/validation-evidence/eac764d9b32a1b13f8ac963f8c14888fd50db4a3/b-rereview-20261017-01/INDEX.md`（仅本机可读）。独立 Python 全套 **158/158 PASS**；独立反例 **7/7 复现验收误放行**：返回未过滤多源、选中源缺主流、仅其他项目遗留行、旧地址与旧行相互匹配、缺地址源被漏掉、没有实际 FullRefresh 处理、失败媒体从未修复。反例绿灯只说明缺口被复现，不是产品验收 PASS。反例首次有一项 B 自身断言误用了随机生成的新 missing URL，已改为核对原缺失路由；首次日志和重跑均保留，产品输入未改变。

已阅读 Developer 当前索引、C#／Python／构建／格式日志、包与扫描结果、配置／播放／批量日志及 `scan-all/` 全部文件。其记录的 C# 202 项和各门槛退出 0 为原始运行事实，但下述验收器与证据缺口仍阻止 RO-3 PASS。本轮已有确定 P1 阻塞，B 的真实 Jellyfin／ZIP／C#／配置全套复跑为 **NOT RUN**；未把 Developer 自报 PASS 当成独立验收，也未操作运行中的实例。

上一轮修正要求及审查保留于 `d36c376:TASK.md`；本轮以以下**剩余工作**为准，不要求重做已补齐的部分。已见的有效改进：变化移到实际扫描窗口、要求 Completed 与完整摘要、使用真实后端事件界定延迟区间、跨 128 批停止并观察 Cancelling／阻止新轮、ZIP 单项失败隔离，以及外置事件文件和异常清理。这些改进不足以签发当前完整结果。

### BR-42-1（P1，部分修正）确保删除／移出的是本轮未处理候选

定位：`scripts/run_isolated_scan_integration.py:892`、`:1160`。`capture_candidate_sources` 是启动前独立读取的媒体源集合，不是本轮批量实际固定的候选身份清单；仅验证目标曾在库中，不能证明操作时尚未处理。当前固定选择 Bulk 000／001，再等另一个随机位置的 hold 源开始，其他消费者可能已经跳过目标。当前 scope 原始摘要为 candidates=136、checked=136、missing=0、not_processed=0；快照没有目标身份、批次／开始边界或逐项结算，不能据此证明“未开始候选消失／移出”的必要控制。

按顺序完成：

1. 复用现有夹具和 ID 查询，记录所选原生库、当前候选 item ID／源映射、排序及批次。使本轮固定集合与观测清单可核对；不能把媒体源数直接当候选 item 数，合并版本单独映射。
2. 安排首批确需探测的阻塞源，并从确定尚未读取的后批选择删除／移出目标；按产品实际 Guid 排序和 128 边界安排，记录已实际开始的阻塞探测与目标尚未处理的依据。无需引入新队列／状态机，也不要求持久化运行状态。
3. 在本轮集合固定且原生扫描 Running、阻塞探测仍执行的窗口完成变化，保留旧／新文件身份、item／source ID、当前库关系和完整操作时刻。移出后的身份重新查询，不用旧 ID 代替当前身份。现有“变化在扫描区间内”的检查保留。
4. 在下一轮启动前对账本轮：目标消失／移出被安全结算、没有目标批量探测；新增／移入未进入本轮；保存本轮源结果和摘要。原生扫描自身的工作单列。下一轮才验证发现新增与移入，不要求清理遗留指纹。
5. 添加驱动实际 `scope_change_round`／等价编排的控制：目标已处理、目标并非实际固定候选、移出后新身份被错误准入时必须 FAIL。只给 `require_captured` 传自建集合的单测不能替代该控制。

### BR-42-2（P1，部分修正）用当前 Manifest 与当前项目／源逐项证明结果

定位：`:1080`、`:1257`、`:1310`、`:1365`。稳定对账只在同 source_key 的任意历史行里找与原生 Path 相同的 URL 哈希；没有核对当前 Manifest，也没有要求当前项目的行。`:1393` 又用当前 Path 算出的哈希检查自身，无法发现“原生旧地址＋遗留旧指纹”一致的错误。缺 Id／Path 的源直接 `continue`。选源函数只从响应里筛匹配项，未拒绝额外源，且未检查主流；现有单测还明确接受未过滤响应。FullRefresh 循环未绑定本轮日志／完成信号，超时后也继续成功。

1. 在稳定原生扫描和批量完成后，从**当前范围关系＋实际 STRM 夹具／Manifest**生成预期项目／源清单。对每个当前 `(canonical item_id, source_key)` 读取确切五字段行，逐项核对 URL 哈希、有效 SHA-1／Size、原生当前地址和必要主流；允许旧孤儿行存在，但它不能替代当前键。暂缺 SHA-1 按既有同版本保留规则生成预期，不改产品规则。
2. 缺 item／source 身份、地址、主流或应有指纹必须失败。逐项集合比较能发现漏源／重复／错项目；不要依赖非空结果或总数相同。普通／旧／范围外输入单独列出预期，不用缺字段隐式跳过本应验收的源。
3. 探测 B 前保存可信 A 的**完整行**；B 结束且下一轮尚未开始时要求 A 完全相等。当前只核对 A 的 URL 哈希。C、内容 SHA-1 和 Size 后续成功分别关联本次实际探测、原生保存／条件提交及五字段行，不只读最终某一字段；保留拒绝过期结果的日志与快照。
4. 显式选源按本 Task 已定合同拒绝未过滤多源、错源、错地址与缺主流；请求 MediaSourceId、唯一返回源、原生保存流与对应当前键指纹必须一致。修正当前“多源仍可通过”的测试期望，添加真正应拒绝的反例，不只改注释。重启后覆盖发生变化的源及相关多版本源，并核对指纹没有倒退。
5. FullRefresh 前记录 ETag／原生状态及日志边界；等待**这次**实际处理和结束的可核验信号，缺失／超时即 FAIL，再读两个当前源及指纹。不能用历史匹配字符串或 204 替代，不强求原生一定执行探测。刷新如需独立窗口，可在受控轮次执行并记录其与实际运行工作的时序。
6. 将 B 的旧地址／遗留键／漏源／多源／缺主流／无刷新处理控制转为工具回归，增加 A 其他字段被改写也拒绝的场景。优先调用真实对账／场景函数；不得通过移除不变量或任意历史行兜底修掉测试。

### BR-42-3（P1，部分修正）在重跑前证明停止提交，并真正修复失败源

定位：`:1411`、`:1759`。跨批停止、Cancelling 进度和新轮禁止已补，但当前只按摘要认定已开始者提交，直到收尾后又运行批量才读指纹；这会掩盖“停止轮没提交、下一轮补交”的错误，且缺已加入工作在停止时的 ZIP 证据。恢复场景把失败源改为随机 missing 路由后从未修复；状态库恢复轮允许单项失败，因此 Completed 并不证明媒体修复或健康变化完成。

1. 停止前保存所有受控变化源完整旧行、已实际开始／已加入／未开始的身份。复用现有播放先开始→批量加入能力，至少让一个已加入源跨越这次停止并继续正常保存／提交；不注入执行取消源。
2. 旧轮结束后、任何自动排队轮或手动重跑开始前，保存逐源原生流／地址和五字段行：已开始／已加入成功源为新值，未开始源仍是完整旧行。把这些结果与停止轮摘要逐项关联。测试期间移除干扰触发器；旧轮收尾期间的再次运行尝试仍保留，并记录实际是否进入及何时进入。
3. 随后再运行并核对剩余变化成功、未变轮零插件探测；保留现有“停止后一个批次、Cancelled、实际进度不满 100%、收尾无新探测”的断言。不能以最终全已提交代替停止轮提交证据。
4. 单项失败对照完成后，把该失败源真实改为可达的新 URL；重新执行，要求该源一次必要探测、可靠保存／新指纹和可用 PlaybackInfo，原可信失败前基线只在成功后替换。健康变化源亦核对新地址／主流／五字段，不只核对任务 Completed。
5. 禁用配置要求保存成功并重读生效；SQLite 恢复／重启后逐源核对故障期间待处理变化已成功，随后未变复查零探测。保留原库备份／恢复和所有路由计数，不清库。false 权限、末项全局故障等原计划控制仍需完整证据，复用时列出对应运行与输入。
6. 增加停止轮未提交但重跑补交、已加入探测被取消、失败路由从未修复、恢复 Completed 但待处理变化未完成时工具拒绝的行为测试。

### BR-42-4（P1，部分修正）保存支持判断的原始证据

定位：`:155`、`:1858` 及 Developer 当前 `scan-all/`。本轮目录仅 10 个文件、12 条高层 events；没有原始任务轮询、请求／响应、容器／媒体日志或保存／五字段指纹快照。scope 快照只有变化时刻和汇总，没有目标身份；recovery 仅布尔值。`record` 大多在整个场景成功结束后调用，异常时仍会丢失该场景已发生的动作。外层 `scan-all.log` 也是最终摘要，不能弥补销毁后的原始记录。

1. 复用 `EvidenceRecorder`，在 API 观测、变更和关键保存／指纹读取发生时立即追加：完整 UTC／单调时间、当前容器启动身份、任务 Key／ID／执行起止、当前 item／source、脱敏 Manifest 身份和原始状态／结果。每次任务轮询保留脱敏原始数据，事件摘要可以另存。
2. 每个阶段保留前后 Manifest／原生源与主流／确切五字段行、实际探测开始／结果及提交事件。日志按本轮日期／容器／since 边界采集，来源明确，不能只留下 `True` 或计数。原生扫描和插件工作分别归因。
3. 在每次重建实例及最外层 finally **删除实例之前**采集脱敏原始 Jellyfin／媒体日志、任务最后状态和失败片段；场景尚未返回也要有已完成操作记录。实例仍可读时先取证，再恢复／对账／清理。保持当前进程归属检查、旧工作区保护和收尾失败整体 FAIL。
4. INDEX 写准确命令／cwd／完整源码与报告 SHA、实际工作区内容身份、SDK／锁／镜像／配置／夹具／ZIP／部署摘要、耗时／退出／计数、首败及重跑链接，逐项指向上述原始文件。`git diff --stat` 的摘要不能唯一标识有改动源码；用准确内容清单／差异身份。仅本机证据不声称远程可读。
5. 对字符串异常／嵌套响应／Path 对象检查脱敏，避免敏感值经无敏感关键词的 `error`／`message` 或 Path 直接输出。增加“执行到一半异常”和“日志取证／清理失败”的控制，确认此前观测保留且总体 FAIL；不要只测试 recorder 单独写一个文件。
6. 更新下层事实文档时明确本轮仍 FIX REQUIRED，4.1 仍 B PASS，RO-2／RO-4 NOT RUN。不要修改上位合同／Roadmap；其事实指针由 A 协调。当前上位及部分稳定文档仍留有初始 4.1／“尚无实现”指针，记录为协调项，不授权 Developer 改合同或把当前结果写为 PASS。

### 修正顺序、最终门槛与 Slice 重核

先用上述反例定位错误放行，再优先补原始取证与当前键／Manifest 对账，随后安排未处理候选和停止／恢复场景；完整行为仍在同一 Task，不另拆字段或测试 Task。开发反馈先跑 Python 聚焦／全套与小型 ZIP overlap／stop／recovery，保留首败。产品源码未发现已实证缺陷；若确需产品修复，仅限本 Task 已授权必要修复，核心成功／保存边界变化须按上位流程交 A。

最终候选仍执行本 Task 上方完整 T4 门槛：locked restore／Release build／全部 C#／format／全部 Python、重新打包、同一 ZIP 的 package all 和 scan all、三个既有开发部署回归、治理／差异及本地 Markdown 检查。工具／夹具变化后不得把当前旧实机输出冒充新最终证据。Developer 新报告逐项回应 BR-42-1..4，提供真实实现 SHA 与原始索引；B 再独立验证范围变化、当前键／Manifest、选源、停止提交／恢复及原始证据完整性。

Required Outcomes／Surfaces 重核：RO-1 为 Task 4.1 B PASS，安装包 Surface 的当前候选回归仍须满足；RO-3 及扫描／范围／持久化／停止／证据 Surfaces 仍 FIX REQUIRED；RO-2 真实十万库／成本、RO-4 实际代理及对应 Surfaces NOT RUN。独立 Slice Final／文档协调／Closure Packet 尚未完成。本轮不创建 4.3、不提交关闭包、不代替 A 最终审查。

可复用经验候选供 Slice 收尾：原生地址与历史地址相互一致仍可能同时陈旧 → 以当前 Manifest 和当前项目／源键作为独立预期，并用陈旧双方一致的反例验证拒绝能力 → 适用于指纹／多源持久化验收。本轮不改角色经验文件。

上一轮后续动作已由下方 2026-10-18 B 复审替代；以下 Developer 修正报告保留其交接时的事实与状态。

### Developer 修正报告（2026-10-18，BR-42-1～4）

- 修正提交：`86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`。保留前次 B `FIX REQUIRED`、所有失败及 Task Base 复现，没有改写审查历史。本次 BR 修正仅改 `scripts/run_isolated_scan_integration.py` 与 `tests/test_isolated_scan_integration.py`；未改 Slice／Roadmap／稳定需求或产品行为合同。
- BR-42-1（本轮未处理候选）：扫描入口固定并记录所选库的原生 item ID／MediaSourceId 清单、Guid 排序和 128 对象批次。最终扫描证据中候选集合为 136 个项目，首批阻塞源为 batch 0，删除与移出目标均为 batch 1 且变化时未开始；本轮先安全结算，新增／移入均在下一轮发现，移出身份重新按当前库关系核验。`scope_change_round` 的最终结果同时证明删除／移出在固定集合、尚未处理窗口的边界控制。
- BR-42-2（当前键、源与 FullRefresh）：逐项以本轮 Manifest 和当前原生项目／MediaSourceId 生成预期，对应当前 `(canonical item_id, source_key)` 的五字段行、当前 URL、SHA-1／Size 和主流均须完整匹配；缺身份或缺地址不能跳过，旧孤儿行不能代替当前键。显式选源拒绝额外源、错源、错地址或无主流。修复独立 FullRefresh 选取：把 Jellyfin 当前可见的合并项目 ID 映射到其唯一当前版本／source_key，再对可见合并项目发出 Refresh；不再用隐藏的 pre-merge 子项 ID 等待另一个版本的处理。最终 ZIP 上本轮请求返回 204，目标是可见版本 `Scan MV B 2382fe84`，观察到本次处理开始及结束，后续仅该 source_key 实际探测并提交一次；另一版本指纹保持完整稳定，两版本 PlaybackInfo 选源均匹配各自地址。FullRefresh 完成 UTC：`2026-10-17T21:17:38.142374Z`。
- BR-42-3（停止与恢复）：最终停止场景固定 130 项、两批；在下一轮前保留逐源状态，记录 2 个已开始源成功提交、1 个未开始源撤销、任务 `Cancelled`，并核对收尾期间没有新探测／新轮实际进入；显式下一轮随后收敛，已提交源不重复探测。恢复场景真实修复之前失败的媒体 URL，要求该源成功探测、保存新地址及当前指纹；禁用配置保存并读回，任务 `Cancelled`、零探测且旧指纹保持；SQLite 故障轮为 `Failed` 且故障期间编码器／路由探测计数未增加，恢复重启后待处理源成功提交，未变复查零探测。
- BR-42-4（原始证据）：最终扫描 `events.jsonl` 为运行中追加记录，含完整 UTC／单调时间、任务轮询、容器启动身份、候选／Manifest、文件变更、原生源／主流／五字段快照、探测／提交及恢复事件；`rounds/` 保存每轮前后状态，`logs/` 保存实例重启及删除前脱敏 Jellyfin／媒体原始日志，`result.json` 和 `INDEX.md` 记录归档身份、恢复、对账和清理。首次实例创建前没有容器可采集的两条记录明确记为 `log_capture_unavailable`，随后每次实际重启和 teardown 日志均有留存。外置索引与完整原始结果均为本机可读，不声称远程可读。
- FullRefresh 失败诊断：候选 `afe1cfdf5409809e30356d5f65fa996c85d85ad8` 的最终扫描在返回 204 后未观察到本轮处理，是保留的失败证据。使用 Task Base 插件归档对相同 harness 的独立回放也在 `base-fullrefresh-20261018-02` 以相同错误失败，排除了仅凭 Developer 自报判断；原因是发送了隐藏的版本子项 ID，但等待合并后另一项目 ID 的日志。修复后同一 Task Base 的回放 `base-fullrefresh-20261018-03` PASS；最终候选 ZIP 的完整扫描再次 PASS。较早的 SQLite 故障时间窗误包含健康探测也保留于 `5a2c5b7b6e401abf3cd36d209d1a8cbb068d1194/final-20261018-06`；时间窗改为从故障轮实际开始时刻取证，之后的候选 `afe1...` 扫描已通过该检查并暴露独立 FullRefresh 缺口。没有删除首败或把失败写作 PASS。
- 最终 T4 候选 `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5` 的门禁：locked restore PASS；Release build PASS（0 warnings／0 errors）；C# tests 202/202 PASS；format verify PASS；完整 Python tests 196/196 PASS（其中扫描工具回归 74 项）；重新打包 PASS，ZIP SHA-256 `434f930d6ad8282c1d68d47c7fc4456d52a025ae05e273db7b2f21551071ccaf`，metadata 来源 SHA 与候选一致。Package `all` 对同 ZIP PASS，clean／upgrade／recovery／invalid 全过，实例对账 CLEAN、清理 CLEANED；Scan `all` 消费同 ZIP PASS，overlap／controls／stop／recovery 全过，触发器 restored and verified、实例对账 CLEAN、清理 CLEANED。
- 最终扫描真实三方重叠：原生扫描 `21:16:49.559924Z–21:16:52.125773Z`，批量后端探测 `21:16:49.341767Z–21:17:09.343180Z`，播放后端探测 `21:16:49.342759Z–21:17:09.343740Z`；两次探测实际开始后才观察到扫描 Running 并在该区间内执行 B→C、SHA-1 和 Size 有限变化。136 项稳定复查零探测；多版本按项目共享／source_key 独立；共同控制记录双向共享实际探测及并发峰值 2。既有开发部署入口另行串行执行：`run_isolated_plugin_integration.py` PASS；`run_isolated_batch_integration.py --scenario suite` PASS（state restoration verified）；`run_isolated_configuration_integration.py --scenario all` PASS（19 个浏览器场景，configuration restoration verified）。这些旧入口单列为开发部署回归，不替代同 ZIP 安装验收。
- 证据索引：`.git/validation-evidence/86946cc4ef5c0648b71aafc00aa666f2a2bb20c5/final-20261018-08/INDEX.md`。固定运行时 .NET SDK 10.0.401、Python 3.11.2、Node 22.23.3、Playwright 1.55.0、Chromium 140.0.7339.16；镜像使用 Jellyfin `sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037` 与媒体服务 `sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`。重新打包前将旧 `artifacts/releases` ZIP 和旁车文件原样留存于证据索引的 `preexisting-release-files/`，未静默丢弃旧产物。
- 剩余边界：RO-2 十万候选与分层成本、RO-4 实际代理联调、独立 Slice Final／Closure Packet 仍为 NOT RUN／未完成；最终夹具是小型多库／多版本与跨 128 批次验证，不代表真实十万库或生产压力结果。没有远程推送。
- Developer 决定：`READY FOR B REVIEW`。这是交接状态，不是 Developer 对 BR、RO 或 Slice 的 PASS 裁决；请 B 独立审查 Base..Implementation Head 和上述本机原始证据。

Implementation Head: `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`

### B 复审（2026-10-18）— BR-42-2 重启验收仍 FIX REQUIRED

本节保留补证前的审查与修正要求；当前决定以下方「B 独立补证与最终 Task 裁决」为准。Task ID、Base、Goal、Scope、Contract Checkpoint、High／T4 和最终门槛保持不变；不需要修改合同或交 A 重定范围。

B 已审查完整 Base..Implementation Head、上次拒绝后的追加差异与报告检查点。起始工作区干净，治理 PASS；`86946cc..03f62bc` 仅有 `TASK.md` 报告变化。本 Task 全部可执行变化包括扫描入口／工具测试、合成媒体服务观测标记，以及 `StrmPlaybackOptimizer` 中批量加入已开始探测的诊断日志；该日志不改变执行／提交边界。未发现已实证的产品行为缺陷。

B 证据索引：`.git/validation-evidence/86946cc4ef5c0648b71aafc00aa666f2a2bb20c5/b-review-20261018T020330Z/INDEX.md`（仅本机可读）。独立 Python 全套 **196/196 PASS**；`restart_controls.py` 的两项独立反例均复现当前验收误放行，见 `restart-controls.log`：清空重启后 SHA-1／Size 仍被接受；驱动实际 `convergence` 时，缺少版本 B 且没有核对批量源重启后基线仍返回成功。反例复现成功不表示产品故障已实证，也不算重启验收 PASS。

完整实机复跑结果和证据复用清单见本节末尾。B 运行使用当前最终 ZIP，SHA-256 为 `434f930d6ad8282c1d68d47c7fc4456d52a025ae05e273db7b2f21551071ccaf`；消费包与 Developer 最终候选相同，没有重建包或开发部署覆盖。审查期间仅修改本文件，未改变可执行输入。

#### 已补齐的部分

- BR-42-1：当前候选 item ID／源映射、Guid 排序和 128 边界明确；首批持有探测，删除／移出目标来自未读取后批。B 独立复跑观察到 136 候选、两个目标安全结算、仅一个持有源成功探测，新增／移入下一轮发现。
- BR-42-2 的重启前部分：当前 Manifest 与当前项目／源键逐项五字段对账、完整 A 行保留、C／内容／Size 的本轮成功关联、严格唯一选源和必要主流、FullRefresh 本次实际处理起止均已补齐。B 独立复跑通过这些控制；不要求重做已完成部分。
- BR-42-3／BR-42-4：独立实机已通过停止轮重跑前完整快照、已加入源跨停止收尾、真实修复失败媒体、禁用持久化读回与 SQLite 恢复后待处理源提交；增量任务轮询／源快照／重建及清理前原始日志可读，异常留证／收尾失败控制通过。停止轮 130 候选，仅一批对象读取，2 个已开始／已加入成功源在重跑前提交，另 2 个受控变化源保留完整旧行；原始日志对账确认已提交源未在收敛轮重复探测。上述部分不再列为剩余阻塞。

#### 唯一剩余 P1：完成重启前后独立预期的逐源比对

定位：`scripts/run_isolated_scan_integration.py:173`、`:196`、`:2652`。`assert_committed_address_survives` 用刚读到的重启后行自身的 `sha1`／`file_size` 构造预期；`convergence` 重启后先调用批量源 PlaybackInfo，只比较 URL，随后只检查多版本 A。没有重启后的批量源完整行和多版本 B 核对。Developer 最终原始事件中，重启到 `convergence` 成功之间只有容器身份及结论，没有重启后逐源状态快照，无法从原始证据补证该义务。上轮 BR-42-2 第 4 项、Task AC-5 和 Slice AC-5 的重启一致性尚未闭合。

按以下简单顺序在同一 Task 修正：

1. **保存独立预期。** 在稳定扫描、稳定批量与未变复查结束、所有工作空闲后，复用 `reconcile_expected_sources`／`current_source_state` 的当前身份和 Manifest 映射。至少为 URL B→C 的批量源及合并项目的 A、B 两个源保存当前 `(item_id, source_key)`、完整五字段行、Manifest 身份、原生地址摘要和必要主流。预期只从这些重启前状态及当前夹具生成，不从重启后实际行取 SHA-1／Size 作为预期。可复用已返回的对账清单，不增加持久化运行状态或新的产品服务。
2. **先只读检查，再请求播放。** 重启并重新鉴权后，在任何 PlaybackInfo／批量／手动刷新可能补建指纹之前，读取上述三个目标的当前原生源与确切指纹。逐源核对完整五字段、地址和必要主流，并保存原始脱敏快照。没有扫描／文件变化时身份和完整行应保持；如实际观察到原生身份变化，保留前后映射的独立原生依据并明确验证新当前键，不能按相同 URL 任选历史行或默认容许重建。
3. **覆盖两个版本及返回结果。** 只读验证通过后，为批量源和 A、B 分别请求 PlaybackInfo；多版本显式传各自 MediaSourceId，复用严格唯一选源／地址／主流断言。请求后再次核对指纹与原生保存状态，记录本次容器启动后的实际插件探测事件；已接受且未变化的三个源不能靠额外探测、首次信任补建或丢失另一个版本掩盖重启问题。不能只检查 A，也不能用一个响应中存在任意匹配 URL 代替选源验证。
4. **把反例接入实际流程回归。** 在 `tests/test_isolated_scan_integration.py` 驱动实际 `convergence`／其共同编排，分别模拟重启后 SHA-1 丢失、Size 回退、完整行缺失、B 缺失／旧地址／缺主流，以及首次播放会修复丢失基线。每项必须在放行前 FAIL；另保留三个源完整一致的成功控制。避免只给纯校验函数传自建正确预期，或 mock 掉要验证的重启比对步骤。
5. **保留可复核原始证据。** 重启前、重启后播放前、播放后均记录 UTC、容器启动身份、当前 item／source、Manifest 摘要、原生源／主流和确切五字段行；把三个源的期望与实际逐项关联。异常时仍立即保留已发生的观测及清理前日志。修复现有入口和 recorder 即可，不建立新环境框架。
6. **按现有 T4 门槛重新交接。** 先运行上述反例与扫描工具测试，再跑小型 `--scenario overlap` 确认重启路径；随后对新的干净实现检查点执行上方完整最终门槛，重新打包并用同一 ZIP 运行 package `all`、scan `all`，三个既有开发部署回归另列。新报告逐项回应本节，提供完整实现 SHA 和原始索引；工具／测试改变后不得沿用旧最终运行作为新候选门槛。

#### 本轮结果与 Slice 重核

独立实机 `python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir .git/validation-evidence/86946cc4ef5c0648b71aafc00aa666f2a2bb20c5/b-review-20261018T020330Z/scan-all` 脚本结果 **PASS**，退出 0，873.194 秒，overlap／controls／stop／recovery 均完成。扫描 `2026-10-18T02:07:06.716525Z–02:07:09.097310Z` 与批量／播放实际探测相交，窗口内变化、完整 A 行保护、当前键收敛和本次 FullRefresh 均通过；定时、双向共享、并发峰值 2、停止提交／再运行、真实媒体修复、SQLite 故障失败且零探测／恢复提交均复现。触发器恢复 verified，实例对账 CLEAN，清理 CLEANED，1294 条增量事件、52 个原始文件留存。**此为脚本实际输出，不消除独立反例证明的重启漏检，不能据此签发 Task／RO-3 PASS。** 精确 cwd／PATH／参数／源码身份见 `scan-command.json` 和索引。

明确复用 Developer `final-20261018-08` 中匹配源码及同一 ZIP 的 locked restore／Release build（0 warning／error）、C# 202/202、format、重新打包、package `all`（clean／upgrade／recovery／invalid）及三个开发部署回归的原始日志；这些门槛本轮没有独立重跑。B 已核对归档摘要、部署记录、原始退出／计数、报告后继输入差异与本轮实际负载；当前可执行输入仍与实现检查点一致，只有 `TASK.md` 审查文档变化。独立 Python 196/196 覆盖 74 项扫描工具控制；治理 PASS、差异检查 PASS、本地 Markdown 25 文件／163 链接／0 断链。旧首败及重跑继续保留，不将它们改记 PASS。

RO-1 保持 Task 4.1 B PASS；RO-3 因上述重启验收缺口仍 FIX REQUIRED；RO-2 十万原生库／分层成本、RO-4 实际代理及对应 Surfaces 仍 NOT RUN。安装包、原生查询／扫描、当前范围、多源持久化、停止／恢复和证据 Surfaces 已逐项重核；重启 Surface 尚未满足完整证明，其他两个 RO 仍有必要工作，因此不进入 Slice Final／Closure Packet，不代替 A 作最终审查或关闭。

供 Slice 收尾的可复用经验候选：播放入口可能补建或修复状态 → 重启后先做只读快照并对比重启前独立预期，再验证播放和探测计数 → 适用于持久化／多源恢复验收。本轮不改角色经验文件。

上述 Developer 修正路线已由下方用户授权的 B 独立补证替代，不再要求 Developer 为本项启动新一轮工具开发。

### B 独立补证与最终 Task 裁决（2026-10-18）

**Decision: PASS。** Reviewed Range 仍为 `0e7b26b381ed5f71781e75d317275afa51d791e9..86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`；Developer 报告检查点仍为 `03f62bc8fafcd3e3b50bf4a21e35c12135f7eaa1`，补证起点为 B 审查文档提交 `baa635ec0770723075f43e080b427881eab55d2a`。没有新的产品实现或包。

**测试计划调整及依据。** 用户明确同意由 B 直接补齐隔离实机事实、按结果重判，不再把验收工具漏检直接交回 Developer 循环开发。B 因此显式替代上节六步 Developer 修正路线：在同一已提交候选／同一 ZIP 上追加独立重启观测，原 Task／Slice 的重启一致性、完整指纹、正确选源和零不必要探测义务全部保留；原完整 T4 门槛仍需满足。产品、正式工具／测试、依赖和夹具定义未变，既有完整门槛与 B 独立 `scan all`／Python 证据按输入核对后继续复用，不要求为纯审查补证重新打包或再造实现候选。本次不是合同变更，也未把原反例改记通过。

**实际验证。** B 复用正式 `--scenario overlap` 流程，以一次性观测脚本在 `convergence` 的实际重启处增加只读 API／SQLite 快照。原扫描、有限变化、FullRefresh、稳定集合检查及重启调用照常执行；不修改插件或已提交验收入口。候选仍为 `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`，消费原 ZIP `434f930d6ad8282c1d68d47c7fc4456d52a025ae05e273db7b2f21551071ccaf`。从当前原生集合解析项目／源映射，检查 URL B→C 的批量源及合并项目 A／B 两源，取得以下结果：

- 重启前、重启后任何 PlaybackInfo 之前、播放后，三个当前项目／源的完整五字段行、Manifest、原生地址和主流签名逐项完全相等；两个版本仍共享当前项目且 source_key 独立，没有使用遗留行兜底。
- 三个源显式 MediaSourceId 的 PlaybackInfo 均为 200，唯一返回源／地址／必要主流正确；重启后插件实际探测开始数为 0，没有靠首次播放重建丢失基线或重新探测修复结果。
- 原始快照落盘后另行读取 JSON，独立比较三个阶段完全相等；没有只信观测脚本的 PASS 标签。整个实机运行 PASS、退出 0、286.411 秒；触发器恢复 verified、实例对账 CLEAN、清理 CLEANED。

本机证据索引：`.git/validation-evidence/86946cc4ef5c0648b71aafc00aa666f2a2bb20c5/b-restart-proof-20261018T022343Z/INDEX.md`。`command.json` 记录准确命令／cwd／驱动摘要，`observe_restart.py` 保留可重复观察步骤，`overlap/rounds/b-restart-before.json`、`b-restart-after-restart-before-playback.json`、`b-restart-after-playback.json`、`b-restart-proof.json` 保存三个阶段及完整结果，`raw-snapshot-audit.json` 是独立逐项比对；增量原始响应和日志在 `overlap/events.jsonl`／`overlap/logs/`。仅本机可读，不声称远程可用。正式工具旧漏检及上一轮两项反例继续保留：其单独重启 PASS 不能替代此次独立证明；补证路线及原始数据可供 A 最终审查复核。

**阻塞重判。** 上一轮唯一 P1 是必要重启事实未被证明，现由真实原生状态和播放结果闭合；没有发现需要修复的产品缺陷。正式扫描工具的重启覆盖不足保留为非阻塞 P2，不要求本 Task 继续扩建工具。后续 Slice Final 必须在最终候选补齐同等重启比对，不能只引用旧工具 PASS 或把本次旧 Task 运行当作 Slice Final。

**全部 Outcomes／Surfaces 重核。** RO-1／安装包与安装恢复为 4.1 B PASS；RO-3／扫描、范围、多源持久化、共享／停止／恢复／重启与原始证据为 4.2 B PASS。RO-2 真实十万候选／成本、RO-4 实际代理及对应 Surfaces 仍 NOT RUN；README／矩阵等事实指针和上位合同中的旧实施指针保留为后续文档协调项，不能据此扩大兼容声明。单独 Slice Final、完整文档协调和 Closure Packet 尚未完成，不交 A 宣布 Slice 关闭。本轮按用户收窄后的授权完成 4.2 补证与裁决，下一项连贯工作仍为固定方案的 4.3，不夹带实施。

NEXT ACTION: B PLANS TASK 4.3 — REAL 100000 NATIVE CANDIDATES AND COST

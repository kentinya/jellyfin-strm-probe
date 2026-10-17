# Task 4.2 — 完整扫描与播放／批量并发下的正确性

必读：[Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。本计划只细化已提交合同的 RO-3；4.1 已独立 PASS，审查原文保留于 `git show 0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`，不修改 Slice／Roadmap／稳定需求。

```text
Task ID: 4.2
Parent Slice: 4
Status: READY FOR B REVIEW
Task Base: 0e7b26b381ed5f71781e75d317275afa51d791e9
Contract Checkpoint: ae265d0dba02aa1c5599871602d4350072b7155f
Difficulty: High
Test Level: T4
Planner / Reviewer: B
Implementation Head: eac764d9b32a1b13f8ac963f8c14888fd50db4a3
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

- [ ] AC-5：完整原生扫描 Running 区间与已实际开始的批量、播放执行有可核验交集；有限增删／移库／URL／内容变化和独立强制刷新都有时序与结果证据，不以 API 排队或串行场景替代。
- [ ] AC-5：候选集合与当前范围符合既有规则，消失项正确结算、新增下一轮发现；不越范围、不接受探测期间变化的过期指纹，不串多版本，最终最新地址／主流／指纹及重启一致。
- [ ] AC-6：最终 ZIP 安装候选上手动／定时、双向共享、不同源与混合并发、停止收尾／再运行、单项失败、SQLite 故障／修复重启真实通过；false 权限及禁用／普通／旧输入、末项全局故障等既有控制通过。无新取消语义或产品状态机制。
- [ ] AC-6：首次信任、可靠成功／跳过／未完成／撤销等统计准确，检查与需要等式成立，进度／终态不虚报；扫描自身与插件探测成本分别记录。
- [ ] AC-8 对应部分：当前源码／包／部署／镜像／配置／夹具身份、精确命令和原始证据一致；完整 T4 门槛、归档安装与新增扫描验收通过。恢复／清理失败不能输出 PASS；签名 URL／凭据不泄露。
- [ ] 改动仅限本行为的验收入口／必要共用帮助、相关测试／事实文档及实际阻碍 RO-3 的最小产品修复；没有改变 Slice／稳定需求或引入排除机制。RO-2／RO-4 和单独 Slice Final 明确未完成。

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
Reviewed: 0e7b26b381ed5f71781e75d317275afa51d791e9..4837cb6d98ebbc60281ab3a66c888588a1120110; report checkpoint 9e3a5b6cff504d8e339e7b0839ad6d9f5b5ef051
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — RO-3 FIX REQUIRED; RO-2/RO-4 NOT RUN
Next: Developer corrects BR-42-1..BR-42-4 in Task 4.2, then submits a new implementation checkpoint for B
```

### 本轮审查与证据

2026-10-17，B 核对真实 Base..Implementation Head、后继报告差异、已提交合同／固定方案及 Developer 原始产物。实现只新增扫描工具和工具测试，产品源码未改变；后继为报告／事实文档。治理准入 PASS，独立 Python 全套 141/141 PASS；另执行 4 项 B 控制，复现串行扰动、失败扫描仍被接受、失败任务且缺失摘要仍宣称收敛、错误选源响应仍被接受。4 项控制的绿灯表示缺口被复现，不表示产品验收 PASS。

B 索引：`.git/validation-evidence/4837cb6d98ebbc60281ab3a66c888588a1120110/b-review-20261017-04/INDEX.md`（仅本机可读）；Developer 索引仍为上方 `run-20261017T102059Z-f765f3d7/`。已读原始 scan/package JSON、构建／测试日志和配置首败／两次重跑。配置的 hometab 噪声与 Chromium SIGSEGV 及末次成功均保留，本轮不据此新增产品缺陷或豁免最终门槛。鉴于已存在以下 P1 阻塞，B 本轮真实 Jellyfin 复跑及 C#／包／配置全套重跑为 NOT RUN，不复用 Developer 的自报 PASS 签发 RO-3 验收。

以下均属当前 Task 的 AC-5／AC-6／AC-8 缺口，修正在原 Task；ID、Base、Goal、Scope、Difficulty High、T4 和合同不变。未发现必须变更 Contract 的依据，不创建 4.3，不改 Slice／Roadmap／稳定需求。Developer 完成报告保留为原候选声明，其中 RO-3 PASS 和逐项“已验证”的表述未被 B 接受。

### BR-42-1（P1）把有限变化放回真实扫描／执行交集

定位：`scripts/run_isolated_scan_integration.py:661`、`:753`。当前 `scenario_overlap` 等扫描结束、批量结束和播放 join 后才调用 `_finite_changes`；增删／移库在下一轮候选获取前完成，未验证已固定集合中的消失／移出与本轮新增边界。

按顺序修正：

1. 复用当前多库、跨 128 对象批次夹具，先记录本轮原生候选身份和范围。让实际已开始的批量／播放保持执行；从原生状态确认本轮扫描 Running，再执行有限变化。不能先等待扫描完成。必要时可分成多个有真实交集的受控轮次，每个变化注明所属轮次和扫描／执行身份，不强求所有变化挤在同一短窗口。
2. 选择已捕获但未开始的候选做删除／移出；在集合固定后做新增／移入。用当前原生身份和库关系验证，移库后的新 ID 不能沿用旧 ID 断言。逐源检查本轮消失／移出安全结算、范围外零批量探测、未捕获新增留下一轮。
3. 把 URL B→C、内容／Size 变化及独立刷新关联到相应真实窗口，记录文件操作 UTC、实际探测、原生保存／提交及任务结算；停止扰动后再进行稳定集合重查。仅 API 接受、sleep 或串行补跑不满足本条。
4. 新增实际驱动控制：没有 Running 交集、变化发生在窗口外或删除对象从未属于固定集合时，工具必须 FAIL。原有区间数学单测不能替代这些控制。

### BR-42-2（P1）补齐逐源结果、选源与成功判定

定位：`:398`、`:729`、`:770`、`:815`、`:853`、`:893`。本轮控制证明 Failed 扫描也能生成重叠成功；`_convergence` 在 Failed 任务、缺失摘要时仍可返回成功。移出只查旧身份无指纹；URL 再变仅要求不等于 B；多版本两个文件初始为同一 URL，且选源只检查响应内任意地址。

1. 对要求成功的原生扫描／批量，统一检查本轮身份、完整开始／结束和 Completed；拒绝 Failed／Cancelled／超时／缺失结果。摘要必须属于本轮、字段完整，缺失不能经 `or 0` 变成零探测。获取／批次／进度和两条统计等式都核对实际结算。
2. 重叠使用实际开始、结束／保存事件，不能把后端请求开始＋配置延时当实际探测完成；要求有正持续时间的真实共同交集。保留匹配编码器开始、真实后端请求及结束身份，核对原生扫描终态。
3. URL 再变前保存完整可信 A 行；B 结束后要求 A 原样保留，而非任意非 B 行。C 后续成功后逐项核对新指纹、原生地址／必要主流，以及 PlaybackInfo 和重启后的 C；内容／Size 变化也关联实际探测与可靠保存。
4. 给合并的两版本设置不同 URL，保留相同内容哈希／Size 的合法对照。校验请求的 MediaSourceId 与返回源 Id、该源 Path、原生流和对应五字段指纹一致；拒绝未筛选源列表、错版本或仅任意地址匹配。独立 FullRefresh 的 204 只是接受，需观察实际处理／原生更新完成再读两源，不能要求原生必定探测。
5. 停止扰动后从当前原生库生成稳定预期集合，按项目／源逐一对账范围、消失／移入移出／新增／多版本、指纹、地址和主流，再核对汇总及零额外插件探测。重启不只检查一个 batch 源；至少覆盖发生 URL 变化及显式选源的相关源。
6. 增加有效反例：缺失／旧摘要、Failed 扫描／批量、可信 A 被换成第三个指纹、错 MediaSourceId／返回多源、移出后新身份被误处理、漏源但总数碰巧相同、缺主流或过期地址时均不得 PASS。优先调用真实断言／场景函数，不再用搜索源码中出现某字符串充当行为测试。

### BR-42-3（P1）补齐最终 ZIP 上的停止及故障恢复控制

定位：`:926`、`:1184`。当前 stop 仅 3 候选、单批次，停止后直接等终态再运行；没有 Cancelling 阶段的进度／再次运行／后续批次准入证据。恢复仅测全局库故障，缺 ZIP 上单项失败隔离；禁用和故障计数只看延迟路由且源未制造变化，无法排除普通路由误探测。

1. 复用跨批次夹具，设置已开始、已加入和未开始工作；记录停止时刻、Running→Cancelling→终态及实际进度。验证停止后无后续批次读取或未开始探测，已开始／已加入工作正常保存、有效提交及结算；不要向探测注入取消源。
2. 在旧轮尚在收尾时通过原生入口尝试再次运行，以实际准入／批次／探测事件确认新轮未开始；不要仅检查 HTTP 返回。旧轮汇总和资源结算后再次运行收敛。验证 Cancelled 未补满 100%，所有源结果与统计一致。
3. 在同一 ZIP 安装候选加入一个确需探测但媒体失败的源和一个健康变化源；失败保留完整旧基线，健康源仍成功，修复后新轮恢复。既有开发部署脚本只能作为另列回归。
4. 禁用／SQLite 故障前制造本来应探测的变化，按当前轮插件编码器开始及所有相关后端路由归因，不能只统计 delay。对照有效配置保存、必要主流／基线不损坏、故障不可伪报 Completed；恢复状态库、重启并实际完成变化。保留 false 权限、末项全局故障等原计划控制，复用需明确对应输入与原始证据。
5. 增加控制证明取消阶段偷偷读下一批／启动新轮、把 Cancelled 当 Completed／100%、单项失败污染其他源、普通路由发生误探测时会被工具拒绝。

### BR-42-4（P1）在销毁实例前保存可审查的证据

定位：`:1252` 和 Developer 的 `scan-all/`。目前该目录仅 `scan-integration-result.json`，外层 `scan-all.log` 也是最终摘要；缺原始任务状态、实际探测／保存／提交、变更事件表和逐源清单。`probe_end` 为计算值。场景返回前异常会丢失该场景已采集内容，默认清理后无法补查。

1. 在外置 evidence-dir 增量记录每轮完整 UTC／单调时间、容器 ID／启动身份、任务运行身份、源／文件／URL 摘要、变更操作和所验证结果。保留脱敏原始任务轮询、必要请求／响应、容器／媒体日志及保存／指纹快照；finally 在删除实例前采集失败片段并记录恢复／清理。不得输出凭据或完整签名地址。
2. 记录准确命令、cwd、完整源码／报告 SHA、工作区内容身份、SDK／镜像／配置／夹具／ZIP／部署摘要，以及退出码／耗时／重试和首败。提供一个 INDEX 指向这些原始文件；仅有汇总布尔值不能代替它们。
3. 增加收尾故障／证据采集中断控制，证明恢复或清理失败使总体 FAIL，且已经产生的场景证据仍存在、旧工作区保持原样。保留并复用已接受的当前进程归属机制。
4. 修正 README、矩阵、兼容性／环境／进度的 CURRENT 事实；4.1 的 B PASS 不退回候选，4.2 缺口不继续标为验收 PASS。不修改上位合同或 Roadmap；如其旧事实指针有冲突，报告给 A 协调。

### 修正反馈、最终门槛与 Slice 重核

先使上述反例在旧候选可复现，再补真实工具回归并跑本 Task Python 聚焦／全套；小型 overlap／stop／recovery 必须在归档安装实例取得新原始证据。不得为了通过而删除原断言、缩小义务或伪造状态。

最终候选仍执行上方完整 T4 命令清单（locked restore／build／全部 C#／format／全部 Python、重新打包、package all、scan all、三个既有开发部署回归、治理／差异／本地 Markdown 检查），包与扫描消费同一新 ZIP。源码／工具改变后不把本轮旧运行冒充新最终证据；保留每次失败及重跑。Developer 新报告逐项回应 BR-42-1..4 并给真实实现 SHA，B 再独立复现三方窗口、逐源对账、错误选源／缺失证据拒绝和停止收尾关键路径。

RO-1 已有 Task 4.1 B PASS；RO-3 及扫描／范围／停止／证据 Surfaces 本轮 FIX REQUIRED；RO-2／RO-4 及对应 Surfaces NOT RUN。独立 Slice Final、完整文档协调与 Closure Packet 尚未完成，未达到交 A 最终审查条件。

可复用经验候选供 Slice 收尾：汇总计数和成功布尔值会掩盖未测试行为 → 用错误选源、缺失摘要、失败任务和窗口外变化驱动真实验收函数，证明拒绝能力 → 适用于并发／安装工具审查。本轮不改角色经验文件。

NEXT ACTION: DEVELOPER CORRECTS TASK 4.2 (BR-42-1..BR-42-4)

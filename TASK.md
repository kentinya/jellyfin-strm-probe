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
Implementation Head: 4837cb6d98ebbc60281ab3a66c888588a1120110
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

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO — RO-2/RO-4 NOT RUN
Next: B reviews Task 4.2 at Implementation Head 4837cb6d98ebbc60281ab3a66c888588a1120110
```

NEXT ACTION: B REVIEWS TASK 4.2

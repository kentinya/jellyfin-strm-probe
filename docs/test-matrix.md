# 测试矩阵

下表状态针对完整产品矩阵，尚未统一执行。Slice 1 原型已完成部分单元／真实 Jellyfin 场景，Task 1.1 经 B 审查 PASS，单独 Slice Final 与 A 最终审查已完成，Slice 1 PASS / CLOSED；分层结果见 [Closure Packet](progress.md#slice-1-closed)，不把有限原型证据直接覆盖完整产品矩阵。表格是 V4.2 目标，不是原型运行报告。通常前提为受支持版本化 STRM、已有主流、历史指纹与允许探测；例外显式说明。

保留 T01～T28 身份以便追溯，但 T08／T22 按 V4.2 改为原生探测后新地址持久化，T02／T17～T19／T27 改为最小指纹合同。旧结果不自动继承。B01～B12 为新增批量／共享并发验收。

## 核心播放与指纹

| ID | 场景 | V4.2 预期 | 需求（REQ- 前缀省略） | 最终证据类型 | 状态 |
|---|---|---|---|---|---|
| T01 | 首次无主流 | 实际原生探测；成功、保存且版本一致后初建指纹 | DECISION-001、STATE-001、PROBE-002 | 单元＋Jellyfin 集成 | NOT RUN |
| T02 | 首次已有主流 | 默认信任接管，建立指纹、零探测，不计本次成功 | STATE-001 | 单元＋Jellyfin 集成 | NOT RUN |
| T03 | URL 不变、SHA-1 相同 | 跳过 | DECISION-002 | 单元＋集成 | NOT RUN |
| T04 | URL 不变、SHA-1 不同 | 实际探测 | DECISION-002、PROBE-001 | 单元＋集成 | NOT RUN |
| T05 | URL 不变、SHA-1 相同、Size 不同 | 跳过；URL 变化不适用此豁免 | DECISION-002 | 单元＋集成 | NOT RUN |
| T06 | URL 不变、SHA-1 不可比、Size 相同 | 跳过 | DECISION-003 | 单元＋集成 | NOT RUN |
| T07 | URL 不变、SHA-1 不可比、Size 不同 | 实际探测 | DECISION-003 | 单元＋集成 | NOT RUN |
| T08 | URL 改变、SHA-1 相同 | 必须实际探测，原生保存新地址和有效主流 | DECISION-004、PATH-001 | 独立单元＋真实探测／播放 | NOT RUN |
| T09 | URL 改变、SHA-1 不同 | 实际探测并保存最新地址 | DECISION-004 | 单元＋集成 | NOT RUN |
| T10 | URL 改变、无 SHA-1、Size 相同 | 必须探测，单独自动化回归 | DECISION-004 | 独立单元＋集成 | NOT RUN |
| T11 | URL 改变、无 SHA-1、Size 不同 | 必须探测 | DECISION-004 | 单元＋集成 | NOT RUN |
| T12 | URL 改变、仅一侧有效 SHA-1 | 必须探测 | DECISION-004、MANIFEST-002 | 单元＋集成 | NOT RUN |
| T13 | 仅 Modified 变化 | 跳过 | DECISION-005 | 单元＋文件集成 | NOT RUN |
| T14 | 同内容 STRM 删除后重放且库记录／指纹保留 | 不因文件重放探测 | DECISION-005 | 文件＋Jellyfin 集成 | NOT RUN |
| T15 | 同 URL、同 SHA-1 重写 STRM | 跳过；地址改变则按 T08 | DECISION-005 | 文件＋集成 | NOT RUN |
| T16 | 同 URL 远程替换、SHA-1 变化 | 实际探测 | DECISION-002 | 原生探测集成 | NOT RUN |
| T17 | 探测失败且旧流仍在 | 旧指纹不变，后续仍识别变化；不写失败状态 | PROBE-002、PROBE-003、STATE-002 | 失败注入＋真实探测 | NOT RUN |
| T18 | 探测期间 STRM 再变 | 不提交过期结果，后续重查最新文件 | PROBE-002、PROBE-003 | 竞态集成 | NOT RUN |
| T19 | 重启，含上次未完成变化 | 指纹恢复并重新比较；无待测状态表也能重试 | STATE-003、PROBE-003 | SQLite＋真实重启 | NOT RUN |
| T20 | 多客户端同源并发，区分排队与实际开始 | 只共享实际已开始的运行中探测；排队不共享，获得执行机会后重查，结束各自重查 | CONCURRENCY-001 | 开始边界／并发＋真实计数 | NOT RUN |
| T21 | 手动强制刷新 | 保留原生，更新事件不足以提交指纹 | REFRESH-001 | Jellyfin 集成 | NOT RUN |
| T22 | 地址变化成功探测后重启 | 新 URL 与有效主流仍可用；不是仅更新路径测试 | PATH-001 | 真实探测＋Jellyfin 重启 | NOT RUN |
| T23 | 未安装插件 | 原生基线 | COMPAT-001、COMPAT-002 | 对照实例 | NOT RUN |
| T24 | 禁用插件 | 原生播放，批量不发起插件探测 | COMPAT-002、CONFIG-001 | 配置＋原生对照 | NOT RUN |
| T25 | 多版本影片 | source_key 独立，地址／流／指纹不串版本 | CONCURRENCY-001、STATE-003 | 多媒体源集成 | NOT RUN |
| T26 | 无协议标记旧 STRM | 默认原生，批量不优化 | COMPAT-002 | 解析＋Jellyfin 集成 | NOT RUN |
| T27 | 同基线 SHA-1 暂缺后恢复；再探测另一版本且新哈希缺失 | 前者保留有效历史哈希；后者不得继承旧版本哈希 | STATE-004、MANIFEST-002 | 指纹序列＋集成 | NOT RUN |
| T28 | allowMediaProbe=false，含同 SHA-1 换 URL | 不发起探测，不提交变化指纹；后续允许请求可重试 | DECISION-006、PATH-002 | 所有分支权限＋真实计数 | NOT RUN |

## 新增批量与全局并发

| ID | 场景／验证 | 预期 | 需求（REQ- 前缀省略） | 最终证据类型 | 状态 |
|---|---|---|---|---|---|
| B01 | 并发默认／配置边界 | 默认 2；1 与 8 可用；0、9、非整数保存反馈，实际并发不越界 | CONFIG-001、CONCURRENCY-002 | 配置＋协调集成＋真实计数 | NOT RUN |
| B02 | 多项目播放与批量混合探测 | 共用插件全局上限；Jellyfin／其他插件独立探测不被限流 | CONCURRENCY-002 | 隔离实机并发对照 | NOT RUN |
| B03 | 媒体库范围及类型过滤 | 默认全部，可选部分；普通媒体、旧／不支持 STRM 不探测；分页稳定去重 | BATCH-002、COMPAT-002、CONFIG-001 | 分页夹具＋实机库 | NOT RUN |
| B04 | 大量已有主流的首次任务／随后增量变化 | 默认信任，不全库重探测；仅缺流／变化者执行，与播放决策一致 | STATE-001、BATCH-002、BATCH-003 | 大规模夹具＋真实增量计数 | NOT RUN |
| B05 | 批量与播放同源，含排队／已开始及播放不允许探测 | 只加入已实际开始的探测；排队请求保持各自生命周期并在执行前重查，避免重复；播放不提高权限，独立批量上下文可执行 | DECISION-006、CONCURRENCY-001、BATCH-003 | 混合并发＋真实计数 | NOT RUN |
| B06 | 两入口遇成功／失败／保存失败／Manifest 再变 | 使用同一提交门槛，无错误新指纹；无法确认的刷新不计成功 | PROBE-002、BATCH-003 | 失败注入＋真实结果／存储 | NOT RUN |
| B07 | 停止后续分页／未开始工作，含已开始仅批量／播放共享及启动竞态 | 未开始撤销，其他调用者排队不受影响；所有已开始探测继续完成并可按全部成功条件提交；任务停止收尾等待其结算、资源释放，不误报全库完成 | CONCURRENCY-001、BATCH-004 | 开始／停止竞态＋真实任务停止／收尾 | NOT RUN |
| B08 | 单项损坏／探测失败及全局数据库不可用 | 单项报告未完成；旧指纹保留；状态库不可用停止优化，不转全库探测；恢复可再查 | MANIFEST-003、FAILURE-001、PROBE-003 | 注入＋实机恢复 | NOT RUN |
| B09 | 进度、完成／取消统计和日志 | 单调进度；成功仅可靠结果；计数可对账，信任接管算跳过；不泄露地址／秘密 | BATCH-005、PRIVACY-001 | 原生任务 UI／日志＋结果对账 | NOT RUN |
| B10 | 原生任务注册、手动／定时／停止、配置 | 名称正确，默认无触发；管理员原生设置；无独立按钮／调度器／扫描后触发；关闭播放检查仍可批量 | BATCH-001、BATCH-006、CONFIG-001 | 固定版本原生任务实测 | NOT RUN |
| B11 | 媒体库扫描／手动刷新同时增删或更新 STRM | 不提交过期指纹、不越范围、不假定时间计划已串行完成；后续增量可收敛 | BATCH-002、BATCH-006、REFRESH-001 | 隔离扫描竞态＋任务 | NOT RUN |
| B12 | 十万条模拟枚举／并发配置变更／队列故障 | 页与队列容量有界，不创建全库 Task；许可不泄漏；配置生效语义与实测一致 | CONCURRENCY-002、BATCH-002 | 压力指标＋代表性实机运行 | NOT RUN |

## 补充边界

| ID | 验证目标 | 状态 |
|---|---|---|
| X01 | STRM 只读、不调用 OpenList API、不计算远程内容哈希；只用临时夹具 | NOT RUN |
| X02 | 全接口委托、普通媒体／直播、DI 顺序、单例／释放、生命周期 | NOT RUN |
| X03 | 编码／BOM／空白、缺失／非法字段、零／溢出 Size、未知／冲突协议、有界读取及非法 URL | NOT RUN |
| X04 | 文件、原生地址／结果保存、SQLite 错误不覆盖指纹；原生回退保留探测权限；首次原生地址已过期不能静默成功 | NOT RUN |
| X05 | 同 URL 信息不足跳过并说明限制，mtime 不参与，签名查询变化仍算 URL 变化 | NOT RUN |
| X06 | SQLite 最小指纹／重启／schema 升级／损坏／不可写；无媒体流、完整 URL、PlaybackInfo 或独立探测状态 | NOT RUN |
| X07 | 实际 ffprobe、新结果、主流与持久化关联；旧流／事件／刷新返回值不足；FullRefresh 额外开销 | NOT RUN |
| X08 | 只共享已开始探测、排队不共享、等待者退出仍收尾、不同源独立、版本变化、条件提交与完成重查 | NOT RUN |
| X09 | 配置保存／生效／错误反馈、默认值、固定规则不做关闭开关 | NOT RUN |
| X10 | 签名 URL、token、Cookie、私有路径不进入状态、日志、进度或证据 | NOT RUN |

## 取消验收上下文

A 实质范围调整保留矩阵 ID 与历史结果，但移除当前 Slice 1 的人为注入取消门槛。当前固定版本的公共 PlaybackInfo 传 `CancellationToken.None`，客户端退出／停止播放不取消该探测；不增加必须取消客户端请求的验收，不将该入口事实写成探测取消 PASS。

- Slice 1／X08：继续验证 Manifest 变化与条件提交；取消只保留原生 token 委托、原生抛出取消异常时保留基线并传播及已有回归，不要求成功返回后的额外取消检查或人为注入取消实机验证。旧注入取消 NOT RUN 不改为 PASS，该子场景已退出当前范围。
- PlaybackInfo 正常／失败验证：未变化且已有主流时跳过，需要时实际探测；执行实际成功、结果已保存且 Manifest 一致时，客户端退出不单独阻止提交。公共入口源码定位如实报告，不以人为注入取消替代当前播放行为。
- 用户本次停止／共享规则由 A 作为 Material Contract Change 替代旧 Slice 2 的人为执行取消门槛。Slice 2／X08 验证实际开始后才共享、排队不共享、开始竞态、等待者退出仍正常收尾和结束重查；不再新增执行取消源或探测中／提交前取消注入实机要求，原生自身取消异常的既有回归保留。
- Slice 3／B07 验证停止后续分页和本任务未实际开始的工作，播放／其他调用者的排队请求不受影响。所有已开始探测继续，无其他等待者的仅批量探测也继续；成功且已保存、Manifest 稳定时仍提交。任务停止收尾等待其结算，按实际结果统计，不把批量停止当作探测执行取消。先确认停止则不开始，已实际开始则完成，竞态必须实测。
- 服务器关闭或进程被杀作为执行中断／重启恢复记录，不充当取消 token 生效的证据。

固定源码与入口见 [兼容性](compatibility.md#播放与批量取消语义)。原型与 Slice Final 的真实运行另见 Closure Packet；已开始共享／批量停止收尾等新矩阵义务未提前验证；被替代的取消注入门槛保留历史 NOT RUN，不改写为 PASS。

## 执行与对账

Task 2.1 完整报告／B PASS 在 `13cb8bdac319fcf0b3e7500661bae1c7455077b0:TASK.md`，通过 Git 读取；根 TASK.md 现为 Task 2.2 的修正候选报告／当前 B FIX REQUIRED 与历史审查，候选报告不能替代旧 Task 记录或产品验收证据。

Slice 2 现已 ACTIVE，Implementation Head 仍指向 Task 2.1 修正候选 `198f4ff2accd5bc9fcd87518a9684b9d068de103`；Task 2.2 首轮候选 `d651950950d6d3ad2be4322ddf8f0afb658c7755` 经 B 判 FIX REQUIRED，修正候选 `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a` 已交回 B 审查，Implementation Head 不提前移动。尚无完整产品矩阵验收；表中各行 NOT RUN 保持原事实。Task 2.1 与 2.2 的部分单元及隔离 Jellyfin 证据见下方说明和 [已接受 Task 记录](progress.md#当前开发指针)，不把部分场景升级为整行 PASS。T24 的批量部分、B07 的批量停止收尾、完整配置页、原生任务及大规模部分继续留在后续 Slice 范围；T20／T25／B01／B02 的共享／并发核心部分已由 Task 2.2 候选提供分层证据，B 已核验首轮部分原始成功记录，修正候选的独立复审仍发现当前源／开始竞态／清理边界失败，详见下方最新结论。

### Task 2.2 修正候选 B 复审

修正候选 `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a` 经 B 判 **FIX REQUIRED**。本机索引 `.git/validation-evidence/dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a/b-rereview-20261014-06/INDEX.md`：独立聚焦 71/71 PASS；四个控制失败观测：T20／X08 开始竞态第二 owner；T20／X08 排队已接受版本重复探测；T01／X04 排队期间主流消失仍复用；X08／X09 禁用准入委托异常泄漏许可／准备登记。不同用户的实际响应独立、保存新并发后重启前运行上限等证据仍需补齐。R3 中途配置写入保护／R4 启动脱敏的对应聚焦控制通过。B 默认实机 NOT RUN（已有明确 P1），Slice Final NOT RUN。

下方 Developer PASS 只保留具体已执行用例的结果，不代表上述边界完整满足；Required Surfaces 的当前接受结论以 [最新 B 决定](../TASK.md#b-review-result) 为准。禁止用旧源已提前更新的队列夹具、顺序 start race 或两个 null user 推定缺失行为 PASS。

### Task 2.2 最新修正候选（待 B 审查）

最新候选 `b3764f43713bbc22bdc00cab122340e241110484` 在同一 Task 内修正 B 复审的 R1／R2／R5／R6，尚未经 B 独立审查，不是 PASS：登记转换收进同一短时锁（消除第二 owner 竞态），开始拒绝抛 `ProbeStartRejectedException` 中止冗余原生调用，排队准入始终重读当前原生源并在每个提前退出前 `Abandon`，`Finish` 幂等单次释放；新增不同 `User` 同源响应、上限 1 以实际开始、`SharedJoinBarrier` 取代延时等确定性用例，实机脚本补保存并发后重启前仍为旧池上限的观测。本机证据 `.git/validation-evidence/b3764f43713bbc22bdc00cab122340e241110484/developer-fix2-t4-20261014-100054/INDEX.md`：C# 110/110、聚焦 79/79、Python 30/30、默认实机 JSON PASS；独立控制 harness 复现 B 四个失败观测全部转 PASS。T20／X08 开始竞态与排队重读、X08／X09 准入清理、B01 运行上限在候选层为 PASS，但完整行与 Required Surfaces 仍待 B 复核；此前 B 对 `dd5f6b80...` 的失败结论保留在下方历史。

### Task 2.2 审查与修正（R1～R5）

B 索引 `.git/validation-evidence/d651950950d6d3ad2be4322ddf8f0afb658c7755/b-review-20261014-04/INDEX.md`：指定聚焦 60/60 PASS，独立控制 7 个失败观测。T20／X08 的准备与实际开始边界、排队成功后重查为 FAIL；T24／X09 的排队启停为 FAIL；X09 的中途配置文件写入失败保护为 FAIL；X10 的非法配置日志私有路径为 FAIL。B 默认实机本轮 NOT RUN（已有明确 P1，先修正）。详细 R1～R5 及同 Task 修正门槛见 [B Review Result](../TASK.md#b-review-result)。以上失败属于控制层，不冒充真实 Jellyfin 故障注入。

Developer 修正候选 `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a` 按 R1～R5 修正，本机证据 `.git/validation-evidence/dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a/developer-fix-t4-20261014-05/INDEX.md`：C# 全套 102/102、聚焦 71/71、Python 30/30、默认实机 JSON PASS。新增确定性证据逐项映射：

| 矩阵项 | 修正候选证据层与场景 | 状态 |
|---|---|---|
| T20／X08 实际开始边界 | 单元 `ProbeCoordinatorTests.PreparingReservationIsNotRunningAndNotSharedAsStarted`、`StartRaceRegistersExactlyOneRunningProbe`、`PlaybackOptimizerTests.PreparationIsNotRegisteredAsStartedAndIsNotSharedAsRunning`（准备阶段 RunningCount=0、第二调用者不记为 running）；实机 `same_source_sharing`（`probes_started=1`、`fingerprints_committed=1`） | PASS（Task 范围） |
| T20／X08 排队重查 | 单元 `QueuedOwnerReReadsAcceptedVersionAndDoesNotProbeAgain`、`QueuedOwnerReReadsChangedManifestAndProbesTheLatestVersion`；实机 `same_source_sharing.followup_probe_calls=0` | PASS（Task 范围） |
| AC-6 零等待者收尾 | 单元 `StartedProbeCommitsEvenWhenNoCallerAwaitsAndTheWaiterCancels`（等待者取消、leader 未 await，仍提交新指纹） | PASS（单元） |
| B01 上限 1／8 | 单元 `GlobalLimitCapsConcurrentStartedProbes`、`GlobalLimitOneSerializesAndGlobalLimitEightAllowsEight`；实机 `global_concurrency_limit`（默认 2 两个重叠＋一个排队；配置 1 串行） | PASS（Task 范围；配置 8 仅确定性） |
| B02／AC-7 独立原生刷新 | 单元 `SaturatedPluginPoolDoesNotBlockNonPluginNativeWork`；实机 `independent_native_refresh`（插件池限 1 饱和时原生 FullRefresh 409 ms 完成） | PASS（Task 范围） |
| AC-5 不同调用者边界 | 单元 `SharedProbeCallersKeepTheirOwnUserAndPathSubstitution` | PASS（单元） |
| X09 配置闭环 | 单元 `ConfigurationTests.LatePersistenceFailureKeepsThePreviouslySavedFileAndEffectiveConfiguration`；实机 `core_configuration_api`（拒绝 0／9／负 400、非整数／错误类型 500 且文件字节不变；保存读回、DetailedLog 下一请求、Enabled=false 下一请求委托、并发重启持久化、恢复默认） | PASS（Task 范围） |
| X10 日志隐私 | 单元 `ConfigurationTests.InvalidPersistedConfigurationDiagnosticDoesNotLeakPrivatePaths` | PASS（单元） |

缺失项（如实报告）：B 对修正候选的独立复现与默认实机 NOT RUN；真实批量停止、分页、原生任务、完整配置页、外部代理及发布仍延期；实机池饱和对照使用原生 FullRefresh 端点，不声称由真实批量任务饱和。

### 其余核心矩阵与表面索引（Task 2.1 已接受 ＋ Task 2.2 修正候选）

| 矩阵项 | 证据层与具体用例／场景 | 状态 |
|---|---|---|
| T17 探测失败且旧流仍在 | 单元 `FailedProbeDoesNotReplaceTheAcceptedFingerprint`、`FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint`、`FailedNativeStreamSaveLeavesChangedAddressFingerprintRetryable`、`PersistenceProxyDoesNotConfirmNativeSavesThatThrow`；实机 `failed_changed_url`（返回≥400、1 次探测、已保存流不变）、`failed_probe_retained_streams` | PASS（Task 范围） |
| T18 探测期间 STRM 再变 | 单元 `ManifestChangedDuringProbeDoesNotCommitAnOldResult`；实机 `manifest_race`（HTTP≥400、`probe_calls=1`、保留指纹、恢复 1 次探测） | PASS（Task 范围） |
| T19 重启含上次未完成变化 | 单元 `RestartWithRepairedRepositoryRechecksAndCommits`、SQLite 七项；实机 `failed_url_after_restart`、`same_failed_url_repaired`（保留基线重启后再探测并提交） | PASS（Task 范围） |
| T20 多客户端同源并发 | 见上表 Task 2.2 行：单元准备／开始边界与排队重查；实机 `same_source_sharing`（1 探测 1 提交） | PASS（Task 范围） |
| T21 手动强制刷新 | 实机 `manual_full_refresh`（ETag 更新但未当作确认；后续地址变化仍触发 1 次探测） | PASS（Task 范围） |
| T22 地址变化成功探测后重启 | 实机 `address_after_restart`、`recovered_after_failure`（重启后新地址与主流仍可用） | PASS（Task 范围） |
| T23 未安装插件 | 未在无插件实例上运行；`disabled_plugin_delegation` 只证明禁用后原生播放可用，不等同未安装 | NOT RUN |
| T24 禁用插件 | 实机 `disabled_plugin_delegation`；单元 `DisabledOptimizerDelegatesOriginalProbePermission`、`DisabledOptimizerDelegatesWithoutStartingOrSharingAProbe`；批量不发起探测属 Slice 3 | PASS（播放部分）；NOT RUN（批量部分） |
| T25 多版本影片 | 实机 `native_multiversion_and_sqlite_recovery`（两版本独立 source_key／地址／主流／五字段，选源正确）；单元 `AlternateVersionUsesItsOwnStrmProbeAndStableProjectSourceIdentity`、`MixedLegacySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped`、`MixedOrdinarySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped` | PASS（Task 范围） |
| T28 allowMediaProbe=false | 单元 `DisallowedProbeIsPassedThroughWithoutReadingOrCommitting`、`DisallowedProbeDoesNotAcceptAChangedAddressOrFingerprint`、`RepositoryReadFaultDoesNotElevateFalsePermission`；实机 `false_permission_stream`（真实流请求 0 提交，后续允许请求 1 次探测） | PASS（Task 范围） |
| X01 STRM 只读／无外部 API／不下载哈希 | 实机 `legacy_strm_delegation`、`ordinary_media_delegation`；工具仅以 `mode=ro` 读取 SQLite；无 OpenList／代理调用；未运行外部代理联调 | PASS（Task 范围）；NOT RUN（外部代理） |
| X02 全接口委托／DI 顺序／生命周期 | 单元 `MediaSourceManagerProxyTests.ProxyDelegatesEveryInterfaceMethod`、`CoreServiceRegistrationTests.RehomedNativeSingletonIsCreatedAndDisposedExactlyOnce`；实机插件加载／启用／禁用重启 | PASS（Task 范围） |
| X04 原生保存／SQLite 错误不覆盖指纹／回退保留权限 | 单元 `FailedNativeStreamSaveLeavesChangedAddressFingerprintRetryable`、`PersistenceProxyDoesNotConfirmNativeSavesThatThrow`、`RepositoryReadFaultStopsOptimizationAndDelegatesWithOriginalPermission`、`RepositoryReadFaultDoesNotElevateFalsePermission`；实机 `failed_changed_url`、`failed_url_after_restart` | PASS（Task 范围；未对 Jellyfin 内部数据库注入故障） |
| X06 SQLite 最小 schema／重启／版本／损坏／不可写 | 单元 `EmptyDatabaseCreatesOnlyVersionedMinimalSchemaAndReopensFingerprint`、`ConditionalCommitRejectsStaleBaselineAndPreservesLatestVersion`、`CompetingFirstInsertionsAcceptOnlyOneBaseline`、`FailedSqlTransactionLeavesPreviouslyAcceptedFingerprintIntact`、`UnknownAndUnversionedDatabasesAreRejectedWithoutReplacingExistingData`、`CorruptDatabaseIsRejectedWithoutReplacingOrDeletingIt`、`EmptyFileIsTreatedAsANewDatabaseAndNotMistakenForCorruption`；实机 `native_multiversion_and_sqlite_recovery` | PASS（Task 范围） |
| X07 实际 ffprobe／新结果／主流／持久化关联 | 单元 `UrlChangeWithSameShaProbesAndCommitsOnlyAfterSavedPrimaryResult`、`NewAddressWithOldPersistedPrimaryStreamDoesNotCommitAndRemainsRetryable`、`AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream`；实机 `same_sha_url_change`、`manual_full_refresh`（GetMediaInfo 计数与本地媒体 GET） | PASS（Task 范围） |
| X10 隐私（URL／token／私有路径不进入状态／日志／证据） | 单元 `ConfigurationTests.InvalidPersistedConfigurationDiagnosticDoesNotLeakPrivatePaths`；实机脚本仅输出 URL 的 SHA-256、主流类型与计数，不打印签名 URL／token／Cookie／私有路径 | PASS（Task 范围） |

Required Surfaces 对账：solution／测试入口、原生 PlaybackInfo 与探测／保存链、私有 SQLite 最小指纹与恢复、项目／源身份映射与 ProbeCoordinator（实际开始、只共享运行中、正常收尾、结束重查）、Jellyfin 配置保存通道与脱敏日志均有上述单元／实机证据；完整 HTML 配置页与批量范围 UI 明确延期 Slice 3，发布包与跨版本延期 Slice 4。

### 首轮实施证据（B 已裁定 FIX REQUIRED，保留历史）

候选 `b99bc00b08fd3a8cad32076a220c5219fcc78ab7` 的 T4 执行记录保存在 `.git/validation-evidence/b99bc00b08fd3a8cad32076a220c5219fcc78ab7/developer-final-t4-20261013-02/INDEX.md`。单元测试和隔离 Jellyfin 分别报告：C# 全套 51/51、Python 全套 30/30；真实实例验证首次信任／持久化重启复用、同内容换 URL、多版本源和主流关联、失败重试及 Manifest 竞态、SQLite 写入／只读故障与重启恢复，以及普通／旧 STRM、直播、false 流权限、禁用插件和 FullRefresh。临时条目和多版本关系已清理，原 STRM 与 Jellyfin 地址已恢复。

### 修正轮证据与逐项索引（候选 `198f4ff2accd5bc9fcd87518a9684b9d068de103`）

响应 B 复审剩余 R2 的修正候选 T4 记录保存在 `.git/validation-evidence/198f4ff2accd5bc9fcd87518a9684b9d068de103/developer-fix2-t4-20261013-234000/INDEX.md`：C# 全套 69/69（含新增未知／冲突版本与换 URL／同 URL 双向哈希矩阵）、Python 全套 30/30、format／治理／diff／compile PASS、隔离实机 JSON PASS（492 秒，临时夹具已清理、原 STRM 与地址已恢复）。候选只改两份测试文件，产品源码、依赖锁与隔离工具未变。下表把合同要求的 T01～T16、T26／T27、X03／X05 逐项映射到实际证据层；证据层列 `单元`＝MSTest，`文件`＝真实文件读写回归，`实机`＝隔离 Jellyfin 默认入口。

| 矩阵项 | 证据层与具体用例／场景 | 状态 |
|---|---|---|
| T01 首次无主流 | 实机 `first_play_without_primary_stream`（缺失媒体 URL，1 次原生探测，无指纹）；单元 `MissingPrimaryStreamTakesPrecedenceOverFirstTrust`、`AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream` | PASS（Task 范围） |
| T02 首次已有主流 | 实机 `first_trust`（禁用插件原生保存主流后信任接管，0 探测）；单元 `FirstTrustRequiresAnExistingPrimaryStreamAndCurrentAddress` | PASS（Task 范围） |
| T03 URL 不变、SHA-1 相同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`；实机 `unchanged_repeat` | PASS（Task 范围） |
| T04 URL 不变、SHA-1 不同 | 单元 `DifferentComparableShaRequiresProbe`、`FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint`；实机 `same_url_content_replacement`（真实本地媒体替换，SHA-1／Size 变化，1 次探测并提交） | PASS（Task 范围） |
| T05 URL 不变、SHA-1 相同、Size 不同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability` 的“双侧有效且相同 SHA-1、Size 不同”分支（SkipProbe／Sha1Matches） | PASS（单元） |
| T06 URL 不变、SHA-1 不可比、Size 相同 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`（八个缺失／非法组合两侧方向、Size 相同 SkipProbe／Unchanged）；实机 `same_url_noncomparable_size_unchanged`（0 探测） | PASS（Task 范围） |
| T07 URL 不变、SHA-1 不可比、Size 不同 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`（八个缺失／非法组合两侧方向、Size 不同 RequireProbe／SizeChanged）；实机 `same_url_noncomparable_size_change`（无可比 SHA-1，Size 改变，1 次探测并提交） | PASS（Task 范围） |
| T08 URL 改变、SHA-1 相同 | 实机 `same_sha_url_change`（同 SHA-1／Size 换 URL，1 次探测并提交，重启后新地址）；单元 `UrlChangeRequiresProbeEvenWhenShaAndSizeMatch`（原生仍为旧地址，RequireProbe／NativeUrlMismatch）及 `HistoricalUrlChangeRequiresProbeWhenNativeAddressAlreadyMatchesCurrentManifest`（原生已为新地址而历史 URL 不同，RequireProbe／UrlChanged） | PASS（Task 范围） |
| T09 URL 改变、SHA-1 不同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧有效且不同 SHA-1”分支（原生地址已等于当前 Manifest，仅历史 URL 不同，RequireProbe／UrlChanged）；`same_failed_url_repaired` 是相同有效 SHA-1 的失败恢复，归 T08／T17，不充当本行不同 SHA-1 实机证据 | PASS（单元）；NOT RUN（实机双侧有效不同） |
| T10 URL 改变、双侧无 SHA-1、Size 相同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧缺失且 Size 相同”分支（RequireProbe／UrlChanged）；原 `alternate_url_change_without_sha` 为旧侧有效／新侧缺失，属 T12，不作本行证据；双侧缺失的实机分支 NOT RUN | PASS（单元）；NOT RUN（实机双侧缺失） |
| T11 URL 改变、无 SHA-1、Size 不同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧缺失且 Size 不同”“旧侧非法／新侧缺失且 Size 不同”分支（RequireProbe／UrlChanged）；实机无该输入的换 URL 分支 | PASS（单元）；NOT RUN（实机） |
| T12 URL 改变、仅一侧有效 SHA-1 | 实机 `alternate_url_change_without_sha`：旧侧有效／新侧缺失、Size 相同，1 次探测并提交且新 SHA-1 存空；单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 覆盖旧侧有效／新侧缺失与旧侧缺失／新侧有效的两个方向（Size 相同），以及旧侧有效／新侧缺失且 Size 双侧缺失；不能据此声称换 URL 时两侧方向都测过非法哈希或不同 Size | PASS（实机＋双向单元） |
| T13 仅 Modified 变化 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.mtime_only`（0 探测） | PASS（Task 范围） |
| T14 同内容删除后重放 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.delete_and_replay`（0 探测，指纹不变） | PASS（Task 范围） |
| T15 同 URL、同 SHA-1 重写 STRM | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.identical_rewrite`（0 探测） | PASS（Task 范围） |
| T16 同 URL 远程替换、SHA-1 变化 | 实机 `same_url_content_replacement`（真实本地媒体替换等价于远程内容替换） | PASS（Task 范围；远程代理未联调） |
| T26 无协议标记旧 STRM | 实机 `legacy_strm_delegation`（默认原生，无插件事件）；单元 `ReadTreatsMissingProtocolAsUnsupported`、`LegacyStrmDelegatesOriginalProbePermission` | PASS（Task 范围） |
| T27 暂缺 SHA-1 后恢复／另一版本缺哈希不继承 | 实机 `temporary_missing_sha_preserves_history`（保留有效历史 SHA-1）与多版本 `alternate_url_change_without_sha`（存空、不继承另一版本 SHA-1） | PASS（Task 范围） |
| X03 编码／BOM／空白／非法字段／Size／协议／有界读取 | 文件 `ReadRejectsInvalidUtf8AndDuplicateOptionalMarkers`、`ReadRejectsUnsupportedSchemesWithoutSkippingToALaterAddress`、`ReadRejectsInvalidSha1LengthsAndCharacters`、`ReadAcceptsMaximumValidSizeAndZero`、`ReadTreatsMissingEmptyAndOverflowingSizesAsUnavailable`、`ReadRejectsFilesOverTheBoundedInputLimit`、`ContentHashIncludesBomBytesWhileParsingTheSameManifest`、`ReadTreatsUnknownProtocolVersionsAsUnsupported`（version 0／2／1-beta → Unsupported）、`ReadRejectsConflictingProtocolVersions`（1+2、0+1、2+2 拒绝）；URL scheme 与 STRM 协议版本分别由 `ReadRejectsUnsupportedSchemesWithoutSkippingToALaterAddress` 与本行两个版本用例覆盖 | PASS（文件用例） |
| X05 信息不足跳过、mtime 不参与、签名变化算 URL 变化 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`、`ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest`；文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `same_url_noncomparable_size_unchanged`、`replay_and_mtime_zero_probe` | PASS（Task 范围） |

缺失项（如实报告，不升级为 PASS）：T16 的远程代理（OpenList／JellyfinProxy）联调 NOT RUN，当前以本地媒体替换证明同 URL 内容变化分支；T01～T16 中依赖真实远程内容的部分未做外部联调；T10／T11 的换 URL 双侧无 SHA-1 分支仅有单元证据、实机 NOT RUN；T20～T25 的共享／并发／身份行、B01～B12 与其余 X 项仍见上表 NOT RUN。

B 独立证据索引：`.git/validation-evidence/198f4ff2accd5bc9fcd87518a9684b9d068de103/b-rereview-20261014-03/INDEX.md`。独立 C# 聚焦 65 passed／0 failed／0 skipped；实际未知／冲突协议六组输入的原生委托与无指纹已由控制 harness 核验；默认实机 JSON PASS、487.172 秒，原夹具／媒体／地址恢复且临时条目清理。T09～T12 的新增逻辑输入已逐项复现，仍无对应输入的实机分支保持 NOT RUN。

这些证据支持 B 对 Task 2.1 修正候选的审查，不替代逐行完整矩阵对账。B 第二轮独立复审已确认 R1／R2／R3 全部满足并裁定 Task 2.1 PASS；详细决定与证据见 [B 审查检查点](progress.md#当前开发指针)。T01～T28、B01～B12 与 X01～X10 状态仍按上表记录；没有运行外部代理／OpenList、批量任务、运行中共享／全局并发、其他 Jellyfin 版本或完整发布门槛。表中标注的是具体用例的分层执行状态，不单独代表完整产品矩阵整行验收；Task PASS 以完整独立审查决定为准。

按开发流程保留源码／工作区身份、精确命令、版本、隔离配置、耗时、日志及原生 ffprobe 计数。所有哈希／地址／媒体使用假数据。区分单元、真实 Jellyfin、压力夹具与外部代理；十万条模拟枚举不冒充十万条真实库通过。

任务统计按检查对象（item_id＋source_key）去重，不把共享等待者当作多次实际 ffprobe。完成时需要数分为可靠成功与探测未完成；解析等检查阶段错误另外标注，计入未完成总数，避免不一致。首次信任计跳过；批量停止收尾统计已开始工作的实际成功／未完成，另报未开始／未遍历情况，不伪造 100%。具体进度分母及扫描期间库变化语义在 Slice 3 固定。

原生成功必须有失败对照，定时／停止／重启／并发要求真实证据。外部代理联调不可用时 BLOCKED／NOT RUN，不算 PASS。

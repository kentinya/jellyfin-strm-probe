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

Slice 2 现已 ACTIVE，Implementation Head 指向 B 复审仍为 FIX REQUIRED 的 Task 2.1 修正候选 `3488e6b1df48d4c142595d27694a792bb32f0aad`。尚无完整产品矩阵验收；表中各行 NOT RUN 保持原事实。Task 2.1 的部分单元及隔离 Jellyfin 证据见下方说明和 [Developer Completion Report](../TASK.md#developer-completion-report)，不把部分场景升级为整行 PASS。T24 的批量部分、B07 的批量停止收尾、共享／并发、完整配置页、原生任务及大规模部分继续留在后续 Slice 范围。

### 首轮实施证据（B 已裁定 FIX REQUIRED，保留历史）

候选 `b99bc00b08fd3a8cad32076a220c5219fcc78ab7` 的 T4 执行记录保存在 `.git/validation-evidence/b99bc00b08fd3a8cad32076a220c5219fcc78ab7/developer-final-t4-20261013-02/INDEX.md`。单元测试和隔离 Jellyfin 分别报告：C# 全套 51/51、Python 全套 30/30；真实实例验证首次信任／持久化重启复用、同内容换 URL、多版本源和主流关联、失败重试及 Manifest 竞态、SQLite 写入／只读故障与重启恢复，以及普通／旧 STRM、直播、false 流权限、禁用插件和 FullRefresh。临时条目和多版本关系已清理，原 STRM 与 Jellyfin 地址已恢复。

### 修正轮证据与逐项索引（候选 `3488e6b1df48d4c142595d27694a792bb32f0aad`）

响应 B FIX REQUIRED R1～R3 的修正候选 T4 记录保存在 `.git/validation-evidence/3488e6b1df48d4c142595d27694a792bb32f0aad/developer-fix-t4-20261013-221013/INDEX.md`：C# 全套 65/65、Python 全套 30/30、format／治理／diff／compile PASS、隔离实机 JSON PASS（约 500 秒，新增临时媒体已清理、原夹具与地址已恢复）。下表把合同要求的 T01～T16、T26／T27、X03／X05 逐项映射到实际证据层；证据层列 `单元`＝MSTest，`文件`＝真实文件读写回归，`实机`＝隔离 Jellyfin 默认入口。

| 矩阵项 | 证据层与具体用例／场景 | 状态 |
|---|---|---|
| T01 首次无主流 | 实机 `first_play_without_primary_stream`（缺失媒体 URL，1 次原生探测，无指纹）；单元 `MissingPrimaryStreamTakesPrecedenceOverFirstTrust`、`AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream` | PASS（Task 范围） |
| T02 首次已有主流 | 实机 `first_trust`（禁用插件原生保存主流后信任接管，0 探测）；单元 `FirstTrustRequiresAnExistingPrimaryStreamAndCurrentAddress` | PASS（Task 范围） |
| T03 URL 不变、SHA-1 相同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`；实机 `unchanged_repeat` | PASS（Task 范围） |
| T04 URL 不变、SHA-1 不同 | 单元 `DifferentComparableShaRequiresProbe`、`FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint`；实机 `same_url_content_replacement`（真实本地媒体替换，SHA-1／Size 变化，1 次探测并提交） | PASS（Task 范围） |
| T05 URL 不变、SHA-1 相同、Size 不同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`（相同 SHA-1 忽略 Size） | PASS（单元） |
| T06 URL 不变、SHA-1 不可比、Size 相同 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`；实机 `same_url_noncomparable_size_unchanged`（0 探测） | PASS（Task 范围） |
| T07 URL 不变、SHA-1 不可比、Size 不同 | 单元同上；实机 `same_url_noncomparable_size_change`（无可比 SHA-1，Size 改变，1 次探测并提交） | PASS（Task 范围） |
| T08 URL 改变、SHA-1 相同 | 实机 `same_sha_url_change`（同 SHA-1／Size 换 URL，1 次探测并提交，重启后新地址） | PASS（Task 范围） |
| T09 URL 改变、SHA-1 不同 | 原引用的 `alternate_only_url_change`、`same_failed_url_repaired` 和 `UrlChangeRequiresProbeEvenWhenShaAndSizeMatch` 都保持有效 SHA-1 相同，实际属于 T08；待补新旧有效 SHA-1 不同的换 URL 用例 | NOT RUN（指定分支） |
| T10 URL 改变、双侧无 SHA-1、Size 相同 | `alternate_url_change_without_sha` 的旧指纹 SHA-1 有效、新侧缺失，实际为 T12 的一个方向；待补双侧缺失的独立单元／集成回归 | NOT RUN（双侧缺失分支） |
| T11 URL 改变、无 SHA-1、Size 不同 | `UrlPriorityBeatsEveryShaAndSizeCombination` 实际仅使用双侧相同有效 SHA-1、Size 24，未执行本行输入；待补正确用例 | NOT RUN（指定分支） |
| T12 URL 改变、仅一侧有效 SHA-1 | 实机 `alternate_url_change_without_sha`：旧侧有效／新侧缺失、Size 相同，1 次探测并提交且新 SHA-1 存空；原引用的两个单元用例均为 URL 不变，不能证明换 URL 分支 | PASS（上述实机方向）；NOT RUN（完整双向单元组合） |
| T13 仅 Modified 变化 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.mtime_only`（0 探测） | PASS（Task 范围） |
| T14 同内容删除后重放 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.delete_and_replay`（0 探测，指纹不变） | PASS（Task 范围） |
| T15 同 URL、同 SHA-1 重写 STRM | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.identical_rewrite`（0 探测） | PASS（Task 范围） |
| T16 同 URL 远程替换、SHA-1 变化 | 实机 `same_url_content_replacement`（真实本地媒体替换等价于远程内容替换） | PASS（Task 范围；远程代理未联调） |
| T26 无协议标记旧 STRM | 实机 `legacy_strm_delegation`（默认原生，无插件事件）；单元 `ReadTreatsMissingProtocolAsUnsupported`、`LegacyStrmDelegatesOriginalProbePermission` | PASS（Task 范围） |
| T27 暂缺 SHA-1 后恢复／另一版本缺哈希不继承 | 实机 `temporary_missing_sha_preserves_history`（保留有效历史 SHA-1）与多版本 `alternate_url_change_without_sha`（存空、不继承另一版本 SHA-1） | PASS（Task 范围） |
| X03 编码／BOM／空白／非法字段／Size／协议／有界读取 | 文件 `ReadRejectsInvalidUtf8AndDuplicateOptionalMarkers`、`ReadRejectsUnsupportedSchemesWithoutSkippingToALaterAddress`、`ReadRejectsInvalidSha1LengthsAndCharacters`、`ReadAcceptsMaximumValidSizeAndZero`、`ReadTreatsMissingEmptyAndOverflowingSizesAsUnavailable`、`ReadRejectsFilesOverTheBoundedInputLimit`、`ContentHashIncludesBomBytesWhileParsingTheSameManifest`；未知 STRM 版本和不同版本冲突仍缺用例，URL scheme 不等于 STRM 协议版本 | PASS（已列文件用例）；NOT RUN（未知／冲突版本） |
| X05 信息不足跳过、mtime 不参与、签名变化算 URL 变化 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`；文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `same_url_noncomparable_size_unchanged`、`replay_and_mtime_zero_probe` | PASS（Task 范围） |

缺失项（如实报告，不升级为 PASS）：T16 的远程代理（OpenList／JellyfinProxy）联调 NOT RUN，当前以本地媒体替换证明同 URL 内容变化分支；T01～T16 中依赖真实远程内容的部分未做外部联调；T20～T25 的共享／并发／身份行、B01～B12 与其余 X 项仍见上表 NOT RUN。

这些证据支持 B 对 Task 2.1 修正候选的审查，不替代逐行完整矩阵对账。B 本轮复审裁定 FIX REQUIRED，剩余 R2 与具体错配见 [B Review Result](../TASK.md#b-review-result)。T01～T28、B01～B12 与 X01～X10 状态仍按上表记录；没有运行外部代理／OpenList、批量任务、运行中共享／全局并发、其他 Jellyfin 版本或完整发布门槛。表中标注的是具体用例的分层执行状态，不代表 Task PASS 或完整产品矩阵整行验收。

按开发流程保留源码／工作区身份、精确命令、版本、隔离配置、耗时、日志及原生 ffprobe 计数。所有哈希／地址／媒体使用假数据。区分单元、真实 Jellyfin、压力夹具与外部代理；十万条模拟枚举不冒充十万条真实库通过。

任务统计按检查对象（item_id＋source_key）去重，不把共享等待者当作多次实际 ffprobe。完成时需要数分为可靠成功与探测未完成；解析等检查阶段错误另外标注，计入未完成总数，避免不一致。首次信任计跳过；批量停止收尾统计已开始工作的实际成功／未完成，另报未开始／未遍历情况，不伪造 100%。具体进度分母及扫描期间库变化语义在 Slice 3 固定。

原生成功必须有失败对照，定时／停止／重启／并发要求真实证据。外部代理联调不可用时 BLOCKED／NOT RUN，不算 PASS。

# Task 3.1 — 原生按需批量检查与停止收尾闭环

规划／审查依据 [开发流程](docs/development-workflow.md) 与 [B 经验](docs/agent-experience/task-planner-reviewer.md)；实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。范围 authority 是已提交的 [Slice 3](SLICE.md)，不是后续建议任务。

```text
Task ID: 3.1
Parent Slice: 3
Status: READY FOR B REVIEW
Task Base: b86d9c17d7f915108072f54ee098f0f5543fe093
Contract Checkpoint: 2b515f35db7fc8e85d8ac1a8085dd9b8ccc62ef3
Superseded Plan Snapshot: eb4e272743f4c7e184d45fa48b660b2fef24c685
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

管理员通过 Jellyfin 原生「STRM 媒体信息检查」手动或定时检查已保存的全部／部分媒体库，不打开播放会话；任务固定本轮候选 ID，分批读取当前对象并按源增量处理，沿用播放的可靠探测／保存／指纹机制。原生停止撤销本任务未开始工作，等待已开始及已加入的运行中探测完成，正确提交有效结果、结算统计，再以 Cancelled 结束。失败可修复后重跑，状态库故障停止批量优化，不变成全库原生刷新。

本 Task 闭合 RO-1～RO-6 的批量运行旅程及 RO-7 的范围配置保存／兼容后端；完整 HTML 配置页及页面操作旅程不在本 Task。不能因暂未提供页面而削减范围校验、停止、失败或统计规则。通过后 B 重核全部 RO／Surfaces；预计剩余连贯单元是完整管理员配置与页面操作／恢复旅程，届时按真实结果规划，不预先创建活动任务。

## 实际缺口与实施范围

### 规划检查与合法性

初次规划时工作区干净、治理 PASS；原计划及停止补充保留于 Superseded Plan Snapshot。2026-10-14 用户授权 A 采用更简单方案，A 已在 Contract Checkpoint 提交 MATERIAL CONTRACT CHANGE、协调上层文件并暂置无活动 Task。B 在该提交后重新运行治理 PASS，核对工作区与已提交 Slice／Roadmap 一致、产品代码仍与原 Task Base 相同，无 Slice 3 实现。

B 合法性决定：LEGAL ADJUSTMENT — 同一 Task 3.1 继续规划。保留 ID、Task Base、Goal 的批量用户结果、其余范围和 High／T4；按 A 已提交合同将滑动分页／独立等待队列替换为原生候选 ID 集合、分批对象与固定消费者，同时修订计数和必要测试。原排序／重复页／32 项队列门槛由集合／批次等价行为门槛替代；停止实际开始、共享、成功保存提交、故障恢复与实机门槛均保留。没有产品审查 PASS，不替 A 最终关闭，也不启动本轮插件实施。

已读更新后的 AGENTS、开发流程、V4.2 原文、范围／需求／旅程／架构／Roadmap／Slice／Task 与 A／B 经验。Slice Base `6da90ab6bd8995d8204ae0b7faf786c823699fe6` 和 Task Base 不移动；新 Contract Checkpoint 是审查合同的依据，不能当实现 Head。

现有能力及必须修补的接缝：

- `Services/StrmPlaybackOptimizer.cs` 的 `CheckSourceAsync`、owner 行动前重判、稳定项目／源身份及原生结果验证可复用；但 Unsupported、禁用、读取故障和准备期间变化均可能允许原生委托。批量必须有独立调用策略，禁止这些分支误探测普通／旧输入或在状态库故障后继续探测。
- `Services/ProbeCoordinator.cs` 已分 preparing／running，并幂等释放许可；`ProbeExecutionContext.MarkCall` 与 `Interceptors/MediaEncoderDispatchProxy.cs` 是匹配编码器调用的开始信号。目前 acquire 立即获许可、准备、开始转换没有批量停止准入合同；`ExecuteProbeAsync` 仍传调用 token，`JoinSharedAsync` 可因等待 token 退出。这些接缝须在同一 Task 与原生停止实证一起完善。
- 现有执行返回 `MediaSourceInfo?`，条件提交竞争失败或 SQLite 写失败仍可能返回媒体源；共享等待后再次读取可能返回 null。不能据此推导批量可靠成功或把共享成功算跳过。需要同源本次执行／提交的内存结算证据及明确的检查结果，不增加持久化探测状态。
- `PluginConfiguration.cs`／`Plugin.UpdateConfiguration` 已有四项配置、原子保存及启动并发值；没有批量范围。复用保存通道和现有失败保护，新增第五项范围后端；HTML 页面仍未实现。
- 现有 112 项 C#、30 项 Python 及 `scripts/run_isolated_plugin_integration.py` 是继承回归；脚本当前无批量入口。旧证据不证明新任务、停止或定时通过。

固定源码 `artifacts/dev-env/source` 的 HEAD 已核对为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`：`ApplicationHost.RunStartupTasksAsync` 使用 `GetExports<IScheduledTask>(false)` 发现任务；`ScheduledTaskWorker.Execute` 正常返回为 Completed、取消异常为 Cancelled，其他异常会写入日志及任务历史。`ILibraryManager` 提供 `GetVirtualFolders`、`GetCount`、`GetItemsResult`／`GetItemList`；`InternalItemsQuery.IncludeAlternateVersions` 必须显式启用，关闭 presentation grouping 本身不足以保留所有版本。原生 `GetItemIds`／repository ID 投影可用于候选获取，`GetItemList` 的 ItemIds 用于批次读取；同步接口无调用 token。新方案不依赖媒体名称或原生唯一 ID 排序，只在内存固定去重 ID 序列；接口源码不等于该批量组合实机或内存验收通过。设计参考及固定来源见 [references.md](docs/references.md#所选库候选-id-与分批读取参考)。

### 一个批量闭环涉及的层

1. 原生任务发现、固定 Key／名称、可配置任务属性与空默认触发器。使用既有 DI 实例；避免类型导出与手工注册产生两个任务，或为批量创建另一个 optimizer／许可池。任务不持有播放会话，不通过 HTTP PlaybackInfo 伪装批量执行。
2. 全部／显式库 ID 配置、旧配置默认全部、服务端保存验证及每次运行的范围快照。显式空、无效或失效库拒绝保存／运行，不扩大到全部；运行中配置更改下次生效。源所属项目与当前库成员关系在执行准入重核，项目被删除／移出范围就撤销，不能沿多版本链接越范围。
3. 目标版本原生候选 ID 查询、固定集合／分批对象、物理媒体项到所属媒体源的映射及去重。可在现有服务内抽出共用职责，类名不是验收目标；不另建解析、决策、刷新或指纹链，不从目录枚举替代库查询。
4. 共用源检查的批量调用策略、可靠结果、全局不可用反馈及开始／停止准入。播放仍保留原调用 token、用户／选源／路径替换／false 权限和故障时原生委托；批量不走允许探测的故障回退。批量 PlaybackAutoCheck=false 仍独立执行，Enabled=false 停止后续候选获取／批次读取和新开始。
5. 当前对象批次由固定消费者处理，整批结算后才加载下一批，不额外建立生产者／等待队列。原生任务停止 token 只控制 ID 获取／对象查询前后、批次分派、等待许可、准备与开始准入；在匹配编码器边界协调停止与开始先后。执行已实际开始、原生保存、版本验证及提交不接批量停止 token；已加入 running 的批量请求也须等待可靠结算。等准备项仅等待后重查，不算共享探测；停止后不能重查再启动新探测。
6. 新批量确定性测试与隔离实机入口，复用现有本地媒体、探测／保存计数、只读 SQLite 核对与恢复工具。更新 Task 完成报告和本 Task 实际实现事实／操作说明；不改变 Slice、Roadmap 或稳定需求。

代码边界：现有插件项目内配置／注册、Services、Interceptors 及新增原生 Tasks；现有 MSTest 项目、必要工具回归；批量隔离工具及必要本地媒体夹具控制。仅当实际依赖需要时更新锁文件，并验证隔离部署加载。

### 单项失败与重跑

“单项失败可重试”指失败原因修复后，在下一轮手动或定时批量检查中重新读取当前 STRM 与可信历史指纹，按共用规则判断；仍需探测时再次尝试。下一次允许探测且启用播放自动检查的播放请求也可触发该重新判断。本轮不自动重试失败项目，不新增重试队列或持久化失败状态。

例如某个 STRM 的媒体地址暂时不可达，本次探测失败时不计成功、不覆盖旧可信指纹，并计入未完成；其他项目继续检查。地址恢复后，重新运行任务可再次尝试。单项失败隔离不适用于 SQLite／全局不可用等故障，这些情况仍按 AC-T6 停止后续批量工作并收尾。

### 停止收尾与再次运行

用户补充要求：收到停止指令后，必须等本轮已实际开始或已加入的运行中探测完成收尾，才允许下一轮批量实际执行。旧轮停止后不再获取后续候选、读取下一批或启动新探测；其 `ExecuteAsync` 保持未结束，直到这些工作完成原生保存／验证／条件提交、汇总和本轮资源结算，再抛出停止异常。复用固定版本原生 worker 的 `Cancelling → Idle` 生命周期，不新增插件运行开关、独立按钮或持久化任务状态。等待范围为本轮启动或已加入的执行，不要求全局其他播放探测全部结束。

收尾期间重复手动运行或定时触发不能开始新一轮批量查询／探测；原生调度器可能将定时触发排队，只能在旧轮结算结束后实际运行。原生手动 StartTask 返回 204 本身不证明新轮已启动，验收核对 worker 状态、执行入口及实际查询／探测计数。收尾后再次运行从当前已保存范围重新获取候选 ID，沿用新鲜指纹判断，不恢复旧批次位置或撤销工作。这是现有 RO-5 的明确验收，不改变 Slice 合同。

### 候选 ID、检查单位与分批工作

1. 复制本轮有效库 ID。用 `ILibraryManager.GetItemIds` 按所选库原生关系查询非文件夹、非虚拟 Audio／Video 媒体项，显式 IncludeAlternateVersions，关闭 presentation／series grouping 和 box-set collapse；不按文件目录扫描或预先读取所有 STRM。允许每个库一次取得全部候选 ID，合并去重后以明确的 Guid 比较顺序固定序列。所有所选库 ID 获取成功前不开始对象处理；任一库查询失败报告不可用，不把部分集合当完整范围继续。
2. 以固定序列每批最多 128 个候选 ID，用原生 `GetItemList(ItemIds=本批ID)` 读取当前对象；同一基本类型过滤继续适用，范围通过原生库关系重核。返回顺序不必与输入一致，以 ID 对齐；重复／额外返回不得生成额外工作，非请求对象拒绝处理；请求 ID 未返回、项目变类型／消失／移出选定范围单列结算，不能认领默认源、越界追踪或原生允许探测回退。固定候选在本轮只分派一次。
3. 每批至多 8 个固定消费工作处理当前对象，消费工作从本批取得下一个候选，不为 128 个对象分别创建 Task。等待全批结算、释放完整媒体对象和消费者后才读下一批。任务总体只有单个批次驱动与当前固定消费者，不要求另建 32 项队列、生产者或预取下一批。插件主动探测仍取得现有 Coordinator 的启动时 1～8 许可，默认 2；共享已开始的工作不新增许可池。
4. 执行机会到来后重查源身份、当前库范围、启用状态、Manifest、主流及旧指纹。按真实 `project_item_id＋source_key` 计源，source_key 为所属项 ID 的 N 格式，alternate 的 project 使用当前原生 PrimaryVersionId；每个物理候选最多一个所属源单位，原生返回其他版本不再次展开。集合固定后的新增 ID 不追加本轮；下轮重取集合。身份集合非事务快照，不代替当前读取或可靠保存／提交。

原生同步 ID／对象查询没有 token 时，调用前后确认停止／禁用；调用中停止等待返回，之后不继续查询、分派或开始探测。不得使用未等待的 Task.Run／后台获取或额外执行取消源宣称立即停止。记录 ID 获取／合并／排序和对象读取的耗时与分配，以及获取期间停止到返回的延迟。集合获取失败／停止时无媒体处理，部分已取 ID 数可记录，完整候选总数和剩余仍未知。空集合可正常完成。

`Nraw` 为各原生 ID 查询返回的身份数，`N0` 为完成合并去重后的固定候选数；不再用 GetCount 的独立查询估计或随新增扩大分母。每个候选只结算一次，`S` 为已结算候选数，包括普通／旧／不支持的不处理、缺失／移出及进入源检查后取得的最终结果；受支持源检查与错误统计另列，不能把 N0 当成合格源总数。Unsupported／普通媒体零批量探测；Invalid／Unavailable 的 STRM 尝试计检查阶段未完成，单列未确认受支持的读取／解析错误。

集合准备阶段报告 0%；其后按 `max(上次值, min(99, 100 × S / max(1, N0)))` 报告。正常遍历固定集合并等待全部工作结算才另报 100%，表示本轮候选处理结束；单项失败已结算可继续，停止／禁用／全局不可用不得补满。汇总仍满足合同源统计等式，首次信任计跳过，共享可靠成功须关联同源本次执行与提交，排队旧判断不作为最终计数。

集合完整后，候选总数对账为：N0＝已结算候选＋本批已加载但未进入检查即撤销候选＋已请求但获取未完成候选＋尚未请求读取候选。原生批次查询失败时该批计获取未完成，不能当消失／不处理或已完成源检查；项目／源映射异常在取得对象后的结算中单列。停止未分派的当前批候选计撤销，后续批按 ID 计未读取；这些数量只描述捕获身份，不宣称对应当前仍存在源数或剩余探测数。

全部候选 ID、去重集合、排序副本和原生查询临时分配允许随 N 增长，必须单列身份数量／容量、峰值内存和获取耗时，不宣称总内存恒定。只对批次完整对象和固定消费者／活动执行工作承诺上限；原生单项多版本临时数据另报。无需滑动 offset 游标、逐页增长 ExcludeItemIds 或无限重扫；有限 ID 序列与明确批次终点提供枚举终止。若原生适配无法满足静态完整、多版本或范围安全，提交真实事实给 B／A，不能弱化其他不变量。

## 验收条件

- [ ] **AC-T1 原生入口（RO-1）**：真实实例仅发现一个目标任务、默认触发器为空，手动执行与管理员设置的真实时间触发均有效；触发器重启持久化且无默认／启动意外运行。无需播放会话，手动运行／停止／时间都由原生任务管理。
- [ ] **AC-T2 范围与有界遍历（RO-2、RO-7 后端）**：默认全部、显式部分、旧配置、空／失效选择保存与运行、每次范围快照及移出／消失安全。确定性覆盖至少两个库、多批、同名／重复 ID／跨库重复、对象返回乱序／重复／缺失、集合获取失败、多版本及音频源；真实至少两个库、完整 ID 获取、多批、多版本按源对账，范围外／普通／旧／未知协议零批量探测。集合固定后增删／移库安全结算、新增下一轮发现；十万模拟候选证明批次／消费者上限，身份集合及查询临时成本单列。
- [ ] **AC-T3 共用可靠结果（RO-3）**：首次信任及未变零探测、不计真实成功；缺主流、同 SHA-1／Size 换 URL、同 URL 有效 SHA-1 变化、不可比 SHA-1 的 Size 变化使用共用原生链。结果／新地址／主流／SQLite 与重启后 PlaybackInfo 一致。成功计数仅关联本次同源真实成功、保存、稳定 Manifest 及条件提交；提交拒绝／失败不伪报成功，恢复可重试。
- [ ] **AC-T4 混合共享（RO-4）**：确定性 1／2／8、准备／排队不共享、立即获许可与完成重查、多版本／调用者隔离。实机批量先开始→播放加入、播放先开始→批量加入都仅一次匹配探测，批量成功与实际调用分别统计；同源排队完成后无重复。不同源混合不超启动上限、保存并发下次启动才生效，独立 FullRefresh 正常；false 播放原权限和基线不升级。
- [ ] **AC-T5 停止与资源（RO-5）**：确定性屏障覆盖同步 ID 获取／对象读取前后、批次未分派、等许可、立即获许可未登记、准备取源 await、准备登记、实际开始／停止双方先发生、已开始仅批量及两方向共享。同步查询中停止等待返回且无后续准入，不泄留后台获取。停止确认后无新实际开始，其他调用者排队不受影响；已开始／已加入工作成功仍提交，原生自身失败／取消异常保留旧基线。任务等到结算／汇总后才抛原生停止异常，最终 Cancelled，非 Completed；批次对象、消费者、候选 ID 引用及本轮 preparing／running／许可释放。真实停止证明未开始撤销与已开始完成；收尾期间重复手动运行及定时触发不实际启动新轮，旧轮结算后可以再次运行并按最新指纹跳过已成功源。独立播放探测不因等待旧批量收尾被禁止。不拿进程杀死或手动 API 的 204 替代真实执行证据。
- [ ] **AC-T6 故障与汇总（RO-6）**：损坏／不可达、Manifest 再变、独立保存失败控制隔离单项；SQLite 读取／提交故障、全局不可用、候选获取／批次读取异常及时停止准入并收尾。不可用使用脱敏失败结果（管理员同时停止时保留取消原因及不可用汇总），不自动删库，不通过原生委托继续全库探测。修复重启后重跑成功；单项原生取消不得伪造管理员停止。
- [ ] **AC-T7 可对账反馈（RO-6）**：检查＝跳过＋需要＋检查阶段未完成；需要＝可靠成功＋探测未完成；未完成总数＝检查阶段未完成＋探测未完成。首次信任计跳过，共享源只计一次但必须保留本次成功关联，实际调用次数另计。原生 ID／去重候选／不处理／消失或移出／重复／撤销／读取未完成／未读取分别标注，集合未完成时总数未知；原生进度单调且提前结束不补 100%，正常空库可完成。Completed／Cancelled／Failed、计数、保存／提交和日志一致；必要汇总不依赖 DetailedLog，异常及原生任务历史无秘密／私有路径。
- [ ] **AC-T8 回归与交接（全部接入表面）**：T4 完整候选门槛与 B 指定关键复现有可核验证据；新增部署依赖实际加载。改动属于本 Task、STRM 产品只读、固定原生委托／播放响应与最小五字段 schema 保持；准确交代 HTML／浏览器旅程仍未完成。未运行／不可用门槛如实记录，不能先 PASS 再延期当前阻塞。

## 必要测试

工作目录均为仓库根 `/opt/jf-strm-probe`；SDK 固定 `global.json` 的 `10.0.401`／net10.0，Controller／Model `12.2.0` 与上述源码／本机锁定镜像组合。测试阶段遵循开发流程；最终全套覆盖聚焦测试时记录包含关系，不重复相同用例。

### 开发／修正反馈

新增批量行为测试统一加 `TestCategory("Batch")`，覆盖查询／范围、源结果、任务执行及停止／统计；可沿用现有 fake、真实临时 STRM 与 SQLite，并通过屏障控制竞态，不用 sleep 碰运气。修正先跑已知失败与直接受影响测试：

```bash
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'TestCategory=Batch|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~ProbeExecutionContextTests|FullyQualifiedName~PlaybackOptimizerTests|FullyQualifiedName~ConfigurationTests'
python3 -m unittest discover -s tests -v
```

首次或依赖变更先执行下节 locked restore。聚焦覆盖 AC-T2～T7 与既有播放权限／保存／准入；Python 保护隔离工具、治理与新增批量脚本的恢复／脱敏边界。新增工具回归须被该 discover 命令实际发现。

本 Task 新增 `scripts/run_isolated_batch_integration.py`（当前不存在，属于交付物），复用现有工具能力；必须提供默认全部和 `--scenario stop`、`--scenario sharing` 两个可独立复现入口。进入实机阶段可先执行对应场景，全部门槛仍保留：

```bash
python3 scripts/run_isolated_batch_integration.py --scenario stop
python3 scripts/run_isolated_batch_integration.py --scenario sharing
```

### 最终检查点门槛

对最终可执行候选运行以下完整 T4；更改产品、测试、工具、依赖或运行输入后重新满足对应最终候选门槛：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py
python3 scripts/check_governance.py
git diff --check
```

- C# 全套包含全部新 Batch 用例、十万模拟候选集合／分批对象及现有解析／决策、SQLite／保存失败、DI／完整委托、权限／多源／调用者响应、开始／完成重查／资源回归。模拟记录峰值批次完整对象／消费者／活动 Task、全部 ID／去重／排序及原生临时分配与获取耗时；不用模拟行数代替真实库规模。
- 既有默认隔离脚本继续执行完整播放／失败／重启回归。新默认批量脚本实际执行 AC-T1～T7 的代表性任务发现／手动／真实定时／触发器重启、范围保存／多库 ID 获取与多批多版本、首次信任与变化／失败／恢复、新地址重启、两方向共享／混合上限、真实原生停止与收尾、禁用／关闭播放检查、状态库不可用修复；输出分场景结果及进度／统计／调用／原生保存／SQLite 对账。真实定时须观察任务实际自动运行，接口返回成功或源码定位不能替代。
- 新脚本只使用仓库隔离 Compose project、临时库／手写 STRM 和本地媒体。运行前保存配置／触发器／夹具身份；finally 恢复触发器、配置、STRM／媒体及原生地址，移除本轮临时库条目，证据核对恢复。准备／停止的极窄竞争以确定性屏障证明，实机证明实际未开始撤销及开始后收尾；未对 Jellyfin 内部数据库注入保存故障仍如实 NOT RUN，独立保存失败控制不可省。
- 文件／锚点链接及 CURRENT／TARGET 事实核对只涉及本 Task 改动；不把完成报告改成已关闭 Slice。HTML 页面加载／浏览器交互的 RO-7 门槛保留给后续管理员页面旅程与独立 Slice Final，不能称本 Task 已满足全部 Slice。

### B 独立验证

审查真实 `Task Base..Developer Head`、固定原生查询／导出／worker／保存源码及原始日志／计数。独立运行上述 Batch／Coordinator／Context／Playback／Configuration 聚焦命令；全套输入匹配的 restore／build／test／format／Python／既有默认实机可以核验后明确复用，缺日志、输入不符或矛盾须重跑。

独立复现以下关键控制，使用本 Task 提供的准确测试名／命令并记录，不由 Developer 的 PASS 标签替代：

1. 重复候选／同名／跨库去重、alternate 查询过滤、对象批次乱序／缺失／额外返回、多库范围变更／删除、集合固定后新增下轮发现及十万候选的对象／消费者上限；候选 ID 到逐源统计换算对账，真实原生获取／批次读取与同步查询停止边界有原始证据。
2. 停止先确认禁止匹配调用、实际开始先发生保留执行／保存／提交；立即获许可／准备 await 后停止不漏启动；仅批量已开始任务收尾后 Cancelled，本轮资源归零。真实停止场景同时复现收尾期间手动再次运行及定时触发不启动新轮、结算后新轮可运行且不重复探测已成功源。
3. 已加入 running 的共享成功保留本次可靠关联；已完成／仅准备的结果不冒充运行中共享；SQLite 提交竞争拒绝／写失败不报成功且停止后续批量。
4. 保存失败使用与旧流相同的媒体元数据对照，拒绝新基线且允许修复重试；播放 false 及原生自身取消异常回归。

真实实例独立运行 `python3 scripts/run_isolated_batch_integration.py --scenario stop` 和 `python3 scripts/run_isolated_batch_integration.py --scenario sharing`，至少分别核对真实停止／结算、两方向共享与实际调用数。新默认批量全部运行的定时／范围／恢复／重启等其他场景，匹配原始产物后可明确复用；若这两个入口不能独立可靠运行，证据缺口留同一 Task 修正。

### 证据与重跑规则

每个测试候选稳定保存在 `.git/validation-evidence/<完整源码SHA>/<run-id>/`，包含索引、准确命令／cwd／SDK、源及未提交内容身份、锁／镜像／脱敏范围与夹具／选择／并行／重试设置、部署产物摘要、退出码／计数／耗时及首次失败和每次重跑。配置及触发器前后身份、状态／进度时间线、实际开始及最大并发、批次完整对象／消费者／全部身份和原生获取临时内存峰值、逐源可靠保存／提交与资源结算必须可核验。保留到 A 最终决定；仅本机可访问，不声称远程可读。

记录只暴露假媒体身份或 URL 摘要，原生任务异常对外脱敏且不带包含私有数据的 inner exception。报告与实现分检查点记录真实 Head，不预填自身提交 SHA。带工作区改动的运行证明内容与提交候选相同；纯文档后继核对全部可执行／配置输入并重跑消费文档的治理／链接／差异检查。最终验证后可执行变更使 T4 候选证据失效；改变合同义务先交 A，普通修正留在 Task 3.1。

## 非目标

- 完整 HTML 配置页、浏览器加载／五项保存／错误提示与页面操作恢复旅程；本 Task 必须交付范围后端和可操作的原生配置 API／说明，不能移出校验义务。
- 十万真实库性能、完整扫描增删并发压力、广泛格式／客户端、外部 JellyfinProxy／OpenList 联调、发布 ZIP 和跨版本兼容；均保留 Slice 4。
- 独立调度、运行／停止按钮、扫描后自动触发、持久化任务状态／媒体流副本、新指纹表／字段、路径单独更新器、另一套 FFmpeg、并发热调整或通用 FullRefresh 性能改造。
- 生成程序、OpenList API／远程内容哈希／代理改造、生产配置／媒体操作、无关重构、推送或历史重写。
- 修改 Slice／Roadmap／稳定需求、替 A 最终审查或宣布 Slice 关闭。

## Developer Completion Report

- Changed Files：新增 `Services/BatchProbeTypes.cs`（批量停用边界、可靠结果与计数枚举）、`Services/BatchLibraryScope.cs`（范围解析与原生候选源）、`Services/BatchCheckRunner.cs`（固定候选集、分批对象、固定消费者与统计）、`Tasks/StrmProbeScheduledTask.cs`（原生计划任务）、`tests/.../BatchCheckTests.cs`、`scripts/run_isolated_batch_integration.py`、`tests/test_isolated_batch_integration.py`；修改 `PluginConfiguration.cs`（第五项批量范围）、`Services/IPlaybackSettings.cs`、`Services/StrmPlaybackOptimizer.cs`（批量准入与可靠结果）、`ServiceRegistrator.cs`、两个测试夹具与 `PlaybackOptimizerTests`／`MediaSourceManagerProxyTests`。未提交 `TASK.md` 本身。
- Implemented：原生 `IScheduledTask`／`IConfigurableScheduledTask` 任务「STRM 媒体信息检查」，空默认触发器；默认全部／显式库范围的保存后端与运行前范围快照；原生 `GetItemIds` 一次取得候选 ID、Guid 排序去重固定本轮集合、`GetItemList(ItemIds=本批)` 每批最多 128、每批最多 8 个固定消费者、整批结算后读下一批；批量源检查复用解析、决策、`ProbeCoordinator`、原生探测与条件提交，批量从不原生委托、从不升级 `allowMediaProbe`；单一停止／开始边界保证停止确认后不启动、已实际开始则完成并可用 `CancellationToken.None` 提交；原生停止后先等待结算、释放资源、输出可对账统计再抛取消异常；状态库故障停止后续批量并报告不可用；脱敏汇总日志不依赖详细日志。
- Tests and Results：证据索引 `.git/validation-evidence/c5192ba1e2bf1e23929b33919597d7dca34a1f50/developer-final-t4-20261014-221222/INDEX.md`。锁定 restore PASS；Release build 0 警告 0 错误；C# 全套 138/138（含 26 项新增 `TestCategory=Batch`）；format PASS；Python 35/35（含 4 项新增批量脚本守护回归）；治理 PASS；`git diff --check` PASS。真实隔离：默认播放脚本 PASS；新批量脚本 `all`（任务发现／无默认触发／手动运行／触发器重启持久化／新 STRM 首次信任／变化提交／重复零提交）PASS；`--scenario stop` 真实原生停止记录 `cancelled`、已开始探测提交、下一轮可运行 PASS；`--scenario sharing` 批量与播放共享同一次真实慢探测（slow 请求 1）PASS。全部夹具、触发器与地址已恢复。
- Decisions：批量任务注入真实原生 `IMediaSourceManager` 实现而非播放代理，避免批量探测重入播放入口；候选 ID 以 `Guid` 比较顺序固定，不依赖名称或原生分页；停止边界集中在 `BatchStopSignal` 一把短锁，先确认停止则不启动、开始后 `CancellationToken.None` 完成提交；批量共享后重新读取当前源与指纹重判，不把等待返回当作成功；范围与批量读取均经原生库关系重核。
- Remaining In-Slice Work：完整 HTML 配置页／浏览器交互旅程、真实定时（墙钟）触发、代表性真实多库多批多版本逐源对账与十万真实库压力、单独 Slice Final 仍未完成；本次新增验收均如实按分层证据记录。
- Risks / Deviations：真实定时触发未观察墙钟触发（仅验证触发器持久化）；Jellyfin 内部数据库保存故障实机注入仍 NOT RUN（沿用既有边界）；十万候选仅确定性模拟，不代表真实大库性能。无产品 PASS 声明。
- Head SHA：`c5192ba1e2bf1e23929b33919597d7dca34a1f50`。

若实施产生新的可复用方法，提供少量经验候选供 A 收尾合并；本次规划不向经验文档写历史或虚构验收结论。

## Developer Fix Completion Report（FIX REQUIRED 修正后）

- Fix Base：`c5192ba1e2bf1e23929b33919597d7dca34a1f50`（上一轮 Developer Head）；同一 Task 3.1 修正，Task Base、Goal、Scope、High／T4、验收与必要测试均不变。
- Changed Files：修改 `Services/ProbeCoordinator.cs`（把 owner 的本次条件提交结果随共享结算传播）、`Services/StrmPlaybackOptimizer.cs`（已加入运行中探测的停止收尾、共享可靠成功关联、执行准入范围重核）、`Services/BatchCheckRunner.cs`（拒绝额外／重复返回对象、已故障状态库报告不可用、候选获取未完成不发布总数、单调进度、重复／实际调用／耗时计数）、`Services/BatchLibraryScope.cs`（`IBatchScopeVerifier` 与 `ILibraryIdProvider`）、`PluginConfiguration.cs`／`Plugin.cs`／`ServiceRegistrator.cs`（保存时校验所选库真实存在）、`Tasks/StrmProbeScheduledTask.cs`（汇总扩展）、`tests/.../BatchCheckTests.cs`、`tests/.../ConfigurationTests.cs`、`scripts/run_isolated_batch_integration.py`、`tests/test_isolated_batch_integration.py`。未提交 `TASK.md` 本身。
- Fixed：BR-1 已加入 running 的共享探测在批量停止后仍以 `CancellationToken.None` 等待本次执行、保存、验证与条件提交完成，停止只结束对仍在准备 owner 的等待；BR-2 `ProbeCoordinator` 传播本次条件提交结果，等待者仅当共享 owner 本次已提交且当前版本一致时计可靠成功；BR-3 批次只接受请求 ID，额外／重复对象被拒，执行入口与取得许可后的准入均重核当前库关系，越界对象计 missing；BR-4 已 latch 的与运行中触发的状态库故障都置 `StoreUnavailable` 并计检查阶段未完成，任务抛故障而非静默 Completed；BR-5 候选获取被停止／禁用打断时不发布完整候选总数，进度在并发消费者下单调，新增重复 ID、实际匹配探测调用次数与获取／批次读取耗时；BR-6 保存时通过 `ILibraryIdProvider` 校验显式选择只引用真实存在的库；BR-7 新批量脚本加入真实墙钟定时、scope／failure 场景、两方向共享、收尾期再次运行控制与配置／触发器恢复校验，十万候选测试物化真实对象并断言消费者上限；BR-8 新候选重新生成原始证据。
- Tests and Results：证据索引 `.git/validation-evidence/753f7952bd9eac2857f9dc1b98c0ad92a8a33021/developer-fix-t4-20261014-162650/INDEX.md`。锁定 restore PASS；Release build 0 警告 0 错误；C# 全套 145/145（含 32 项 `TestCategory=Batch`）；format PASS；Python 39/39；治理 PASS；`git diff --check` PASS。B 六项 ReviewerControl 对修正源码独立复现 6/6 PASS。真实隔离：默认播放脚本 PASS；批量 `all`（发现／无默认触发／手动／真实墙钟定时实际触发／触发器重启持久化／新 STRM 首次信任／换 URL 提交并保留 SHA-1／重复零探测／重启后地址）PASS；`--scenario stop` 真实 `cancelled`、收尾期再次手动不启动新探测、已开始提交、下一轮可运行 PASS；`--scenario sharing` 批量先开始与播放先开始两方向各只一次真实慢探测 PASS；`--scenario scope` 两库范围、失效库保存拒绝（400）、禁用不新增探测 PASS；`--scenario failure` 状态库不可用任务 `failed`、无新探测、修复重启后 `completed` PASS。全部夹具、配置、触发器与地址已恢复并校验。
- Remaining In-Slice Work：完整 HTML 配置页／浏览器交互旅程（后续连贯单元）；十万真实库压力与完整扫描压力留 Slice 4。真实墙钟定时已观察。
- Risks / Deviations：Jellyfin 内部数据库保存故障实机注入仍 NOT RUN（沿用既有边界）；十万候选为确定性模拟，不代表真实大库性能。无产品 PASS 声明。
- Head SHA：`753f7952bd9eac2857f9dc1b98c0ad92a8a33021`。

经验候选（供 A 收尾合并，不写入经验文档）：共享等待返回不等于本次可靠成功，必须由执行 owner 在结算时把本次条件提交结果与稳定版本一起传播给等待者；旧指纹行存在不能证明新版本已提交。

## Developer Second Fix Completion Report（第二轮 FIX REQUIRED 修正后）

- Fix Base：`753f7952bd9eac2857f9dc1b98c0ad92a8a33021`（上一轮 Developer Head）；同一 Task 3.1 修正，Task Base、Goal、Scope、High／T4、验收与必要测试均不变。
- Changed Files：修改 `Services/BatchProbeTypes.cs`（`FingerprintStoreFailureStage` 阶段化故障异常、`BatchStopSignal.AbortProbe` 回滚被协调器拒绝的临时开始计数）、`Services/BatchCheckRunner.cs`（状态库故障按阶段计数、集合完整后停止保留 N0／未读取、获取失败保留停止原因、`ResolveOwnSource` 拒绝不匹配单源、获取／批次读取耗时与分配及批次读取次数）、`Services/StrmPlaybackOptimizer.cs`（已加入运行中探测失败结算为探测未完成且不在同轮重试、`PickOwnSource` 拒绝不匹配单源、开始计数回滚）、`Services/BatchLibraryScope.cs`（`IsInScope` 经原生 `GetItemById` 重读当前对象并拒绝删除／改类型／移出范围）、`Tasks/StrmProbeScheduledTask.cs`（汇总新增分配与批次次数）、`tests/.../BatchCheckTests.cs`、`scripts/run_isolated_batch_integration.py`、`tests/test_isolated_batch_integration.py`。未提交 `TASK.md` 本身。
- Fixed：BR-1／BR-2 已加入 running 的同源共享失败现按探测未完成结算（不撤销、不重试、不计成功），停止后已加入失败亦计探测未完成；BR-3 `ResolveOwnSource`／`PickOwnSource` 不再把唯一但 ID 不匹配的源认领为自身源，`IsInScope` 经原生当前对象重核范围（删除／改类型／移库均拒绝）；BR-4 状态库故障按阶段区分，探测已实际开始后的提交／执行故障计探测未完成并保留在需要分母，决策读取故障仍计检查阶段未完成；BR-5 完整集合后停止保留候选总数并把未读取候选计 `Unread`，同步查询中确认停止后的获取失败保留 `StopRequested`，`AbortProbe` 避免被拒开始虚增实际调用数，汇总新增候选获取／批次读取耗时与分配及批次读取次数；BR-6 `--scenario scope` 现覆盖真实两库显式部分范围、133 候选多批、合并多版本、范围外库零处理、固定集合后新增下一轮发现、切换范围、失效库拒绝（400）与禁用零探测，`restore_state` 重新发布有效配置并重启校验有效内存配置；BR-7 `--scenario stop` 用独立延迟请求 ID 逐源对账已开始提交／未开始撤销／下一轮不重复，收尾窗口核对任务状态、查询入口时间线与探测计数，默认 `suite` 在同一会话运行全部场景，`--scenario failure` 核对任何媒体请求均未启动；BR-8 新候选重新生成完整原始证据。
- Tests and Results：证据索引 `.git/validation-evidence/71a397007827fe9b086838d6a4495e63b7d20485/developer-fix2-t4-20261015-082721/INDEX.md`。锁定 restore PASS；Release build 0 警告 0 错误；C# 全套 153/153；format PASS；Python 43/43；治理 PASS；`git diff --check` PASS；B 原六项 ReviewerControl 与六项 RereviewControl 独立复现 12/12 PASS。真实隔离：默认播放脚本 PASS；批量默认 `suite` 单会话运行 discovery／stop／sharing／scope／failure 全部 PASS（逐源对账、多批 133 候选、两方向共享各一次实际调用、状态库故障无任何媒体请求、恢复重启 completed）。全部夹具、配置、触发器与有效内存配置已恢复并校验。
- Remaining In-Slice Work：完整 HTML 配置页／浏览器交互旅程（后续连贯单元）；十万真实库压力与完整扫描压力留 Slice 4。
- Risks / Deviations：Jellyfin 内部数据库保存故障实机注入仍 NOT RUN（沿用既有边界）；十万候选为确定性模拟，不代表真实大库性能。无产品 PASS 声明。
- Head SHA：`71a397007827fe9b086838d6a4495e63b7d20485`。

经验候选（供 A 收尾合并，不写入经验文档）：同源共享失败的结算取决于开始边界而非等待结果——已实际开始的失败按本轮探测未完成结算且不在同轮重试，仅准备阶段的失败才可重判；状态库故障必须携带发生阶段，否则会把已决定需要探测的候选错误移出分母。

## Developer Third Fix Completion Report（第三轮 FIX REQUIRED 修正后）

- Fix Base：`71a397007827fe9b086838d6a4495e63b7d20485`（上一轮 Developer Head）；同一 Task 3.1 修正，Task Base、Goal、Scope、High／T4、验收与必要测试均不变。
- Changed Files：修改 `Services/ProbeCoordinator.cs`（`ProbeWorkItem.FingerprintStoreUnavailable` 与 `Complete(..., fingerprintStoreUnavailable)` 重载，结算时发布执行阶段状态库故障）、`Services/StrmPlaybackOptimizer.cs`（`JoinBatchSharedAsync` 以本轮实际执行结果结算已加入 running 的候选；owner 准入重读当前项目身份；播放 owner 传递执行阶段状态库状态）、`Services/BatchCheckRunner.cs`（消费者先重读当前对象并使用当前项目／源键、部分获取保留已测计数与耗时、`CandidateSetCapacityBytes`／`CandidateTotalKnown`、获取失败保留停止原因）、`Services/BatchLibraryScope.cs`（`IBatchScopeVerifier.GetCurrentItem` 与 `LibraryBatchCandidateSource` 实现、`IsInScope` 拒绝主版本变更）、`Tasks/StrmProbeScheduledTask.cs`（脱敏汇总新增 `total known`／`candidate set capacity`，新增 `STRM media information check entered` 入口标记）、`tests/.../BatchCheckTests.cs`、`scripts/run_isolated_batch_integration.py`、`tests/test_isolated_batch_integration.py`。未提交 `TASK.md` 本身。
- Fixed：BR-1／BR-2 已加入 running 的探测现完全按本轮执行结果结算：`Committed=false`、文件再变或执行阶段状态库故障均计探测未完成（故障同时置 `StoreUnavailable`），停止不把已开始结果改为撤销，且不在同轮重试；仅 preparing 等待仍独立重判，正常共享成功与后续新请求的最新输入检查保持。BR-3 消费者先经 `GetCurrentItem` 重读当前对象，用当前项目（PrimaryVersionId）／源键／自身源进行决策、协调与提交；`IsInScope` 拒绝主版本变更；owner 准入也重读当前项目身份。BR-5 部分获取失败保留已取得的 raw／重复数与真实耗时，`CandidateTotalKnown=false` 明确未知总数，完整获取后停止保留 N0／未读；新增 O(N) 身份容量测量并随汇总输出；`AbortProbe` 保留。BR-7 新脚本用逐 ID 计数而非集合差集核对下一轮不重复；stop 场景加入 `batch_run_entries` 入口时间线证明收尾期未实际启动新轮；新增 `--scenario shared_stop`（已加入播放探测时停止、已开始提交、独立播放继续）与 `--scenario mixed`（不同源各探测一次、独立 FullRefresh 不被池阻塞）；scope 场景核对真实分支（need_probe＝actual_probe_calls、FirstTrust=0）与 canonical item_id＋source_key 唯一；禁用分支核对所有媒体路由；清理失败不再 `except: pass`，而是进入最终失败。BR-8 新候选重新生成完整原始证据。
- Tests and Results：证据索引 `.git/validation-evidence/5d7b48f03b566e0253d397be74c1eabbe11cdda5/developer-fix3-t4-20261015-104716/INDEX.md`。锁定 restore PASS；Release build 0 警告 0 错误；C# 全套 162/162（含 49 项 `TestCategory=Batch`）；format PASS；Python 46/46；治理 PASS；`git diff --check` PASS；B 原 17 项 ReviewerControl／RereviewControl／Review3Control 独立复现 17/17 PASS。真实隔离：默认播放脚本 PASS；批量默认 `suite` 单会话运行 discovery／stop／shared_stop／sharing／scope／mixed／failure 全部 PASS（真实 `cancelled` 后已开始提交／未开始撤销、收尾期零新入口、下一轮仅重检撤销源；共享停止中已加入成功计可靠成功且撤销 0、独立播放 200；混合 3 源各一次实际调用、独立 FullRefresh 0.026 s；133 候选 2 批多版本 canonical 关联；状态库故障任务 `failed` 无任何媒体请求、修复重启 `completed`）。全部夹具、配置、触发器与有效内存配置已恢复并校验，清理失败会进入最终失败。
- Remaining In-Slice Work：完整 HTML 配置页／浏览器交互旅程（后续连贯单元）；十万真实库压力与完整扫描压力留 Slice 4。
- Risks / Deviations：Jellyfin 内部数据库保存故障实机注入仍 NOT RUN（沿用既有边界）；十万候选为确定性模拟，不代表真实大库性能；本次未单独运行 `--scenario` 分场景入口（由同一 `suite` 会话覆盖）。无产品 PASS 声明。
- Head SHA：`5d7b48f03b566e0253d397be74c1eabbe11cdda5`。

经验候选（供 A 收尾合并，不写入经验文档）：已加入运行中探测的结算必须以执行 owner 发布的本次提交／故障结果为准，等待返回或文件再变都不能作为同轮重试或撤销的依据；原生对象重读只有把返回对象用于后续项目身份、源键与取源，才构成有效身份重核。

## Developer Fourth Fix Completion Report（第四轮 FIX REQUIRED 修正后）

- Fix Base：`5d7b48f03b566e0253d397be74c1eabbe11cdda5`（上一轮 Developer Head）；同一 Task 3.1 修正，Task Base、Goal、Scope、High／T4、验收与必要测试均不变。
- Changed Files：修改 `Services/StrmPlaybackOptimizer.cs`（匹配编码器调用处重读当前原生项目身份并在准备期变化时中止批量探测）、`Services/BatchProbeTypes.cs`（`BatchIdentityChangedException`、`BatchStopSignal.StoppedTimestamp`）、`Services/BatchCheckRunner.cs`（状态库 latch 报未知总数、身份成本估算／保留内存／同步查询停止延迟测量）、`Services/ProbeCoordinator.cs`（`PermitWaitBarrier`）、`Tasks/StrmProbeScheduledTask.cs`（脱敏汇总改用估算／保留／停止延迟字段）、`scripts/isolated_media_server.py`（参数化延迟路由）、`scripts/run_isolated_batch_integration.py`、`tests/.../BatchCheckTests.cs`、`tests/test_isolated_batch_integration.py`。未提交 `TASK.md` 本身。
- Fixed：BR-3 `ExecuteProbeAsync` 在 `TryBeginProbe` 后、`TryMarkStarted` 前重读当前原生对象；对象消失／改类型／主版本变化即中止原生调用（`BatchIdentityChangedException`），放弃预留并计 `Missing`，旧项目基线不再被覆盖。BR-5 latch 状态库报 `CandidateTotalKnown=false`，与完整空集合区分；用文档化尺寸模型 `CandidateSetEstimatedBytes` 与实测 `CandidateSetRetainedBytes`（`GC.GetTotalMemory(true)` 前后差）替代误导性的 capacity 命名，并新增实测 `StopQueryReturnLatencyMilliseconds`。BR-7 `--scenario stop` 改用参数化长延迟路由、在收尾窗口内装载真实墙钟触发器，证明手动与定时均不提前进入新轮、排队轮仅在结算后实际运行且只重探被撤销源；`--scenario shared_stop` 覆盖两方向、独立源置于 local 库使批量不处理、证明独立播放确在旧轮 `Cancelling` 期间启动新探测；`--scenario mixed` 用插件自身 running 计数测量批量＋播放跨源重叠峰值并要求恰好达到且不超过默认 2，独立 FullRefresh 仅记排队受理并显式复用默认播放脚本的池饱和刷新完成证据。BR-5 补充准备期身份变化、已知空总数、同步查询停止延迟三个确定性回归，并加 `PermitWaitBarrier` 使等许可用例先确认第二源到达等待。
- Tests and Results：证据索引 `.git/validation-evidence/work-fix4/INDEX.md`。锁定 restore PASS；Release build 0 警告 0 错误；C# 全套 165/165（含 53 项 `TestCategory=Batch`）；format PASS；Python 51/51；治理 PASS；`git diff --check` PASS；默认播放隔离脚本 PASS；批量默认 `suite` 单会话 discovery／stop／shared_stop／sharing／scope／mixed／failure 全部 PASS（stop 原生 `Cancelled` 后已开始提交／未开始撤销、收尾窗口定时不启动新轮、结算后排队轮只重探撤销源；shared_stop 两方向独立播放实际启动新探测、已加入计可靠成功／撤销 0；mixed 峰值 running＝2 不超默认；scope 133 候选／2 批、范围外零处理、多版本 canonical；failure 状态库不可用任务 `failed` 无新探测、修复重启 `completed`）。全部夹具、配置、触发器与有效内存配置已恢复并校验；构建产物与部署 DLL SHA-256 一致（`9b0f0c36…`）。
- Remaining In-Slice Work：完整 HTML 配置页／浏览器交互旅程（后续连贯单元）；十万真实库压力与完整扫描压力留 Slice 4。
- Risks / Deviations：Jellyfin 内部数据库保存故障实机注入仍 NOT RUN（沿用既有边界）；十万候选为确定性模拟；mixed 独立 FullRefresh 仅记原生排队受理，真实池饱和刷新完成证据复用默认播放脚本。无产品 PASS 声明。
- Head SHA：`c8fffe3eda2e2806e172ed4128b19965253dc8c3`。

经验候选（供 A 收尾合并，不写入经验文档）：准备期身份变化必须由实际开始边界的当前原生重读发现，仅前置准入检查无法覆盖；实测证据要区分“估算”“实测保留”与“实测延迟”，命名不能把估算冒充峰值。

## B Review Result

Reviewed: b86d9c17d7f915108072f54ee098f0f5543fe093..5d7b48f03b566e0253d397be74c1eabbe11cdda5
Fix Reviewed: 71a397007827fe9b086838d6a4495e63b7d20485..5d7b48f03b566e0253d397be74c1eabbe11cdda5
Report Checkpoint: 56eea4f97f395c9434705a04727f171c2c8e7b40
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER FIXES THE SAME TASK 3.1

2026-10-15，B 完成 AGENTS 必读清单与 B 经验；初始工作区 `## main`、无已有改动，治理 PASS。已提交 Slice／Roadmap／稳定需求／开发流程自上轮 B 检查点后没有变更；完整 Task Base..Head 结合前轮审查重核，第三轮修正涉及的 8 个产品／测试／工具文件及仅空白的后继修正逐项审阅。候选之后仅 TASK.md 完成报告／计数更正，不含产品变化。Task ID、Base、Goal、Scope、High／T4、AC-T1～T8 与必要测试继续有效；当前没有 Contract 无法满足的事实，不交 A RESCOPE，不规划下一 Task。上轮完整 B 决定保留于 `0601c841d0250dbf47b848e64e9e7954e852c551:TASK.md`，首次失败与本轮证据均保留。本轮只提交 TASK.md。

### 已确认的修正

- 前三轮 17 项独立控制全部通过。已加入 running 的正常返回但未提交、停止后的非提交、Manifest 再变均计 ProbeIncomplete，且不在同轮重试；执行阶段状态库故障随 owner 结算传播。原 BR-1／BR-2 的已复现重试／误撤销问题不再列为当前失败。
- 消费者重读并使用当前对象取源、计算 PrimaryVersionId／source_key；准入检查当前主版本。原读取前主版本变化控制通过，不匹配唯一源保护保留；尚未覆盖原生准备阶段发生的变化，见当前 BR-3。
- 部分 ID 获取失败保留 raw 计数与耗时，新增 CandidateTotalKnown；完整集合停止口径保留。逐 ID 请求次数取代集合差集，成本解析保留小数且缺字段实际拒绝；Python 恢复守护测试已 mock API／restart，独立 46/46 在约 3 秒内完成，没有上轮未隔离的重启调用。
- 临时条目清理失败现汇入最终失败；suite 包含 discovery／stop／shared_stop／sharing／scope／mixed／failure。Developer 原始日志有实际停止 2 项提交／1 项撤销、播放先开始的 shared_stop 可靠成功 1／撤销 0／批量调用 0、独立播放 200、普通两方向共享、133 候选／2 批及两版本 canonical item_id 关联、禁用所有媒体路由零新请求及状态库恢复。新事实予以保留，不重复沿用已解决的上一轮描述。
- Developer 全套 162 C#／46 Python、restore／build／format、默认播放和批量 suite 的原始输出及精确命令存在。00 输入清单的 8 个源码／测试／工具与两个锁文件摘要均匹配当前候选；报告中 build／deployed DLL 摘要相等的描述与原记录不一致，B 已用当前相同可执行输入显式设置候选 SourceRevisionId 重建，得到与部署 DLL 完全一致的 `f72f73f76b62e401e1bbd7152a355edfcba3aa70576b6ea59534cada1bffd708`，故不把可解决的摘要记录错误另立 P1。B 未部署或重跑实机。

### 当前 P1 阻塞（均属原 Task／BR 义务）

1. **BR-3：原生准备期间的当前源／主版本变化仍可覆盖旧关联（AC-T2／T3／T4／T5）**。`AdmitBatchOwnerAsync` 在原生 GetPlaybackMediaSources 准备前检查主版本；后续真正匹配调用的开始边界只核对 stopSignal／Coordinator，没有把准备期间变更的当前原生身份带回验证。独立 `ReviewerPreparingPrimaryVersionChangeMustKeepTheOldBaseline` 先建立旧指纹，再改变 URL；在 fake 原生准备完成、匹配编码器调用之前，用真实 LibraryBatchCandidateSource 的 fake 原生查找返回同 ID／类型／库／路径但新 PrimaryVersionId 的对象，复现 StartedProbes=1、ReliableSuccess=1，旧 project＋source 的可信指纹被新 URL 覆盖。控制不取消实际执行，也没有修改产品。须闭合原审查已要求的“准备期间身份变化”边界，确保实际取源、协调、决策及提交使用同一当前关联，或者拒绝变化候选留下一轮；不能只在取得许可时检查。当前路径变化的处理也须与该关联规则一致。已实际开始后的正常收尾仍保留，不引入人为执行取消源；不能以回滚原生已保存结果代替指纹条件保护。

2. **BR-5：未知总数与身份资源观测仍未完全闭合（AC-T2／T7／T8）**。独立 `ReviewerLatchedStoreMustNotReportAnUnqueriedLibraryAsKnownEmpty` 复现：状态库故障 latch 后下一轮未调用任何 ID 查询，却返回 CandidateTotalKnown=true、CandidateCount=0；测试库实际仍有候选。须保持“未获取，未知”与“完整空集合”区别，保留不可用与适用停止原因。新增 CandidateSetCapacityBytes 是 `List.Capacity×16＋HashSet.Count×24` 公式，集合 Count 不是底层容量，也未计 bucket／扩容／原生临时对象；不能将它称为实测容量或峰值。十万用例仍未输出完整身份结构容量、峰值内存、分阶段原生临时成本与同步查询停止到返回延迟。按原 Task 在测试／稳定证据报告这些数据，区分测量与估算即可，不要求新增产品 UI／持久化状态或总内存恒定承诺。现有累计线程分配／小规模容量正数断言不代替原门槛。

3. **BR-7／BR-8：停止／混合及运行中范围变化的原实机门槛仍缺证明（AC-T2／T4／T5／T8）**。已有新场景不再当作完全缺失；下列具体缺口仍留同一 Task：

   - stop 已观测实际 Execute 入口数，解决了只看完成 summary 的弱断言；但场景仍没有安排收尾窗口内的定时触发，所以不能称定时再运行边界已实测。shared_stop 只有播放先开始方向；独立播放调用虽返回 200，却使用已接受未变源且不要求新探测，也未保存调用起止时旧轮仍 Cancelling 的时间线。须验证原定两方向停止共享、独立播放探测确在旧轮收尾窗口继续，以及手动／定时不提前进入新轮。
   - mixed 的前三个源全部由批量处理，代码没有在同一阶段发起不同源的播放请求，也未计算探测开始／完成重叠或最大 running／许可数；actual_probe_calls=3 只能证明总数，不能证明播放／批量混合峰值不超过启动值。其 FullRefresh 对照仅启动一个播放探测，默认两许可并未饱和；`force_full_refresh` 返回 204 只是原生排队受理，0.026 秒不是刷新实际完成。原默认播放脚本已有池饱和／原生独立刷新证据，可明确复用相应覆盖；新混合上限仍须实际测量，不把弱断言产出的布尔值扩张为 PASS。
   - scope 的新增仍发生在上一轮 run_task 完成后，没有运行中集合固定后的增删／移库证据；确定性控制及代表性实机应补原约定场景，不要求 Slice 4 的完整扫描压力。canonical 行关联断言已改善，但报告仍须保留逐源、原生地址／主流、统计／进度与配置／触发器／夹具前后身份。
   - 批量特有的立即获许可未登记／准备 await 与仅 preparing 等待、保存拒绝／原生自身取消、1／2／8 的原覆盖仍须提供准确用例映射。新增 BatchStopWhileWaitingForAPermitRevokesWithoutStarting 在第一个源一开始就取消，未用屏障确认第二源已进入等待，不能单凭名称证明等待路径。已有 Coordinator／Playback 测试可按真实覆盖复用，不能因全套通过推定全部新增 Batch 分支已测。无需机械重跑同一覆盖用例或新增执行取消机制。

### B 独立验证与证据复用

索引：`.git/validation-evidence/5d7b48f03b566e0253d397be74c1eabbe11cdda5/b-review4-20261015/INDEX.md`（仅本机可访问）。

- PASS：指定 Batch／Coordinator／Context／Playback／Configuration 聚焦 121/121、0 failed／skipped、退出 0；01-focused.log/json。
- PASS：独立 controls locked restore；02-controls-restore.log/json。前三轮控制 17/17、0 failed／skipped；03-prior-controls.log/json。
- FAIL：04-preparing-identity.log/json 首次身份控制 1/1 失败；08-final-controls.log/json 最终合并为旧控制 17 PASS、新控制 2 FAIL、0 skipped，退出 1。controls 源码／项目／锁保留在稳定目录，使用临时 STRM／假原生执行保存及内存指纹，不能称真实 Jellyfin 竞态。
- PASS：Python 46/46、退出 0；05-python.log/json。候选 SourceRevisionId 独立重建 0 警告／错误，产物与部署 DLL 全字节一致；07-candidate-rebuild.log/json 及 07-artifact-reconciliation.json。普通 B 测试编译 DLL 带报告 HEAD，单列于 06-artifacts.json，没有冒充相同部署产物。
- Developer 01～12 原始输出、JSON／统计及脚本已核阅，接受它们“实际运行了什么”的事实；不签作所有 AC 通过。00-build 摘要陈旧已由 B 重建补证，后续报告应修正原描述。治理、差异、文档链接及可执行输入一致性检查见本轮索引。
- NOT RUN（B 本轮）：真实 stop／sharing、其余完整 T4、Slice Final。按流程在确定 P1 后先拒绝；PASS 前仍按原计划独立复现这两个入口及关键行为。未改产品、已提交测试／工具、部署、生产实例或隔离运行配置。

### Slice 全部 Required Outcomes / Surfaces 重核

| Outcome | 本轮结果 |
|---|---|
| RO-1 原生入口／定时 | 原生发现／普通墙钟触发／重启有证据；停止收尾期触发仍欠证明。 |
| RO-2 范围／有界对象 | 当前对象初读与多批／多版本已有修正；准备期间身份竞态、运行中集合变化与身份成本仍阻塞。 |
| RO-3 共用可靠结果 | 非提交共享结算已修；旧项目身份仍能被提交覆盖，尚未满足。 |
| RO-4 共享／并发 | 正常两方向共享有证据；混合峰值与新增准入边界未完整验证。 |
| RO-5 停止收尾 | 实际入口标记及播放先开始共享停止已补；两方向／定时窗口／独立新探测证据不足。 |
| RO-6 反馈／恢复 | 部分 ID／故障阶段／清理副作用已改善；未查询总数仍误报已知空，资源／进度证据不足。 |
| RO-7 范围后端／完整页面 | 后端已有范围验证与有效配置恢复；HTML／浏览器旅程未实施，按原非目标不单独阻塞 3.1。 |

Required Surfaces 尚未全部满足；当前没有 Task PASS，不创建 3.2，不运行 Slice Final／提交 Closure Packet，不代替 A 最终审查或关闭 Slice。可复用经验候选：重读验证须覆盖实际原生准备与开始之间的身份变化；累计调用数不能证明混合并发峰值，异步受理不能证明工作完成。仅供 A 收尾合并，不向经验文档写历史。

Developer 在同一 Task 3.1 修正当前 P1，保留原 Base／Goal／Scope／High／T4；以新提交及完整候选证据再交 READY FOR B REVIEW。如果实证无法满足 Contract，再交 A 判定；当前不改变合同、削减必要门槛或把当前义务延期。

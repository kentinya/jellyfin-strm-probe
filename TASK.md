# Task 3.1 — 原生按需批量检查与停止收尾闭环

规划／审查依据 [开发流程](docs/development-workflow.md) 与 [B 经验](docs/agent-experience/task-planner-reviewer.md)；实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。范围 authority 是已提交的 [Slice 3](SLICE.md)，不是后续建议任务。

```text
Task ID: 3.1
Parent Slice: 3
Status: PLANNED
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

- Changed Files：NOT IMPLEMENTED。
- Implemented：NOT IMPLEMENTED。
- Tests and Results：产品候选测试 NOT RUN；本次规划前治理 PASS，仅为合法性检查。实施后逐项填写 AC-T1～T8 的分层结果及稳定证据索引、候选／输入身份、准确命令／计数／耗时、首败／重跑／复用和缺失门槛。
- Decisions：待实施记录原生发现方式、候选查询／去重／Guid 顺序及批次对齐、容量／整批结算、同步查询停止延迟、开始唯一边界及共享可靠结算方式。
- Remaining In-Slice Work：全部新增 RO 尚未验收；预计完整 HTML 配置／浏览器旅程及单独 Slice Final 仍需完成，不能以此预判后续 Task 数量。
- Risks / Deviations：A 已提交候选 ID 集合方案的实质合同变更，B 决定同一 Task 合法调整；剩余风险为原生库／alternate 查询、全部 ID 及临时分配成本、同步查询停止延迟、故障允许探测回退、停止 token 传播及可靠提交结算，无产品 PASS。
- Head SHA：NOT SET。

若实施产生新的可复用方法，提供少量经验候选供 A 收尾合并；本次规划不向经验文档写历史或虚构验收结论。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO — RO-1～RO-7 的新增义务尚未验收
Next: DEVELOPER IMPLEMENTS TASK 3.1
```

当前是新合同上的合法调整计划，不是实施审查 PASS。本轮仅文档，Task Status 保持 PLANNED。Developer 提交完整实现与报告后 B 审查 PASS／FIX REQUIRED；修正通常留同一 Task。PASS 后逐项重核 Slice 全部 RO／Surfaces；满足则停止创建 Task，单独运行 Slice Final 并提交 Closure Packet 给 A，否则只规划剩余连贯用户行为。

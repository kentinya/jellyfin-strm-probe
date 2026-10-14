# Task 3.1 — 原生按需批量检查与停止收尾闭环

规划／审查依据 [开发流程](docs/development-workflow.md) 与 [B 经验](docs/agent-experience/task-planner-reviewer.md)；实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。范围 authority 是已提交的 [Slice 3](SLICE.md)，不是后续建议任务。

```text
Task ID: 3.1
Parent Slice: 3
Status: PLANNED
Task Base: b86d9c17d7f915108072f54ee098f0f5543fe093
Contract Checkpoint: b86d9c17d7f915108072f54ee098f0f5543fe093
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

管理员通过 Jellyfin 原生「STRM 媒体信息检查」手动或定时检查已保存的全部／部分媒体库，不打开播放会话；任务有界分页并按源增量处理，沿用播放的可靠探测／保存／指纹机制。原生停止撤销本任务未开始工作，等待已开始及已加入的运行中探测完成，正确提交有效结果、结算统计，再以 Cancelled 结束。失败可修复后重跑，状态库故障停止批量优化，不变成全库原生刷新。

本 Task 闭合 RO-1～RO-6 的批量运行旅程及 RO-7 的范围配置保存／兼容后端；完整 HTML 配置页及页面操作旅程不在本 Task。不能因暂未提供页面而削减范围校验、停止、失败或统计规则。通过后 B 重核全部 RO／Surfaces；预计剩余连贯单元是完整管理员配置与页面操作／恢复旅程，届时按真实结果规划，不预先创建活动任务。

## 实际缺口与实施范围

### 规划检查与合法性

2026-10-14 开始检查时 `git status --short --branch` 为 `## main`，无已有改动；规划前 `python3 scripts/check_governance.py` PASS。已读 AGENTS.md 全部必读文件、B 经验、Task 模板、测试矩阵和环境交接；核对当前产品／测试、隔离脚本及固定 Jellyfin 源码。HEAD 已提交 ACTIVE 合同，Roadmap 匹配，Slice Base 为 `6da90ab6bd8995d8204ae0b7faf786c823699fe6`，无旧活动 Task，本计划合法。Task Base 取合同激活提交，不移动 Slice Base，不继承 Slice 2 的 Task 身份。

现有能力及必须修补的接缝：

- `Services/StrmPlaybackOptimizer.cs` 的 `CheckSourceAsync`、owner 行动前重判、稳定项目／源身份及原生结果验证可复用；但 Unsupported、禁用、读取故障和准备期间变化均可能允许原生委托。批量必须有独立调用策略，禁止这些分支误探测普通／旧输入或在状态库故障后继续探测。
- `Services/ProbeCoordinator.cs` 已分 preparing／running，并幂等释放许可；`ProbeExecutionContext.MarkCall` 与 `Interceptors/MediaEncoderDispatchProxy.cs` 是匹配编码器调用的开始信号。目前 acquire 立即获许可、准备、开始转换没有批量停止准入合同；`ExecuteProbeAsync` 仍传调用 token，`JoinSharedAsync` 可因等待 token 退出。这些接缝须在同一 Task 与原生停止实证一起完善。
- 现有执行返回 `MediaSourceInfo?`，条件提交竞争失败或 SQLite 写失败仍可能返回媒体源；共享等待后再次读取可能返回 null。不能据此推导批量可靠成功或把共享成功算跳过。需要同源本次执行／提交的内存结算证据及明确的检查结果，不增加持久化探测状态。
- `PluginConfiguration.cs`／`Plugin.UpdateConfiguration` 已有四项配置、原子保存及启动并发值；没有批量范围。复用保存通道和现有失败保护，新增第五项范围后端；HTML 页面仍未实现。
- 现有 112 项 C#、30 项 Python 及 `scripts/run_isolated_plugin_integration.py` 是继承回归；脚本当前无批量入口。旧证据不证明新任务、停止或定时通过。

固定源码 `artifacts/dev-env/source` 的 HEAD 已核对为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`：`ApplicationHost.RunStartupTasksAsync` 使用 `GetExports<IScheduledTask>(false)` 发现任务；`ScheduledTaskWorker.Execute` 正常返回为 Completed、取消异常为 Cancelled，其他异常会写入日志及任务历史。`ILibraryManager` 提供 `GetVirtualFolders`、`GetCount`、`GetItemsResult`／`GetItemList`；`InternalItemsQuery.IncludeAlternateVersions` 必须显式启用，关闭 presentation grouping 本身不足以保留所有版本。`ItemSortBy` 无 Id，原生 `ApplyOrder` 没有保证唯一 ID 尾排序，不能凭空填写 `ItemSortBy.Id` 或把 SortName 当唯一键。

### 一个批量闭环涉及的层

1. 原生任务发现、固定 Key／名称、可配置任务属性与空默认触发器。使用既有 DI 实例；避免类型导出与手工注册产生两个任务，或为批量创建另一个 optimizer／许可池。任务不持有播放会话，不通过 HTTP PlaybackInfo 伪装批量执行。
2. 全部／显式库 ID 配置、旧配置默认全部、服务端保存验证及每次运行的范围快照。显式空、无效或失效库拒绝保存／运行，不扩大到全部；运行中配置更改下次生效。源所属项目与当前库成员关系在执行准入重核，项目被删除／移出范围就撤销，不能沿多版本链接越范围。
3. 目标版本原生媒体查询、物理媒体项到所属媒体源的映射、稳定分页及去重。可在现有服务内抽出共用职责，类名不是验收目标；不另建解析、决策、刷新或指纹链，不从目录枚举替代库查询。
4. 共用源检查的批量调用策略、可靠结果、全局不可用反馈及开始／停止准入。播放仍保留原调用 token、用户／选源／路径替换／false 权限和故障时原生委托；批量不走允许探测的故障回退。批量 PlaybackAutoCheck=false 仍独立执行，Enabled=false 停止分页和新开始。
5. 单个有界生产消费运行、进度／统计和所有完成路径的资源结算。原生任务停止 token 只控制枚举、排队、准备与开始准入；在匹配编码器边界协调停止与开始先后。执行已实际开始、原生保存、版本验证及提交不接批量停止 token；已加入 running 的批量请求也须等待可靠结算。等准备项仅等待后重查，不算共享探测；停止后不能重查再启动新探测。
6. 新批量确定性测试与隔离实机入口，复用现有本地媒体、探测／保存计数、只读 SQLite 核对与恢复工具。更新 Task 完成报告和本 Task 实际实现事实／操作说明；不改变 Slice、Roadmap 或稳定需求。

代码边界：现有插件项目内配置／注册、Services、Interceptors 及新增原生 Tasks；现有 MSTest 项目、必要工具回归；批量隔离工具及必要本地媒体夹具控制。仅当实际依赖需要时更新锁文件，并验证隔离部署加载。

### 停止收尾与再次运行

用户补充要求：收到停止指令后，必须等本轮已实际开始或已加入的运行中探测完成收尾，才允许下一轮批量实际执行。旧轮停止后不再分页或启动新探测；其 `ExecuteAsync` 保持未结束，直到这些工作完成原生保存／验证／条件提交、汇总和本轮资源结算，再抛出停止异常。复用固定版本原生 worker 的 `Cancelling → Idle` 生命周期，不新增插件运行开关、独立按钮或持久化任务状态。等待范围为本轮启动或已加入的执行，不要求全局其他播放探测全部结束。

收尾期间重复手动运行或定时触发不能开始新一轮批量查询／探测；原生调度器可能将定时触发排队，只能在旧轮结算结束后实际运行。原生手动 StartTask 返回 204 本身不证明新轮已启动，验收核对 worker 状态、执行入口及实际查询／探测计数。收尾后再次运行从当前已保存范围重新枚举，沿用新鲜指纹判断，不能恢复已撤销的旧队列。这是现有 RO-5 的明确验收，不改变 Slice 合同。

### 查询计数、检查单位与有界工作

查询从运行时固定的有效媒体库 ID 集合逐库递归读取非文件夹、非虚拟的 Audio／Video 媒体项，显式包含 alternate versions，关闭 presentation／series grouping 和 box-set collapse，不预先按版本协议排除未读取的 STRM。计数使用相同范围／过滤的原生 `GetCount`（无分页参数）；分页用同一过滤和明确排序。去重键为实际 `project_item_id＋source_key`，source_key 为源所属项 ID 的 N 格式；alternate 的 project 使用原生 PrimaryVersionId。每个物理候选最多形成一个所属源单位，原生返回的其他版本不再次展开成工作。无法映射的源明确报告，不能认领默认源或扩大范围。

初始候选估计 `N0 = 各选定库原生候选计数之和`，可能含跨库重复、普通媒体和旧 STRM，不是精确受支持源总数。维护实际原始查询行数、去重候选数、已结算候选数、受支持检查数、不处理数及错误／撤销数；重复行只增原始查询行／重复计数，不再次推进结算或探测。候选为 Supported 的 STRM 才进入优化；Unsupported／普通媒体计不处理、零批量探测。Invalid／Unavailable 的 STRM 尝试按同一源键计检查阶段未完成，并单列“未确认受支持的读取／解析错误”，不能把它们宣称为合格受支持数或普通跳过。已经发现但尚未进入检查即撤销的源只计撤销。

每个所属源单位最多计一次检查；检查数包含明确单列的检查阶段未完成，满足合同统计等式。单位结算推进百分比的分子 `S`（含已结算不处理候选）；分母估计 `E = max(N0, 已发现的去重候选单位数, S)`，多发现候选只增估计。报告 `max(上次值, min(99, 100 × S / max(1, E)))`；只在正常遍历结束、全部工作结算时另报 100%。这表示遍历进度，不能标注为逐源准确总量；静态空范围可直接正常完成。单项失败可结算后继续、正常遍历最终 100%；停止／禁用提前结束／分页或状态库全局失败均不能补满。未知未遍历数量明确为未知。

工作容量目标：单页最多 128 候选、等待队列最多 32 源单位、至多 8 个消费工作及一个枚举工作；消费工作获得全局许可后仍遵守启动时 1～8 上限，不能创建全库 Task。紧凑去重身份集可随发现数量线性增长，单列条目／容量和内存，不能说总内存恒定。原生单项取源的多版本临时数据同样披露，不保留跨全库媒体对象／URL／播放响应。Developer 可选择更小容量；改变以上上限或计数换算须由 B 先记录修订原因。

分页方案须记录实际原生查询参数、排序／相同排序值处理、终止及运行中增删策略。不得只在分页取回后排序便声称全局稳定，不得依赖不存在的 ID 排序。静态同名／相同排序值跨页须无漏重；重复页和无推进异常不能无限循环。若受支持接口无法满足合同，先提交事实给 B／A，不替换为全库物化或弱化 AC-2。

## 验收条件

- [ ] **AC-T1 原生入口（RO-1）**：真实实例仅发现一个目标任务、默认触发器为空，手动执行与管理员设置的真实时间触发均有效；触发器重启持久化且无默认／启动意外运行。无需播放会话，手动运行／停止／时间都由原生任务管理。
- [ ] **AC-T2 范围与有界遍历（RO-2、RO-7 后端）**：默认全部、显式部分、旧配置、空／失效选择保存与运行、每次范围快照及移出／消失安全。静态至少两个库、跨多个页、同排序值、重复页、多版本及音频源确定性覆盖；真实至少两个库、多页、多版本按源对账，范围外／普通／旧／未知协议零批量探测。增删控制安全结束、重跑收敛；十万模拟候选有容量和身份内存实测。
- [ ] **AC-T3 共用可靠结果（RO-3）**：首次信任及未变零探测、不计真实成功；缺主流、同 SHA-1／Size 换 URL、同 URL 有效 SHA-1 变化、不可比 SHA-1 的 Size 变化使用共用原生链。结果／新地址／主流／SQLite 与重启后 PlaybackInfo 一致。成功计数仅关联本次同源真实成功、保存、稳定 Manifest 及条件提交；提交拒绝／失败不伪报成功，恢复可重试。
- [ ] **AC-T4 混合共享（RO-4）**：确定性 1／2／8、准备／排队不共享、立即获许可与完成重查、多版本／调用者隔离。实机批量先开始→播放加入、播放先开始→批量加入都仅一次匹配探测，批量成功与实际调用分别统计；同源排队完成后无重复。不同源混合不超启动上限、保存并发下次启动才生效，独立 FullRefresh 正常；false 播放原权限和基线不升级。
- [ ] **AC-T5 停止与资源（RO-5）**：确定性屏障覆盖分页、满队列、等许可、立即获许可未登记、准备取源 await、准备登记、实际开始／停止双方先发生、已开始仅批量及两方向共享。停止确认后无新实际开始，其他调用者排队不受影响；已开始／已加入工作成功仍提交，原生自身失败／取消异常保留旧基线。任务等到结算／汇总后才抛原生停止异常，最终 Cancelled，非 Completed；页、队列、消费者及本轮 preparing／running／许可归零。真实停止证明未开始撤销与已开始完成；收尾期间重复手动运行及定时触发不实际启动新轮，旧轮结算后可以再次运行并按最新指纹跳过已成功源。独立播放探测不因等待旧批量收尾被禁止。不拿进程杀死或手动 API 的 204 替代真实执行证据。
- [ ] **AC-T6 故障与汇总（RO-6）**：损坏／不可达、Manifest 再变、独立保存失败控制隔离单项；SQLite 读取／提交故障、全局不可用、分页异常及时停止准入并收尾。不可用使用脱敏失败结果（管理员同时停止时保留取消原因及不可用汇总），不自动删库，不通过原生委托继续全库探测。修复重启后重跑成功；单项原生取消不得伪造管理员停止。
- [ ] **AC-T7 可对账反馈（RO-6）**：检查＝跳过＋需要＋检查阶段未完成；需要＝可靠成功＋探测未完成；未完成总数＝检查阶段未完成＋探测未完成。首次信任计跳过，共享源只计一次但必须保留本次成功关联，实际调用次数另计。候选／不处理／重复／撤销／未知未遍历分别标注；原生进度单调且提前结束不补 100%，正常空库可完成。Completed／Cancelled／Failed、计数、保存／提交和日志一致；必要汇总不依赖 DetailedLog，异常及原生任务历史无秘密／私有路径。
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

- C# 全套包含全部新 Batch 用例、十万模拟枚举及现有解析／决策、SQLite／保存失败、DI／完整委托、权限／多源／调用者响应、开始／完成重查／资源回归。模拟记录峰值页／队列／活动 Task、去重集合容量／内存与耗时；不用模拟行数代替真实库规模。
- 既有默认隔离脚本继续执行完整播放／失败／重启回归。新默认批量脚本实际执行 AC-T1～T7 的代表性任务发现／手动／真实定时／触发器重启、范围保存／多库多页多版本、首次信任与变化／失败／恢复、新地址重启、两方向共享／混合上限、真实原生停止与收尾、禁用／关闭播放检查、状态库不可用修复；输出分场景结果及进度／统计／调用／原生保存／SQLite 对账。真实定时须观察任务实际自动运行，接口返回成功或源码定位不能替代。
- 新脚本只使用仓库隔离 Compose project、临时库／手写 STRM 和本地媒体。运行前保存配置／触发器／夹具身份；finally 恢复触发器、配置、STRM／媒体及原生地址，移除本轮临时库条目，证据核对恢复。准备／停止的极窄竞争以确定性屏障证明，实机证明实际未开始撤销及开始后收尾；未对 Jellyfin 内部数据库注入保存故障仍如实 NOT RUN，独立保存失败控制不可省。
- 文件／锚点链接及 CURRENT／TARGET 事实核对只涉及本 Task 改动；不把完成报告改成已关闭 Slice。HTML 页面加载／浏览器交互的 RO-7 门槛保留给后续管理员页面旅程与独立 Slice Final，不能称本 Task 已满足全部 Slice。

### B 独立验证

审查真实 `Task Base..Developer Head`、固定原生查询／导出／worker／保存源码及原始日志／计数。独立运行上述 Batch／Coordinator／Context／Playback／Configuration 聚焦命令；全套输入匹配的 restore／build／test／format／Python／既有默认实机可以核验后明确复用，缺日志、输入不符或矛盾须重跑。

独立复现以下关键控制，使用本 Task 提供的准确测试名／命令并记录，不由 Developer 的 PASS 标签替代：

1. 相同排序值跨页、重复页、alternate 查询过滤、多库范围变更／删除和十万枚举边界；逐源枚举集合与查询计数换算对账。
2. 停止先确认禁止匹配调用、实际开始先发生保留执行／保存／提交；立即获许可／准备 await 后停止不漏启动；仅批量已开始任务收尾后 Cancelled，本轮资源归零。真实停止场景同时复现收尾期间手动再次运行及定时触发不启动新轮、结算后新轮可运行且不重复探测已成功源。
3. 已加入 running 的共享成功保留本次可靠关联；已完成／仅准备的结果不冒充运行中共享；SQLite 提交竞争拒绝／写失败不报成功且停止后续批量。
4. 保存失败使用与旧流相同的媒体元数据对照，拒绝新基线且允许修复重试；播放 false 及原生自身取消异常回归。

真实实例独立运行 `python3 scripts/run_isolated_batch_integration.py --scenario stop` 和 `python3 scripts/run_isolated_batch_integration.py --scenario sharing`，至少分别核对真实停止／结算、两方向共享与实际调用数。新默认批量全部运行的定时／范围／恢复／重启等其他场景，匹配原始产物后可明确复用；若这两个入口不能独立可靠运行，证据缺口留同一 Task 修正。

### 证据与重跑规则

每个候选稳定保存在 `.git/validation-evidence/<完整源码SHA>/<run-id>/`，包含索引、准确命令／cwd／SDK、源及未提交内容身份、锁／镜像／脱敏范围与夹具／选择／并行／重试设置、部署产物摘要、退出码／计数／耗时及首次失败和每次重跑。配置及触发器前后身份、状态／进度时间线、实际开始及最大并发、页／队列／消费者／身份内存峰值、逐源可靠保存／提交与资源结算必须可核验。保留到 A 最终决定；仅本机可访问，不声称远程可读。

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
- Decisions：待实施记录原生发现方式、查询／相同排序值处理、容量／终止策略、批量停止与开始唯一边界及共享可靠结算方式。
- Remaining In-Slice Work：全部新增 RO 尚未验收；预计完整 HTML 配置／浏览器旅程及单独 Slice Final 仍需完成，不能以此预判后续 Task 数量。
- Risks / Deviations：原生排序唯一性、alternate 隐藏默认、故障允许探测回退、停止 token 传播及缺少提交结算结果是已识别的实施风险；未提出合同变更，无产品 PASS。
- Head SHA：NOT SET。

若实施产生新的可复用方法，提供少量经验候选供 A 收尾合并；本次规划不向经验文档写历史或虚构验收结论。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO — RO-1～RO-7 的新增义务尚未验收
Next: DEVELOPER IMPLEMENTS TASK 3.1
```

当前是合法计划，不是实施审查 PASS。Developer 提交完整实现与报告后 B 审查 PASS／FIX REQUIRED；修正通常留同一 Task。PASS 后逐项重核 Slice 全部 RO／Surfaces；满足则停止创建 Task，单独运行 Slice Final 并提交 Closure Packet 给 A，否则只规划剩余连贯用户行为。

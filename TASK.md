# Task 3.1 — 原生按需批量检查与停止收尾闭环

依据已提交 [Slice 3](SLICE.md)、[A Final Review／AF-1](SLICE.md#a-final-review)、[开发流程](docs/development-workflow.md) 与 [B 经验](docs/agent-experience/task-planner-reviewer.md)。Developer 先读 [实施经验](docs/agent-experience/developer-implementation-role.md)。本次恢复原 Task 的纠正计划，不创建新 Task 或独立 Fix 生命周期。

```text
Task ID: 3.1
Parent Slice: 3
Status: FIX REQUIRED
Task Base: b86d9c17d7f915108072f54ee098f0f5543fe093
Contract Checkpoint: e03052655d298adb30cbb7f315da684f27a07285
Original Contract Checkpoint: 2b515f35db7fc8e85d8ac1a8085dd9b8ccc62ef3
Superseded Plan Snapshot: eb4e272743f4c7e184d45fa48b660b2fef24c685
Previous B PASS Snapshot: 2f74aa83f15707df56c4b15409ba1538a488f83a
Correction Start Checkpoint: e03052655d298adb30cbb7f315da684f27a07285
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

管理员通过 Jellyfin 原生「STRM 媒体信息检查」手动或定时检查已保存的全部／部分媒体库，不打开播放会话；任务固定本轮候选 ID，分批读取当前对象并按源增量处理，沿用播放的可靠探测／保存／指纹机制。原生停止撤销本任务未开始工作，等待已开始及已加入的运行中探测完成，正确提交有效结果、结算统计，再以 Cancelled 结束。失败可修复后重跑，状态库故障停止批量优化，不变成全库原生刷新。

本次纠正闭合 RO-6、AC-6／AC-7 中 AF-1 的必要故障反馈，并保护 RO-3／4／5 的已开始探测、共享、提交及资源收尾。原 Task 的 RO-1～RO-6 和 RO-7 范围配置后端、Goal、Base 与完整验收不变；完整页面已由 Task 3.2 交付，作为现有能力保护，不重新纳入本 Task 的开发范围。

## 实际缺口与实施范围

### 规划检查与合法性

2026-10-16，B 完成 AGENTS 必读清单及 B 经验，初始 `git status --short --branch` 为干净的 main。规划前治理实际 FAIL：`FIX REQUIRED needs a corrective Task`；A 已在 Contract Checkpoint 提交完整拒绝决定，合同／Roadmap 与工作区一致，缺失项正是待 B 恢复的纠正 Task。可据已提交合同规划；Developer 仍须等待本计划提交且治理 PASS 后开始，不修改治理器规避门槛。

**B 合法性决定：CONTINUE SAME TASK 3.1 — CORRECTION REQUIRED。** AF-1 是原 AC-T6／AC-T7 的未闭合行为，不是新能力或 Material Contract Change。保留原 ID／Task Base／Goal／Scope／High／T4，历史计划、Developer 报告、B PASS 及失败记录从 Previous B PASS Snapshot 读取；原 PASS 是历史事实，不覆盖 A 本轮反例。Task 3.2 的 Base `2f74aa83f15707df56c4b15409ba1538a488f83a`、实现 `5580492a5cacbdc0772dd2f14f9b527ab3851746` 和 B PASS 快照 `678bcf5c3a6ba5c6743402ec27367dd76d0f101d:TASK.md` 保留，不重设 Base、不重新实施页面。

本轮实际核对产品准入／开始／runner 计数／原生任务结果代码、现有 Batch 用例和屏障、A 四项控制原始结果；核对固定源码 `ScheduledTaskWorker.Execute` 正常返回为 Completed、取消异常为 Cancelled、其他异常为 Failed。当前产品与 A 被审查候选一致，`5580492..Correction Start Checkpoint` 仅含文档。本轮是计划，不宣称修正实现或新产品测试通过。

### 已存在的机制与实际缺口

- `StrmPlaybackOptimizer.AdmitBatchOwnerAsync` 在 owner 取得执行机会后，将禁用与已 latch 状态库故障共同返回 `BatchAdmission.NotProcessed()`。`RunBatchProbeAsync` 随后放弃 reservation 并输出普通 NotProcessed，导致真实终止原因消失。
- `BatchCheckRunner.ProcessCandidateAsync` 已能分别接收 `BatchDisabledException` 与带阶段的 `FingerprintStoreUnavailableException`，记录 Disabled／StoreUnavailable，并维护撤销／检查未完成／探测未完成；`RunAsync` 最终完成条件只消费本轮原因。最后一批不会再经过下一批的全局检查，遗漏原因就可能补满 100%。复用这些结果和既有幂等结算，采取最小修正；只在最后读一次当前 Enabled 不能替代已观察原因的传递。
- `StrmProbeScheduledTask.ExecuteAsync` 已按原因抛出脱敏异常，原生 worker 负责终态；不需要新增调度器、状态库或另一套任务结果接口。
- `BatchDecisionBarrier`／`OnBatchDecision`、Coordinator 的许可等待／取得屏障和现有假原生／保存代理足以确定性控制 AF-1 窗口。已有 `BatchDisableDuringNativePreparationPreventsANewProbeAndReportsEarlyEnd` 与 `BatchLatchedStoreFaultDuringNativePreparationPreventsANewProbeAndReportsUnavailable` 发生在更晚窗口，不能代替准入前复现。
- A 索引 `.git/validation-evidence/5580492a5cacbdc0772dd2f14f9b527ab3851746/a-final-review-20261016/INDEX.md` 的最终 `admission-controls-results.json` 有禁用／另一源实际读取仓库失败并 latch 同一个 optimizer × runner／ExecuteAsync 四项反例；都出现 0 次探测、旧指纹未变但进度到 100%，runner Completed=true 或 ExecuteAsync 正常返回。读取的是最终有效控制，早期 helper 参数错误不算产品证据。

### 本次实施边界

1. 在原批量资格检查／owner 准入／未开始拒绝与 runner 结算链中保留真实禁用、状态库不可用和管理员停止原因；已被本轮观察的原因不能因后续重启用或其他消费者结算而丢失。不把受支持且已判断变化的源当成普通／旧输入的不处理。
2. 批量故障及时停止后续准入及下一批读取，已经实际开始或已加入 running 的工作仍等待收尾。新探测数、可靠成功、需要／未完成、撤销、未读取及原生终态一致；保持指纹故障阶段含义，已决定需要探测后才拒绝的故障不能从需要数中消失。管理员停止与故障同时发生时保留原取消优先及不可用汇总；单项原生异常仍不冒充管理员停止。
3. 复用现有内存结果／异常与幂等许可结算；不以全局取消 token 终止已开始工作、不在有效成功后新增取消／禁用检查来否决提交。原生保存或状态库写入确实失败时仍保护可信基线；状态库本轮不可用的报告不能因为别的源成功结算被抹去。
4. 将四项反例与同类许可等待／多消费者边界加入现有 MSTest 项目；优先复用 BatchHarness、临时 STRM、故障仓库及同步进度，不复制产品算法、不靠 sleep 或生产调试入口。新增测试标记 `TestCategory("BatchAdmissionFailure")`，同时保留 Batch 类别，令独立复现命令可发现它们。
5. 主要文件边界为 `Services/StrmPlaybackOptimizer.cs`、必要的 `BatchProbeTypes.cs`／`BatchCheckRunner.cs`／`Tasks/StrmProbeScheduledTask.cs`、`BatchCheckTests.cs`。仅在同一根因确实需要时调整 Coordinator／相关测试或隔离工具，不要求为每个文件产生改动。报告精确列出涉及的层；未触及的配置页／原生保存／schema 等不得借修正重构。

### 简化实施方案（开发指导，2026-10-16）

首选复用已有两个异常、runner 的原因计数和原生任务结果映射。先修正丢失原因的接缝，再按现有测试验证同根因边界；无需新增结果类型、持久化状态或调度机制。以下是原验收内的实现建议，Task 身份／Base／范围／T4 不变。

**第一步：在 owner 准入处分别报告真实原因。** 将 `AdmitBatchOwnerAsync` 开头合并返回 NotProcessed 的分支替换为两个检查，保持当前开始边界的状态库优先顺序：

```csharp
// 设计示意：在已有 owner 准入检查中使用现有类型。
if (IsFingerprintStoreUnavailable)
{
    throw new FingerprintStoreUnavailableException(
        FingerprintStoreFailureStage.Execution);
}

if (!_settings.Enabled)
{
    throw new BatchDisabledException(projectItemId, sourceKey);
}
```

这里已经根据当前源判断需要探测，所以状态库故障沿用 Execution 阶段的“需要但未完成”计数；实际原生调用数仍为 0，不把阶段标签当作已经开始探测。普通／旧／不支持输入原有的 NotProcessed 分支继续按原规则工作。

**第二步：让未开始拒绝安全释放 owner 并向上传播。** 在 `RunBatchProbeAsync` 最外层、现有通用 `catch (Exception)` 之前，覆盖这两类异常。可以把已有最外层状态库 catch 扩展为：

```csharp
catch (Exception exception) when (
    exception is BatchDisabledException or FingerprintStoreUnavailableException)
{
    Coordinator.Abandon(workItem);
    throw;
}
```

现有原生准备阶段和状态库分支若已结算，`Abandon` 的幂等性使重复调用成为空操作；不要为整理重复 catch 重写整条执行链。新准入分支走到此处时尚未开始，不调用 EndProbe、不提交指纹、不转成 ProbeIncomplete 返回而吞掉异常。其他真正执行异常保留原 Fail／收尾语义。

**第三步：复用 runner／scheduled task 的现有结果路径。** `ProcessCandidateAsync` 已有的两个 catch 负责保存本轮原因，不需另建一套结果转换。消费者取下一项前，将本轮已记录的 `counters.Disabled != 0` 与已有停止／不可用条件一起检查，避免其他消费者继续取项时忽略已观察的禁用；仍让已开始／已加入的工作正常结算。原因一旦写入本轮计数不清零，不能只靠最后重新读取当前配置来决定是否完成。

| 准入前拒绝原因 | 复用的本轮统计 | 复用的原生任务结果 |
|---|---|---|
| 禁用 | Disabled=true；该未开始候选计 Revoked；Completed=false | 汇总及收尾后抛取消异常，Cancelled |
| 已决定需探测后状态库不可用 | StoreUnavailable=true；Checked／ProbeIncomplete 各增加 1，NeedProbe 保留；Completed=false | 汇总及收尾后抛脱敏不可用异常，Failed |

两条路径都不报 100%，不增加 ActualProbeCalls 或 ReliableSuccess，保留旧基线。现有 `RunAsync` 完成条件和 `StrmProbeScheduledTask.ExecuteAsync` 已能消费这些标志，优先保持其结构；管理员停止与故障同时出现仍沿用既有取消优先、汇总保留故障的规则。

**验证顺序：** 先用现有 `OnBatchDecision` 重现四项最小末项反例并保留失败；完成上述局部修正后，验证先等待许可、跨批末项、多消费者及已开始／共享对照，最后执行下节完整候选门槛。生产代码不增加用于卡竞态的按钮、延时或注入开关。若确定性测试揭示同根因的其他未开始路径仍丢原因，在原 Task 范围内修补该接缝，不能靠只改终态掩盖它。

### 并发遗漏的最小修复方案（不增加状态字段，2026-10-16）

**核心做法：复用 `BatchStopSignal` 已有的 `_stopped`／短锁／`TryBeginProbe()` 关闭本轮准入，用已有 `counters.Disabled` 保存禁用原因。** 按用户本次要求，不增加 `IsDisabled` 字段、原因枚举、CancellationTokenSource 或持久化状态。本节替代此前“另增本轮禁用标志”的建议；Task／合同／T4 不变，不代表实现或审查通过。

1. **让已有停止位也能关闭禁用后的准入。** 可增加一个幂等方法 `CloseAdmission()`，在现有 `_gate` 内将已有 `_stopped` 置位，不增加字段。它与 `TryBeginProbe()` 使用同一把锁：先关闭就不能开始，已开始者继续收尾。下一轮仍新建 signal，不清除旧轮停止位。这个位只回答“本轮是否还能准入”，不承担结束原因分类。
2. **在发现禁用处立即关闭，再沿原路径结算。** runner 的禁用分支及 optimizer 的 owner 准入／匹配原生开始回调发现 Enabled=false 时，先关闭准入，再记录已有 Disabled 或抛已有 `BatchDisabledException`；不能等释放许可、返回 runner 后才关闭。入口、取得许可后、准备等待返回和实际开始处复用既有停止检查。重新启用只改变当前配置，不能清除旧轮停止位；owner 拒绝释放自己的 reservation，follower 不得放弃别人的工作。
3. **分清准入已关闭与管理员停止。** runner 当前多处用 `stopSignal.IsStopped` 推导 `StopRequested`，本方案下须改用原始任务 token 的 `IsCancellationRequested`；已有 `counters.Disabled` 仍由真正观察禁用的工作置位，等待所有工作结算后用于汇总，后续撤销项不凭停止位猜原因。已有状态库 latch／阶段计数及原生结果优先顺序保持：管理员实际停止优先、状态库不可用 Failed、禁用提前结束 Cancelled。`BatchStopRejectedException` 继续表示未开始工作被拒绝，不据此伪造管理员停止。检查 `IsStopped` 的现有调用，准入判断与原因判断分别处理，不能只增加一次 `ConfirmStop()` 调用。
4. **保护原有收尾和计时，再验证。** `CloseAdmission()` 不取消原 token、不改执行 token，不影响已开始／已加入 running 的保存与条件提交，也不影响独立播放。现有 `ConfirmStop()` 继续由原任务 token 确认管理员停止并记录 `StoppedTimestamp`；即使此前已因禁用关闭准入，也应在真正管理员停止时记录该时间。`RecordStopQueryLatency` 只计算真实管理员停止，避免把禁用时刻算成停止耗时。先跑 B 的三个并发反例及真实许可等待的宽窗口控制，再保护正常停止、禁用与停止同时发生、已开始成功提交、独立播放和收尾后新轮；最后执行原完整 T4 与 B 指定验证。

主要修改位置仍为 `BatchProbeTypes.cs`（复用停止位及短锁）、`BatchCheckRunner.cs`（观察禁用、原因／耗时分类）、`StrmPlaybackOptimizer.cs`（发现禁用时关闭准入）、`BatchCheckTests.cs`（并发和原因回归）。沿已有方法局部修正，无需调整配置页、SQLite schema 或调度结构。等待许可／准备工作的原 token 不会因禁用而取消，可能等既有等待返回后撤销；实际开始边界必须拒绝，不能提前返回并遗留后台工作。

B 补充控制及原始结果仅本机可读：`.git/validation-evidence/071142f69e110d6406c81294fc03f0918bb0fc0f/b-reachability-20261016/INDEX.md`。宽窗口控制使用独立 reservation 持有许可、产品真实等待；另一消费者观察禁用并撤销后才重新启用、释放许可，仍新增一次探测／提交。它证明现有等待链可达，不冒充真实 Jellyfin 配置页切换验收；初次 helper 的对象返回顺序假设错误与修正记录均保留。

## 验收条件

以下 AC-T1～AC-T8 保留原 Task 的业务与安全验收；仅将 AC-T8 的旧页面缺失说明同步为 Task 3.2 已交付的事实，不改变页面义务。复选框表示纠正候选待重新核验；旧通过与限制在历史快照中保留，不虚构历史失败或新的已通过结果。

- [ ] **AC-T1 原生入口（RO-1）**：真实实例仅发现一个目标任务、默认触发器为空，手动执行与管理员设置的真实时间触发均有效；触发器重启持久化且无默认／启动意外运行。无需播放会话，手动运行／停止／时间都由原生任务管理。
- [ ] **AC-T2 范围与有界遍历（RO-2、RO-7 后端）**：默认全部、显式部分、旧配置、空／失效选择保存与运行、每次范围快照及移出／消失安全。确定性覆盖至少两个库、多批、同名／重复 ID／跨库重复、对象返回乱序／重复／缺失、集合获取失败、多版本及音频源；真实至少两个库、完整 ID 获取、多批、多版本按源对账，范围外／普通／旧／未知协议零批量探测。集合固定后增删／移库安全结算、新增下一轮发现；十万模拟候选证明批次／消费者上限，身份集合及查询临时成本单列。
- [ ] **AC-T3 共用可靠结果（RO-3）**：首次信任及未变零探测、不计真实成功；缺主流、同 SHA-1／Size 换 URL、同 URL 有效 SHA-1 变化、不可比 SHA-1 的 Size 变化使用共用原生链。结果／新地址／主流／SQLite 与重启后 PlaybackInfo 一致。成功计数仅关联本次同源真实成功、保存、稳定 Manifest 及条件提交；提交拒绝／失败不伪报成功，恢复可重试。
- [ ] **AC-T4 混合共享（RO-4）**：确定性 1／2／8、准备／排队不共享、立即获许可与完成重查、多版本／调用者隔离。实机批量先开始→播放加入、播放先开始→批量加入都仅一次匹配探测，批量成功与实际调用分别统计；同源排队完成后无重复。不同源混合不超启动上限、保存并发下次启动才生效，独立 FullRefresh 正常；false 播放原权限和基线不升级。
- [ ] **AC-T5 停止与资源（RO-5）**：确定性屏障覆盖同步 ID 获取／对象读取前后、批次未分派、等许可、立即获许可未登记、准备取源 await、准备登记、实际开始／停止双方先发生、已开始仅批量及两方向共享。同步查询中停止等待返回且无后续准入，不泄留后台获取。停止确认后无新实际开始，其他调用者排队不受影响；已开始／已加入工作成功仍提交，原生自身失败／取消异常保留旧基线。任务等到结算／汇总后才抛原生停止异常，最终 Cancelled，非 Completed；批次对象、消费者、候选 ID 引用及本轮 preparing／running／许可释放。真实停止证明未开始撤销与已开始完成；收尾期间重复手动运行及定时触发不实际启动新轮，旧轮结算后可以再次运行并按最新指纹跳过已成功源。独立播放探测不因等待旧批量收尾被禁止。不拿进程杀死或手动 API 的 204 替代真实执行证据。
- [ ] **AC-T6 故障与汇总（RO-6）**：损坏／不可达、Manifest 再变、独立保存失败控制隔离单项；SQLite 读取／提交故障、全局不可用、候选获取／批次读取异常及时停止准入并收尾。不可用使用脱敏失败结果（管理员同时停止时保留取消原因及不可用汇总），不自动删库，不通过原生委托继续全库探测。修复重启后重跑成功；单项原生取消不得伪造管理员停止。
- [ ] **AC-T7 可对账反馈（RO-6）**：检查＝跳过＋需要＋检查阶段未完成；需要＝可靠成功＋探测未完成；未完成总数＝检查阶段未完成＋探测未完成。首次信任计跳过，共享源只计一次但必须保留本次成功关联，实际调用次数另计。原生 ID／去重候选／不处理／消失或移出／重复／撤销／读取未完成／未读取分别标注，集合未完成时总数未知；原生进度单调且提前结束不补 100%，正常空库可完成。Completed／Cancelled／Failed、计数、保存／提交和日志一致；必要汇总不依赖 DetailedLog，异常及原生任务历史无秘密／私有路径。
- [ ] **AC-T8 回归与交接（全部接入表面）**：T4 完整候选门槛与 B 指定关键复现有可核验证据；新增部署依赖实际加载。改动属于本 Task、STRM 产品只读、固定原生委托／播放响应与最小五字段 schema 保持；准确区分本 Task 后端纠正与 Task 3.2 已交付的页面／浏览器旅程，保持当前页面验证门槛。未运行／不可用门槛如实记录，不能先 PASS 再延期当前阻塞。


### AF-1 的具体闭合证据（落实 AC-T6／AC-T7，不替代其余条件）

- [ ] **禁用的两个入口**：已有可信基线且 URL 已变，在决策之后、owner 准入之前禁用。最后一个候选／最后一批仍返回 Disabled=true、Completed=false，已加载但未开始者按撤销结算，实际开始／可靠成功为 0、可信基线不变、全程进度低于 100%；经真实产品 ExecuteAsync 抛取消异常，不正常返回。
- [ ] **故障的两个入口**：同一窗口由另一源通过同一 optimizer 的真实仓库读取失败 latch 全局不可用，不能只把属性直接设为 true。最后项 StoreUnavailable=true、Completed=false，不伪报普通不处理；已经判断需要探测者保留需要／探测未完成口径，实际开始／可靠成功为 0、旧基线不变、进度低于 100%；ExecuteAsync 抛脱敏不可用异常，不正常返回或仅作单项错误继续。
- [ ] **并发与许可边界**：确定性覆盖立即获许可与先等待许可再准入；单候选最小末项、跨 128 边界后的末批，以及多消费者收尾中有候选被拒绝。两种原因都可到达结果，不依赖下一批检查；一次观察到原因后不可由其他结果或重新启用清空。后续候选获取／对象批次／未开始探测停止，候选与源统计各自一次结算、等式成立，preparing／running／许可归零。
- [ ] **已开始／共享对照**：禁用或批量停止不会取消已开始探测，不增加客户端取消源；只有批量等待者及两方向共享仍完成必要收尾。满足真实成功／保存／稳定 Manifest／可用条件提交时仍接受结果；真实提交失败仍不计可靠成功、不覆盖旧基线。保留原生自身取消／false 权限、多源及正常未变／首次信任／空库结果，不把正常 Completed 一律改成 Cancelled。
- [ ] **实际用户反馈与恢复**：原生 stop／sharing 实机独立入口和完整默认 batch 的 failure／恢复等代表场景、配置页禁用／恢复旅程仍通过，原生状态、脱敏汇总、实际调用／保存／SQLite 对账。窄准入窗口由确定性测试证明，不新增生产开关强行注入，也不把 fake ExecuteAsync 异常称为实机 worker 终态。

## 必要测试

本 Task 原 High／T4 不降低，固定 SDK `10.0.401`／net10.0、Jellyfin Controller／Model `12.2.0`、原生源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。命令均从 `/opt/jf-strm-probe` 执行。原 Task 的全部门槛保留；本次增加 AF-1 独立类别及当前已交付配置页的候选验证。产品、测试、工具或运行输入变化后需更新纠正候选的完整 T4 证据，不能沿用旧绿灯宣称修复。

### 开发／修正反馈

先将四项 AF-1 复现纳入测试，保留修正前必要行为 FAIL；A 旧 collector 退出 0 只是记录观察，不代替会失败的产品断言。新增类别是本 Task 交付物，当前尚未存在，执行时必须记录发现数非零。首次／依赖变化先 locked restore。

```bash
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'TestCategory=BatchAdmissionFailure'
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'TestCategory=Batch|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~ProbeExecutionContextTests|FullyQualifiedName~PlaybackOptimizerTests|FullyQualifiedName~ConfigurationTests'
python3 -m unittest discover -s tests -v
```

第一项直接检验原因传播／末项状态／资源；第二项保护停止开始边界、共享、权限、保存、配置与既有批量；Python 保护治理和隔离工具。只有修改 C# 时可先完成两项 C# 反馈再进入工具与实机；不把每次编辑都当最终候选。

```bash
python3 scripts/run_isolated_batch_integration.py --scenario stop
python3 scripts/run_isolated_batch_integration.py --scenario sharing
```

以上现有真实入口用于受影响停止／共享反馈，最终 suite 已覆盖时无需机械重复；B 的独立复现义务另列如下。

### 最终检查点门槛

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py
python3 scripts/run_isolated_configuration_integration.py
python3 scripts/check_governance.py
git diff --check
```

- C# 全套实际包含新增 AF-1 类别和全部既有解析／决策、SQLite／保存失败、DI／权限／多源、协调／停止／完成重查、范围／统计、十万模拟候选成本与有界对象／消费者控制。记录新增／总数、失败／skip，不要求维持旧 182 的固定数字。
- 默认播放完整运行保护原权限／故障原生委托、并发／共享、地址与媒体流保存／重启；默认 batch 完整 suite 保留发现／无默认触发、手动／真实定时／触发器重启、所选库／多批／多版本／固定集合增删、两方向共享／混合、原生停止收尾／再次运行、状态库不可用／修复重启。完整配置页入口保护五项配置、禁用／恢复和页面值驱动任务；不因本 Task 不写 HTML 删掉当前 Slice Final 的页面义务。
- 只运行仓库隔离 Compose project／临时库／手写 STRM／本地媒体。前后保留配置、全部触发器、夹具与媒体摘要、地址／主流与库条目恢复，证明部署 DLL 是本候选。最终候选证据可由完整套件覆盖聚焦用例；独立实机与 Slice Final 仍按各自阶段执行。
- 极窄准入竞态以确定性屏障验证；代表性真实状态／停止／保存／恢复必须运行。真实十万库、内部 Jellyfin 数据库物理保存故障注入和外部代理等未运行项继续按原合同分别 NOT RUN，不扩大为本轮阻塞。Markdown 文件／锚点及改动范围核对不能替代产品门槛。

### B 独立验证

B 审查真实 `Task Base..Developer Head`，并单列 `Correction Start Checkpoint..Developer Head` 的纠正差异；原 Task 3.1、其间 Task 3.2 与纯报告的接受事实通过可达 Git 和匹配原始证据核对，不重设 Base 或把页面改动算成本次修正。独立执行上述 Batch／Coordinator／Context／Playback／Configuration 聚焦命令；其完整发现覆盖新增类别时不重复跑同一用例。

必须逐项检查新增 AF-1 类别确实被执行，独立复现禁用／另一源 latch × runner／ExecuteAsync 四项，许可等待／立即准入、末批／多消费者与已开始／共享对照；核对真实 latch、全部进度、原生异常种类、逐源基线、阶段计数和资源，而非仅看 Completed=false。单独保存 B 的断言与原始结果。

保留原 B 的独立实机命令：`python3 scripts/run_isolated_batch_integration.py --scenario stop` 和 `python3 scripts/run_isolated_batch_integration.py --scenario sharing`。逐项核对旧轮收尾中新轮不进入、实际已开始源成功结算、未开始撤销、之后可重跑，以及两方向一次探测／提交关联。Developer 完整候选的其余门槛可在全部输入匹配且原始产物充分时明确复用；不匹配、矛盾或缺失则重跑对应门槛。

### 证据与重跑规则

每个候选在 `.git/validation-evidence/<完整源码SHA>/<run-id>/` 或 CI 保留索引、测试与被审查 SHA、实际工作区内容身份、精确 argv／cwd、SDK／锁／镜像／配置／夹具／浏览器与构建部署产物摘要，命令退出／计数／耗时、原始日志／进度／源结算以及首败和每次重跑。只在本机时明确本机可读。保存 A 反例与原 Task 历史，不覆盖旧文件。

最终测试前后源／测试／工具／依赖／配置输入必须匹配；产品可执行变化后完整候选 T4 重新执行。纯报告后继比较所有输入并重跑消费文档的检查。使用现有浏览器工具记录生效与恢复；长验收观察用日志／文件，避免并行复用同一测试鉴权身份。批量历史日志的日期／会话限制如实披露，不能过滤掉实际重入制造 PASS；不将现有 P2 时间工具改造变成独立产品义务。

## 非目标

- 修改 Slice、Roadmap、稳定需求、协议、判断规则或安全／取消语义；改变 Required Outcomes／验收含义先交 A，Developer 不自行继续。
- Task 3.2 页面开发、指数措辞润色、保存通道／schema／原生保存链重构、运行中并发热调整、数据库自动修复、通用 FullRefresh 性能证明；本次仍验证既有能力。
- 新 Task／Slice、独立 Fix 生命周期、持久化探测状态、独立运行／停止／定时 UI、额外执行取消源、为全库建立 Task 或完整对象集。
- Slice 4 的真实大库／完整扫描压力／广泛客户端格式／外部 JellyfinProxy／OpenList 联调／发布 ZIP；以及生成器、远程哈希／API／代理改造、生产操作、推送、历史重写。
- 以本计划、治理通过或旧 Final 宣告 AF-1 修复、Task PASS 或 Slice 关闭。

## Developer Completion Report — 上轮并发纠正（历史输入）

历史完成报告及各轮 B 结果保留于 Previous B PASS Snapshot 与上轮 B Review Result；下表记录本轮
“已分派但未开始工作跨重新启用”的并发纠正。

- Changed Files：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchProbeTypes.cs`
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchCheckRunner.cs`
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/StrmPlaybackOptimizer.cs`
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/BatchCheckTests.cs`
- Implemented：复用已有 `BatchStopSignal` 的 `_stopped`／短锁，新增幂等 `CloseAdmission()`（不新增字段、
  枚举、`CancellationTokenSource` 或持久化状态）。任一消费者在决策、许可等待／立即取得或原生准备处观察到禁用
  时立即 `CloseAdmission()`，使同轮所有已分派但未开始的工作在实际开始边界被拒绝，即使管理员在第二项到达前
  重新启用也不会新增探测。`StopRequested` 只由真实管理员 token（`CancellationToken.IsCancellationRequested`）
  推导，不再由共享准入位推导，因此禁用仍报告为 `Disabled`／Cancelled，真实管理员停止保留优先级与自身耗时；
  `ConfirmStop` 仅在首次真实停止时记录时间戳。已开始探测、原生保存、验证与条件提交不受影响，独立播放与下一轮
  不受影响。
- Tests and Results：
  - 新增 3 个并发回归（`BatchAdmissionFailure` 同时保留 `Batch`）：决策后、立即取得许可、真实等待许可后三种窗口，
    断言“第一项已结算禁用、第二项此前未开始、重新启用后同轮零新增开始、零 `ProbeCalls`、两项撤销、各候选一次结算、
    两个旧基线保留、Disabled=true／Completed=false、ActualProbeCalls=0、进度 < 100%、资源归零”。
  - 修正前以 `HEAD~1` 产品源码运行新增类别：**FAIL 3／pass 7**（`prefix-failure.log`），证明回归确实捕获该缺口。
  - 候选 `TestCategory=BatchAdmissionFailure`：PASS 10／0 failed／0 skipped。
  - 聚焦 Batch／Coordinator／Context／Playback／Configuration：PASS 142／0 skipped。
  - `dotnet-local restore ...sln --locked-mode`：PASS。
  - `dotnet-local build ...sln -c Release --no-restore`：PASS，0 警告 0 错误。
  - `dotnet-local test ...sln -c Release --no-restore`：PASS 192／0 failed／0 skipped（189 + 3）。
  - `dotnet-local format ...sln --verify-no-changes --no-restore`：PASS。
  - `python3 -m unittest discover -s tests -v`：PASS 63。
  - `python3 scripts/run_isolated_plugin_integration.py`：PASS（731 s）。
  - `python3 scripts/run_isolated_batch_integration.py`：PASS（317 s），discovery／failure／mixed／scope／
    shared_stop／sharing／stop 全跑，配置／触发器／夹具恢复并核验。
  - `python3 scripts/run_isolated_configuration_integration.py`：PASS（274 s）。
  - `python3 scripts/check_governance.py`：PASS；`git diff --check`：PASS；Markdown 140 本地链接／锚点：PASS。
  - 三项实机入口在清理后的 HEAD 构建（`dotnet-local restore --locked-mode` + `build -c Release`）上重跑，部署 DLL
    身份 `sha256 d7a4c24ee66026184f332cbf768c74431ab44cd7e9eeee3f7a7bb7537fdb06d9`（配置页实机记录一致）；
    隔离入口只部署产品构建产物，不部署测试程序集。同源清理重建三次哈希一致；程序集 informational version 含提交号
    （`0.1.0+<commit>`），故报告提交前后的构建哈希不同而产品源相同（`git diff 97e68dfa HEAD -- src/ tests/` 为空）。
  - 证据索引（仅本机）：`.git/validation-evidence/97e68dfa2f246488174e47e2ba0cf45910a4947f/af1-concurrency-correction-20261016/INDEX.md`。
- Decisions：原范围纠正，无合同变更；复用既有停止位、异常、runner 原因计数与原生任务结果映射，未新增执行取消源、
  持久化状态、调度机制或生产注入开关；不将准入停止扩散到独立播放、其他调用者或下一轮。
- Remaining In-Slice Work：本并发缺口已实现并自测通过；修正后由 B 重核七个 RO／六类 Surfaces，独立聚焦、三项并发
  控制及指定 stop／sharing 实机。
- Risks / Deviations：未运行项继续 NOT RUN（真实十万库、内部数据库物理保存故障注入、外部代理／OpenList 联调、
  广泛格式／客户端、发布 ZIP）；窄窗口以确定性屏障证明，未新增生产开关。
- Head SHA：`97e68dfa2f246488174e47e2ba0cf45910a4947f`。

## Developer Completion Report — 单次读取禁用观测纠正（2026-10-16）

B 已就“同一边界内多次读取动态 `Enabled` 丢失首次拒绝原因”签发 FIX REQUIRED（P1）。本报告记录同一 Task 3.1 内该接缝的最小纠正。

- Changed Files：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchCheckRunner.cs`
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/BatchCheckTests.cs`
- Implemented：新增私有 `ObserveDisabled(counters, stopSignal)`，在每个决策边界只读取一次 `_settings.Enabled`；读到 false 时立即 `CloseAdmission()` 并置位已有 `Disabled` 计数，返回本轮是否已观察禁用。`BatchCheckRunner` 内全部 `Enabled` 读取点（候选查询前／返回后、集合固定后、批次前、消费者取项）统一改走该方法，不再用后续读取的当前配置重建或清除原因。未新增字段／枚举／CTS／持久化状态；已开始／已加入探测、原生保存、验证与条件提交不变；管理员停止与状态库不可用优先级不变。新增 `ConsumerPrecheckEntered` 测试钩子（生产为 null）用于确定性编排。
- Tests and Results（源码 HEAD `717595c631489c2dbea817ebb755507271f806bd` + 两个工作文件；实现提交 `9b5e488a0c7f8ac46989f244a7835032b61246b1`）：
  - 新增 5 个回归（`BatchAdmissionFailure` 同时保留 `Batch`）：消费者边界单次 false 后重启用、消费者 ExecuteAsync、候选获取边界、候选获取 ExecuteAsync、候选查询返回后边界；均断言 `Disabled=true`、`StopRequested=false`、`Completed=false`、进度 < 100%、零探测、旧基线保留、资源归零。
  - 修正前以 HEAD 产品源码运行新测试：**FAIL 5／pass 10**（`prefix-failure.log`），证明回归确实捕获该缺口。
  - 候选 `TestCategory=BatchAdmissionFailure`：PASS 15／0 failed／0 skipped。
  - 聚焦 Batch／Coordinator／Context／Playback／Configuration：PASS 147／0 skipped。
  - `dotnet-local restore ...sln --locked-mode`：PASS。
  - `dotnet-local build ...sln -c Release --no-restore`：PASS，0 警告 0 错误。
  - `dotnet-local test ...sln -c Release --no-restore`：PASS 197／0 failed／0 skipped（192 + 5）。
  - `dotnet-local format ...sln --verify-no-changes --no-restore`：PASS。
  - `python3 -m unittest discover -s tests -v`：PASS 63。
  - `python3 scripts/run_isolated_plugin_integration.py`：PASS。
  - `python3 scripts/run_isolated_batch_integration.py`：PASS，discovery／failure／mixed／scope／shared_stop／sharing／stop 全跑，stop 场景 `task_status=cancelled`／HTTP 204，夹具与状态恢复并核验。
  - `python3 scripts/run_isolated_configuration_integration.py`：PASS，19 场景，配置／触发器恢复并核验。
  - `python3 scripts/check_governance.py`：PASS；`git diff --check`：PASS；Markdown 140 本地链接／锚点：PASS。
  - 三项实机入口部署的插件 DLL 与本最终构建同为 sha256 `252928de7c753b05c2fdde769cbf8f2b7fc6f4ccfab4bfcf4ab261bdb1c84a55`，产品源码自实机运行后未再改变，故无需重跑；测试程序集 sha256 `528e0a6368396bade565ffd969a148f33c7aed27794242f28a196198e18cade1`。
  - 证据索引（仅本机）：`.git/validation-evidence/97e68dfa2f246488174e47e2ba0cf45910a4947f/af1-single-read-correction-20261016/INDEX.md`。
- Decisions：原范围纠正，无合同变更；复用既有停止位、异常、runner 原因计数与原生任务结果映射，未新增执行取消源、持久化状态、调度机制或生产注入开关；不将准入停止扩散到独立播放、其他调用者或下一轮。
- Remaining In-Slice Work：本单次读取缺口已实现并自测通过；修正后由 B 重核七个 RO／六类 Surfaces、独立聚焦、单次读取控制及指定 stop／sharing 实机。
- Risks / Deviations：确定性控制以可编排设置模拟合法并发配置发布，真实页面切换时序 NOT RUN；真实十万库、内部数据库物理保存故障注入、外部代理／OpenList 联调、广泛格式／客户端、发布 ZIP 继续 NOT RUN。
- Head SHA：`9b5e488a0c7f8ac46989f244a7835032b61246b1`。

历史报告的交接动作已由下方当前 B Review Result 替代。

## B Review Result

```text
Reviewed: b86d9c17d7f915108072f54ee098f0f5543fe093..9b5e488a0c7f8ac46989f244a7835032b61246b1
Correction Reviewed: e03052655d298adb30cbb7f315da684f27a07285..9b5e488a0c7f8ac46989f244a7835032b61246b1
Current Fix Reviewed: 717595c631489c2dbea817ebb755507271f806bd..9b5e488a0c7f8ac46989f244a7835032b61246b1
Review Checkout / Developer Report: de01271ad51395907fc68139cf2f8190c13a56f7
Decision: FIX REQUIRED
P0/P1 Blockers: AF-1 (P1), global store failure omitted by final skipped candidate
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CONTINUES THE SAME TASK 3.1 CORRECTION
```

2026-10-16，B 完成 AGENTS 必读清单及 B 经验，初始 main 干净、规划／审查前治理 PASS。以已提交 Slice 为 authority，保留 Task ID／Base／Goal／Scope／High／T4 与不新增状态字段的实施约束；单列完整 Task 范围、本次纠正范围及最新两个文件的差异，未将其间 Task 3.2 页面交付计作本次修正。Developer 被测工作文件与提交 blob 相同，82 项 tracked 输入只有 TASK.md 与当前 checkout 不同。上轮重复读取反例、详细指导与 B FIX REQUIRED 保留于 `de01271ad51395907fc68139cf2f8190c13a56f7:TASK.md`，原始失败证据保持不变。

### 已修复行为与独立验证

- **PASS**：独立聚焦 147／0 failed／0 skipped，TRX 逐项确认全部 15 项 `BatchAdmissionFailure` 被执行。单次禁用观测立即复用 CloseAdmission 和已有 Disabled；没有增加字段、枚举、CTS 或持久化状态。两个新增 ExecuteAsync 用例实际只断言取消异常，不能按 Developer 报告概括成每个用例均检查全部计数／基线／资源；下述独立控制补充核验这些项。
- **PASS**：B 独立重跑此前禁用／另一源实际仓库读取失败 latch × runner／ExecuteAsync 四项、决策后／立即获许可／实际等待许可的三个并发重新启用控制、一个真实许可等待宽窗口控制、消费者／候选获取单次 false 后恢复 true × runner／ExecuteAsync 四项，共 **12 个控制**。原因／异常正确，未开始源零新增探测、旧基线保留、资源归零、进度低于 100%；宽窗口仍有一个正常未变跳过、两个撤销。double-read helper 仅适配新 ObserveDisabled 调用帧，仍通过公开构造参数替换动态设置，不修改产品／已提交测试。
- **PASS**：B 独立 locked restore、Release build（0 警告／0 错误）、C# 全套 **197／0 failed／0 skipped**、format、Python **63**、治理、差异和 **140** 个本地 Markdown 链接／锚点。
- **PASS**：B 指定真实 `--scenario stop`（104.689 秒）和 `--scenario sharing`（83.335 秒）。停止最终 Cancelled，2 个已开始源提交、1 个撤销；收尾期零新轮／零新探测，排队轮只处理撤销源，再次显式运行零重复。两方向共享各一次真实探测，批量 ActualProbeCalls 分别 1／0、ReliableSuccess 均 1。夹具／地址、配置和全部触发器 restored and verified。部署产品 DLL 为当前构建 `21a595b0949a9c35b88fb282fceae4fffe6afc03dc50dbe223ceb5b7be36e357`，不冒称与 Developer 的旧构建摘要相同。

以上支持禁用修正及原停止／共享行为，不能排除以下 RO-6 遗漏。

### AF-1 残留：末项跳过路径未将共享状态库故障带入本轮终态（P1）

`CheckBatchSourceAsync` 在已有基线、未变化时直接返回 Skipped，不经过 owner 准入的故障检查。此时若另一源已经通过同一个 optimizer 的真实仓库读取失败置位 `IsFingerprintStoreUnavailable`，本候选仍会正常跳过。`BatchCheckRunner` 在整批结算后及最终完成判断只消费 `counters.StoreUnavailable`，没有把已置位的共享故障纳入结果；末批不会再到下一批的全局检查。因此仍得到 `StoreUnavailable=false／Completed=true`，补 100%，ExecuteAsync 正常返回，固定原生 worker 会记 Completed。

B 使用单个末项、临时受支持 STRM 和已有可信基线，保留 URL／SHA-1／Size 不变。在其决策之后，用另一源通过同一 optimizer 实际读取故障仓库；没有直接设置私有 latch。独立控制包括原源级批量入口和真正的公开播放入口 `GetPlaybackMediaSourcesAsync`，各覆盖 runner／ExecuteAsync。播放控制使用原有假原生的已有流作为合法委托返回；只检查插件故障传播，不声称是真实数据库物理故障注入。

| 控制 | 实际结果 |
|---|---|
| 另一源经 CheckBatchSourceAsync latch，末项 runner | latch=true；Checked=Skipped=Settled=1，NeedProbe=0；StoreUnavailable=false、Completed=true；进度 `[0,99,100]`。 |
| 相同窗口，ExecuteAsync | 正常返回，无不可用异常；进度到 100%。 |
| 另一源经公开播放入口实际读取失败 latch，末项 runner | 同样 latch=true、Skipped=1、StoreUnavailable=false、Completed=true；进度 `[0,99,100]`。 |
| 相同公开播放故障，ExecuteAsync | 正常返回，无不可用异常；进度到 100%。 |

四项零批量／假原生探测、旧基线未变、许可／preparing／running 归零；独立必要行为断言 **4 FAIL，退出 1**。正确的跳过计数与零探测不抵消必要故障反馈。此问题违反原 RO-6、AC-6／AC-7／AC-T6／AC-T7 的“状态库全局不可用报告不可用、全局故障不补满”义务，是 AF-1 的终态传播残留；不是新 Outcome、额外状态要求或 Material Contract Change。

### 同一 Task 的最小继续修正

2026-10-16，按用户要求收敛为以下简单实施方案。保留同一 Task 的 ID／Base／Goal／Scope／High／T4；这是开发指导，当前审查仍为 FIX REQUIRED。

**1. 先加回归，保存修正前 FAIL。** 复用 `BatchHarness`、决策屏障和故障仓库：唯一候选已有可信基线且未变化，决定跳过后，另一源通过同一 optimizer 的公开播放入口实际读取仓库失败，再让本候选结算。覆盖 runner 和 ExecuteAsync，归入现有 `BatchAdmissionFailure`。期望 runner 的 `StoreUnavailable=true`、`Completed=false`、进度低于 100%；ExecuteAsync 抛现有脱敏 `InvalidOperationException`。同时检查 `Checked=Skipped=1`、`NeedProbe=0`、零额外探测、旧基线保留、统计等式及资源归零；保留无故障正常跳过 Completed／100% 对照。现有 B helper 和原始失败见下方证据索引。

**2. 在最终结算处补一行，沿用现有结果路径。** 主要修改 `BatchCheckRunner.RunAsync`：所有批次消费者已经等待结束、未读取数已经结算后，在现有 `completed` 判断之前，把 optimizer 已记录的全局故障合入本轮已有计数。局部示意：

```csharp
counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
counters.StoreUnavailable |= _optimizer.IsFingerprintStoreUnavailable ? 1 : 0;
var completed = counters.StopRequested == 0
    && counters.StoreUnavailable == 0
    && counters.Disabled == 0
    && counters.ReadIncomplete == 0
    && counters.Unread == 0;
```

`|=` 保留本轮此前已记录的故障。现有 Copy 会带出 StoreUnavailable，completed=false 就不会补 100%，现有 ExecuteAsync 会在汇总后报告不可用；管理员停止仍按已有顺序优先。预计只需修改 `BatchCheckRunner.cs` 和 `BatchCheckTests.cs`，无需新增字段、枚举、CTS、状态表或结果类型。保留已经完成的真实 Skipped／Checked 计数；已开始／已加入探测仍完成保存、验证和条件提交，不能用本轮故障反馈事后否决有效提交。

**3. 聚焦通过后执行原门槛。** 先运行现有 `BatchAdmissionFailure` 与 Batch／Coordinator／Context／Playback／Configuration 聚焦命令，保护禁用单次观测、重新启用、正常跳过、已开始成功及共享收尾；再执行上文完整 T4 最终候选门槛。B 继续独立复现本轮四项故障控制、既有 12 项控制及指定 stop／sharing 实机。准确命令与证据要求沿用“必要测试”，不降低门槛。本轮只修订指导，插件实施仍由 Developer 在同一 Task 内完成。

### 证据、未运行与 Slice 重核

本机索引：`.git/validation-evidence/9b5e488a0c7f8ac46989f244a7835032b61246b1/b-review-20261016/INDEX.md`。保存真实范围 diff、输入／SDK／锁／构建与部署身份、TRX、12 个原控制和 4 个末项故障控制的 helper 源码／原始结果／独立断言、真实 stop／sharing 原始日志与恢复，以及精确命令／退出码／耗时。collector 退出 0 仅表示采集成功；4 FAIL 的产品断言退出 1 才是本轮阻塞判定。

已核阅 Developer 的原始 build／fulltest／首败／三项实机日志，核对输入和工作文件身份，并将其仅在临时目录的浏览器原始产物复制到稳定 B 证据目录；历史自测保留，不签发完整 T4 复用 PASS。发现明确 P1 后按流程提前拒绝：当前 B 的完整默认 playback／batch suite／configuration 及 Slice Final 均 **NOT RUN**；已启动的独立 sharing 正常完成和恢复后，剩余昂贵门槛未启动，未取消在执行的探测。Developer 的既有全套不改写成本轮 B 或 Slice Final 结果。

七个 RO／六类 Surfaces 已重新核对：RO-1／2／3／4／7 的历史交付保留，RO-5 本轮真实停止／收尾得到支持，禁用准入反例已闭合；**RO-6 的全局故障反馈和原生终态仍未满足**。进度／结果表面阻塞整 Slice 接受；原生任务、库查询、共用执行、SQLite 与配置页保留分层事实，不能整体签发 PASS。因此不创建下一 Task、不运行 Slice Final、不替换旧 Closure Packet、不改 Slice／Roadmap／稳定需求，也不代 A 关闭。

真实十万库、内部数据库物理保存故障注入、外部代理／OpenList、广泛格式／客户端及发布 ZIP 的既有 NOT RUN 边界不变。供收尾合并的经验候选：只检查需要探测分支会漏掉并发全局故障 → 同时覆盖末项正常跳过与跨播放入口故障，核对本轮终态 → 适用于共享不可用 latch 的批量任务；本轮不写经验流水账。

NEXT ACTION: DEVELOPER CONTINUES THE SAME TASK 3.1 CORRECTION

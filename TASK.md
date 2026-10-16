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

## Developer Completion Report

历史完成报告及各轮 B 结果保留于 Previous B PASS Snapshot；下表只记录本轮 AF-1 纠正。

- Changed Files：
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/StrmPlaybackOptimizer.cs`
  - `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchCheckRunner.cs`
  - `tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/BatchCheckTests.cs`
- Implemented：`AdmitBatchOwnerAsync` 不再把禁用／已 latch 状态库不可用合并为 `NotProcessed`，而是分别抛出
  `BatchDisabledException` 与执行阶段 `FingerprintStoreUnavailableException`；`RunBatchProbeAsync` 以
  `Coordinator.Abandon(workItem)` 释放未开始 reservation 后向上传播，不 `EndProbe`、不提交指纹、不转成
  `ProbeIncomplete`。runner 的消费者在取下一项前也检查本轮已记录的 `Disabled`，使已观察原因不被其他结果或
  重新启用清空。新增 7 个 `TestCategory("BatchAdmissionFailure")`（同时保留 `Batch`）回归，覆盖末项禁用／故障、
  等待许可、跨 128 末批、重新启用、原生任务 `Cancelled`／`Failed` 结果。
- Tests and Results：
  - 新增类别 `TestCategory=BatchAdmissionFailure`：候选 7 passed／0 failed／0 skipped；先以 `HEAD~1` 产品源码运行
    7 failed（`prefix-failure.log`），证明回归确实捕获 AF-1。
  - `bash scripts/dotnet-local restore ...sln --locked-mode`：PASS。
  - `bash scripts/dotnet-local build ...sln -c Release --no-restore`：PASS，0 警告 0 错误。
  - `bash scripts/dotnet-local test ...sln -c Release --no-restore`：PASS 189／0 failed／0 skipped（原 182 + 7）。
  - `bash scripts/dotnet-local format ...sln --verify-no-changes --no-restore`：PASS。
  - `python3 -m unittest discover -s tests -v`：PASS 63。
  - `python3 scripts/run_isolated_plugin_integration.py`：PASS（718 s）。
  - `python3 scripts/run_isolated_batch_integration.py`：PASS（313 s），discovery／stop／shared_stop／sharing／
    scope／mixed／failure 全跑，配置／触发器／夹具恢复并核验。
  - `python3 scripts/run_isolated_configuration_integration.py`：PASS（249 s）。
  - `python3 scripts/check_governance.py`：PASS；`git diff --check`：PASS；Markdown 140 本地链接／锚点：PASS。
  - 证据索引（仅本机）：`.git/validation-evidence/071142f69e110d6406c81294fc03f0918bb0fc0f/correction-20261016/INDEX.md`。
- Decisions：本次为原范围纠正，无合同变更；复用既有异常、runner 原因计数与原生任务结果映射，未新增结果类型、
  持久化状态、调度机制或执行取消源。
- Remaining In-Slice Work：AF-1 已实现并自测通过；修正后由 B 重核七个 RO／六类 Surfaces，并独立复现关键行为。
- Risks / Deviations：未运行项继续 NOT RUN（真实十万库、内部数据库物理保存故障注入、外部代理／OpenList 联调、
  广泛格式／客户端、发布 ZIP）；准入窄窗口以确定性屏障证明，未新增生产注入开关。
- Head SHA：`071142f69e110d6406c81294fc03f0918bb0fc0f`。

## B Review Result

```text
Reviewed: b86d9c17d7f915108072f54ee098f0f5543fe093..071142f69e110d6406c81294fc03f0918bb0fc0f
Correction Reviewed: e03052655d298adb30cbb7f315da684f27a07285..071142f69e110d6406c81294fc03f0918bb0fc0f
Review Checkout / Developer Report: e5b5462735ecb7a59009fbd993339802820c6db3
Decision: FIX REQUIRED
P0/P1 Blockers: AF-1 (P1), concurrent unstarted admission remains open
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CONTINUES THE SAME TASK 3.1 CORRECTION
```

2026-10-16，B 完成必读清单、B 经验、干净 main 状态及治理 PASS 核查。保留 Task ID／Base／Goal／Scope／High／T4 与已提交合同，不改 Slice、Roadmap 或稳定需求。核对真实 Task Base..Developer Head 的文件范围及可达历史 B PASS，单列纠正差异：本次仅两个产品文件及 `BatchCheckTests.cs`；其间 Task 3.2 页面交付沿用历史身份，不计成本次修正。Developer Head 到报告 checkout 仅 `TASK.md` 不同；当前聚焦构建与独立控制的可执行输入匹配该候选。

### 已修复部分与独立验证

- PASS：B 独立执行指定 Batch／Coordinator／Context／Playback／Configuration 聚焦命令，139 passed／0 failed／0 skipped；TRX 确认包含全部 7 项新增 `BatchAdmissionFailure`，并非零发现。
- PASS：B 以 A 原控制为起点，使用当前测试程序集中的 BatchHarness、真实产品 runner／ExecuteAsync、临时 STRM／内存仓库和假原生保存，独立复现禁用／另一源真实仓库读取失败 latch × runner／ExecuteAsync 四项。禁用返回 Disabled、Revoked=1、Completed=false；状态库故障保留 Checked=NeedProbe=ProbeIncomplete=1、StoreUnavailable=true。四项均零探测、旧基线不变、进度最高 99%、许可／preparing／running 归零；ExecuteAsync 分别抛 OperationCanceledException／InvalidOperationException。仅证明确定性入口，不冒充真实 worker 终态。
- 当前新增异常传播和 Abandon 释放修复了 A 的四个最小反例；已开始后的成功提交规则没有因此失效。但新增“重新启用”回归设置 `ConsumerLimit=1`，只保护下一次取项，不能证明已取出的并发工作也停止准入。

### AF-1 尚未闭合：本轮原因只挡下一次取项，已分派工作可在重新启用后开始（P1）

`BatchCheckRunner.ProcessBatchAsync` 在取项后检查 `counters.Disabled`，随后进入 `ProcessCandidateAsync`。这个本轮已观察原因没有传入后续 `CheckBatchSourceAsync`／owner 准入／实际开始边界；这些路径仍只读当前 `_settings.Enabled` 与管理员停止信号。因此一消费者已报告禁用并结算为撤销后，管理员重新启用会让同轮另一个已分派、尚未开始的消费者恢复探测。最终 Disabled=true／Completed=false 只保证结果标签，不能阻止额外工作。

B 使用两个已有可信基线、URL 已变的源、两个消费者和确定性屏障独立复现；所有实际探测均发生在禁用已被第一项观察／结算、随后重新启用之后：

| 窗口 | 屏障与实际结果 |
|---|---|
| 决策后、取得许可前 | 两项都已通过消费者前置检查并作出需探测决策；第一项禁用并撤销，结算回调重新启用，再释放第二项。额外开始／调用 1，ReliableSuccess=1，Revoked=1，两个基线中一个更新。 |
| 立即取得许可、尚未登记 | 并发上限 2，两项均实际取得许可；第二项卡在 PermitAcquiredBarrier，第一项拒绝结算后重新启用并释放第二项。仍额外开始／提交 1。 |
| 等待许可后、尚未登记 | 并发上限 1，独立 reservation 暂占许可，确认两项均到 PermitWaitBarrier 后释放；第一项因禁用拒绝，第二项获许可但等第一项结算／重新启用后继续。waitCount=2，仍额外开始／提交 1。 |

三个控制均得到 Disabled=true、Completed=false、Checked=NeedProbe=ReliableSuccess=1、Revoked=1、ActualProbeCalls=1，进度 `[0, 50, 99]`、资源最终全零。期望是已观察原因持续约束本轮未开始工作：后续实际开始／成功为 0，两项撤销、两个旧基线保留。统计等式和不补 100% 已满足，不能据此忽略准入义务。第二项在禁用之前没有实际开始，故本反例不要求撤销任何已开始探测或否决其有效提交。

这正是原 AF-1 验收“原因一经观察不能由重新启用清空，后续未开始探测停止”与并发准入边界的未闭合部分，影响 RO-6 及 RO-5／配置禁用的未开始工作约束；不是新范围或 Material Contract Change。维持原 Task 纠正，不另建 Task，不交 A 改合同。

### 同一 Task 的继续纠正与测试要求

1. 将本轮已经观察到的禁用／不可用原因持续约束到已分派但未实际开始的工作，覆盖决策后、许可等待／立即取得、原生准备及实际开始边界。不能仅在下一次取项检查本轮原因，也不能仅靠最终 Completed=false 掩盖新增调用。复用既有本轮上下文和开始／停止协调机制；不要求新增调度器、持久化状态或通用框架。
2. 加入上述三个会失败的并发回归，保留修正前 FAIL。至少明确断言：拒绝原因已被第一项结算、第二项此前未开始、重新启用后同轮零新增开始、各候选一次结算、两项撤销、旧基线与进度／资源正确。以屏障证明立即取得与实际等待，保留单消费者及 A 四项控制；原 `BatchAdmissionFailure` 类别继续作为聚焦入口。
3. 不能将本轮准入停止扩散到独立播放、其他调用者或下一轮；已开始／已加入 running 的工作仍完成保存／验证／条件提交。保留原生自身取消、管理员停止与状态库不可用的原因优先／汇总，不能用新的执行取消源或成功后的禁用检查达成零调用断言。
4. 本轮已有明确 P1，B 不运行昂贵的 stop／sharing 实机及 Slice Final；这些项目本轮均为 **NOT RUN**，不是 PASS 或删减门槛。修正候选仍须执行上文完整 T4，B 下轮独立聚焦、上述控制及指定 stop／sharing；Developer 原完整门槛不能代替新可执行候选的验证。

### 证据、复用边界与 Slice 重核

本机索引：`.git/validation-evidence/071142f69e110d6406c81294fc03f0918bb0fc0f/b-review-20261016/INDEX.md`。包含 helper 源码、四项旧控制与三个新控制的原始结果、单独产品断言（4 PASS／3 FAIL，退出 1）、精确命令、TRX、源码／锁／SDK／构建输入与产物身份。collector 退出 0 只表示成功采集；不将其称为产品 PASS。本机证据不宣称远程可读。

已读取 Developer INDEX、identity 与相关原始测试／batch 日志，保留其自测结果为历史事实；本轮因明确阻塞提前拒绝，**不签发完整 T4 可复用 PASS**。Developer INDEX 对每项新增用例均具有全部断言的概括比实际代码更宽（ExecuteAsync 两项仅断言异常）；本轮四项独立控制已补充核验基线、进度与资源，后续报告须按实际用例说明覆盖。

全部 RO／六类 Surfaces 重新核对：RO-1／2／3／4／7 的历史交付不撤销；RO-5 的本轮未开始工作约束与 RO-6 故障停止仍受本反例阻塞。共用执行／实际开始和进度／结果表面尚不能签发当前 PASS；原生任务、库查询、SQLite 和配置页原始证据保持历史事实，不写成当前全 Slice 已满足。因此不创建下一 Task、不运行 Slice Final、不替换旧 Closure Packet，也不代 A 关闭。真实十万库、内部数据库物理保存故障注入、外部代理／OpenList、广泛格式／客户端和发布 ZIP 继续保留原 NOT RUN 边界。

供 Slice 收尾的经验候选：本轮原因已写入汇总仍可能漏过已分派工作 → 用同轮两个消费者跨决策、许可和实际开始边界验证原因持续生效 → 适用于可重新启用的批量准入；与既有并发屏障经验合并，不记录流水账。

NEXT ACTION: DEVELOPER CONTINUES TASK 3.1; B RE-REVIEWS THE CORRECTION

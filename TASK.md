# Task 2.2 — 运行中探测协调、正常收尾与核心配置

模板来源：[Task 模板](Task/TEMPLATE.md)。范围 authority 为已提交的 [Slice 2](SLICE.md)，流程见 [开发流程](docs/development-workflow.md)；规划／审查参考 [B 经验](docs/agent-experience/task-planner-reviewer.md)，实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 2.2
Parent Slice: 2
Status: READY FOR B REVIEW
Task Base: 13cb8bdac319fcf0b3e7500661bae1c7455077b0
Contract Checkpoint: 7e0240cd1cada74f142b7b0afd612943ca991a91
Slice Base: 924816a84c74f5d79c107478f2d40e621cb8be8d
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

多个客户端播放同一版本化 STRM 时，仅在该源原生探测实际开始后共享其进行中的工作；各客户端随后按自己的原生权限、选源和路径替换取得正确响应。排队不共享，不同源不串用，全局插件主动探测受默认 2／合法 1～8 的统一上限控制。已开始工作在无人等待时继续验证、保存、条件提交和释放资源；管理员能通过 Jellyfin 现有通道保存核心配置、禁用优化并按说明恢复。

闭合 RO-4／RO-5 及 RO-6 剩余核心配置／诊断部分，保持 Task 2.1 已接受的 RO-1～RO-3 和状态库恢复。此计划合并协调与核心配置，因为并发许可池必须消费真实保存配置，启停和故障会影响排队／开始边界；不再按配置字段或内部类另拆 Task。此 Task 后重新对账全部 RO／Required Surfaces；已满足则运行单独 Slice Final 并交 A，不自动创建 Task 2.3。

## B 合法性决定与实际缺口

2026-10-13，规划前 main 工作区干净；`python3 scripts/check_governance.py` 退出 0，已提交 ACTIVE 合同及真实 SHA／祖先关系合法。已核对全部 Required Outcomes／Surfaces，剩余协调／配置义务尚未满足。Task 2.1 已经 B 独立复审 PASS，完整 Base..Head 为 `7e0240cd1cada74f142b7b0afd612943ca991a91..198f4ff2accd5bc9fcd87518a9684b9d068de103`；报告／B 决定保留在 `13cb8bdac319fcf0b3e7500661bae1c7455077b0:TASK.md`，本机证据见 `.git/validation-evidence/198f4ff2accd5bc9fcd87518a9684b9d068de103/b-rereview-20261014-03/INDEX.md`。完整产品、批量与共享能力没有由该 PASS 提前验收。

已核对真实代码：`StrmPlaybackOptimizer.CheckSourceAsync` 是共用源入口，`ProbeAndVerifyAsync` 直接调用原生刷新并验证本次结果／保存后条件提交；`ProbeExecutionContext.MarkCall` 与 `MediaEncoderDispatchProxy` 可观察匹配的原生 GetMediaInfo 调用，但没有协调登记、许可池或实际开始通知。SQLite 已支持项目＋源主键和原子 expectedPrevious 提交，无需另造存储／状态机。`PluginConfiguration` 只有 PlaybackAutoCheck，`IPlaybackSettings` 只读这一项；Enabled、DetailedLog、并发保存／启动生效与操作说明不存在。

固定源码 `BasePluginOfT.UpdateConfiguration` 先替换内存配置再保存，原生 API 以 `Plugins/{id}/Configuration` GET／POST 暴露配置；不能仅沿用赋值顺序就声称保存失败不生效。开始信号、共享结果与用户响应分离、配置校验／持久化失败及启动许可池属于本 Task 必需验证。已提交 Contract 可满足，保持 Slice ID／Base／不变量和停止边界，不交 A 修改合同。

## 实际缺口与实施范围

1. **共用协调与实际开始。** 在既有源检查／原生适配链接入一个进程内 ProbeCoordinator，键为稳定项目 ID＋源键，播放和未来批量共用。登记只包含已经进入匹配原生探测调用且仍在执行的工作；创建 Task、进入刷新准备、排队、取得许可均不足。明确接入层实际开始通知与同源开始竞态：准备中的同源请求可以等待并重新判断，但不能被登记或报告成已加入共享探测，也不能因此重复实际启动。排队请求各自保留生命周期；获得机会后重读当前 STRM、指纹及本源原生结果，不按排队时旧决策盲目探测。
2. **共享与正常收尾。** 共享的是探测／验证／提交工作，不是第一位用户的完整 MediaSourceInfo／PlaybackInfo。每个调用者按自己的用户可见范围、选源、路径替换及原生语义重新读取源和 Manifest；源集／版本变化按现有明确重试路径处理。等待者退出或数量为零不取消已开始工作，执行继续完成全部成功条件核对和条件提交。完成／失败／原生取消异常／Manifest 再变／提交冲突／状态库异常均清除运行登记并释放许可；完成 Task 不留作进行中缓存。保留原生自身取消异常保护，不新增客户端停止关联、共享执行取消源或成功后人为取消检查。未接管入口继续原 token／权限委托。
3. **全局上限与权限。** 所有插件主动发起的源探测走同一个许可池，默认 2，可保存 1～8，下一次 Jellyfin 启动采用新值。加入实际运行中同源工作不额外占许可；不同源独立，不持有阻碍其他源的全局锁等待。许可覆盖主动原生执行及可靠收尾，不让异步返回或等待者退出提前释放。false 请求不启动、排队执行或接受变化指纹，其他允许上下文不能被记作它获准探测；普通／旧／不支持输入、禁用和外部独立原生刷新不进入插件限流。状态库故障沿用停止优化／原生委托，不转无条件插件探测。
4. **核心配置与生效。** 新增 Enabled 默认 true、保留 PlaybackAutoCheck 默认 true、并发默认 2、DetailedLog 默认 false；可选字段名称由实施决定并记录准确 API 示例。启用／播放检查保存成功后下一次检查请求生效，未实际开始的排队工作在准入时也重读最新成功保存的启停值；详细日志下一次检查操作生效。已实际开始的探测使用稳定上下文，禁用不取消其收尾；排队请求执行前重新核对是否仍可优化；关闭后的原生委托保留权限，并明确独立原生探测不受插件许可池约束。并发变更只在重启后生效，读回保存值与当前运行上限须能区分。拒绝 0／9／负数／非整数／错误类型等非法值，提供可识别错误反馈，不落盘、不改变当前有效配置；模拟持久化失败也不能呈现已生效或成功保存。既有仅含 PlaybackAutoCheck 的配置加载保留该值并补合法默认；已存非法配置须明确诊断及恢复方法，不静默接受。
5. **用户操作与诊断。** 利用 Jellyfin 已有配置保存通道提供可操作 GET／POST／核验和重启步骤，示例仅使用占位认证，不增加独立 UI／调度按钮。说明禁用／播放检查关闭的差异、并发生效时机、SQLite 修复后重启再次检查，以及无 SHA-1 同 URL／同 Size 的识别限制。日志区分首次信任、复用、真实成功、未完成／冲突／库不可用和排队／实际运行中加入；详细日志开关不能关闭必要故障反馈。不泄露完整 URL、签名、token、Cookie、私有路径，不把等待者数量计为探测成功数。
6. **回归与实证。** 在既有 solution／MSTest 项目增加确定性协调和配置集成用例；使用可控开始／完成屏障，避免靠 sleep 或调用时间猜共享成功。扩展 `scripts/run_isolated_plugin_integration.py` 默认入口，在仓库隔离实例验证实际开始后的同源共享、不同项目／版本源、代表性全局上限、核心配置保存／拒绝／生效／重启与原生对照，保留 Task 2.1 全部实际场景和清理恢复。按分层证据补完整核心矩阵索引，修正缺失项；不把 B01／B02 的批量部分、X08 的真实批量停止或延期 UI 写成 PASS。

允许文件边界：现有插件配置／生命周期／注册、Services／Interceptors 及必要协调代码，现有测试项目，确有必要的依赖／锁，隔离集成／媒体工具及其 Python 回归、核心配置操作说明／README、architecture CURRENT／test-matrix／progress／Task 报告。不要求拆分 NativeProbeExecutor 或重构类名；先复用既有解析、决策、SQLite 和成功／保存信号。SLICE／Roadmap／稳定需求和 V4.2 原文冻结；发现 Contract 问题交 A。

## 验收条件

- [ ] **AC-T1：实际开始与只共享运行中。** 确定性证明排队、许可已得但未进匹配原生调用、刷新准备均不登记共享；实际开始后同源允许请求才加入且同次只实际执行一次。开始竞态不重复，同键排队仍各自重查；完成后新请求重读当前版本／指纹，正常已接受版本不重复探测，失败或新变化可重试。对应 RO-4、AC-5／AC-6、T20／X08。
- [ ] **AC-T2：独立收尾与保护。** 所有等待者退出后已开始执行仍完成保存／验证／稳定版本条件提交，资源不提前释放。失败、原生自身取消异常、保存失败、文件再变、提交竞争及库故障各路径保留可信基线且释放许可／登记，后续请求不复用完成／失败任务；维持同元数据保存失败对照。退出验证只作用于等待生命周期，不创造执行取消源／人为取消实机门槛。对应 RO-2／RO-5、AC-3／AC-4／AC-6。
- [ ] **AC-T3：全局上限、多源及调用者边界。** 默认 2、配置 1／8 有确定性最大同时执行验证；代表性隔离 Jellyfin 默认 2／配置 1 的计数和实际重叠证明上限生效、不同源可独立执行。真实关联版本／不同项目不串结果、指纹或地址；同源不同调用者按自身原生授权／选源／路径替换重新构建完整响应。false 请求不提高权限，不归因另一执行；独立原生刷新不被插件限流。对应 RO-4、AC-5／AC-7、T25／T28、B01／B02 核心部分。
- [ ] **AC-T4：核心配置完整闭环。** 四项默认、旧配置兼容、合法 GET／POST 保存／读回／重启持久化和生效时机可操作验证；0／9／负数／非整数／错误类型拒绝且有效配置与保存文件不变，保存失败明确反馈且不生效。禁用整个插件与关闭播放检查保留原生，未开始排队工作准入时重新判断，进行中执行收尾不受影响；并发保存不热改当前池。操作说明可用于隔离环境，不依赖未来 HTML 页。对应 RO-6、AC-7、X09、B01 核心部分。
- [ ] **AC-T5：诊断、恢复与既有能力。** 首次信任／复用／真实成功／未完成／共享／库不可用证据可区分且脱敏，详细日志关闭仍有必要错误反馈。SQLite 故障停止优化、原权限／旧库保护与修复重启恢复不退化；T01～T28 核心部分和 Required Surfaces 有实际用例／输入／原始产物索引，延期部分单独 NOT RUN。对应 RO-1～RO-3／RO-6、AC-1～AC-4／AC-7／AC-8、X01／X10。
- [ ] **AC-T6：完整 T4 与范围。** 新候选全部指定门槛、真实默认实机入口及部署产物核对通过；原始日志／首次失败／重跑与恢复可核验。只改 Task 文件范围，不改 Contract、固定业务规则或生产数据。Task PASS 后由 B 重查全部 RO／Surfaces，完整时另跑 Slice Final 并提交 Closure Packet，A 才最终审查／关闭。

## 同 Task 修复实施方案（简化版，B，2026-10-14）

本方案按用户“判断复用还是探测应在实际行动之前”的要求，修订 `26587a1532ab5f49a7821a9da9549471490bd493` 的实施建议，保留最新 B Review 的全部阻塞、验收与下方必要测试。继续同一 Task 2.2，ID／Base／Goal／Scope／High／T4／Contract 不变；状态仍为 FIX REQUIRED。本轮只调整规划。Developer 接手后标记 IN PROGRESS，交付修正及证据后交 READY FOR B REVIEW。

只修补现有协调器与播放检查流程，沿用 preparing／running、ProbeAdmission、Complete／Fail／Abandon。无需新增 lease 类、业务状态枚举或持久化状态。优先修改 `Services/ProbeCoordinator.cs`、`Services/StrmPlaybackOptimizer.cs`，开始拒绝保护确有必要时调整现有 Context／encoder proxy。解析、决策、SQLite、配置写入保护及启动脱敏继续复用。

### 阻塞与修复对应关系

以下是当前修正候选的结论；方案调整没有使任何未修复项自动 PASS。R1／R2／R5／R6 仍阻塞，R3／R4 保留通过的控制事实。完整原始复审与首轮历史继续保留在下方 B Review Result。

| ID／当前状态 | 剩余问题与用户影响 | 对应修复／主要位置 | 必须通过的验证 |
|---|---|---|---|
| **R1：待修复** | 开始通知位置已修正，但同源准入与开始转换不原子，仍可产生第二 owner；开始拒绝后仍可能调用原生，造成重复探测和额外等待。 | 代码修补 1：ProbeCoordinator 的登记操作共用一把短时锁；现有 Context／encoder proxy 的开始拒绝必须阻止被拒调用。实际开始登记继续在匹配 GetMediaInfo 处。 | 可控 Acquire／开始／结束交错，同源实际调用一次；准备不算运行共享，拒绝调用为零；完成后重查，旧收尾不删新登记。 |
| **R2：待修复** | 等待后沿用已有主流的旧源，已处理版本仍重复探测，或当前主流消失却跳过探测。 | 代码修补 3：统一到行动前的检查执行循环，读取当前源／Manifest／基线／配置后 Decide；等待许可或同源工作后回到同一位置重读重判。 | 从真实旧源入队：新版本已接受后零新增探测，当前缺流后必要探测；版本／启停／库故障变化按当前输入处理，地址／主流／指纹正确；复用不等待探测许可。 |
| **R3：已修正，保持回归** | 原配置中途写入失败破坏旧文件的问题，已由临时文件完整写入后原子替换修正。 | 复用现有 Plugin.UpdateConfiguration 实现；本轮保持已接受的文件／内存保护行为。 | 中途写入失败保留旧文件与有效配置，重启仍可读旧值，随后合法保存可恢复。 |
| **R4：已修正，保持回归** | 原启动非法配置日志泄漏私有路径的问题已修正，错误反馈仍存在。 | 复用现有启动脱敏诊断；继续保留插件标识及可操作恢复说明。 | 非法配置仍有诊断，日志不含私有目录／完整签名 URL／token／Cookie；必要故障反馈不受详细日志关闭影响。 |
| **R5：待补证** | 不同账号响应、实际边界上限、并发保存后的运行行为、无人等待收尾缺少完整行为证明；不能据此认定账号已串用或配置已出错。 | 在既有测试及默认隔离脚本补控制屏障／差异响应／实际计数，更新矩阵与证据索引；发现产品失败时继续修正同 Task 的现有代码。 | 两个不同 User 各自响应正确；实际开始上限 1／2／8；保存 1→2 后重启前仍按 1、重启后按 2；等待退出后已开始工作仍提交／释放。新候选完整 T4 与默认实机证据闭合。 |
| **R6：待修复** | owner 获得许可后，准入异常在清理保护之外，泄漏许可／准备登记；后续需要探测的影片可能一直等待。 | 代码修补 2：扩大现有异常保护至全部 owner 路径；Complete／Fail／Abandon 共用 Finish，在统一锁内取出并清空现有 Permit，锁外单次释放／通知；原生委托前放弃未开始 owner。 | 禁用／取源／库故障委托抛错后登记与许可归零，异常和旧基线保持；重新启用后的另一源能继续；重复结算不重复释放，等待者退出不影响已开始收尾。 |

R1 管“谁能开始”，R2 管“本次行动该复用还是探测”，R6 管“各结束路径如何释放”，R5 验证这些行为及剩余调用者／配置边界。共同使用现有协调／检查链，避免为每个编号新增内部模块。实施顺序仍为 **R6 → R1 → R2 → R5 补证**；R3／R4 进入原 T4 回归。

### 三处代码修补

1. **同一把短时锁保护登记（R1）。** 用同一把锁包住 running／preparing 查询、owner 登记、准备转运行和结束移除，避免两次独立查询之间产生第二 owner。锁内只操作内存登记；等待许可、文件／数据库／原生调用、任务通知都在锁外。只有当前 preparing owner 才能在匹配 GetMediaInfo 调用处转为 running；开始被拒绝时阻止该次原生调用并明确退出／重查，不能只记警告后继续。保留准备等待与运行中共享的区别；移除时核对 work item 身份。
2. **扩大现有 try/catch，统一单次释放（R6）。** 将获得 owner 后的准入代码也纳入现有异常保护，所有退出沿用 Complete／Fail／Abandon。Finish 在上述锁内取出现有 `workItem.Permit` 并置空，作为已结算判据；重复结算直接返回，首次才移除自己的登记，锁外释放许可并通知等待者。不必再增加完成标志。禁用／原生委托前先 Abandon 自己的未开始 owner，保留原权限和原异常；已开始探测继续覆盖保存／验证／提交全部收尾。测试也通过这些方法清理，不能直接 Permit.Release 绕过登记。
3. **把复用／探测判断集中到实际行动前（R2）。** 将现有 CheckSourceCoreAsync 与 AdmitQueuedOwnerAsync 中重复的业务决策收敛到一个共用检查执行循环；入口只筛选权限／支持输入和协调等待，不把入口或入队时的决定保存成执行依据。每轮按本请求 user／source Id／路径替换获取当前原生源（不探测），读取 Manifest／可信基线／适用启停，再调用现有 Decide 并按结果行动：复用／首次信任、原生委托或主动探测。需要探测但尚未取得许可时先等待，取得后回到这个位置重读重判；等待同源准备／运行工作结束后也回到这里。立即可复用的请求不必先等待探测许可。主流是否存在依据当前源判断，不能按旧快照决定是否重读。保留 Manifest 一致性、expectedPrevious、false 权限和各调用者响应边界；实际探测开始登记仍位于匹配 GetMediaInfo 调用，不在该回调中加入文件／SQLite／业务决策。

最终决策位置统一为：

```text
读取当前源／Manifest／基线／配置 → Decide → 执行相应行动
                                      │
                       需要探测但须等待许可／同源工作
                                      │
                           等待结束 → 回到读取处
```

判断和行动之间避免插入新的排队等待；发生等待就重新读取判断，更新本次探测 Manifest／expectedPrevious 上下文。已取得的 owner／许可沿用当前调用的局部变量，不因回到读取处重复取许可；重判为复用或委托时调用 Abandon，重判为探测时使用当前 owner。判断到原生探测仍可能经过原生刷新准备，文件也可能随后再变；保留实际开始资格核验及探测后的保存／Manifest 核对，不以“行动前已判断”代替成功提交门槛。无需新增决策服务或业务状态，只调整现有调用位置与控制流。

### 验证与交付

先修复 R6，再修复 R1／R2，补 R5 证据；都在原 Task 内完成。先运行下方聚焦命令，最后运行完整 T4 和默认隔离 Jellyfin 入口，保留首败、重跑与实际候选身份。以下是必要行为验证，不以新增内部类型／字段数量验收：

| 输入 | 必须得到的结果 |
|---|---|
| 排队禁用后委托抛错；无探测取源／源消失／库故障委托失败 | 原异常／旧基线保护；登记和许可归零；恢复启用后另一源能继续，不需重启。重复结算不重复释放，旧 owner 不删除同键新登记。 |
| 第二请求准入与第一请求开始／结束交错 | 同源只有一个实际探测；准备不算运行共享；开始拒绝不调用原生；完成后重查，不缓存完成任务。用可控屏障，不靠顺序调用或概率循环。 |
| 行动前统一决策；等待期间新版本已接受、主流消失、启停或基线再变 | 无等待／等待许可／等待同源结束都回到同一业务决策位置。从 old URL／old 主流入队：接受新版本后零新增探测，当前缺流后按需探测；核对当次地址／主流／指纹，补 Manifest／SHA-1／Size、源身份和库故障再变化。另证无需探测的请求不受已占满的探测池阻塞。 |
| 两个不同 User／路径替换共享同源 | 同次一次探测，各自得到合法且可区分的原生响应／可见源，不能只记录参数或使用两个 null user。 |
| 实际开始的上限 1／2／8；保存并发 1→2 前后与重启 | 控制用例验证实际最大执行数；实机重启前仍按 1、重启后按 2，保留默认 2／配置 1及原生刷新独立对照；恢复配置和夹具。 |
| 运行中等待者退出／无人等待 | 用加入与退出屏障替代 Task.Delay；已开始探测仍保存、条件提交并释放，保留固定 PlaybackInfo None token 和原生取消异常回归。 |

已失败输入及 B 控制源见 `.git/validation-evidence/dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a/b-rereview-20261014-06/`；修正起点实现 `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a`，审查检查点 `ab738917bc6fc0fa4703c0e6d7297b7dc43e5b03`。工具内部屏障可随代码组织适配，原交错、输入和用户结果不得删减；忽略目录不作为产品依赖。新报告逐项关联 R1／R2／R5／R6、原始证据与矩阵，保持 R3／R4 的通过事实和旧失败。B 复审后才判 PASS；不提前移动 Slice 指针或新增 Task。

## 必要测试

cwd 为 `/opt/jf-strm-probe`；固定 SDK `10.0.401`／net10.0，solution `Jellyfin.Plugin.StrmProbeOptimizer.sln`，插件／MSTest 项目路径沿用现有目录。目标 Jellyfin `12.2.0`／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`，镜像／环境见 [环境交接](docs/development-environment.md)。本计划无产品测试 PASS。

### 开发／修正反馈

实施前记录已有改动并运行 `python3 scripts/check_governance.py`。先跑新增／修改、已知失败与直接受影响回归，再运行昂贵最终门槛；不得删减既有测试来取得通过。

```bash
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~Coordinator|FullyQualifiedName~Configuration|FullyQualifiedName~PlaybackOptimizerTests|FullyQualifiedName~Fingerprint|FullyQualifiedName~CoreServiceRegistrationTests|FullyQualifiedName~ProbeExecutionContextTests|FullyQualifiedName~MediaSourceManagerProxyTests'
python3 -m unittest discover -s tests -v
```

新协调／配置测试名称包含 Coordinator／Configuration 以进入聚焦筛选，实际类型与发现数写入报告；现有代理／注册测试已按真实类型纳入，实施后补核对，不用筛选零发现冒充通过。覆盖开始屏障／同源竞态、全局上限、版本再变／成功及故障收尾、不同调用者／false 权限与配置原子保存。集成边界改变时尽早运行 `python3 scripts/run_isolated_plugin_integration.py`，工具先用相应 Python 回归反馈。依赖如有真实新增先生成锁并审查，再 locked restore，不预设新增依赖。

### 最终检查点门槛

共享工作跨原生刷新、保存、SQLite、并发和用户权限，T4 保留全部既有回归及真实入口：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/check_governance.py
git diff --check
python3 scripts/run_isolated_plugin_integration.py
```

最终全套覆盖聚焦用例时记录关系，无须机械重复。检查修改文档本地链接／锚点并留精确命令。实机至少对账：同源实际开始后的第二请求与一次匹配探测／一次提交；排队场景获取机会后重查不重复已成功版本；默认 2 和重启生效的 1 在三个独立变化源上表现出实际重叠／排队与最大执行数；至少两个原生关联版本不串地址／主流／五字段指纹；配置 API 四项默认／合法保存读回、非法值／错误类型拒绝、下一请求启停／详细日志及并发重启生效；代表性独立原生刷新不被插件池阻塞。计数必须来自实际开始／结束观测，不能只看 HTTP 返回、Task 数量或媒体 GET 总数。非整数由真实 API 反序列化拒绝，保存失败可用原生配置序列化／持久化控制测试，不强制破坏运行实例文件。

仅使用仓库专用实例、临时源与慢速本地媒体服务；新增前确认作用域，退出恢复 STRM／媒体／配置／权限／版本关系和原生地址，核验临时库条目已移除、实例健康。无真实批量任务、外部代理或人为执行取消实机门槛。确定性无人等待收尾与开始竞态测试不能写成真实客户端取消探测。音频-only 实机限制保持原披露。

### B 独立验证

审查真实 `Task Base..Developer Head` 与原始产物。在匹配候选独立运行上述聚焦 C# 命令及默认实机脚本，复现实际开始前不共享／开始后共享、无人等待仍提交、默认／边界上限与异常释放、版本重查／不同调用者权限和非法／失败配置不生效；实机关键为同源一次探测、不同源代表性上限、配置下一请求／重启生效及既有 SQLite／原生地址重启恢复。原生开始／授权／保存和配置更新源码边界重新核对。其余完整门槛按流程核验匹配原始证据后可复用，缺失／矛盾／不匹配重跑；不因角色变化机械重复全部构建。

### 证据与重跑规则

稳定本机索引 `.git/validation-evidence/<implementation-sha>/<run-id>/INDEX.md` 或 CI 产物，保留到 A 最终决定。记录候选 SHA／被测工作区内容、精确命令／cwd／SDK、依赖锁／源码／镜像、隔离配置与夹具内容身份、并行／筛选／重试、产物／部署依赖摘要、退出码／耗时／通过失败跳过数及原始脱敏日志；每次实机使用独立目录，不覆盖首败。逐项关联 AC、矩阵行和真实输入，计数区分排队／已开始／加入／成功／未完成及每源 SQLite／返回／已保存结果。

可执行源码、测试、工具、依赖、配置或夹具改变后新候选重跑完整 T4；文档后继可明确比较输入后复用，重跑消费文档的治理／链接检查。既有 Task 2.1 原生基线必须持续回归，不拿旧运行代替新协调候选。Task 通过不替代单独 Slice Final，未跑外部／批量／发布不写 PASS。

## 非目标

- IScheduledTask、真实批量停止／分页／有界生产消费／进度／定时、媒体库范围、HTML 完整配置页、ILibraryPostScanTask、独立运行按钮／调度器（Slice 3）。
- 大规模真实库／十万模拟枚举、扫描联调、广泛客户端／格式／OpenList／JellyfinProxy、发布 ZIP、其他服务器版本（Slice 4）。
- 并发热调整、自动修复数据库、新持久化执行状态、媒体流／PlaybackInfo 缓存、UpdatePathOnly／独立路径同步；生成器／STRM 写入／移动／删除、远程内容哈希／OpenList API／代理改写、另带 FFmpeg、生产操作。
- 新增客户端停止到探测取消关联、共享执行取消源、成功后额外取消检查、人为执行取消实机验收；原生自身取消异常保留原语义与回归。
- 改变 Slice／Roadmap／稳定需求、移动 Slice Base、宣称关闭 Slice 或自动实施未授权后续范围。

## Developer Correction Report (R1 / R2 / R5 / R6, current candidate)

- Changed Files：`src/Jellyfin.Plugin.StrmProbeOptimizer/Services/ProbeCoordinator.cs`、`Services/StrmPlaybackOptimizer.cs`；`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ProbeCoordinatorTests.cs`、`PlaybackOptimizerTests.cs`；`scripts/run_isolated_plugin_integration.py`。未改配置字段、依赖锁、`ServiceRegistrator`、解析／决策、SQLite schema 或 `Plugin.UpdateConfiguration`。
- R1 实际开始边界原子化：`ProbeCoordinator` 改用同一把短时锁包住 running／preparing 查询、preparing 插入、preparing→running 转换与结束移除，消除两次独立查询之间的第二 owner 竞态；`TryMarkStarted` 只有当前 preparing owner 才能转为 running。`StrmPlaybackOptimizer.MarkStarted` 在经核验的匹配 `IMediaEncoder.GetMediaInfo` 调用处回调，`TryMarkStarted` 失败即抛 `ProbeStartRejectedException` 阻止该次原生调用，不再只记警告后继续；失败经 owner 的 catch 结算为 Fail。
- R2 准入重读当前源：`AdmitQueuedOwnerAsync` 不再按传入旧快照是否有主流决定是否重取，而是始终按本调用者 user／source Id／路径替换重新取当前原生源，再读取当前 Manifest／可信基线／启停并 `Decide`。排队期间已接受版本零重复探测，主流消失仍按需探测；等待同源工作结束后经 `CheckSourceAsync` 重新准入，禁用后按原权限委托。
- R6 准入清理：owner 取得许可后的全部准入、委托、执行与提前退出纳入同一 try/catch；`AdmitQueuedOwnerAsync` 在每个提前退出（禁用／非 STRM／库故障／复用／加入）前先 `Abandon` 自己的未开始 owner，避免在原生委托期间占用许可；`ProbeCoordinator.Finish` 在同一锁内以 `Interlocked.Exchange` 取空 `Permit` 作为单次结算判据，重复 Complete／Fail／Abandon 不重复释放、不删除同键更新登记；`Abandon` 不再返回，所有释放与通知走 `Finish`。
- R5 补证：新增确定性用例覆盖开始竞态第二 owner（注入真实协调器 `PermitAcquiredBarrier`）、准入委托异常许可／登记归零并恢复、同源共享两个不同 `User` 各自可见源、上限 1 以实际开始边界、零等待者仍提交且以 `SharedJoinBarrier` 取代 `Task.Delay`；实机脚本新增保存并发 1 后重启前的运行上限仍为 2 的观测。
- Tests and Results：候选 `b3764f43713bbc22bdc00cab122340e241110484`，本机证据 `.git/validation-evidence/dc62db4661286f2a7fa59e4c53cef1bf8c363614/developer-fix2-t4-20261014-100054/INDEX.md`。locked restore、Release build（0 警告 0 错误）、全套 C# 110/110、format verify、Python 30/30、governance、`git diff --check` 全部 exit 0；聚焦筛选 79/79；默认实机脚本 JSON `status=PASS`（同源一次探测一次提交、默认 2／重启前保存 1 仍为 2／重启后配置 1 串行、池饱和原生刷新独立、配置拒绝／保存／下一请求／重启、既有场景与清理恢复）。独立控制 harness 复现 B 的四个失败观测，全部转为 PASS：R1 `secondOwner=false`、R2 已接受版本 `probes=0`、R2 主流消失 `probes=1`、R6 `ActivePermits=0/PreparingCount=0`。
- Decisions：`MarkStarted` 在原生调用前同步触发（同一异步链），拒绝时抛异常中止冗余调用；准入统一为“读取当前源／Manifest／基线／启停 → Decide → 行动”，等待后回到同一位置重读；`Abandon` 语义改为幂等结算。
- Risks / Deviations：控制证据使用测试原生代理与临时 STRM，不是真实 ffprobe 竞态注入；非整数／错误类型配置仍由 Jellyfin 反序列化层拒绝（HTTP 500），插件级越界值为 400，未统一状态码。
- Head SHA：`b3764f43713bbc22bdc00cab122340e241110484`。

## Developer Correction Report (R1–R5, superseded candidate)

> Historical. This report describes the rejected candidate `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a`; its
> R1 start boundary, R2 source re-read and R6 cleanup were found insufficient by B. Retained for traceability.

- Changed Files：`src/Jellyfin.Plugin.StrmProbeOptimizer/Services/ProbeCoordinator.cs`、`Services/ProbeExecutionContext.cs`、`Services/StrmPlaybackOptimizer.cs`、`Plugin.cs`；`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ProbeCoordinatorTests.cs`、`ConfigurationTests.cs`、`PlaybackOptimizerTests.cs`；`scripts/run_isolated_plugin_integration.py`、`scripts/isolated_media_server.py`。未改配置字段、依赖锁、`ServiceRegistrator`、解析／决策或 SQLite。
- R1 实际开始边界：`ProbeCoordinator` 新增 `_preparing` 状态；`AcquireAsync` 先 `_permits.Wait(0)` 判断是否等待；`TryMarkStarted` 由 `ProbeExecutionContext.MarkCall` 在经核验的匹配 `IMediaEncoder.GetMediaInfo` 调用处（经 `MediaEncoderDispatchProxy`）回调触发，不再在刷新准备前登记。准备中的 owner 可被同源请求等待但 `IsRunning=false`，不会记为“Joined a running”，也不重复实际启动；`TryMarkStarted` 发布 running 后再清除 preparing，避免竞态重复准备；开始失败／委托／放弃路径经 `Abandon` 释放许可与登记。
- R2 排队重查：`ProbeReservation.Waited` 区分是否真的等待过；只有等待过的 owner 在获得机会时执行 `AdmitQueuedOwnerAsync`，重读当前 Manifest、可信基线、本调用者原生源、库故障标记与成功保存的启停配置，再决定复用／委托／按最新版本开始。首次立即取得许可的请求行为不变，避免对既有入口重复原生取源。
- R3 配置持久化保护：`Plugin.UpdateConfiguration` 先把候选序列化到同目录临时文件，完整写完后 `File.Move(overwrite: true)` 原子替换；中途失败删除临时文件并保留旧有效文件与内存值，返回错误反馈。
- R4 隐私：启动读到非法配置的诊断改为不含 `ConfigurationFilePath`／私有目录，使用插件 ID 与“重新保存并重启”的可操作说明；必要错误反馈保留。
- R5 必要验证：新增准备边界、上限 1／8 最大执行数、零等待者仍提交、池饱和时普通原生工作与原生刷新不受阻、同源共享调用者各自路径替换等确定性用例；实机脚本新增拒绝请求前后持久化文件字节比较、`DetailedLog` 下一请求生效、`Enabled=false` 下一请求委托、并发重启持久化，以及插件池限 1 饱和时原生 FullRefresh 仍完成的对照。
- Tests and Results：候选 `dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a`，本机证据 `.git/validation-evidence/dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a/developer-fix-t4-20261014-05/INDEX.md`。locked restore、Release build（0 警告 0 错误）、全套 C# 102/102、format verify、Python 30/30、governance、`git diff --check` 全部 exit 0；聚焦筛选 71/71；默认实机脚本 JSON `status=PASS`（同源一次探测一次提交、默认 2／配置 1 上限、原生刷新独立于插件池、配置拒绝／保存／读回／重启、既有 Task 2.1 场景与清理恢复）。计数取自实际开始事件与慢速媒体标记。
- Decisions：`MarkCall` 回调在原生调用前同步触发（同一异步链），因此准备与真实开始边界确定；等待过的 owner 才重查，避免破坏 Task 2.1 已接受入口的原生调用计数。
- Risks / Deviations：非整数／错误类型配置仍由 Jellyfin 反序列化层拒绝（HTTP 500），插件级越界值为 400，未统一状态码；实机池饱和对照使用原生 FullRefresh 端点，不声称由真实批量任务饱和。
- Head SHA：`dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a`。

经验候选供 A 在 Slice 收尾取舍（问题 → 做法 → 适用条件）：

1. 开始信号接在刷新准备而非匹配原生调用 → 把共享登记挂到经核验的匹配编码器调用，并把“准备中”与“运行中”分离 → 适用于接入层共享边界，准备态不能当作已开始。
2. 排队任务沿用入队前决策 → 只对真正等待过的 owner 在取得机会时重读当前 Manifest／指纹／原生源／启停 → 适用于许可池排队准入；立即获准的请求无需重复重查。
3. 原生 XML 序列化先截断目标文件，仅在序列化前抛错的对照掩盖了中途失败 → 用完整写入临时文件后原子替换，并以“打开／写入后失败”验证旧文件与内存值不变 → 适用于配置持久化保护。

## Developer Completion Report（首轮，历史）

- Changed Files：`src/Jellyfin.Plugin.StrmProbeOptimizer/Plugin.cs`、`PluginConfiguration.cs`、`Services/IPlaybackSettings.cs`、`Services/ProbeCoordinator.cs`（新增）、`Services/StrmPlaybackOptimizer.cs`；`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ProbeCoordinatorTests.cs`（新增）、`ConfigurationTests.cs`（新增）、`PlaybackOptimizerTests.cs`、`MediaSourceManagerProxyTests.cs`；`scripts/run_isolated_plugin_integration.py`。`ServiceRegistrator.cs` 最终未改（曾试加早建 `ProbeCoordinator` 注册，因启动顺序问题回退）。
- Implemented：新增进程内 `ProbeCoordinator`，以项目 ID＋source key 只登记已实际进入匹配原生调用且仍在执行的工作；`AcquireAsync` 先取全局许可再判断是否已有同源运行中探测，排队／等待许可不算开始，`TryMarkStarted` 是接入层实际开始信号，`TryMarkStarted` 失败即释放多余许可并加入已有执行；`Complete`／`Fail` 先移除登记再释放许可，完成／失败／取消／校验失败均释放，完成项不被后续请求复用。`StrmPlaybackOptimizer` 在获得执行机会时重读当前 Manifest／指纹，加入者只等待共享结果、随后按自身原生权限重新取源并重查，不串用他人的 `MediaSourceInfo`；等待者取消只结束其等待，不取消已开始执行；同版本共享失败原样上抛，不同版本则重新判断。全局池惰性创建、读取插件启动时捕获的并发值（默认 2，合法 1～8），规避 Jellyfin 先解析 `IMediaSourceManager` 后创建插件实例导致的过早构造。`PluginConfiguration` 新增 `Enabled`（默认 true）、`MaxConcurrentProbes`（默认 2）、`DetailedLog`（默认 false），保留 `PlaybackAutoCheck`；`Plugin.UpdateConfiguration` 先校验再持久化、成功后才发布内存值，非法值抛 `ArgumentException` 且不落盘不生效，持久化失败保留旧有效配置；启动读到已存非法并发时记录诊断并退回默认 2。`IPlaybackSettings` 暴露实时启用／播放检查／详细日志与启动并发。日志区分开始／加入（带运行数与许可数）、复用、真实成功提交、失败与库不可用，脱敏。
- Tests and Results：候选 `d651950950d6d3ad2be4322ddf8f0afb658c7755`，本机证据 `.git/validation-evidence/d651950950d6d3ad2be4322ddf8f0afb658c7755/developer-t4-20261014-0203/INDEX.md`。最终门槛：locked restore、Release build（0 警告 0 错误）、全套 C# 91/91、format verify、Python 30/30、governance、`git diff --check` 全部 exit 0；聚焦筛选 60/60；默认实机脚本 JSON `status=PASS`（含同源共享、默认 2／配置 1 上限、配置 API 拒绝／保存／读回／重启、既有 Task 2.1 场景与清理恢复）。计数取自实际开始事件与慢速媒体标记，非 HTTP 返回或任务数。
- Decisions：`ServiceRegistrator` 不再早建全局池，改为在 `StrmPlaybackOptimizer` 内惰性创建并消费 `IPlaybackSettings.MaxConcurrentProbes`；非整数／错误类型配置由 Jellyfin JSON 反序列化拒绝（HTTP 500），插件级越界值由 `UpdateConfiguration` 拒绝（HTTP 400），二者都不改变有效配置与文件，如实记录未统一状态码。
- Remaining In-Slice Work：RO-4／RO-5 与 RO-6 核心配置／诊断已在本候选实现并验证；待 B 独立审查后重新对账全部 RO／Required Surfaces，满足时运行单独 Slice Final 并交 A。
- Risks / Deviations：启动顺序导致全局池若在插件注册前创建会读到默认 2，已用惰性创建规避并有实机重启生效证据；非整数／错误类型拒绝状态码为 500 而非 400，属 Jellyfin 反序列化层，未做插件内统一。
- Head SHA：`d651950950d6d3ad2be4322ddf8f0afb658c7755`。

经验候选供 A 收尾：合同矩阵应索引到具体新旧输入和原始产物，不能以测试名称／总数或脚本 PASS 推断缺失分支；本轮不另写开发流水账。

## B Review Result

```text
Reviewed: 13cb8bdac319fcf0b3e7500661bae1c7455077b0..dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a
Reviewed Contract: committed SLICE.md; Contract Checkpoint 7e0240cd1cada74f142b7b0afd612943ca991a91; unchanged
Report Checkpoint: 74b1e9f21f8e85293f0968ab89645a32a7d15272 (documentation-only successor; executable inputs unchanged)
Decision: FIX REQUIRED
P0 Blockers: NONE FOUND
P1 Blockers: R1 (start race) / R2 (current native source) / R5 (remaining evidence) / R6 (admission cleanup)
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CORRECTS TASK 2.2 IN PLACE
```

2026-10-14，B 完成必读清单和 B 经验阅读；初始 main 工作区干净，规划／审查前治理 PASS。审查真实 Task Base..修正 Head、后继文件清单、协调／原生开始／准入／配置代码、测试及 Developer 原始日志与实机 JSON。后继只修改六份文档，src／tests／scripts／SDK／solution 输入没有变化。当前 Contract 可满足；保留 Task ID、Base、Goal、Scope、High／T4、验收和全部门槛，不修改 Slice／Roadmap／稳定需求，不创建 Task 2.3。

独立本机证据：`.git/validation-evidence/dd5f6b80b9bd0bf63e16f2d1923995514ebebf4a/b-rereview-20261014-06/INDEX.md`。指定聚焦测试 **PASS：71 passed／0 failed／0 skipped，exit 0**。独立控制 harness 首轮三个观测 FAIL，补入真实 Acquire／MarkStarted 交错后最终 **FAIL：四个合同失败观测，exit 1**；首轮和最终日志均保留。控制只使用临时 STRM、假原生服务和进程内协调器，不是实机故障注入；开始竞态用保持标准键相等／哈希语义的屏障 comparer 延迟 preparing 查询，没有改产品代码或伪造登记结果。

Developer 的 locked restore／build（0 警告 0 错误）／102 项全套 C#／format／30 项 Python／治理／diff 日志和默认实机 JSON 已读取。实机记录确有同源一次开始／一次提交、默认 2／配置 1、配置拒绝前后文件一致、下一请求 Enabled／DetailedLog、重启及清理恢复；这些成功保留为 Developer 实际结果，不能覆盖下述缺口。B 默认实机 **NOT RUN**（已有确定 P1，按流程先拒绝）；Slice Final **NOT RUN**，Closure Packet **NOT SUBMITTED**，不把 Developer 实机结果当作 B 独立复现。

### 当前阻塞与原 Task 修正

1. **R1 — 开始通知已移动，但开始竞态仍可产生第二 owner（AC-T1／AC-T2，RO-4）。** `ProbeCoordinator.AcquireAsync` 对 running、preparing 的查询与 preparing 插入不是同一个原子状态转换。独立交错：第二请求先查不到 running，停在 preparing 查询；第一 owner 发布 running 并删除 preparing；第二请求继续得到新的 owner。观测 `firstStarted=true / secondOwner=true / secondRunning=false / ActivePermits=2`。第二 owner 的 TryMarkStarted 返回 false；`ExecuteProbeAsync.MarkStarted` 只记录警告并 return，编码器代理随后仍调用原生，不能阻止重复探测。现有 StartRace 测试是顺序获取后顺序开始，未覆盖此交错。协调查询／登记／准备转运行的同键原子边界，竞争失败者必须在原生调用前退出多余执行并加入／重查，释放自己的资源；也核对 TryAdd 失败后字典索引的并发移除边界。补可控的 Acquire 与开始、结束交错回归，证明匹配原生调用只有一次。开始通知位于匹配调用的修正保留，不退回准备阶段登记。
2. **R2 — 排队准入仍沿用有主流的旧源（AC-T1／AC-T3／AC-T5，RO-1／RO-3／RO-4）。** `AdmitQueuedOwnerAsync` 第 350～355 行仅在传入旧源缺主流时重新取源；旧源已有主流则沿用旧 Path／MediaStreams。独立对照 A：入队时旧源为 old URL，等待期间可信基线和原生源已接受 new URL，放行仍发生一次匹配探测（预期零）。对照 B：等待期间主流消失，旧快照仍有主流且当前基线已接受，放行返回复用 null、零匹配探测（预期缺主流 RequireProbe）。现有 accepted-version 测试入队前就给 new URL，掩盖问题。准入时按本调用者权限／user／路径替换重新取得当前源，再判断地址和必要主流；不能用旧快照或 item.ShortcutPath 替代当前源。补从真实旧源开始的已接受版本零重复、主流增删及源身份／用户边界对照。
3. **R6 — 准入异常泄漏许可与准备登记（AC-T2／AC-T4，RO-4／RO-6）。** 第 448 行的 `AdmitQueuedOwnerAsync` 在第 488 行 try/catch 之外；禁用／解析或库故障的原生委托、无探测取源等如果抛异常，未调用 Abandon／Fail。独立对照：占满唯一许可，播放排队，设置 Enabled=false，再放行并令委托抛 IOException；异常传播后 `ActivePermits=1 / PreparingCount=1 / RunningCount=0`。上限 1 的后续插件工作因此无法准入。把 owner 获得许可后的全部准入、委托、执行和提前退出纳入可靠的单次释放保护；保留原异常／权限，唤醒同源准备等待者，避免双重释放。补委托／取源抛错及未开始等待退出的资源回归，不新增已开始执行取消源或成功后取消检查。
4. **R5 — 剩余证据须随修正闭合（AC-T3／AC-T4／AC-T6）。** 新增路径替换用例两位调用者 user 都是 null，返回的源也相同，只证明参数记录，不证明不同用户可见源／响应独立；补两个真实不同 User 的控制对照并断言各自响应。实机配置脚本注释称“不热调整”，实际只做读回、Enabled／DetailedLog 和重启，未观察保存新并发后、重启前旧池的执行上限；补匹配行为证据。上限 1 控制测试目前只持有准备许可，补实际匹配开始的边界。无人等待用例保留正常完成事实，以明确加入／退出屏障替代 Task.Delay(25)，不引入客户端停止关联。矩阵／Required Surfaces 中“缺失边界已补齐”与“R1～R5 已修正”改为候选事实，当前 R1／R2／R6 失败不能仍写成该边界 PASS。

R3 配置中途写入保护和 R4 启动诊断脱敏：修正代码及独立聚焦中的对应控制用例通过，原失败保护修正保留；没有发现需重新开放的当前阻塞。原生独立刷新、配置非法请求拒绝及代表性共享成功也保留分层事实。

修正先跑上述已失败输入及直接相关回归，再对新实现 SHA 跑原计划完整 T4 和默认隔离实机入口。保留旧候选／首败／每次重跑；更新准确输入、命令、耗时、产物身份与矩阵索引。不得只改报告、削弱断言或将 constructor／参数记录／HTTP 成功当作缺失行为。报告交回 B 后才重新判断 PASS。

### Slice 全部 Required Outcomes／Surfaces 对账

| 合同结果／表面 | 本次结论 |
|---|---|
| RO-1：解析／决策／首次信任／原生边界 | Task 2.1 已接受；新准入用旧主流复用由 R2 阻塞，不升级整个 Slice PASS。 |
| RO-2：SQLite／条件提交／失败保护 | 已接受能力及聚焦回归保持；协调过期源／多 owner 风险须随 R1／R2 回归。 |
| RO-3：共用链／真实成功／原生地址与主流 | 已有链保留；准入重读／开始竞态由 R1／R2 阻塞。 |
| RO-4：实际开始共享／上限／调用者边界 | 未满足：R1／R2／R5／R6。 |
| RO-5：无人等待正常收尾 | 已有继续完成提交控制事实；资源全路径保护与必要确定性证据由 R5／R6 阻塞。 |
| RO-6：核心配置／恢复／诊断 | 配置写入保护／脱敏已修正；禁用准入异常影响恢复与后续工作，R5／R6 未闭合。 |
| solution／测试、原生播放／探测保存、最小 SQLite／身份映射 | 表面已存在，原有分层证据保留；R2 下当前源与主流判断未满足，不作整行 PASS。 |
| 共用检查／Coordinator／实际开始与结束重查 | 未满足：R1／R2／R5／R6。 |
| 原生配置保存／可操作禁用恢复／脱敏诊断 | 写入保护及启动脱敏通过；重启前运行上限／故障收尾仍缺。 |
| 固定隔离计数／失败／多源／共享／重启及矩阵原始产物 | Developer 成功实测已读；B 默认实机尚未运行，修正候选完整门槛和缺失控制证据待补。 |

**B 决定：FIX REQUIRED；Developer 继续同一 Task 2.2，Slice 保持 ACTIVE，已接受 Implementation Head 不移动。** 少量经验候选：重新准入必须从实际旧快照测试；许可清理保护从获得 owner 起覆盖全部提前退出。留给 A 收尾取舍，不记经验流水账。

## B Review Result（首轮历史）

```text
Reviewed: 13cb8bdac319fcf0b3e7500661bae1c7455077b0..d651950950d6d3ad2be4322ddf8f0afb658c7755
Reviewed Contract: HEAD:SLICE.md (Contract Checkpoint 7e0240cd1cada74f142b7b0afd612943ca991a91; working contract unchanged)
Report Checkpoint: 0f3ee63a9af318150f26efe7d4dbb40c4e6431be (documentation-only successor; executable inputs unchanged)
Decision: FIX REQUIRED
P0 Blockers: NONE FOUND
P1 Blockers: R1 / R2 / R3 / R4 / R5
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CORRECTS TASK 2.2 IN PLACE
```

2026-10-14，B 已完成必读清单，初始 `git status --short --branch` 为干净 main；规划／审查前治理退出 0。审查真实 Base..Developer Head、文档后继差异、协调／配置／原生接入源码、测试和 Developer 原始日志／实机 JSON。产品范围合法，现有 Contract 可满足；保留 Task ID、Base、Goal、Difficulty、T4、Scope 和全部门槛，不交 A 改变义务，不创建 Task 2.3。

独立本机证据：`.git/validation-evidence/d651950950d6d3ad2be4322ddf8f0afb658c7755/b-review-20261014-04/INDEX.md`。指定聚焦命令为 **PASS：60 passed／0 failed／0 skipped**。独立边界／配置控制 harness 的最终运行为 **FAIL：7 个合同失败观测，exit 1**；仅操作临时文件和假原生服务，不是实机故障注入。初次五项诊断及追加配置对照的日志均保留。原生源码确认 GetPlaybackMediaSources 先执行 FullRefresh 准备，之后才进入匹配 GetMediaInfo；原生 XML 序列化直接以 FileMode.Create 打开配置文件。

Developer 的 restore／build／91 项全套 C#／format／30 项 Python／治理／diff 原始日志及默认实机 JSON 已读取，记录的成功仍是其实际执行结果；这些绿灯不能证明以下缺失边界。此次 B 默认实机入口 **NOT RUN**：已有确定 P1，按开发流程先拒绝并保留其他未运行门槛，未把 Developer 实机成功写成 B 独立复现。Slice Final **NOT RUN**，Closure Packet **NOT SUBMITTED**。

### 当前 Task 阻塞与同 Task 修正要求

1. **R1 — 实际开始信号接在刷新准备之前（AC-T1／AC-T2，RO-4／RO-5）。** `StrmPlaybackOptimizer.ProbeAndVerifyAsync` 在第 334 行调用 TryMarkStarted，之后才创建 ProbeExecutionContext 并调用 native.GetPlaybackMediaSources；ProbeExecutionContext.MarkCall／MediaEncoderDispatchProxy 没有协调开始通知。控制屏障停在原生取源准备、尚未调用 MarkCall 时，RunningCount 已为 1，第二调用者已记录 Joined a running，匹配探测调用为 0。现有测试的 probeStarted 屏障也在 MarkCall 之前，不能证明真实开始。把可共享登记和开始日志接到经核验的匹配编码器调用边界；准备中的同源工作可以独立等待后重查，但不能登记为已开始或重复进入探测。开始失败／竞争及各提前退出路径都要释放许可，不能让仅取得许可成为开始。增加准备／已获许可／匹配原生调用三个独立屏障及真实开始后加入的回归；实机计数不能继续使用准备阶段的 started 日志充当实际开始。
2. **R2 — 排队后不重查版本、基线、源和启停（AC-T1／AC-T3／AC-T4，RO-2／RO-4／RO-6）。** AcquireAsync 返回 owner 后直接执行排队前的 manifest／previous／previousSource，没有重新判断。独立占满许可再排队的控制对照复现：期间已提交相同当前版本并更新原生源，放行后仍新增 1 次匹配探测；期间 Enabled=false 或 PlaybackAutoCheck=false，放行后仍建立插件 ProbeExecutionContext 并探测；期间 Manifest 改到另一 URL，仍使用旧上下文进入原生，匹配调用为 0 后失败。取得机会／实际开始前重读当前 STRM、可信基线、本调用者原生源、库故障标记及成功保存的配置；已接受版本复用，变化按最新版本决策，关闭后按原权限委托且不进入插件执行。播放检查关闭仅约束播放上下文，保留未来共用源入口的批量边界。补同源排队成功后零重复、版本／基线再变、排队启停、进行中禁用仍收尾以及状态库故障的确定性回归。
3. **R3 — 保存失败只保护内存，不能保护配置持久化（AC-T4，RO-6）。** Plugin.UpdateConfiguration 第 59 行使用原生 SaveConfiguration；原生 MyXmlSerializer.SerializeToFile 在序列化前 FileMode.Create 截断旧文件。独立临时配置用例在打开并写入部分 XML 后抛 IOException，保存反馈失败且内存保留旧值，但旧配置文件已改变／损坏。现有 FailedPersistence 测试在 File.Create 之前抛异常，掩盖中途写入失败；重启可能丢失先前有效禁用／并发配置。使配置持久化与发布满足失败保护：写入完整候选后安全替换，失败保留原有效文件／内存与明确错误反馈；不改 Jellyfin 核心代码。增加真实临时文件中途写入失败、失败后重新加载旧有效值及合法修复保存的控制验证，不要求破坏运行实例文件。
4. **R4 — 非法配置诊断泄露私有路径（AC-T5，RO-6／X10）。** Plugin.ResolveStartupMaxConcurrentProbes 第 73～76 行把完整 ConfigurationFilePath 放入错误日志；独立捕获 ILogger 已确认 privatePathInLog=true。改为不含私有绝对路径的配置标识和可操作恢复说明，并对非法配置／保存故障／库故障等必要诊断断言日志不含假私有路径、签名 URL 或秘密。保留必要错误反馈，不借详细日志关闭来掩盖故障。
5. **R5 — 必要验证／索引尚未闭合（AC-T2／AC-T3／AC-T4／AC-T5／AC-T6）。** GlobalLimitCapsConcurrentStartedProbes 只跑上限 2；1／8 仅构造合法性断言，未验证边界最大执行数。WaitingCallerCancellation 用例仍有 leader 等待且用 Task.Delay(25)，不证明全部等待者退出后的正常提交。无不同 user／路径替换的同源共享对照；配置 API 场景只保存／读回，未比较非法请求前后文件内容，也未验证下一请求启停／详细日志与保存并发不热改现有池；顺序 manual_full_refresh 不能证明池饱和时独立原生刷新仍可执行。按原计划补以上确定性控制／适用实机关键验证，索引所有 T01～T28 核心部分及 Required Surfaces 的具体输入、原始产物和实际边界；当前矩阵仅有 T01～T16／T26／T27／X03／X05 明细及候选概述。不要新增客户端取消关联、执行取消源、成功后人为取消门槛或真实批量要求。若无人等待用例涵盖首次调用者退出，明确仅退出等待生命周期，已开始执行仍独立收尾。

修正先跑失败边界和直接相关回归，再为新实现 SHA 跑原计划全部 T4 门槛与默认隔离实机入口，保留首次失败／每次重跑和恢复证明。产品／工具改动使旧候选门槛失效；不得删测试、弱化断言、只改报告或以 Constructor／HTTP 200 代替所需行为。新完成报告交回 B；原实现 SHA、Developer 成功运行与本次 FAIL 都保留。

### Slice 全部结果／表面对账（本次未 PASS）

| 合同结果／表面 | 当前结论 |
|---|---|
| RO-1：解析／决策／首次信任／原生边界 | Task 2.1 已接受，60 项聚焦保持通过；最终新候选全回归仍须满足。 |
| RO-2：SQLite／条件提交／失败保护 | Task 2.1 已接受；本次排队使用旧版本／基线问题由 R2 阻塞协调闭环。 |
| RO-3：共用播放／真实成功／已保存地址与主流 | 既有接入和提交门槛仍在；Task 2.2 新开始边界及计数归因由 R1／R2 阻塞。 |
| RO-4：只共享已开始／全局上限／调用者边界 | 未满足：R1／R2／R5；代表性 Developer 实机成功不补缺失控制边界。 |
| RO-5：无等待者仍正常收尾 | 未充分证明：R1／R5；现有 follower 退出且 leader 仍在不等于零等待者。 |
| RO-6：核心配置／恢复／诊断 | 未满足：R2／R3／R4／R5；非法输入拒绝和部分成功保存已有原始证据。 |
| solution／测试入口、原生 PlaybackInfo／探测保存、私有 SQLite／身份映射 | 现有表面存在且 Task 2.1 已接受；保留源／权限／保存失败／重启全部回归，不升级整行产品 PASS。 |
| 共用检查／Coordinator／实际开始与结束重查 | 未满足：R1／R2／R5。 |
| 配置保存／操作恢复／脱敏日志 | 未满足：R3／R4／R5；操作文档改为候选说明。 |
| 固定隔离计数／失败／共享并发／真实重启及矩阵原始产物 | Developer 部分实测已核验；必要补证和 B 默认实机复现待修正候选，R5 未闭合。 |

少量经验候选供 A 在 Slice 收尾取舍：开始屏障必须落在实际接入边界，准备入口的屏障会把错误登记测成绿灯；持久化失败对照应覆盖打开／写入后的失败，提前抛错不能证明文件保护。本次不追加经验流水账。

**B 决定：FIX REQUIRED，Developer 在同一 Task 2.2 内修正；Slice 保持 ACTIVE，已接受 Implementation Head 不移动。**

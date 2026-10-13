# Slice 1 — Jellyfin 核心接入与指纹提交验证

```text
Slice ID: 1
Name: Jellyfin 核心接入与指纹提交验证
Owner: A
Status: READY FOR A REVIEW
Base SHA: 8a6a955357a6fe7a6aea9dafead0ec33ffd203f3
Implementation Head: 2b1e1b5bcf77b06997fabed5a31147838db16b47
```

## V4.2 合同修订

用户授权按新方案重规划。本合同实质替代旧同 SHA-1 换 URL 时仅更新路径的验收，以及持久化独立探测状态的假设。原始 Base 仍是未实施插件的真实起点，保留 Slice ID／Base；旧合同与 Task 的重规划前快照为 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485`。

A 合同决定：RESCOPE，同一 Slice 保留核心验证目标，改为 V4.2 的 URL 变化必探测及最小指纹提交门槛；尚无产品实现，无有效产品验收被迁移或宣布通过。先提交修订合同与无活动 Task，再由 B 重规划 Task 1.1；本次不执行插件实施。

## A 取消语义澄清（2026-10-13）

本节保留前次决定；其中 Slice 1 的执行取消防御与注入验收义务已由下方 A 实质范围调整替代。

用户授权 A 将已核对的播放／批量取消语义同步到合同。Decision: CLARIFICATION；Required Outcomes、Required Surfaces、成功保存与取消不覆盖基线的验收义务均保留，Slice ID、Base 和 T4 不变。本段明确取消的对象与入口，不是产品 PASS 或 A Final Review。

- PlaybackInfo 按需获取媒体信息，不保证每次请求都执行探测。受支持 STRM 未变化且已有必要主流时插件跳过；需要探测时走原生流程，不能由请求开始推定探测已经执行。
- 当前固定 Jellyfin `12.2.0` 的 PlaybackInfo 取源传 `allowMediaProbe=true` 与 `CancellationToken.None`；客户端退出／断开连接和停止播放不沿此入口取消探测。插件保留该语义，不额外连接客户端停止事件或替换为请求取消 token。
- 客户端退出后，本次执行若仍实际成功、结果已保存且 Manifest 未变化，可以按原条件提交指纹。RO-3、AC-4 和不变量中的取消指执行本身收到取消信号；执行取消或失败仍不接受新指纹，不能将客户端退出本身标记为探测取消。
- Slice 1 仍验证带可取消 token 的真实隔离 Jellyfin 原生执行链及提交边界，并准确记录入口；不要求不可触发的客户端取消 PlaybackInfo 场景，不用假对象或私有测试入口冒充公共客户端行为。真实原生执行取消尚未验证时继续 NOT RUN／BLOCKED，不能写成 PASS。
- 原生计划任务停止的实机行为属于 Slice 3；同源共享中仅取消一个等待者，不取消仍有其他等待者的执行，也不阻止该执行满足全部成功条件后提交。通用协调实现仍属于 Slice 2，不在本次文档同步中铺开。

接口与固定源码依据见 [兼容性中的取消语义](docs/compatibility.md#播放与批量取消语义)。B 在本澄清提交后核对 Task 1.1 的继续决定；保存关联、执行取消保护和缺失真实对照的已有阻塞不由本段消除。

## A 播放取消范围调整（2026-10-13）

Decision: RESCOPE。用户要求当前播放链不增加取消保护的防御性约束；沿用会话已授予的 A 权限。本次改变 RO-3／AC-4 与最终验证中的取消义务，属于实质合同变更。保留 Slice ID、Base、Required Surfaces、核心接入目标和 T4；原实现检查点与审查证据保留，不宣称修复或 PASS。

- 固定 PlaybackInfo 入口传 `CancellationToken.None`，当前插件没有额外执行取消源。Slice 1 不要求原生成功返回后的额外取消检查，也不要求为当前播放链人为传入可取消 token 进行单元或真实原生取消验收。
- 原调用 token／权限仍原样传递；原生抛出 `OperationCanceledException` 时保留旧基线并传播异常，已有异常处理与回归保留。失败、无法确认本次成功或保存、Manifest 再变仍不得提交新指纹。
- 具有实际取消源的共享执行在 Slice 2 验证探测中与提交前取消保护；原生批量停止在 Slice 3 验证。共用提交机制与单等待者取消不影响其他人的需求保留。当前不实施这些机制。
- BR-2 的假对象复现与 FAIL 日志保持原事实；该防御场景退出当前 Task 阻塞范围，不改写成 PASS。真实注入取消的旧 NOT RUN 记录不变，当前 Slice 不再以此作为门槛。保存关联与其他真实验证缺口继续阻塞。
- 更换 Jellyfin 版本、入口或增加执行取消源后，须由 A／B 重新核对范围与验证，不把本次取舍用于新的可取消执行上下文。

A 先提交本合同，B 再明确调整当前 Task；本轮只修改文档。

## 用户目标

在一个明确 Jellyfin 版本上安装隔离原型并正常启动：未变化的版本化 STRM 重复播放避免实际 ffprobe；变化时原生探测实际执行；成功且已保存后才接受对应新指纹。URL 改变（包括相同 SHA-1）时探测，当次与重启使用新地址和有效媒体流；普通播放与原生刷新继续正常。

## Required Outcomes

- RO-1：固定一个服务器／源码／SDK／依赖组合，建立可构建、可加载的最小 C# 原型及隔离环境。
- RO-2：证明接入保留单一原生实例、生命周期和完整委托；已有主流且未变化时零探测增量，需要探测时确有原生执行。
- RO-3：取得关联本次新结果与持久化的可靠信号，区分成功、失败后旧流保留及 Manifest 变化；原生取消异常按异常路径保留基线；证明变化指纹提交门槛成立，不引入持久化成功／失败状态机。客户端退出按上述原生语义处理。
- RO-4：证明 URL 改变即使 SHA-1 相同也实际探测，原生保存最新地址和有效主流，当次与重启均正确；拒绝探测与保存失败分支不伪报成功。
- RO-5：记录可复现版本与风险证据、额外刷新开销、任务接口可行性及继续／调整结论，不宣传未经验证的兼容性。

## Required Surfaces

- 最小真实 C# 原型项目及单元／集成验证入口。
- 隔离 Jellyfin 的加载、生命周期、PlaybackInfo 和原生媒体源链路。
- 实际探测计数、本次成功／失败信号、原生结果及地址保存／重启证据。
- 可重复的指纹提交条件验证（允许使用原型存储，不宣称已完成正式 SQLite）。
- 目标版本定位与计划任务接口调研结论；完整批量任务不在本 Slice 实施。

## 用户与正确性约束

只用临时库、手写版本化 STRM 和假／本地媒体服务，不改生产实例。播放器保持原生入口，用户不操作哈希或内部数据库。

原型仅做验证所需路径，但已实现分支必须满足 [V4.2 稳定需求](docs/requirements.md)。核心包装或成功信号不可靠时报告 BLOCKED／调整方案，不继续完整插件开发。

## 不变量

1. STRM 只读；不开发生成器、不调用 OpenList 元数据 API、不改代理。
2. allowMediaProbe=false 不提高探测权限；失败回退同样遵守。
3. 普通媒体、旧 STRM、禁用、直播及手动刷新保持适用原生行为。
4. URL 改变始终 RequireProbe；无 UpdatePathOnly／独立路径同步器。
5. 除首次默认信任接管外，只有本次原生探测实际成功、结果已保存且 Manifest 一致，才接受新指纹。
6. 旧流、更新事件或刷新返回值不能证明本次成功；失败／原生取消异常／版本再变不覆盖旧指纹。当前播放不要求成功返回后的额外取消防御；客户端退出仍适用全部成功提交条件。
7. 不持久化 Assumed／Verified／PendingProbe／ProbeFailed，不复制原生媒体信息。
8. 隔离夹具与日志脱敏；不虚构 Git、测试、独立审查或兼容事实。

## 明确延期／排除

- 全面解析／决策、首次接管产品实现、正式 SQLite／迁移、通用共享及全局并发、可取消执行的提交保护与验证：Slice 2。
- 原生计划任务运行／停止／定时、分页／范围、进度统计、完整配置页：Slice 3。
- 大规模、扫描、广泛客户端／代理联调与生产发布包：Slice 4。
- 生成器、远程内容哈希、OpenList API、代理代码、独立调度器、独立状态机、首版扫描后自动触发：始终排除。

## Slice 验收

| ID | 验收条件 |
|---|---|
| AC-1 | 精确服务器版本／镜像、源码 SHA、SDK、依赖与 build／load 记录；启动／关闭正常。 |
| AC-2 | 全接口委托、普通媒体／直播／禁用对照正常；原生单例、释放和循环依赖结论明确。 |
| AC-3 | 未变化且已有主流的版本化 STRM 二次播放 ffprobe 零增量；变化路径有真实新增调用。 |
| AC-4 | 成功、失败保留旧流、Manifest 再变可靠区分；原生取消异常不提交并传播；原型指纹只在有效成功条件下提交。当前播放成功返回后额外取消检查与人为注入取消验收不作为门槛。客户端退出不冒充执行取消，也不单独否决有效成功提交。 |
| AC-5 | 同 SHA-1 换 URL 实际探测；当次 PlaybackInfo 与重启均新地址且有有效主流；地址／结果保存失败不提交指纹。 |
| AC-6 | allowMediaProbe=false 各原型分支均不发起探测；普通／旧媒体与手动刷新保留原生；不加入独立状态机或仅更新路径分支。 |
| AC-7 | 原始证据、版本／接口定位、额外刷新开销、缺失项及继续／调整结论真实；假对象、未运行、源码存在不冒充实机 PASS。 |

## 最终验证

核心接入、刷新与播放风险要求 T4：全部已有原型单元／集成回归，固定 SDK 的 restore／Release build／相关质量检查，真实隔离 Jellyfin 加载／播放／失败／版本变化／重启，治理与差异检查。

取消验证按本次 A RESCOPE 执行：当前播放只保留原生 token 委托、取消异常处理及已有回归，不要求成功返回后的额外取消检查和人为注入取消实机门槛。可取消共享执行在 Slice 2、批量停止在 Slice 3 验证，均不提前算通过。

记录完整候选身份、命令、版本、实际调用计数和脱敏原始产物；没有隔离环境或可靠成功信号时如实 BLOCKED／NOT RUN。任务接口定位是调研，不替代 Slice 3 注册与定时实机验收。

## 事实更新与停止规则

B／Developer 只记录真实实现 Head、结果和 Required Outcomes 进度，不移动 Base 或降低验收。全部 Outcomes 满足后交一份 Closure Packet；核心证据不能成立时不得先宣布通过。

## Closure Packet

本段由 B 提交最终审查包；不是 A Final Review，也不关闭 Slice。

```text
Slice: 1
Slice Base: 8a6a955357a6fe7a6aea9dafead0ec33ffd203f3
Implementation Head: 2b1e1b5bcf77b06997fabed5a31147838db16b47
Reviewed Contract Checkpoint: 4c749d7cce0f48b5c8146755db43837960e79f4f
Task: 1.1 — PASS
Task Review Checkpoint: 15ce799b1ca0330378f498a4cd83ec8064cae783
Slice Final Tested Checkout: 15ce799b1ca0330378f498a4cd83ec8064cae783
B Decision: SLICE READY FOR A REVIEW
P0/P1 Blockers: NONE
Next: A independently reviews Slice Base..Implementation Head
```

### 实现与 Task 索引

最小原型在固定 Jellyfin 12.2.0／SDK 10.0.401 上包装原生媒体源、编码器和两处保存服务，使用只读 Manifest 与纯决策、进程内最小指纹条件提交。变化 URL 的本次编码器结果、媒体流事务保存、地址事务保存、返回主流和稳定 Manifest 必须相符；失败或不能证明时保留基线。普通媒体、旧 STRM、禁用、false 权限及未匹配接口继续原生委托。未增加生成器、独立状态机、路径单独更新分支或另一套 FFmpeg。

只有一个实施单元：[Task 1.1 当前 B 审查](TASK.md#current-b-review-result)；完整任务／Developer 报告保留于根 TASK 与其 Git 检查点。原 BR-1／BR-3 已解决；BR-2 依 A RESCOPE 退出当前门槛，旧 FAIL／NOT RUN 不改写为 PASS。Task Base 未移动；停止创建 Task，不激活后续 Slice。

### Required Outcomes / Surfaces 对账

| Outcome | 完成与证据 |
|---|---|
| RO-1 | 满足：真实 solution、固定 SDK／依赖锁与源码 SHA／镜像 digest，Release 构建、实际加载与正常启停。镜像整体源码溯源限制见下。 |
| RO-2 | 满足：全接口委托和单例释放回归、固定源码注册核对、真实普通媒体／Live TV／禁用对照；首信任／未变化 0 匹配调用，地址变化 1。 |
| RO-3 | 满足：成功保存代理在原生事务完成后取证，关联本次主流；不可达 URL 保留旧流／重试，真实 Manifest 竞态不提交；独立保存失败 harness 与原生取消异常回归。 |
| RO-4 | 满足：同 SHA-1／Size 换 URL 实际探测，当次／重启均新地址与 Video／Audio 主流；地址保存失败拒绝、false 权限保留、手动 FullRefresh 原生对照。 |
| RO-5 | 满足：本地可核验证据、版本／接口定位、附带提供器观察及继续结论。原生计划任务接口调研不计 Slice 3 实机验收。 |

| Required Surface | 已交付 |
|---|---|
| 真实 C# 原型及验证入口 | solution、产品／测试项目、锁文件、单元与隔离运行脚本 |
| 隔离加载／生命周期／PlaybackInfo／原生媒体源链 | 独立 Task 与 Slice Final 的实际启停、对照和 PlaybackInfo 输出 |
| 实际计数／本次成功失败／原生保存与重启 | 匹配调用＋本地媒体 GET、保存信号、流摘要、正确 URL／主流、真实重启 |
| 可重复指纹提交条件 | 进程内条件提交、既有回归、独立三类保存失败 harness、真实失败／竞态恢复 |
| 目标版本／任务接口调研 | 固定源码中的注册、ExecuteAsync 的进度／token、空默认触发与错误回退定位 |

### Slice Final 与验收

独立于 Task 验证再次运行当前合同最终门槛。证据索引：`.git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/slice-final-20261013/INDEX.md`；Task B 证据：同级 `b-review-20261013/INDEX.md`。均仅本机可读，A 需要本工作区读取。索引记录完整测试 HEAD、前后跟踪输入／运行配置／夹具摘要、构建与部署 DLL、精确命令、退出码、计数、耗时和脱敏原始产物。此文档后继只同步状态／事实；产品、测试、工具、依赖与夹具定义未变，另跑消费文档的治理／链接／工具检查。

| 最终门槛 | 结果 |
|---|---|
| 固定 SDK locked restore／Release build | PASS；0 warnings／errors |
| 全部 C# 回归 | PASS；32 passed，0 failed，0 skipped |
| format verify | PASS |
| 真实隔离 Jellyfin 完整脚本 | PASS；包含加载／启停、播放／失败／Manifest 变化／真实重启及恢复 |
| Python 工具全部回归 | PASS；30 passed，0 failed，0 skipped |
| 治理／差异／本地 Markdown 链接检查 | PASS；文档后继的治理复验见证据索引 |

AC-1～AC-7 按上述证据及 Task B Review 映射满足。两轮独立集成均观察到首信任／未变化零调用，同内容换 URL 1 次、当次及重启正确；不可达新 URL 两次 HTTP 500／1 次且旧流摘要不变，Manifest 竞态 HTTP 500／1 次、保留指纹并恢复。普通媒体、Live TV、旧 STRM、禁用和恢复及手动刷新真实对照正常。

false 权限实机采用固定源码真实 `/Videos/{itemId}/stream?static=true` 入口；返回 HTTP 200／20995 字节，随后允许的 PlaybackInfo 仍探测一次。公共 PlaybackInfo 固定传 true／CancellationToken.None，不声称验证了其 false 参数或客户端取消。原生取消异常传播及保留基线由现有单元回归证明；当前合同移除的人为取消实机门槛保持历史 NOT RUN。

FullRefresh 的两次独立提供器日志观察均为 ProbeProvider、MovieNfoProvider、TrickplayProvider 各一次，条目 ETag 改变，1 次匹配探测／1 次合成媒体 GET；91／75 ms 是本地短媒体下含诊断日志的端到端观察。它证明附带提供器调用，未证明远程下载、Trickplay 生成或开销分项。临时日志级别和 STRM 已恢复；只保存提供器名与项目身份摘要。Slice Final 的完整脚本另保留手动 FullRefresh 与重复地址切换计数，不把探测计数替代全部附带工作。

### 不变量证据

- 源码与提交审查：插件只读 STRM、解析／决策没有网络／数据库／刷新副作用，无 OpenList API／代理改写／媒体下载哈希；只有隔离测试写夹具。产品指纹只保存最小内存身份，不复制媒体流／PlaybackInfo，不引入持久化探测状态。
- 决策回归与实机：URL 优先且改变必探测，SHA-1 双侧有效才比较，相同忽略 Size；无比较哈希时有效 Size 判断，mtime 不参与。完整产品矩阵仍延期，原型证据不覆盖其所有变体。
- 权限／恢复：false、禁用／旧／普通／直播保留原生；首次信任不计实测成功；新结果在实际探测／保存／Manifest 一致后才条件提交。失败、原生取消异常、解析或版本变化保护旧基线；保存抛错或仅内存地址不能确认成功。
- 保存边界：固定源码流保存与条目保存均在事务 Commit 后正常返回，代理随后记录；提供器上层吞错不能制造信号。独立 harness 包括“旧流与本次结果完全相同但流保存失败”，避免只靠字段差异检验拒绝逻辑。
- 隐私／环境：日志不输出完整 URL／token／Cookie／私有路径；证据经过指定提取。临时媒体库和专用 Compose 实例，仅本机端口；未使用生产媒体／配置。

### 非阻塞限制、延期与文档协调

原型仓库为进程内 `primary`，重启重新信任；重启证据只证明 Jellyfin 原生地址／媒体流。正式 SQLite／迁移／异常回退、多源身份、完整矩阵、共享与全局并发、实际可取消执行保护属于 Slice 2。原生批量任务／停止／定时／分页／进度与完整配置属 Slice 3；大规模、扫描、外部代理／OpenList 联调、广泛格式／客户端与发布属 Slice 4，均不预先 PASS。

内部数据库保存故障没有真实注入；本 Slice 以事务边界固定源码、实际成功保存／重启、真实不可达失败和独立保存失败控制测试组合取证，不把单元当成数据库故障实机证据。镜像缺 revision 标签：digest／实际版本、源码及 NuGet repository commit 分别固定，不能证明镜像所有构建输入。合成短媒体、禁用远程提供器的配置不代表生产开销或多版本支持；仍无发布包。

本交接同步 README、Progress、架构、兼容性、环境、范围与 Roadmap 的当前事实，完整需求／旅程保持 TARGET；测试矩阵保留后续产品状态并指向原型分项证据。Roadmap 当前行仍 ACTIVE，表示等待 A；关闭账本保持无已关闭 Slice。A 最终决定后才进行 Closure Reconciliation、PASS / CLOSED、角色经验合并及下一 Slice 选择／激活。

可复用经验候选（由 A 关闭时酌情合并）：提供器可能吞掉保存异常 → 在实际事务返回处关联本次结果，并独立验证保存失败仍可重试 → 适用于原生刷新接入；FullRefresh 只有探测计数看不到附带工作 → 同时观察提供器调用与端到端计数并声明调用／完成边界 → 适用于刷新成本验证。取消入口经验沿用现有候选，不新增流水账。

## A Final Review

```text
Reviewed Range: NOT SET
Decision: PENDING
P0/P1 Blockers: NOT REVIEWED BY A
```

B 已交 Closure Packet；A 尚未进行独立最终审查。Task PASS 和 B 的 READY 决定不是 A PASS / CLOSED，后续 Slice 未激活。

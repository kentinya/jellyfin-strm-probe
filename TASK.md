# Task 4.3 — 真实 3000 项原生库的增量检查与成本

必读：[已提交 Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。本 Task 仅细化 RO-2，不改变合同、Roadmap 或稳定需求。

```text
Task ID: 4.3
Parent Slice: 4
Status: IN PROGRESS
Task Base: a06a80fac90a86085f25116568aa24b54847c562
Contract Checkpoint: 611c31c31115b02c3fb60cef2826d9348e352b7b
Difficulty: High
Test Level: T4
Planner / Reviewer: B
Implementation Head: 70acae9cacaeddd3a494b2086a2a84c614820929
```

## Goal

交付 Slice 4 RO-2、AC-3／AC-4 及 AC-8 的大库、成本与恢复证据部分：在固定 Jellyfin 12.2.0／Linux x64 的 ZIP 安装隔离实例上，完成至少 3000 个真实已索引的受支持 STRM 物理候选的首次信任、未变检查、少量增量和准备／分批停止后重跑。证明静态范围不漏不重、仅所需源实际探测，完整对象和活动工作有界；分别披露 O(N) 身份集合、原生查询临时分配、对象读取、进程内存、耗时、进度和停止延迟。

## 实际基线、已接受结果与缺口

- 规划开始 `main` 干净，治理 PASS。Task Base 是 4.2 最终 B PASS 提交；Slice Base 固定为 `03169b07d110964562f7da31d2c3d7add82e5ff5`。当前 Contract Checkpoint 为 `611c31c31115b02c3fb60cef2826d9348e352b7b`；固定交付方案在 `ae265d0dba02aa1c5599871602d4350072b7155f`，二者合同义务一致，差异仅为当前大库门槛和下一步指针。
- RO-1／4.1 B PASS 保留在 `0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`；RO-3／4.2 完整计划、历史拒绝和补证 B PASS 保留在 `a06a80fac90a86085f25116568aa24b54847c562:TASK.md`，不用永久 Task 归档。最新已审查实现为 `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`，原 ZIP SHA-256 为 `434f930d6ad8282c1d68d47c7fc4456d52a025ae05e273db7b2f21551071ccaf`；它们不是未来 4.3 候选的验收证明。
- 已核对 `BatchLibraryScope.cs`、`BatchCheckRunner.cs`、`StrmProbeScheduledTask.cs`、`BatchCheckTests.cs` 与包／扫描／批量工具。已有原生 GetItemIds、Guid 去重排序、每批最多 128 个对象、每批最多 8 个消费者，共同 optimizer／Coordinator／条件提交，以及候选／对象读取成本摘要。历史十万规模单元测试使用合成 ID 和普通对象，不是 3000 个真实 STRM／已有主流的证据。
- 复用 `scripts/package_environment.py` 的新工作区、当前进程 token 归属、镜像锁、Compose、解包安装／摘要和清理；复用 `run_isolated_scan_integration.py` 的完整日期／运行关联、原生任务 API、只读源／五字段快照和增量 EvidenceRecorder，以及 `run_isolated_batch_integration.py` 的成本字段解析。只复用无开发部署副作用的函数，不调用旧入口 main 来准备包实例。
- 重要准备事实：现有 `native_probe_and_save` 明确指出原生扫描不为 STRM 探测主流，须在插件禁用时通过原生 PlaybackInfo 等既有原生入口准备。不得对 3000 个文件逐项调用会再次全库扫描的 `scan_and_wait`／`native_probe_and_save`；先扫描完成，再有界逐源准备并核验保存。
- 已阅读 4.2 B 重启补证索引及原始审计：三个源完整行／地址／主流在重启前、重启后播放前和播放后三阶段相等且零额外探测。正式扫描工具的重启漏检为已知 P2，不在本 Task 扩建该工具；新的大库重启检查使用独立重启前预期，Slice Final 仍须补齐最终候选的同等证明。
- 2026-10-18 用户授权迁移开发服务器并取消旧主机依赖。B 在同一 Task 内修订执行环境计划：保留 ID、Base、Goal、Scope、AC 和 High／T4；旧规划／资源观测保留在 `b92bea58a2552997bd750f059fc7d6c6cca23b93:TASK.md`。新主机重新准备环境和记录预算，不继承旧资源 BLOCKED，不要求读取旧本机证据才能开工；新真实大库结果仍全部 NOT RUN。

## 实施范围与顺序

按以下顺序完成同一个行为。先工具和 1000 级反馈，再 3000 级，最后完成 3000 候选验证。已有能力不重写；遇到本行为的真实产品缺陷才在同 Task 最小修复。需要改变合同、核心接入／成功／保存边界时交 A，B 重判后才继续。

### 1．增加一个薄验收入口，复用现有隔离环境

新增 `scripts/run_isolated_large_library_integration.py` 与 `tests/test_isolated_large_library_integration.py`。命令接口为本 Task 待实现，当前 NOT RUN：

```bash
python3 scripts/run_isolated_large_library_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --count 1000 --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/large-1000
```

`--count` 仅接受 1000、3000；`--scenario all` 完成本节全部轮次，不用小规模默认值冒充最终验收。两个规模按顺序串行，各自使用新的本轮所有工作区和干净实例，避免前一级指纹污染首次信任；外置证据始终保留。允许开发反馈重复 1000 级，不为每个规模建立新环境框架。端口采用包验收默认的本机 18097（可用现有 `JF_PROBE_PACKAGE_PORT` 在进程启动前选择空闲端口），project 由当前检出路径派生；已有非空工作区／占用端口／活跃非本轮容器拒绝，不接管、不停止它们。

只消费指定 ZIP 并验证加载负载摘要；服务器不挂源码／SDK／NuGet，不构建或补 DLL。环境写入和清理继续核验当前进程确实取得的 token、目录及容器挂载归属。场景串行，记录并暂时清除会干扰运行的原生触发器，结束恢复核验。

### 2．先落实资源、超时和观测，再建库

按新服务器实际资源制定运行预算，不再使用旧服务器的 CPU／内存限额、2432 MiB 准入值、磁盘／inode 数值或整轮超时表，也不继承旧主机内存不足的 BLOCKED。保留以下可执行的准备顺序：

1. 在当前检出根目录记录 OS／架构、SDK、Docker／Compose、Node／浏览器、固定镜像 digest、CPU／内存／swap／空闲磁盘／inode及空闲端口；以 doctor 和实际依赖检查判断就绪，不依赖旧主机的已有缓存／账户／容器。
2. 在任何实机运行前，于已有证据索引记录本轮 Jellyfin／媒体服务的 CPU 与内存限制、编排进程预算、宿主余量、磁盘／inode 余量、资源中止条件，以及启动、单次 API／同步查询、建库、原生主流准备、每轮批量、全源对账、停止收尾、每级总时长上限。所有数值与依据使用新主机资源，不得缺省为无限等待；不新增环境审批或治理对象。
3. 先运行 1000 级，依据其实际准备／执行成本，在 3000 级启动前确认并固定预算。首次设定和换机调整可在已有授权内进行，无须再次申请 B 批准；改变参数时保留前一预算和原因。失败后的调整保留原始失败和重跑身份，交 B 审查，不改变样本数量、业务规则或验收含义。
4. 使用本轮容器资源限制时只调整本轮 Compose，复用 writer 的最小可选参数，既有入口默认行为保持；不改宿主配置或其他服务。准备原生调用仍最多 2 个同时执行；每 1 秒采样本轮服务 cgroup 内存／可用 peak／CPU／进程数、Jellyfin RSS、宿主 MemAvailable／磁盘，每 0.5 秒轮询任务状态／进度。
5. 按运行前固定的资源中止条件和超时工作：停止新增准备／批量准入，立即留证，请求原生停止，等待同步查询真实返回及已开始探测正常收尾。不以杀进程冒充取消。确需终止本轮确认归属的隔离容器时记录 FAIL／中断，保留清理前资料和工作区；不后台遗留运行，不删除唯一诊断证据。
6. 新环境实际缺依赖、超预算、超时、OOM 或结算不完整时如实 BLOCKED／FAIL，不能通过降低 3000 验收数量、跳过主流准备、隐藏首败或放松断言制造 PASS。环境适配不移动 Task／Slice Base；合同数量或安全义务改变仍交 A。

### 3．原生准备与逐项独立清单

1. 每级在专用目录创建 N 个受支持的版本 1 STRM，N 为该级 count；每文件唯一稳定名称与物理身份，避免被 Jellyfin 自动合并为版本。可按每目录 1000 个分组，均指向少量复用的本地合成 MP4。夹具只用于隔离测试，不做生产生成器。插件保持只读。
2. 使用所选库与独立范围外库。所选库另加普通视频、旧 STRM、未知协议各一个对照；范围外有受支持 STRM 对照。N 是受支持物理候选数，对照与原生查询所得全部候选数 C 分别记录，不能混用。保持范围／文件静态直到指定增量轮。
3. 从原生完整扫描任务本轮起止和 Completed 确认建库，不以 POST 返回或文件数代替索引成功。关闭插件优化／自动任务时，用最多 2 个固定准备 worker 为每个受支持源取得并持久化必要主流；不得直接写 Jellyfin DB、导入伪造媒体流／NFO 流当成功信号、拷贝指纹或复用一个项目冒充 N 个项目。扫描和准备的原生调用、CPU／内存／媒体请求与耗时单列。
4. 原生 API 分页读回当前物理项目／库关系／MediaSourceId，包含 alternate versions、关闭展示聚合，与磁盘清单逐项双向核对；独立清单覆盖全部 N，不只抽样。每条记录当前 item、source_key、库、文件／URL 摘要、有效 SHA-1／Size、原生已保存地址和必要主流签名。原生返回完整对象只分页保存／处理，证据写 JSONL，可另存排序后的身份集合与摘要。
5. 启用插件前确认 N 个源均已有正确原生主流、地址且没有插件指纹，记录精确键集合；配置只选测试库、主动并发固定默认 2，重启使并发生效，再读回配置和 ZIP 身份。此后首次信任前只使用不会触发插件检查的只读 API／SQLite 查询，不能先请求 PlaybackInfo 偷建指纹。

### 4．真实完整轮次与少量增量

各级 `all` 均完成下列轮次，最终 3000 级不得省略。每轮以原生任务 Key `StrmProbeOptimizerBatchCheck`、本轮 UTC 起止／容器启动身份关联日志，不使用旧完成结果或固定 tail 丢掉完整日志。静态轮次把独立身份清单与本轮候选／结算身份对账，不能仅比较总数。

| 轮次 | 操作和预期 |
|---|---|
| 首次信任 | 完整 C 候选结算，N 个受支持源首次信任且全部建立正确五字段行；它们计跳过、不计可靠探测成功。实际插件探测开始数为 0，范围外／普通／旧／未知协议零插件探测。原生地址／主流来自第 3 步，不借本轮探测补齐。 |
| 未变复查 | 重新获取同一静态范围全部候选；全部受支持源跳过、首次信任为 0、实际插件探测为 0。完整五字段、原生地址／必要主流保持，集合不漏不重。 |
| 少量增量 | 从真实 Guid 排序的不同批次位置选不重叠子集：4 个同 SHA-1／Size 换 URL，4 个同 URL 改有效内容 SHA-1，4 个双侧无可比 SHA-1 且有效 Size 改变；再新增 4 个已索引但原生未探测的受支持 STRM 作为缺主流对照（总数变 N+4）。所有变更在增量轮开始前固定，记录独立新预期。预计仅 16 源各一次实际插件探测、可靠保存／提交，其他行完全不变。 |
| 增量后复查 | 新一轮重新查询 C 的准确当前值，全部当前合格源正确，零额外插件探测；统计、原生地址／主流与五字段按当前键全量对账。 |

Size 对照从最初就不提供 SHA-1，旧 Size 是真实合成媒体 A 大小；变化后同 URL 的专用受控路由实际返回合成媒体 B，SHA-1 仍缺失，新 Size 为 B 实际字节数。内容 SHA-1 对照同 URL 后端也实际换内容。换 URL 对照可复用相同字节。测试工具只计算自己的本地合成媒体夹具哈希，不能为插件加入远程下载／哈希逻辑；不同路由隔离，不能一处替换影响所有 N。新增缺流项通过原生扫描索引，调用批量前只读确认缺流，不先播放。

独立清单决定预期，不从刚读到的实际 SQLite 行反推预期 SHA-1／Size。实际探测计数以匹配的插件编码器开始／结束、保存／提交及后端请求交叉核对，准备／原生外部调用单列；HTTP GET 数不能当插件探测数。原生 Completed 也不能掩盖单项失败，必须核对必要源全部成功与统计。

### 5．大集合准备／分批停止、重跑及收尾

1. 在稳定大集合发起原生任务，准备阶段发原生停止，保留停止请求／确认、候选查询进入／返回与对象读取／探测时序，候选获取期进度 0。同步查询无 token 时允许等返回，返回后零新准入，不做脱离任务的后台查询。
2. 必须证明停止命中阶段，不能把“进度还是 0”当作正在获取。优先现有原生诊断；若缺少阶段证据，只在已有 runner／候选源／任务处加入必要脱敏诊断，记录查询前后、固定集合／批次边界和工作计数，不注入测试等待／新取消源或改变原生查询。真实查询窗口过短时最多 3 次自然重试，全部留证；仍未命中记录 NOT RUN 并交 B，不伪造查询中停止 PASS。开始前停止与查询中停止分别报告；确定性测试继续覆盖同步查询内竞争。
3. 再从固定排序的首批选择两个需探测源，使用受控 20 秒延迟使实际探测开始；后批另放两个需探测源。确认首批实际执行、后批未读取后，原生停止。停止后无后续批次／新实际探测；已开始的两个继续保存并满足全部条件后提交，后批两个完整旧行保持。记录 Cancelling 期间进度 <100、统计与终态 Cancelled，不将任务停止视为探测取消。
4. 已开始工作收尾时，从原生入口尝试再次运行，核对新一轮未实际进入；待旧轮全部结算／汇总／资源释放、原生 Idle 后再跑，必须重新取候选并只处理剩余变化。重跑前保存完整已提交／保留行快照，避免把重跑修复误记为停止轮成功。
5. 再运行两轮未变检查，各零插件探测。每轮前／后固定 30 秒空闲观察，保存相同采样方法下内存、线程／句柄／任务／子进程、状态库行数、实际工作计数；结束无活动探测或消费者／待处理许可残留。与确定性边界一起判断资源收尾，GC／原生缓存增长单列解释，不把 RSS 必须完全回到起点当验收，也不把增长未经解释直接称无泄漏。
6. 3000 级稳定后重启，重启前保存全部当前源的独立完整预期；重启后在任何播放或批量之前只读核对完整指纹集合、地址和主流。再对 16 个增量源显式选 MediaSourceId 取得 PlaybackInfo 并核对返回地址／主流与零额外探测，随后全量只读复核。不可从重启后行自身构造预期，也不靠首次播放补建基线。1000 级也执行同一流程以尽早发现编排错误。

### 6．分层成本与可审查输出

每级输出一份阶段表，分别列建库／原生主流准备、原生候选查询、去重排序／集合、对象读取／消费、首次／未变／增量／停止／重跑、只读对账和清理；固定资源、样本数／间隔、缺采样区间与实际时间必须可追溯。

- 复用现有 CandidateFetchMilliseconds／AllocatedBytes／PeakBytes、CandidateSetEstimatedBytes／MeasuredCapacityBytes／RetainedBytes 和 BatchReadMilliseconds／AllocatedBytes／Count。说明 fetch 当前包含原生查询＋去重排序，当前线程累计分配可能包含其他同线程分配，进程 managed heap 前后样本不是精确临时峰值或独占归因；retained 的有 GC 前后差也不是集合独占大小。容量字段使用实际槽位数乘大小模型，不是精确堆占用。
- 如现有汇总无法单列原生查询／去重排序，增加最小只读计时／分配观测，复用已有结果与日志，不新建监控服务／接口／表。记录各库原始数量、去重数、集合 Count／Capacity、查询时间／当前线程累计分配，区分查询返回集合与排序保留集合；临时精确峰值无法测得时明确限制，以累计分配和固定间隔进程／cgroup 样本披露，不填估算成实测。
- 在真实运行记录最大请求／返回完整对象批次、活跃消费者／探测和批次数，并结合实际代码及确定性测试证明最多 128 对象一批、8 个消费者、默认 2 个主动探测，不为每个 ID 建 Task。允许每批创建固定 worker，总创建数与活跃峰值分别报告；不声称 Jellyfin 自身缓存完整对象也受 128 限制。
- 每轮完整集合／结算身份可采用现有诊断或只读诊断补充，流式记录，优先每批摘要与必要身份；不能只拿“候选数＝检查数”证明无漏重。观测有开销，记录详细日志状态和证据体积；对三规模使用同一观测方式，不借关闭关键观测得到假比较。
- 原生准备进度、批量获取期 0%、结算期单调且最高 99%、正常收尾才 100%；检查＝跳过＋需要＋检查阶段未完成，需要＝可靠成功＋探测未完成。候选与不处理／消失／撤销／未读取／读取失败另行对账，候选总数未知时明确未知。停止分别报请求至服务确认、同步查询返回、已开始探测完成和原生 Idle 的延迟，不将内部单字段当用户端总延迟。

### 7．完成最小事实同步与交接

只更新本行为实际结果需要的 `docs/test-matrix.md`、`docs/compatibility.md`、`docs/development-environment.md`、`README.md` 等事实说明，注明资源、阶段成本、代表性媒体和适用限制；不改 Slice、Roadmap、稳定需求或扩大兼容承诺。现有文档仍有 4.1 待审／4.2 旧候选指针，以以上不可变审查快照为准，可在允许的事实文档修正，合同／Roadmap 指针留 A 最终协调。RO-4、单独 Slice Final／Closure Packet 仍未完成。

## 验收条件

- [ ] AC-3：两级按顺序有真实原生库证据，3000 级 N≥3000 受支持物理源的文件／项目／源／库／主流来源全部可核对；没有直接写原生 DB、伪造媒体流或以模拟 ID 冒充。
- [ ] AC-3：首次信任和未变轮次零插件实际探测、静态集合逐身份无漏重、完整五字段／地址／必要主流正确；受控 URL／内容／Size／缺流仅所需源探测且后续复查零探测，范围外及不支持对照不优化。
- [ ] AC-4：原生 ID／去重排序 O(N) 成本、原生临时分配、对象读取与活动工作分别记录；128／8／默认 2 上限有实际观测及代码／确定性证据，非全库对象物化或每候选 Task。
- [ ] AC-4：真实大库准备和分批阶段停止命中可核验，停止后零新准入；已开始工作有效提交、未开始旧基线保持，旧轮收尾前不能实际再运行；停止终态／进度／统计／延迟真实，重跑收敛并完成资源结算和只读重启核对。
- [ ] AC-8 对应部分：最终完整 T4、同 ZIP 安装／扫描／两级大库验收均取得真实证据，原始材料、资源与输入身份、失败与恢复／清理完整；无秘密泄露，NOT RUN／BLOCKED 不算 PASS。
- [ ] 只含本 Task 的工具／测试、必要诊断、实际阻碍 RO-2 的最小产品修复与事实文档；没有合同、schema、业务规则、取消语义或额外调度／状态架构变更。

## 必要测试

High／T4：真实大库、原生查询／持久化、停止并发及安装候选，需要完整现有回归和适用实机门槛，由 B 在独立验收阶段承担。本轮仅规划，不声明下列产品测试已运行。

### 开发／修正反馈

Developer 先运行新增工具用例、已知失败和由改动文件直接影响的回归，并列出未运行的其他测试；再跑 1000 级，资源／时间预算可行才升到 3000。B 负责完整全量回归和独立验收，不通过不得通过降低 3000 数量／隐藏超时／跳过主流准备继续标绿。

```bash
python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~BatchCheckTests|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~PlaybackOptimizerTests'
```

Python 文件待本 Task 新增，必须发现非零用例。控制要驱动实际大库编排和证据输出：只有磁盘文件／不足 3000 索引／主流未准备、身份重复加缺失但数量相等、误用当前实际行为预期、缺成本字段、探测数错误、停止阶段未命中／停止后新准入、收尾期间新轮、丢旧日志、超时／OOM／资源不足及清理失败均不能 PASS。成功控制覆盖完整流程。保持已接受确定性同步查询中停止、开始竞争、8 消费者／全局许可／末项故障与不提高权限测试；不要用 3000 份测试假对象替代实机。

### 最终检查点门槛

以下完整命令清单由 B 在独立验收／最终检查点承担；Developer 开发反馈只执行改动文件直接影响的测试并报告省略项。命令从当前检出的仓库根目录、使用 SDK 10.0.401、在干净已提交实现候选上执行；下方 `<source-sha>`／`<run-id>` 须先替换为完整实际 SHA／唯一 ID，不能照抄成 shell 重定向。新增大库命令当前待实现／NOT RUN，其他入口已存在。所有修改同一实例／配置／鉴权的实机串行；大库运行期间不同时构建或运行其他实机套件。

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/package-all
python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/scan-all
python3 scripts/run_isolated_large_library_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --count 1000 --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/large-1000
python3 scripts/run_isolated_large_library_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --count 3000 --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/large-3000
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py --scenario suite
python3 scripts/run_isolated_configuration_integration.py --scenario all
python3 scripts/check_governance.py
git diff --check
```

另检查本地 Markdown 文件／锚点和事实协调并保存准确命令。配置浏览器原始输出用现有 `STRM_CONFIG_EVIDENCE_DIR` 指向外置证据。最终 package／scan／large 三类必须消费同一最终 ZIP，部署负载匹配；三个开发部署回归另列。scan all 沿用已有行为覆盖，本 Task 不要求修其 P2；不能以它独自证明最终重启义务，大库独立重启核对按第 5 步执行。单独 Slice Final 仍要核对扫描的变化批量源及多版本 A／B 全部完整状态。

完整套件已覆盖聚焦用例无需机械重复。打包前保留既有发布产物与旁车文件；最后一次可执行输入改变后重新取得完整门槛，不能用开发期 1000 级或旧 4.2 运行拼成新候选最终验证。

### B 独立验证

审查真实 Task Base..Implementation Head、所有必要变化和原始证据。独立复现工具错误放行控制及 1000 级全流程；3000 级独立验证当前原生候选／全源清单、完整行对账、首次／未变零探测、小集合精确探测和真实准备／分批停止与重跑的关键行为。B 负责完整 C#／Python 全量回归、Task 指定全量门槛和独立验收；可复用匹配且可核验的完整建库／准备、昂贵全轮和其他最终门槛，但不能以 Developer 的聚焦结果替代全量门槛。若需保留 3000 实例供 B 观测，Developer 先按现有归属模式设计明确保留／人工交接及随后清理证据，不能让新进程仅凭旧 token 接管。默认完整证据在清理前外置落盘。缺失或不匹配时重跑对应门槛，不能凭报告标签复用。

B PASS 后重新核对全部 RO／Surfaces：RO-1／安装恢复和 RO-3／扫描仍检查回归及证据有效性；RO-2 达标才 PASS。RO-4 实际代理仍必要，依固定方案规划 4.4；若事实未满足不得进入 Closure Packet 或宣布 Slice 关闭。

### 证据与重跑规则

每个候选／运行索引保留在 `.git/validation-evidence/<完整源码SHA>/<唯一run-id>/` 或稳定 CI，写明仅本机可读。包含完整源码／审查 SHA、准确工作区身份、SDK／锁／镜像／配置／夹具／包／部署摘要、新主机资源限制／运行前预算与宿主样本、准确命令／cwd／退出码／计数／耗时、查询／批次／实际开始保存／五字段／地址主流／进度／终态／延迟原始记录。清单和响应流式、脱敏保存，不留完整 URL、token、Cookie、凭据或私有路径；证据目录在实例之外，归档不得混入状态库或测试资料。

保留首次失败、每次重跑、缺失与不可用；资源／超时／阶段未命中必须如实记录。准备、执行、对账和清理各自结论独立，任何必要阶段未完成不能总 PASS。测试／工具／配置／夹具／依赖或可执行输入改变时相关证据失效，最终候选重走完整 T4；纯报告后继显式比较输入后才复用并重跑文档消费检查。环境预算及调整由实施者留证、B 审查，不移动 ID／Base／Goal 或弱化 AC。旧服务器的忽略目录不随 Git clone 迁移；无法访问历史原始运行时按开发流程重跑拟复用门槛，不将历史目录存在作为启动本 Task 的条件。

## 非目标

RO-4 的实际 JellyfinProxy 联调（后续 4.4）、单独 Slice Final／Closure Packet、A 最终审查或关闭；不重复实现已接受播放／扫描能力，不为已知 P2 扩建扫描工具，不改 Slice／Roadmap／稳定需求。排除生产操作、停止其他服务、系统资源调优、插件推送／上架、生成器／OpenList API、代理改造、远程内容哈希、新 FFmpeg、持久化任务状态／独立调度器／队列、全库对象／Task、schema 或取消／共享／并发语义改变、无关重构与通用性能 SLA。

## Developer Completion Report

- Changed Files：`scripts/run_isolated_large_library_integration.py`（新增）、`tests/test_isolated_large_library_integration.py`（新增）、`src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchCheckRunner.cs`（仅在 `FetchCandidates`／对象批次处追加脱敏阶段诊断与候选身份日志，不改任何决策、计数、取消或并发语义）。纯报告更新 `TASK.md`、`docs/test-matrix.md`、`docs/compatibility.md`、`docs/development-environment.md`。未改 schema、业务规则、稳定需求、Slice／Roadmap。
- Implemented：
  - 新增 `scripts/run_isolated_large_library_integration.py`（`--count 1000|3000 --scenario all`），只消费指定 ZIP 并部署到 4.1 的独立包实例（Compose project `jf-strm-probe-package-*-large-*`、默认端口 18097、工作区 `artifacts/package-env`），不调用 `deploy_plugin()`、不在验收期间补 DLL 或重建包；复用 `package_environment`／`package_plugin`／`run_isolated_package_integration` 的新工作区选择、镜像锁、归属检查、ZIP 校验／部署、鉴权、媒体准备、对账与清理，以及 `run_isolated_scan_integration` 的日期／运行关联、原生任务 API、只读源／五字段快照和增量 `EvidenceRecorder`。
  - 真实建库：写 `count` 个受支持版本 1 STRM 加库内普通视频／旧 STRM／未知协议对照和范围外受支持 STRM 对照；等待原生扫描任务 Idle 后发起真实扫描并轮询分页原生查询，直到全部受支持夹具索引（Jellyfin 扫描异步，任务 Completed 不等于索引完成）。插件禁用时用最多 2 个固定 worker 经原生 PlaybackInfo 持久化每个源的主流，扫描／准备的原生调用单列。
  - 完整轮次：首次信任（`first_trust==count`、零插件探测）、未变复查（零探测）、少量增量（预分配的 4 URL／4 内容／4 Size／4 缺流对照各按需一次探测并全部可靠提交）、增量后复查（零探测）、准备阶段停止（并发 watcher 命中同步查询窗口，停止后无对象读取）、分批停止（首批 2 源实际开始后原生停止，已开始提交、后批未读取、Cancelled 且进度 <100）、恢复轮（剩余变化 2 探测收敛）、两轮未变（零探测）、重启只读核对（完整五字段／地址／主流）与 16 个变化源显式选源 PlaybackInfo（零额外探测）。
  - 分层成本：逐轮记录候选获取／原生查询时间与当前线程累计分配、进程堆采样峰值、集合估算／实测容量／保留、批次读取时间／分配与批次数；身份集合、原生临时分配与对象读取分别报告，不称精确峰值或恒定总内存。
  - 脱敏：证据外置 `.git/validation-evidence/<source-sha>/<run-id>/large-<count>/`，仅保存摘要／哈希／计数，`events.jsonl` 流式追加、`rounds/` 快照、日志经 `redact_log_text`，不含完整 URL、token、Cookie 或私有路径。
- Tests and Results（original implementation head `850224a2e910e2131771699e9ae77e53d3b265c8`; correction checkpoint `70acae9`；ZIP SHA-256 `edf0aa9ab75a2fb83dea991e04b1b51d661ae5dc3db4d5829668cdd09288ba8d`）：
  - `bash scripts/dotnet-local build … --configuration Release --no-restore` 0 警告／0 错误（约 15s）。
  - `bash scripts/dotnet-local test … --filter 'FullyQualifiedName~BatchCheckTests|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~PlaybackOptimizerTests'` 138/138 PASS（约 9s）。
  - `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` original 13/13 PASS；correction 14/14 PASS。
  - 1000 级：`python3 scripts/run_isolated_large_library_integration.py --package … --count 1000 --scenario all` **PASS**；`actual_query_stage_stop: PASS`；实例对账 `CLEAN`、清理 `CLEANED`。证据索引 `.git/validation-evidence/850224a2e910e2131771699e9ae77e53d3b265c8/run-20261019T012120Z-21426e72/large-1000/`。
  - 3000 级：同命令 `--count 3000` **PASS**；首次信任 `candidates 3003 / first_trust 3000 / actual_probe_calls 0`；增量 `candidates 3007 / reliable_success 16 / actual_probe_calls 16`；未变与增量后复查零探测；停止后恢复 2 探测、再两轮零探测；`actual_query_stage_stop: PASS`；实例对账 `CLEAN`、清理 `CLEANED`；首轮 24 批、`candidate_fetch_ms` 511.4546、`candidate_fetch_allocated_bytes` 13820992、`candidate_fetch_peak_bytes` 2658416、`candidate_set_estimated_bytes` 120120、`candidate_set_measured_capacity_bytes` 162712、`candidate_set_retained_bytes` 149032、`batch_read_ms` 918.7819、`batch_read_allocated_bytes` 44829744。证据索引 `.git/validation-evidence/850224a2e910e2131771699e9ae77e53d3b265c8/run-20261019T023348Z-d3a0cb33/large-3000/`。
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases` PASS，归档 SHA-256 与上一致。
  - 未运行（明确交 B）：完整 C#／Python 全量回归、`format`、治理／差异、三个既有默认实机回归、包／扫描全场景、RO-4 代理联调、单独 Slice Final。
- Decisions：只新增大库验收入口与对应工具回归，并在 `BatchCheckRunner.FetchCandidates`／批次读取处补最小脱敏诊断；不改决策、计数、取消、共享、并发、schema 或持久化语义。受控同 URL 内容／Size 变化使用**同容器**的独立合成 MP4（B）作为后端真实内容，因为同 URL 改变容器会让 Jellyfin 持久主流身份与编码器结果不匹配而被拒——这超出本 Task 的受控内容／Size 变化合同，故不采用。同步查询窗口极短，用并发 watcher 在查询开始标记出现时立即停止，未注入等待／取消源或改变原生查询；未命中时如实 NOT RUN。
- Remaining In-Slice Work：RO-2 本 Task 待 B 独立验收；RO-4 后续 4.4；单独 Slice Final、事实协调与 Closure Packet。
- Risks / Deviations：1000／3000 为 Developer 聚焦开发反馈，非 B 独立验收或 Slice Final；完整全量回归与独立复现交 B。真实大库停止依赖真实时序，已保留每次自然重试与未命中记录；RO-4 代理、其他 Jellyfin／平台、通用性能 SLA 仍 NOT RUN。首次失败与多次重跑原始证据保留在各运行目录。
- Head SHA：original `850224a2e910e2131771699e9ae77e53d3b265c8`; correction `70acae9`。

可复用经验只提供少量候选供 Slice 收尾，不记录开发流水账，不作为 Task PASS 门槛。

## B Review Result

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..850224a2e910e2131771699e9ae77e53d3b265c8 plus correction 70acae9cacaeddd3a494b2086a2a84c614820929 (static review; affected gates pending rerun)
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — RO-2 is blocked by an evidence/tooling inconsistency; RO-4 remains NOT RUN
Next: rerun the affected 1000/3000 gates on correction 70acae9cacaeddd3a494b2086a2a84c614820929, then B re-review
```

### B Findings

1. **FIX REQUIRED — query-stage stop evidence can mix attempts.** `LogTail` intentionally reads a two-second overlap, but `run_query_stage_stop` treated every returned marker as belonging to the current attempt. The 3000 evidence therefore records `execution.read_started=true` while the filtered phase event list contains no object-read marker. `query_stop_observed` also ignored that execution flag. This is contradictory evidence for AC-4 and cannot be reused as a PASS gate.
2. Correction `70acae9cacaeddd3a494b2086a2a84c614820929` filters watcher lines by the current attempt's timestamp, rejects any execution that reports an object read, and adds a deterministic regression for the overlap case. The prior large-library evidence remains retained as historical evidence, but is invalid for the corrected executable input and must be rerun.
3. B independently verified the existing 3000 evidence identity (source head `850224a2e910e2131771699e9ae77e53d3b265c8`, ZIP SHA-256 `edf0aa9b...`, clean instance reconciliation) and reused it only for the unaffected candidate, cost, persistence, and restart observations. It is not sufficient to close the query-stage stop gate.
4. C# build and full C# tests pass serially (202 tests); format, governance, and `git diff --check` pass. The complete Python discovery command was attempted but produced 2 failures and 6 errors in existing isolated-scan guard tests without a running package instance; this is recorded as NOT PASS and must be resolved or explicitly blocked before Task PASS.

The working-tree correction is limited to the Task's acceptance tool and its tests; no product contract, persistence, cancellation, or scheduling rule changed. The Task remains active under the same Base and Goal. No Closure Packet or `SLICE READY FOR A REVIEW` decision is issued.

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
Implementation Head: 348567fd17140b064f002d246e3653658e22379c
```

## Goal

交付 Slice 4 RO-2、AC-3／AC-4 及 AC-8 的大库、成本与恢复证据部分：在固定 Jellyfin 12.2.0／Linux x64 的 ZIP 安装隔离实例上，完成至少 3000 个真实已索引的受支持 STRM 物理候选的首次信任、未变检查、少量增量和准备／分批停止后重跑。证明静态范围不漏不重、仅所需源实际探测，完整对象和活动工作有界；分别披露 O(N) 身份集合、原生查询临时分配、对象读取、进程内存、耗时、进度和停止延迟。

### 2026-10-19 用户明确的准备库复用要求

本节优先于下文和历史报告中要求每次新建、逐次清理大库的执行方式；用户进一步明确复用范围为所有需要使用的开发阶段，不限于本 Task、验收轮次或本 Slice。不移动 Task／Slice Base，不改变业务验收结果或签发 PASS。

- **3000 项库准备一次，所有需要使用它的开发阶段复用**：当前及后续 Task／Slice 的实施、调试、修复、回归、联调、独立审查、最终验收和发布前验证，只要需要该库，均复用这份真实原生索引和已保存主流；首次信任、未变、增量、停止／恢复和重启是其中的验证场景，不是复用范围的上限。不因换阶段／角色、修改代码／工具或 Task／Slice 结束就重新建库或逐源准备，不据此启动未授权的后续实施。
- 准备完成且首次信任尚未发生时，在实例完全停止、工作已结算后保留一份一致的离线基线：原生库／配置、STRM／受控媒体及服务配置、插件指纹初始状态和独立清单。离线整体备份／恢复即可，不新增快照框架，不逐行修改原生数据库或伪造媒体流。首次信任前须核验对应源没有插件指纹。
- 同一次场景序列保留自然演进状态，不能在停止与恢复之间还原基线掩盖错误。重复首次信任或完整场景时从上述基线恢复；只补某阶段时核验其所需前置状态。重启测试必须保留被测状态，不能用恢复备份代替重启持久化验证。
- 每轮重新记录实际源码／ZIP／工具／配置身份、候选／源清单、前置状态及本轮日志与结果。复用的是准备数据，不是旧 PASS；新候选和 Final 仍执行所需行为验证。输入变化先核查准备库是否仍适用，仅在身份／协议／媒体或主流前提失效时修复受影响准备，不能默认全部重建。
- 跨进程／角色／开发阶段继续使用须显式交接并核验隔离目录、容器、挂载及当前操作权限，不仅凭旧 token 接管；不操作非本轮或生产实例。大库持续保留，每次使用结束仍核对无残留工作及配置／触发器恢复；确认后续开发不再需要时才安排统一清理，不能仅因当前验收、Task PASS 或 Slice 关闭清理，失败证据继续保留。
- 本轮只修订复用计划，不改大库工具／插件、不操作实例；现有自动入口每次创建／清理工作区的行为不代表已经支持跨次复用，未适配前不得直接运行它而销毁保留库。本次未取消 1000 级、真实查询停止或其他既定门槛。

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

`--count` 仅接受 1000、3000；`--scenario all` 完成本节全部轮次，不用小规模默认值冒充最终验收。两个规模按顺序串行、初始状态隔离，避免前一级指纹污染首次信任；3000 项准备库及基线按上方用户要求跨轮复用，不要求每次新建干净实例。外置证据始终保留。允许开发反馈重复 1000 级，不为每个规模建立新环境框架。端口采用包验收默认的本机 18097（可用现有 `JF_PROBE_PACKAGE_PORT` 在进程启动前选择空闲端口），project 由当前检出路径派生；已有非空工作区／占用端口／活跃非本轮容器拒绝，不接管、不停止它们。明确交接并核验的保留大库不属于任意接管例外。

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

审查真实 Task Base..Implementation Head、所有必要变化和原始证据。独立复现工具错误放行控制及 1000 级全流程；3000 级独立验证当前原生候选／全源清单、完整行对账、首次／未变零探测、小集合精确探测和真实准备／分批停止与重跑的关键行为。B 负责完整 C#／Python 全量回归、Task 指定全量门槛和独立验收；可复用匹配且可核验的完整建库／准备、昂贵全轮和其他最终门槛，但不能以 Developer 的聚焦结果替代全量门槛。3000 项准备库按上方用户要求在所有需要它的开发阶段持续保留，B 与 Slice Final 不是复用终点，显式人工交接并核验归属，不能让新进程仅凭旧 token 接管。完整证据持续外置落盘，确认后续开发不再需要时才统一清理。缺失或不匹配时重跑对应门槛，不自动重建准备库，不能凭报告标签复用。

B PASS 后重新核对全部 RO／Surfaces：RO-1／安装恢复和 RO-3／扫描仍检查回归及证据有效性；RO-2 达标才 PASS。RO-4 实际代理仍必要，依固定方案规划 4.4；若事实未满足不得进入 Closure Packet 或宣布 Slice 关闭。

### 证据与重跑规则

每个候选／运行索引保留在 `.git/validation-evidence/<完整源码SHA>/<唯一run-id>/` 或稳定 CI，写明仅本机可读。包含完整源码／审查 SHA、准确工作区身份、SDK／锁／镜像／配置／夹具／包／部署摘要、新主机资源限制／运行前预算与宿主样本、准确命令／cwd／退出码／计数／耗时、查询／批次／实际开始保存／五字段／地址主流／进度／终态／延迟原始记录。清单和响应流式、脱敏保存，不留完整 URL、token、Cookie、凭据或私有路径；证据目录在实例之外，归档不得混入状态库或测试资料。

保留首次失败、每次重跑、缺失与不可用；资源／超时／阶段未命中必须如实记录。准备、执行、对账和清理各自结论独立，任何必要阶段未完成不能总 PASS。测试／工具／配置／夹具／依赖或可执行输入改变时相关证据失效，最终候选重走完整 T4；纯报告后继显式比较输入后才复用并重跑文档消费检查。环境预算及调整由实施者留证、B 审查，不移动 ID／Base／Goal 或弱化 AC。旧服务器的忽略目录不随 Git clone 迁移；无法访问历史原始运行时按开发流程重跑拟复用门槛，不将历史目录存在作为启动本 Task 的条件。

## 非目标

RO-4 的实际 JellyfinProxy 联调（后续 4.4）、单独 Slice Final／Closure Packet、A 最终审查或关闭；不重复实现已接受播放／扫描能力，不为已知 P2 扩建扫描工具，不改 Slice／Roadmap／稳定需求。排除生产操作、停止其他服务、系统资源调优、插件推送／上架、生成器／OpenList API、代理改造、远程内容哈希、新 FFmpeg、持久化任务状态／独立调度器／队列、全库对象／Task、schema 或取消／共享／并发语义改变、无关重构与通用性能 SLA。

## Developer Completion Report

- Changed Files：`scripts/run_isolated_large_library_integration.py`（新增）、`tests/test_isolated_large_library_integration.py`（新增）、`src/Jellyfin.Plugin.StrmProbeOptimizer/Services/BatchCheckRunner.cs`（仅在 `FetchCandidates`／对象批次处追加脱敏阶段诊断与候选身份日志，不改任何决策、计数、取消或并发语义）、`tests/test_isolated_package_integration.py`（仅让 `load()` 复用已导入模块，修复全量发现时的测试隔离）。纯报告更新 `TASK.md`、`docs/test-matrix.md`、`docs/compatibility.md`、`docs/development-environment.md`。未改 schema、业务规则、稳定需求、Slice／Roadmap。
- Implemented：
  - 新增 `scripts/run_isolated_large_library_integration.py`（`--count 1000|3000 --scenario all`），只消费指定 ZIP 并部署到 4.1 的独立包实例（Compose project `jf-strm-probe-package-*-large-*`、默认端口 18097、工作区 `artifacts/package-env`），不调用 `deploy_plugin()`、不在验收期间补 DLL 或重建包；复用 `package_environment`／`package_plugin`／`run_isolated_package_integration` 的新工作区选择、镜像锁、归属检查、ZIP 校验／部署、鉴权、媒体准备、对账与清理，以及 `run_isolated_scan_integration` 的日期／运行关联、原生任务 API、只读源／五字段快照和增量 `EvidenceRecorder`。
  - 真实建库：写 `count` 个受支持版本 1 STRM 加库内普通视频／旧 STRM／未知协议对照和范围外受支持 STRM 对照；等待原生扫描任务 Idle 后发起真实扫描并轮询分页原生查询，直到全部受支持夹具索引（Jellyfin 扫描异步，任务 Completed 不等于索引完成）。插件禁用时用最多 2 个固定 worker 经原生 PlaybackInfo 持久化每个源的主流，扫描／准备的原生调用单列。
  - 完整轮次：首次信任（`first_trust==count`、零插件探测）、未变复查（零探测）、少量增量（预分配的 4 URL／4 内容／4 Size／4 缺流对照各按需一次探测并全部可靠提交）、增量后复查（零探测）、准备阶段停止（并发 watcher 命中同步查询窗口，停止后无对象读取）、分批停止（首批 2 源实际开始后原生停止，已开始提交、后批未读取、Cancelled 且进度 <100）、恢复轮（剩余变化 2 探测收敛）、两轮未变（零探测）、重启只读核对（完整五字段／地址／主流）与 16 个变化源显式选源 PlaybackInfo（零额外探测）。
  - 分层成本：逐轮记录候选获取／原生查询时间与当前线程累计分配、进程堆采样峰值、集合估算／实测容量／保留、批次读取时间／分配与批次数；身份集合、原生临时分配与对象读取分别报告，不称精确峰值或恒定总内存。
  - 脱敏：证据外置 `.git/validation-evidence/<source-sha>/<run-id>/large-<count>/`，仅保存摘要／哈希／计数，`events.jsonl` 流式追加、`rounds/` 快照、日志经 `redact_log_text`，不含完整 URL、token、Cookie 或私有路径。
- Tests and Results（original implementation head `850224a2e910e2131771699e9ae77e53d3b265c8`; correction checkpoint `70acae9`；B FIX REQUIRED 后修正 head `7c5169e9f1b6e527b016360708b9155805afd7ee`；ZIP SHA-256 `edf0aa9ab75a2fb83dea991e04b1b51d661ae5dc3db4d5829668cdd09288ba8d`）：
  - `bash scripts/dotnet-local build … --configuration Release --no-restore` 0 警告／0 错误（约 15s）。
  - `bash scripts/dotnet-local test … --filter 'FullyQualifiedName~BatchCheckTests|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~PlaybackOptimizerTests'` 138/138 PASS（约 4s）。
  - `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` original 13/13 PASS；correction 15/15 PASS。
  - `python3 -m unittest discover -s tests` 修正后 211/211 PASS（此前 B 记录的 2 failures／6 errors 由 `tests/test_isolated_package_integration.py` 的模块重复加载导致，已在 `7c5169e` 系列修正）。
  - 1000 级（修正 head `7c5169e9`）：`python3 scripts/run_isolated_large_library_integration.py --package … --count 1000 --scenario all` **PASS**；`actual_query_stage_stop: PASS`（流式 log follower 在第 1 次尝试命中查询窗口，停止后无对象读取）；首次信任 `candidates 1003 / first_trust 1000 / actual_probe_calls 0`；增量 `candidates 1007 / reliable_success 16 / actual_probe_calls 16`；未变与增量后复查零探测；分批停止后恢复 2 探测、再两轮零探测；实例对账 `CLEAN`、清理 `CLEANED`。证据索引 `.git/validation-evidence/7c5169e9f1b6e527b016360708b9155805afd7ee/run-20261019T051638Z-188989f9/large-1000/`。
  - 3000 级：本修正轮 **NOT RUN**，交 B 独立验收（Task 本就把完整 3000 门槛分配给 B；Developer 只跑 1000 级聚焦反馈）。两次尝试如实保留：`run-20261019T054319Z-2e26b6dd` 因 developer 诊断误用工具设备身份导致运行会话 token 失效而中断（`INTERRUPTED.md`）；`run-20261019T063052Z-535010f8` 在夹具索引进行中被 Developer 主动停止（`DEFERRED.md`），以遵守本轮会话“测试时间 < 总时间 30%”的比例约束并保留 3000 门槛给 B。两次均未取得 3000 级 PASS，不冒充通过。
  - `python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases` PASS，归档 SHA-256 与上一致（`src/` 自 `850224a` 起未改，ZIP 未重建）。
  - 未运行（明确交 B）：完整 C#／Python 全量回归（Developer 只跑聚焦）、`format`、治理／差异、三个既有默认实机回归、包／扫描全场景、RO-4 代理联调、单独 Slice Final。
- Decisions：只新增大库验收入口与对应工具回归，并在 `BatchCheckRunner.FetchCandidates`／批次读取处补最小脱敏诊断；不改决策、计数、取消、共享、并发、schema 或持久化语义。受控同 URL 内容／Size 变化使用**同容器**的独立合成 MP4（B）作为后端真实内容，因为同 URL 改变容器会让 Jellyfin 持久主流身份与编码器结果不匹配而被拒——这超出本 Task 的受控内容／Size 变化合同，故不采用。修正轮针对 B Findings：查询窗口极短（约 20–160 ms），`docker logs --since` 每次 spawn 的观测延迟（约 110–180 ms）会稳定错过窗口，故改用单个 `docker logs --follow` 流式 follower（`readline()` 读取，实测约 20–30 ms）观测，未注入等待／取消源或改变原生查询；未命中时仍如实 NOT RUN。同步查询内竞争仍由确定性测试覆盖。
- Remaining In-Slice Work：RO-2 本 Task 待 B 独立验收（含 3000 级）；RO-4 后续 4.4；单独 Slice Final、事实协调与 Closure Packet。
- Risks / Deviations：1000 为 Developer 聚焦开发反馈，非 B 独立验收或 Slice Final；3000 级与完整全量回归、独立复现交 B。真实大库停止依赖真实时序，已保留每次自然重试与未命中记录；RO-4 代理、其他 Jellyfin／平台、通用性能 SLA 仍 NOT RUN。首次失败与多次重跑原始证据保留在各运行目录。
- Head SHA：original `850224a2e910e2131771699e9ae77e53d3b265c8`; correction `70acae9`; FIX-REQUIRED correction `7c5169e9f1b6e527b016360708b9155805afd7ee`。

可复用经验只提供少量候选供 Slice 收尾，不记录开发流水账，不作为 Task PASS 门槛。

### B Review Result — media-service teardown correction after `dcce752`

```text
Decision: FIX REQUIRED remains active; the corrected cleanup gate correctly rejected the second 1000 run
Finding: media container still exited 137 because ThreadingHTTPServer could block shutdown on active request threads
Correction: isolated_media_server now uses daemon request threads, block_on_close=False, and an explicit SIGTERM/SIGINT shutdown path
```

- The second corrected-tool 1000 run completed all business rounds but returned `FAIL` with the media container `Exited (137)` and Jellyfin `Exited (0)`, proving the new cleanup gate is fail-closed. Its evidence remains at `.git/validation-evidence/dcce752/b-review-20261019T104646Z-media-stop-fix/large-1000/`.
- A short independent delayed-request process test now exits `0` after SIGTERM; focused media/package/large-tool tests pass (2/2, 28/28, 22/22), with governance and diff checks PASS.
- The isolated media-server change is same-Task test infrastructure only. A fresh 1000 run is still required after this correction; 3000 remains NOT RUN. No Closure Packet or `SLICE READY FOR A REVIEW` decision is issued.

### B Review Result — teardown exit-state correction candidate (working tree after `b2f19c2`)

```text
Decision: FIX REQUIRED resolved in the same Task; fresh 1000/3000 gates remain pending
Finding: cleanup_instance reported CLEANED without inspecting owned container exit state; the fresh 1000 run had media exit=137
Correction: package_environment now inspects every owned Compose container after stop, rejects running/nonzero/OOM states, preserves the workspace on failure, and records clean states in cleanup evidence
```

- The correction is limited to the Task acceptance environment and its tests. It does not change plugin behavior, cancellation semantics, product contracts, schema, or the 3000 threshold.
- Focused verification: `test_isolated_package_integration.py` **28/28 PASS**; `test_isolated_large_library_integration.py` **22/22 PASS**; governance and `git diff --check` PASS.
- The prior fresh 1000 result remains retained as a failed cleanup gate despite business-round PASS. It must be rerun with the corrected tool. The required 3000 gate is still NOT RUN; no Closure Packet or `SLICE READY FOR A REVIEW` decision is issued.

### B Review Result — fresh 1000 gate on candidate `b2f19c24f05d806ab75f152f36a302582e60ad67`

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..b2f19c24f05d806ab75f152f36a302582e60ad67 (implementation; report-only Task successor)
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — fresh 1000 business rounds pass, but cleanup evidence does not prove normal container termination; required 3000 gate not run
Next: repair the same Task's isolation teardown evidence/control, then B re-runs the affected 1000 gate and the required 3000 gate on the fixed ZIP
```

#### B Findings

1. The fresh 1000 run used ZIP SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d` and returned process exit 0 / `status=PASS`. Its recorded business rounds are internally consistent: first trust 1000 with zero probes, unchanged zero probes, controlled increment 16 reliable probes, query-stage stop observed before object read, post-stop recovery 2 reliable probes, and clean instance reconciliation.
2. **FIX REQUIRED — teardown does not record or validate owned container exit state.** `scripts/package_environment.py::cleanup_instance()` calls `docker compose stop --timeout 20`, then removes the workspace and returns only `status=CLEANED`. For this run, Docker inspection after completion shows the owned Jellyfin container `Exited (0)` but the owned media container `Exited (137)`; the evidence still reports `CLEANED` and preserves no `ExitCode`/`OOMKilled`/signal state. Task 4.3 explicitly requires that forced termination cannot be reported as normal cleanup, so this run's cleanup gate fails.
3. The raw evidence is retained at `.git/validation-evidence/b2f19c24f05d806ab75f152f36a302582e60ad67/b-review-20261019T083927Z/large-1000/`; the package-run workspace and its owned containers are gone, and the shared development containers were not taken over or stopped. No 3000 run was started after this finding.

This is a same-Task acceptance-tool finding, not a contract or product-scope change. No Closure Packet or `SLICE READY FOR A REVIEW` decision is issued.

### B Review Result — finalization correction candidate `1c3e0176a285774641da265513a9f76510be666a`

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..1c3e0176a285774641da265513a9f76510be666a (implementation); report-only successors 024feea and b2f19c2
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — local gates pass, but required real package/scan/1000/3000 integration gates are BLOCKED by the shared Jellyfin health state; fresh large-library evidence is absent
Next: have the authorized environment maintainer restore a healthy isolated Jellyfin environment; then B runs the blocked real gates on one fixed ZIP and re-reviews without changing Task scope
```

#### B Review Findings

1. The fail-closed query-stage result handling and teardown exit handling were reviewed on `1c3e0176a285774641da265513a9f76510be666a`. The overall status is assigned from required stages, teardown runs before the process exit code is derived, and sampler/reconciliation/cleanup failures are covered by the new focused controls. B ran the focused large-library tool suite: 22/22 PASS (0.094 seconds). This resolves the two prior B code findings; no new code blocker was found in these corrected paths.
2. B ran the fixed candidate's local gates: locked restore PASS; Release solution build PASS (0 warnings/errors); full C# tests 202/202 PASS; `dotnet format --verify-no-changes` PASS; complete Python discovery 218/218 PASS; Linux x64 package creation PASS with ZIP SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4f2a8e14a117d`; governance and `git diff --check` PASS. The reviewer ZIP is in the unique `artifacts/releases/b-review-b2f19c2/` directory; the existing release archive and sidecars were not overwritten.
3. **BLOCKED — real integration gates not run.** Read-only `python3 scripts/development_environment.py status` showed the shared Jellyfin container `jf-strm-probe-6d816bb878-jellyfin-1` as `Up 15 hours (unhealthy)`. Per `docs/development-environment.md`, package installation, playback and large-library real-instance gates remain BLOCKED/NOT RUN until the authorized environment maintainer repairs the isolation instance. B did not restart, take over, or clean any existing container. Consequently the required archive-install/package integration, scan-all, fresh 1000 and 3000 large-library runs, and the shared-instance plugin/batch/configuration integrations are NOT RUN. The 3000-item outcome remains unproven and Task 4.3 cannot PASS.
4. No Slice Required Outcome has been removed or weakened. Keep the same Task Base and scope; once the environment blocker is cleared, B must run the missing real gates against the same final ZIP, preserve raw evidence, and independently inspect the 3000 candidate/settlement and stop/restart results. RO-4, Slice Final and Closure Packet remain outstanding.

This is not a code-scope escalation to A. It is an external test-environment blocker; no `SLICE READY FOR A REVIEW` decision is issued.

## Developer Completion Report — FIX REQUIRED correction round 2

- Changed Files：`scripts/run_isolated_large_library_integration.py`、`tests/test_isolated_large_library_integration.py`。纯报告更新 `TASK.md`。未改 schema、业务规则、稳定需求、Slice／Roadmap、C# 产品代码。
- Implemented（仅修 B Finding #1，保持原 Base／Goal／Scope）：
  - 新增 `overall_acceptance_status(required_stages)`：任一必需阶段未满足即返回 `("FAIL", 1)`，否则 `("PASS", 0)`，使未观测到的准备阶段停止失败关闭而不是 exit 0。
  - 把三次自然重试抽成 `run_query_stage_stop_attempts()`：每次保留独立 attempt 记录（started／execution／events／observed），只在真正命中查询窗口时提前结束；未命中时返回 `observed=False` 与全部尝试证据，由 `run_scenario` 据此走 `required_stages` 并保留 `NOT RUN` 记录、实例对账与清理。
  - `run_scenario` 末尾不再硬编码 `"status": "PASS"`／`return 0`，改用 `overall_acceptance_status({"actual_query_stage_stop": candidate_start_seen})` 决定 summary 状态与退出码。未注入等待、未改原生停止语义、未弱化要求。
- Tests and Results（fix head `b1199d65577448b498315ddbe16f1d65c671e8ba`）：
  - `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` **18/18 PASS**（新增 3 例：未观测必需阶段→FAIL/1、三次未命中保留全部 attempt 且 `observed=False`、命中即停）。
  - `python3 -m unittest discover -s tests` **214/214 PASS**（全量 Python 发现，无 B 先前记录的 2 failures／6 errors；先前已由 `7c5169e` 系列模块共享修正解决）。
  - `bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/…csproj --configuration Release --no-restore --filter '…BatchCheckTests|…ProbeCoordinatorTests|…PlaybackOptimizerTests'` **138/138 PASS**（约 4s；C# 未改，仅受影响回归确认）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` 干净。
  - 未运行（交 B 全量／独立验收）：完整 C# build／format、三个既有默认实机回归、包／扫描全场景、fresh 1000／3000 大库、RO-4 代理、单独 Slice Final。本会话遵守“测试时间 < 本轮 30%”比例，仅跑聚焦反馈；真实 1000／3000 由 B 在独立验收阶段重跑。
- Decisions：B Finding #1 已按要求修在同一个 Task 的工具／测试内；未改合同、取消语义、样本数量或验收含义。上一轮 1000 级 PASS 证据基于修正前可执行输入，对本修正失效，须由 B 在新 head 上重跑。
- Remaining In-Slice Work：RO-2 待 B 独立验收（含 fresh 1000 与 3000）；RO-4 后续 4.4；单独 Slice Final、事实协调与 Closure Packet。
- Risks / Deviations：修正仅覆盖“未观测阶段不得总 PASS”的控制；真实查询窗口是否命中仍依赖运行时序，未命中会如实 FAIL／NOT RUN。3000 级仍 NOT RUN。
- Head SHA：fix-required correction round 2 `b1199d65577448b498315ddbe16f1d65c671e8ba`。

可复用经验只提供少量候选供 Slice 收尾，不记录开发流水账，不作为 Task PASS 门槛。

## B Review Result

### 2026-10-19 用户要求最小修正后的执行口径

- 用户指出工具设计过重并要求开始实施。本轮保持同一 Task／Base／Goal／合同，只修假通过和关键证据，不新建监控框架、治理对象或产品功能。此前审查建议中的“每轮完整前后快照”等实现方式不是新增验收义务；按原 Task 的首次／增量／停止后恢复前／重启前后关键检查点保存必要状态即可。批次／消费者上限可结合已有真实日志、代码及确定性测试证明，不要求每项都另造自动监控。
- 本轮已实施：正常轮次复用现有 Completed／本次执行时间检查，拒绝失败标志和未完成结果；复用原生扫描完成 helper；查询停止分别记录请求与确认并核对每库原生查询边界；按项目＋媒体源核对原始探测启动身份与默认并发；检查已有对象批次日志；停止收尾尝试原生再运行并在恢复前核对旧／新指纹与地址；保存关键五字段／主流签名和脱敏服务日志；已启动实例成功清理要求两项服务完整退出证据，失败保留诊断目录。未改 C#、schema、探测／取消／调度业务语义。
- 实施检查点：`348567fd17140b064f002d246e3653658e22379c`。受影响大库工具 27 项、包工具 30 项先通过；中间工作树完整 Python discovery **231/231 PASS**（5.988s unittest／6.331s command wall）。后续只增加／补充签名与停止回调用例和同一工具的小修正，最终受影响大库工具 **31/31 PASS**（0.135s unittest／0.451s command wall），治理及 `git diff --check` PASS；不把中间全套结果写成最终提交全套已通过。证据为 `.git/validation-evidence/2b49767c0c8e0fa439bfcf8328554e29bcf752c5/minimal-tool-fix-20261019T133605Z/`，`checks.json`／`final-checks.json` 分别记录准确文件摘要、完整 patch、命令／UTC／退出码／原始日志。共享清理 helper 改动影响 Python 多入口，所以追加一次廉价全量 Python，未运行 C# 或实机长测；未操作运行容器。
- 提交后最终核对：在实现 SHA `348567fd17140b064f002d246e3653658e22379c`、仅 TASK 报告脏改动时，完整 Python **233/233 PASS**（5.867s unittest／6.173s command wall）；四项实现／测试文件 SHA-256 与 `final-checks.json` 全部相同。记录为同目录 `committed-python-all.json`／`committed-python-all.log`。这是实施反馈，不是作者自称独立 B PASS；未运行最终指定实机门槛。
- **仍未完成**：BR-43-4 的准备期资源观测／预算执行与空闲窗口；增量样本实际 Guid 批次分布；本修正的真实停止／重启和新候选指定最终门槛。既有长测只保留历史观察，不把它们写成本工具修正后的 PASS。本轮作者同时实施工具，不宣称对自己的改动完成独立 B 审查。当前进入修正中，不签发 Task PASS／Closure Packet，不开启新 Task、不关闭 Slice。

Current decision: 2026-10-19 evidence audit; supersedes conflicting historical reports.

```text
Reviewed Range: a06a80fac90a86085f25116568aa24b54847c562..dfe6dfc597e6a9fd0a6bc6cf7fdd3a9c5d242a7f
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: correct the acceptance controls/evidence in SAME Task 4.3; B retains final full-suite responsibility
```

- Fresh runner observations: 1000 run `a9ffaab115c9` (1243.540s) and 3000 run `df75b733a9fa` (3293.100s) returned exit 0 / runner `PASS`, using ZIP SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`. Both recorded media/Jellyfin exit 0 and no OOM. The 3000 run reports first trust 3000/zero probes, increment 16 reliable probes, recovery 2, subsequent unchanged zero probes and restart row reconciliation. These observations do not resolve the blockers below. Raw runs remain in `.git/validation-evidence/dfe6dfc/b-review-20261019T111748Z-media-stop-fix2/large-1000/` and `.git/validation-evidence/dfe6dfc/b-review-20261019T114014Z-large3000/large-3000/`.
- **P1 BR-43-1 — query-stop classification does not prove the required phase.** `query_stop_observed` accepts query-start + HTTP 204 + no object read without comparing the stop with the per-library native-query return. In the 1000 run the query returned at `11:36:59.923298Z`, all 1007 IDs merged, and the recorded stop timestamp (actually after HTTP acknowledgement) was `11:36:59.932743Z`; this proves a preparation stop but does not prove a synchronous-query stop. The 3000 run instead records acknowledgement before return and `Complete False`/zero merged IDs. Preserve that distinction. Record request initiation and acknowledgement separately, correlate actual per-library query boundaries, reject late/before-query stops, verify Cancelled/zero admission, and add negative controls.
- **P1 BR-43-2 — stopped-state and drain-time assertions are absent.** After the stopped round settles, the tool goes directly to recovery; it never verifies the complete stopped five-field state (two started commits versus two untouched later baselines) or attempts a native run during Cancelling. Recovery can repair damage before the first full-row reconciliation. Save independent before/expected/stopped rows and native addresses/main-stream signatures BEFORE recovery; attempt rerun while delayed probes still drain and prove no new execution.
- **P1 BR-43-3 — per-source evidence is not preserved for independent audit.** `rounds/` holds candidate identities/phase lines and summaries, not expected/actual five-field rows or native address/main-stream signatures; `logs/` is empty in both runs. `reconcile_rows` retains only counts and an expected aggregate digest. Restart verifies a main stream exists but does not compare its pre-restart signature. Preserve redacted per-source expectations/actuals and probe/save/summary/backend observations; compare complete restart state before playback. Aggregate runner PASS cannot replace this requirement.
- **P1 BR-43-4 — required resource evidence/budget controls are incomplete.** Sampling starts after indexing/native preparation (1000 preparation 323.678s; 3000 preparation 958.995s). It observes only Jellyfin Docker stats and host MemAvailable, not preparation/media costs, cgroup peak/RSS/disk, enforceable resource abort thresholds, or the required 30-second pre/post idle windows. The 3000 run has 162 samples only from `12:29:35Z` to `12:35:04Z`, after its `11:40:14Z` start. `--timeout-seconds` limits task loops, not the complete level. Fulfil existing sampling/budget/settlement requirements without changing N or inventing a universal SLA.
- Additional fail-open controls reproduced offline: `run_round` accepts a native task whose result is `Failed` when counters/markers match; require the current task's Completed result and valid monotonic/terminal progress for normal rounds. `cleanup_instance` accepts an empty inspected-container list and removes its workspace; after an instance was started require complete owned-service exit evidence (distinguish legitimate pre-start failure cleanup), reject missing/active/invalid states, and retain diagnostic evidence on failure. These are corrections to existing success/cleanup requirements, not new scope.
- **P1 BR-43-5 — normal-round acceptance checks accounting, not all required successful outcomes.** Follow-up offline controls using the recorded 3000 unchanged summary reproduce `run_round` accepting a nonzero check-stage incomplete count, an unexpected missing-candidate count, and each of `store_unavailable` / `scope_unavailable` / `disabled`, while counter equations and candidate identities still match. Later full-row checks may catch persistent damage, but the unchanged rounds do not immediately compare the full fingerprint/native state, so a subsequent increment or recovery can hide a transient failure. Require the independently expected supported/control settlements, zero unexpected failure flags and incomplete outcomes, and complete before/after state at each required round; normal-round admission alone must not label these cases successful.
- **P1 BR-43-6 — item visibility does not prove the current indexing scan completed.** `prepare_indexed_fixture` waits for an earlier Idle, posts `/Library/Refresh`, then returns when names resolve; the increment path uses the same visibility-only preparation. Neither requires the new scan's start/end identity and Completed result before batch execution. An offline control made the new scan Failed while all fixture names were visible; preparation returned without reading that result. Record and require the actual current scan completion, then independently reconcile all fixture identities, rather than using item visibility or HTTP acceptance as completion.
- **BR-43-3/4 assertion follow-up — probe identities and work bounds are observed but not enforced by normal rounds.** `run_round` checks the reported probe total, not independent `(item_id, source_key)` start/success identities; the raw probe reader is never consulted there. It also accepts object-read phase evidence changed from request/return 128 to 9999. The twelve original increment controls are chosen by filename position before native Guid ordering, not selected and verified across the required actual batches. Enforce exact changed-source identities (reject substitutions/duplicates/unexpected control probes), actual batch/consumer/probe bounds, and actual Guid-batch coverage; preserve raw observations under BR-43-3. These are missing runner assertions, not a finding that the observed real runs exceeded their bounds or probed wrong items.
- Follow-up evidence: `.git/validation-evidence/8f49a669df2ae8d937125b3b661f9c499b9efba8/b-tool-followup-20261019T132116Z/` contains the reproducible script, its SHA-256, source identity, UTC/wall time and eight offline controls (0.697s in-process). All eight reproduced the specified tool-level gaps; this is **BUG REPRODUCED, not acceptance PASS** and not an end-to-end plugin failure claim. No live container/API, full suite or large-library run was started; executable inputs remain unchanged. Initial command-serialization/syntax attempts failed before executing the controls; the corrected run exited 0.
- Evidence salvage: B read only the exact four retained stopped containers after verifying project labels, Jellyfin container IDs/image and exit state, and saved redacted logs plus content hashes under `retained-logs/` in the audit directory. Across all 14 completed-round snapshots, raw probe-start counts match their summaries (including increment 16 and recovery 2), candidate identities match the native manifests exactly, and observed batch requests/returns are at most 128. This recovers logs omitted by the runner but cannot recover deleted expected/actual SQLite/native-state snapshots, preparation sampling or drain-time rerun attempts; BR-43-2/3/4 remain unresolved.
- Executed checks: complete Python discovery **222/222 PASS** (5.929s unittest runtime, 6.226s command wall time); five independent offline negative controls reproduce the above fail-open cases; committed governance PASS; `git diff --check` PASS. Evidence, scripts, exact commands/cwd/UTC/durations/exits: `.git/validation-evidence/dfe6dfc597e6a9fd0a6bc6cf7fdd3a9c5d242a7f/b-audit-20261019T125200Z/`. Python ran with only this Task report changed; executable/test inputs match `dfe6dfc`.
- Existing C# restore/build/full 202-test/format and ZIP build observations are retained from `b2f19c2` (not rerun this continuation). An explicit diff confirms C# source/tests, build/dependency/SDK/packaging and fixed environment inputs unchanged through `dfe6dfc`; this does not validate changed Python environment tools or satisfy missing real gates. Known blockers justify not starting package-all/scan-all/plugin/batch/configuration or repeating expensive large runs now. Those final gates remain NOT RUN and B-owned; Developer runs changed/new tests and directly affected feedback only. Fixed-candidate full gates and independent reproduction remain mandatory; reuse only explicitly matched inputs.
- Independence: this assistant authored environment fixes `dcce752`/`dfe6dfc`; independent review of those implementations is NOT CLAIMED. Correction to the earlier diagnosis: Python `ThreadingHTTPServer` already has daemon request threads. The added SIGTERM shutdown path demonstrates the relevant PID-1 teardown fix; non-daemon threads are not an established original cause.
- Time accounting: the two latest large runs alone used 4536.640s. A complete earlier-round elapsed/test ledger is absent; compliance with the user's test-time <50% limit is NOT PROVEN. This continuation uses short recorded checks and no artificial waiting.
- Same Task ID/Base/contract; no new Task, no RO-4 acceptance, no Closure Packet, no Slice closure and no `SLICE READY FOR A REVIEW`. Conflicting historical reports below are superseded by this current decision; previous failures/raw runner results remain retained.

## B Review Result — historical decision

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

### B Review Result — correction candidate `7c5169e9f1b6e527b016360708b9155805afd7ee`

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..7c5169e9f1b6e527b016360708b9155805afd7ee (implementation); report-only successor 9695a2e
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — the required query-stage stop can remain NOT RUN while the acceptance command exits 0 and reports overall PASS; the 3000-item run is also NOT RUN
Next: fix the same Task's acceptance result handling and regression test, then rerun affected feedback and B's full candidate gates
```

#### B Finding

1. **FIX REQUIRED — an incomplete required query-stage stop can be reported as overall PASS.** In `scripts/run_isolated_large_library_integration.py`, after three natural attempts fail to observe the query-stage stop, the runner records `query_stage_stop: NOT RUN` at lines 1055–1058 but continues through the remaining scenario and later sets `summary.status` to `PASS`. This returns exit code 0 even though the Task requires this stage and explicitly says an incomplete required phase cannot produce total PASS. The 1000-item Developer run did observe the stage, but does not prove the missing-stage control is fail-closed, and the required 3000-item run remains NOT RUN.
2. Fix only the same Task's tool/test: make an unobserved required stage prevent an overall PASS (while preserving the attempt evidence and cleanup), and add a regression proving the overall acceptance result is nonzero/non-PASS when all three attempts miss. Do not inject waits, alter native stop semantics, weaken the requirement, or change Slice scope.
3. No tests or full gates were run in this B turn because the blocking control-flow defect was established by direct source review; per workflow, an existing blocker may be returned before other gates. After the fix, Developer runs the new/affected tool tests and directly affected checks. B must then review the new Task Head and run/reuse only matching complete evidence, independently exercise the fail-closed control, and complete the specified C# / Python full regression, format, packaging, package and scan integrations, fresh 1000 and 3000 large-library runs, plugin / batch / configuration integrations, governance and diff checks before PASS.

This decision does not move the Task Base, change its scope or contract, or satisfy any Required Outcome. RO-4 and Slice Final remain outstanding; no Closure Packet or `SLICE READY FOR A REVIEW` decision is issued.

### B Review Result — fail-closed correction candidate `b1199d65577448b498315ddbe16f1d65c671e8ba`

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..b1199d65577448b498315ddbe16f1d65c671e8ba (implementation); report-only successors 1e12879 and 5352a79
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — the query-stage miss is now fail-closed, but reconciliation/cleanup failure can still leave the process exit code at 0; fresh 1000/3000 acceptance remains NOT RUN
Next: correct same-Task finalization/exit handling and test cleanup/reconciliation failures, then B re-review and run the remaining candidate gates
```

#### B Finding

1. **FIX REQUIRED — cleanup or instance-reconciliation failure may produce exit code 0.** `run_scenario` returns `exit_code` from inside the `try` at line 1227, before its `finally` block performs `reconcile_instance_state` and `cleanup_instance`. If either operation raises, `finally` changes `summary["status"]` to `FAIL` and writes a failing evidence summary, but Python retains the already-evaluated return value of 0. A shell/CI caller can therefore treat a failed cleanup or reconciliation as command success, contrary to the Task rule that any required cleanup failure must not produce overall PASS.
2. The new query-stage fix itself was reviewed and its focused test passed, but its test coverage does not exercise the `run_scenario` finalization path. Keep the same Task and add a focused regression that forces reconciliation/cleanup to fail after otherwise successful execution and proves the final command return code is nonzero and the evidence status is FAIL. Preserve cleanup attempts and original diagnostics; do not weaken cleanup requirements.
3. B ran `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v`: 18/18 PASS (0.086s). No full regression or real-instance gates were run after identifying this blocker. After the fix, Developer runs the changed tool tests and directly affected checks; B must then review the new Task Head, independently verify fail-closed query-stop and finalization controls, and complete the specified full C# / Python full regression, format, package/scan/plugin/batch/configuration integrations, fresh 1000/3000 runs, governance and diff checks before PASS.

This finding does not move the Task Base, alter scope or contract, or satisfy RO-2. RO-4, Slice Final, and Closure Packet remain outstanding; no `SLICE READY FOR A REVIEW` decision is issued.

## Developer Completion Report — FIX REQUIRED correction round 3

- Changed Files：`scripts/run_isolated_large_library_integration.py`、`tests/test_isolated_large_library_integration.py`；纯事实文档同步 `docs/test-matrix.md`、`docs/compatibility.md`（把 RO-2 指针更新到本轮修正 head 与两次既有 FIX REQUIRED）；纯报告更新 `TASK.md`。未改 schema、业务规则、稳定需求、Slice／Roadmap、C# 产品代码。
- Implemented（仅修 B Finding #1，保持原 Base／Goal／Scope）：
  - 把 `run_scenario` 的场景主体抽成 `run_scenario_body(...)`，运行期资源放进 `ScenarioState`（`workspace`／`before_state`／`sampler`）。`run_scenario` 在 `try` 内调用主体，`finally` 调用 `finalize_scenario(...)` 执行 sampler 停止、实例对账与清理，任一失败把 `summary["status"]` 置为 `FAIL`。
  - `run_scenario` 不再在 `try` 内返回，而是在 `finally` 全部完成、证据写入后依据最终 `summary["status"]` 返回 `0/1`。这样清理或对账失败不可能让命令以 0 退出，也不弱化清理要求；原诊断字段（`sampler_cleanup_error`／`instance_reconciliation_error`／`cleanup_error`）与尝试记录保留。
  - 保留上一轮的 fail-closed 查询阶段停止控制（`overall_acceptance_status`／`run_query_stage_stop_attempts`）不变。
- Tests and Results（fix head `1c3e0176a285774641da265513a9f76510be666a`）：
  - `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` **22/22 PASS**（新增 4 例：清理失败、对账失败、sampler 停止失败均强制 exit 1＋summary FAIL，成功收尾保持 exit 0）。
  - `python3 -m unittest discover -s tests` **218/218 PASS**（全量 Python 发现）。
  - `bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore` 0 警告／0 错误（约 16s）。
  - `bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/…csproj --configuration Release --no-restore --filter '…BatchCheckTests|…ProbeCoordinatorTests|…PlaybackOptimizerTests'` **138/138 PASS**（约 4s；C# 未改，仅受影响回归确认）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` 干净。
  - 未运行（交 B 全量／独立验收）：`format`、三个既有默认实机回归、包／扫描全场景、fresh 1000／3000 大库、RO-4 代理、单独 Slice Final。本会话遵守“测试时间 < 本轮 30%”比例，仅跑聚焦反馈；真实 1000／3000 由 B 在独立验收阶段重跑。
- Decisions：B Finding #1 已按要求修在同一 Task 的工具／测试内；通过“先完成 finally、再依据最终状态派生退出码”修复，未改合同、取消语义、样本数量或验收含义。上一轮 1000 级与查询阶段停止证据基于修正前可执行输入，对本修正失效，须由 B 在新 head 上重跑。
- Remaining In-Slice Work：RO-2 待 B 独立验收（含 fresh 1000 与 3000）；RO-4 后续 4.4；单独 Slice Final、事实协调与 Closure Packet。
- Risks / Deviations：修正覆盖“收尾失败不得命令成功”与“未观测必需阶段不得总 PASS”两个控制；真实查询窗口是否命中仍依赖运行时序，未命中会如实 FAIL／NOT RUN。3000 级仍 NOT RUN。
- Head SHA：fix-required correction round 3 `1c3e0176a285774641da265513a9f76510be666a`。

可复用经验只提供少量候选供 Slice 收尾，不记录开发流水账，不作为 Task PASS 门槛。

# NO ACTIVE IMPLEMENTATION TASK

## Task 4.3 — 真实 1000 项原生库的增量检查与成本

本检查点保留完整 Task 4.3 计划、Developer／B 历史与最终 B PASS；没有活动实施任务。下一步 B 依据固定方案规划 4.4，本检查点不启动其实施。

必读：[已提交 Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。本 Task 仅细化 RO-2，不改变合同、Roadmap 或稳定需求。

```text
Task ID: 4.3
Parent Slice: 4
Status: PASS
Task Base: a06a80fac90a86085f25116568aa24b54847c562
Contract Checkpoint: 539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3
Difficulty: High
Test Level: T4
Planner / Reviewer: B
Implementation Head: 8573dfbffebb785261668f9cd5c895be937e000e
```

当前 B 审查以文末 [2026-10-20 最后门禁续审与最终裁决](#b-final-gates-20261020) 为准：完整 T4 与独立验收已满足，Task 4.3 PASS；准备同步适配、原始失败和非阻塞 P2 如实保留。RO-4 与单独 Slice Final 未完成，下一步仅由 B 规划 4.4，不声明 Slice 已通过。

## Goal

交付 Slice 4 RO-2、AC-3／AC-4 及 AC-8 的大库、成本与恢复证据部分：在固定 Jellyfin 12.2.0／Linux x64 的 ZIP 安装隔离实例上，完成至少 1000 个真实已索引的受支持 STRM 物理候选的首次信任、未变检查、少量增量和准备／分批停止后重跑。证明静态范围不漏不重、仅所需源实际探测，完整对象和活动工作有界；分别披露 O(N) 身份集合、原生查询临时分配、对象读取、进程内存、耗时、进度和停止延迟。

### 2026-10-19 用户明确的准备库复用要求

2026-10-19 用户进一步授权将大库门槛从 3000 调整为至少 1000 个真实原生候选，直接使用现存全部 1004 个受支持库内源；不截取为恰好 1000，不再要求另跑 3000 级。本节优先于下文和历史报告中的旧数量门槛、两级运行及每次新建、逐次清理大库的执行方式；用户进一步明确复用范围为所有需要使用的开发阶段，不限于本 Task、验收轮次或本 Slice。不移动 Task／Slice Base，不改变业务验收结果或签发 PASS。

- **现存 1004 项库持续保留，所有需要使用它的开发阶段复用**：当前及后续 Task／Slice 的实施、调试、修复、回归、联调、独立审查、最终验收和发布前验证，只要需要该库，均复用这份真实原生索引和已保存主流；首次信任、未变、增量、停止／恢复和重启是其中的验证场景，不是复用范围的上限。不因换阶段／角色、修改代码／工具或 Task／Slice 结束就重新建库或逐源准备，不据此启动未授权的后续实施。
- 现存可复用库的本机工作区为 artifacts/package-env/runs/run-20261019-104647-796ca45c（另有 run-20261019-101535-82a65ce3 可作为备选；运行时只选一份，不能并行修改）。每份现有 1004 个受支持库内源及其原生主流、1004 条匹配指纹；物理 STRM 总数 1007 包含范围外及旧／未知协议对照，不混入 N。此为已有指纹的运行后状态，尚未确认存在首次信任前的一致离线基线；不得直接当作首次信任前状态，也不因本次下调门槛宣称验收通过。
- 准备完成且首次信任尚未发生时，在实例完全停止、工作已结算后保留一份一致的离线基线：原生库／配置、STRM／受控媒体及服务配置、插件指纹初始状态和独立清单。离线整体备份／恢复即可，不新增快照框架，不逐行修改原生数据库或伪造媒体流。首次信任前须核验对应源没有插件指纹。
- 同一次场景序列保留自然演进状态，不能在停止与恢复之间还原基线掩盖错误。重复首次信任或完整场景时从上述基线恢复；只补某阶段时核验其所需前置状态。重启测试必须保留被测状态，不能用恢复备份代替重启持久化验证。
- 每轮重新记录实际源码／ZIP／工具／配置身份、候选／源清单、前置状态及本轮日志与结果。复用的是准备数据，不是旧 PASS；新候选和 Final 仍执行所需行为验证。输入变化先核查准备库是否仍适用，仅在身份／协议／媒体或主流前提失效时修复受影响准备，不能默认全部重建。
- 跨进程／角色／开发阶段继续使用须显式交接并核验隔离目录、容器、挂载及当前操作权限，不仅凭旧 token 接管；不操作非本轮或生产实例。大库持续保留，每次使用结束仍核对无残留工作及配置／触发器恢复；确认后续开发不再需要时才安排统一清理，不能仅因当前验收、Task PASS 或 Slice 关闭清理，失败证据继续保留。
- 本轮只同步用户授权的数量门槛及复用计划，不改大库工具／插件、不操作实例；现有自动入口每次创建／清理工作区的行为不代表已经支持跨次复用，未适配前不得直接运行它而销毁保留库。本次数量调整取消原 1000→3000 两级义务，但不取消真实查询停止、完整逐源对账、停止／恢复／重启及其他正确性门槛；本轮不修改工具或插件。

### 2026-10-19 保留库备份与聚焦补证（非独立验收）

用户随后明确“开始做吧”，忽略误发数字后继续：本次实际执行只读核验、离线整体备份和新隔离副本上的聚焦行为验证，替代前述“本轮仅文档、尚未备份／操作实例”的执行进度描述；不改变当前合同、Task Base、Implementation Head 或既有 B FIX REQUIRED，不修改插件及大库工具源码。

- **准备数据持续保留**：原库 `artifacts/package-env/runs/run-20261019-104647-796ca45c` 的 1004 项主流／指纹原样保留。运行后整体备份 `artifacts/library-backups/1004-post-run-20261019T143144Z-27eb2f15/workspace.tar.gz`，SHA-256 `4154c1a8aa8baf7552195b74503191e248244823e9c9b3288f3eb3f467adc4fd`；恢复检查 1170 文件逐项哈希一致、两个数据库 quick_check 均 ok，聚焦验证结束再次核对原库全部文件与备份摘要未变。
- **首次信任前基线已补齐**：在新空工作区取得独立归属后复制已准备库，仅把副本中的运行后插件指纹数据库移到私有证据目录保留，不逐行编辑原生库或重建主流；首次启动前保存并恢复验证 1168 文件的一致离线基线，SHA-256 `598ee46a396e08f3421e15879f7e2f440cdade8fc8f0b70e8476e04d2ea02b7a`。启动后确认对应插件指纹为空；此操作不清空原库指纹。
- **固定输入与隔离**：本轮源码检查点 `1493cad0de07a6f9dce481d1cc16fd78e4d35245`，启动前已有的三个工具／测试文件工作区改动保持不变。匹配保留库安装负载的既有 ZIP 为 `b-review-b2f19c2`，SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`，包来源 `b2f19c24f05d806ab75f152f36a302582e60ad67`，不是当前 Task 最终候选的独立验收。唯一新项目 `jf-strm-probe-reuse1004-20261019t143711z-de74d1` 使用本机 18098，所有绑定只指向新副本，不接管生产／共享开发实例。
- **实际行为结果**：首次信任 1004 项、未变复查、重启后任何播放前的完整状态核对均聚焦 PASS。原生候选 1007（1004 支持项＋3 库内对照），每轮候选 ID 完整对账、8 批读取且每批不超过 128；首次信任数 1004，未变轮首次信任数 0，两轮实际探测均 0。逐源保存预期／实际五字段、地址哈希与主流签名，重启前后 1004 项一致且零额外探测，不用备份恢复冒充重启。
- **成本与收尾**：单次聚焦流程 108.080s，不重复扫描或逐源准备主流；92 次资源样本、采样错误 0，观测 cgroup 峰值 Jellyfin 367919104 bytes、媒体服务 15118336 bytes。记录实际 CPU／内存限额及预算；采样不包含历史准备成本，也未满足完整门槛的启动前后 30 秒空闲窗，不宣称完整成本验收。触发器恢复核验 PASS；两个自有容器均退出 0、无 OOM，副本和基线保留，不执行销毁清理。
- **证据与限制**：私有证据 `.git/validation-evidence/1493cad0de07a6f9dce481d1cc16fd78e4d35245/reuse1004-20261019T143711Z-de74d1/`；含一次性执行记录、离线基线／恢复清单、逐源状态、脱敏日志、资源及完整性检查。总状态 **PARTIAL；完整 Task 验收 NOT RUN**。少量跨实际 Guid 批次增量、真实查询停止、延迟探测停止／收尾／恢复、全量回归及独立 B 仍待完成；不以本轮聚焦结果关闭现有发现或进入下一 Task。未运行 C# 构建／测试及全量 Python（无相关源码改动），未自动推送；凭据、运行库、原始证据均不上传。

### 2026-10-19 用户授权的首轮脚本精简

用户在脚本盘点后要求“先调整一波脚本吧”。本轮仅清理已完成使命的 V3.0 初始化工具：删除 `scripts/bootstrap_repository.py` 和 `scripts/bootstrap-manifest.json`；同步 `check_governance.py` 的必需文件清单、CI 的 Python 语法目标，以及 README／开发流程／开发环境中的历史定位。旧文件从 `aa01231` 的 Git 历史读取，不重写历史。保留 `--bootstrap` 只读规划检查、V4.3 方案哈希、现行必需文档、已提交合同和祖先关系约束，不改变产品验收或 Slice／Task 的 Base、状态和 Implementation Head。

- 新增两项治理回归：已删除的旧初始化文件不再成为运行前提，CI 语法目标均指向现存文件。`python3 -m unittest discover -s tests -p 'test_governance.py' -v` **26/26 PASS**；执行修改后的 CI `py_compile` 命令、当前治理检查和 `git diff --check` 均 PASS。
- 仅运行受影响检查；完整 Python／C#、浏览器及真实 Jellyfin 验收 **NOT RUN**，本轮未改对应源码、未启动或操作容器。未修改大库／安装环境脚本，开工前已存在的三个源码／测试文件改动逐文件哈希及完整差异摘要保持不变；1004 项准备库、基线备份和失败证据均未清理。
- 私有检查记录：`.git/validation-evidence/aa01231ea9ebc4f3a25166da8eb8ce6bffb43dc0/` 下 `script-cleanup-20261019T145327Z/`。本次为用户明确授权的仓库维护，不代表解决 Task 4.3 的 B Findings 或完成独立验收；不自动推送。

## 实际基线、已接受结果与缺口

- 规划开始 `main` 干净，治理 PASS。Task Base 是 4.2 最终 B PASS 提交；Slice Base 固定为 `03169b07d110964562f7da31d2c3d7add82e5ff5`。此前 Contract Checkpoint 为 `611c31c31115b02c3fb60cef2826d9348e352b7b`，固定交付方案初始快照为 `ae265d0dba02aa1c5599871602d4350072b7155f`；当前数量门槛以 2026-10-19 用户授权及本次提交合同为准，当前 Contract Checkpoint 指向已提交的新合同，仅同步合同指针，不代表已完成 B 合法性重核或独立验收。
- RO-1／4.1 B PASS 保留在 `0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`；RO-3／4.2 完整计划、历史拒绝和补证 B PASS 保留在 `a06a80fac90a86085f25116568aa24b54847c562:TASK.md`，不用永久 Task 归档。最新已审查实现为 `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5`，原 ZIP SHA-256 为 `434f930d6ad8282c1d68d47c7fc4456d52a025ae05e273db7b2f21551071ccaf`；它们不是未来 4.3 候选的验收证明。
- 已核对 `BatchLibraryScope.cs`、`BatchCheckRunner.cs`、`StrmProbeScheduledTask.cs`、`BatchCheckTests.cs` 与包／扫描／批量工具。已有原生 GetItemIds、Guid 去重排序、每批最多 128 个对象、每批最多 8 个消费者，共同 optimizer／Coordinator／条件提交，以及候选／对象读取成本摘要。历史十万规模单元测试使用合成 ID 和普通对象，不是 1000 个真实 STRM／已有主流的证据。
- 复用 `scripts/package_environment.py` 的新工作区、当前进程 token 归属、镜像锁、Compose、解包安装／摘要和清理；复用 `run_isolated_scan_integration.py` 的完整日期／运行关联、原生任务 API、只读源／五字段快照和增量 EvidenceRecorder，以及 `run_isolated_batch_integration.py` 的成本字段解析。只复用无开发部署副作用的函数，不调用旧入口 main 来准备包实例。
- 重要准备事实：现有 `native_probe_and_save` 明确指出原生扫描不为 STRM 探测主流，须在插件禁用时通过原生 PlaybackInfo 等既有原生入口准备。不得对全库文件逐项调用会再次全库扫描的 `scan_and_wait`／`native_probe_and_save`；先扫描完成，再有界逐源准备并核验保存。
- 已阅读 4.2 B 重启补证索引及原始审计：三个源完整行／地址／主流在重启前、重启后播放前和播放后三阶段相等且零额外探测。正式扫描工具的重启漏检为已知 P2，不在本 Task 扩建该工具；新的大库重启检查使用独立重启前预期，Slice Final 仍须补齐最终候选的同等证明。
- 2026-10-18 用户授权迁移开发服务器并取消旧主机依赖。B 在同一 Task 内修订执行环境计划：保留 ID、Base、Goal、Scope、AC 和 High／T4；旧规划／资源观测保留在 `b92bea58a2552997bd750f059fc7d6c6cca23b93:TASK.md`。新主机重新准备环境和记录预算，不继承旧资源 BLOCKED，不要求读取旧本机证据才能开工；新真实大库结果仍全部 NOT RUN。

## 实施范围与顺序

按以下顺序完成同一个行为。复用现存 1004 项准备库，按至少 1000 项的单一规模执行所需场景，不再为了两级流程重建或扩库；当前只同步文档，不继续扩建工具或执行实机。已有能力不重写；遇到本行为的真实产品缺陷才在同 Task 最小修复。需要改变合同、核心接入／成功／保存边界时交 A，B 重判后才继续。

### 1．复用现有验证能力，不继续扩建大库工具

2026-10-19 用户后续明确授权调整大库脚本：现有入口新增 --reuse-workspace，默认 unchanged，--count 默认 1000 表示下限并保留全部实际 1004 项；baseline／restart 为可选聚焦场景。已停止保留库只读核验后复制到新归属副本，不接管旧 token，不建库／扫描／全库主流准备；结束停止并保留。首次信任只可显式保存并移走副本指纹库，不能静默清空原库。聚焦成功仍为 PARTIAL、完整 Task 为 NOT RUN；旧全流程仅由 --fresh 显式选择，不用于保留库。执行方式与限制见 [测试矩阵](docs/test-matrix.md#slice-4-大库验收本地运行)，当前修正实测结果见下方开发报告；既有 B FIX REQUIRED 不变。

### Developer 修正指导：在复用副本上补齐完整行为

当前 `--reuse-workspace` 只支持 `baseline`／`unchanged`／`restart`，并把增量、查询阶段停止、探测停止收尾、恢复和显式播放列为 `NOT RUN`；这是本 Task 的唯一当前 FIX REQUIRED。请在同一 Task 内扩展该入口，允许：

```bash
python3 scripts/run_isolated_large_library_integration.py \
  --package <最终候选 ZIP> \
  --reuse-workspace <已核验且已停止的 1004 项准备库> \
  --count 1000 --scenario all \
  --reset-copied-fingerprints \
  --evidence-dir <新的外置证据目录>
```

实现约束：

- 只复制并使用已核验的 1004 项准备库副本；不得截成 1000、修改原库、接管原容器／token、调用 `prepare_clean_instance`、重新建库或逐源重新准备全库已有主流。为受控夹具变更调用原生索引扫描不等于重建／全库重探测；须如实披露扫描范围与成本，受影响的主流准备仍仅限受控源。`--fresh --scenario all` 仍是独立兼容入口，不能作为本修正或验收替代。
- 将现有 fresh 流程中的行为轮次与“建库／准备输入”分离。复用模式从副本读取并核对全部 1004 项文件、原生项目／物理源 ID、库关系、地址和必要主媒体流，然后在同一副本上执行完整行为轮次；不得复制出另一套只做聚焦检查的逻辑。
- 完整轮次必须包含：副本指纹库显式清空并保存备份后的首次信任、未变零探测、跨真实 Guid 批次的 URL／内容 SHA-1／Size／缺主流增量、真实同步查询窗口停止、已开始两项探测后的停止／收尾及收尾期间重跑尝试、旧轮完全 Idle 后恢复、两轮未变、重启前后完整指纹／地址／主流核对，以及变更源的显式 PlaybackInfo 检查。停止和重启之间不得恢复基线掩盖演进状态。
- 每个阶段保存独立的预期／实际五字段行、候选及结算身份、实际探测开始／成功／保存、地址和主流签名、批次／消费者／并发边界、进度／停止延迟、资源采样和脱敏原始日志；不能只保留总数或让后续恢复覆盖停止前状态。
- 任一必需阶段未观测、候选／源对账不完整、停止后新准入、收尾／对账／采样／清理失败、资源超限、超时或输入副本改变，整体必须 `FAIL` 且非零退出，并保留副本和诊断；不得用 `PARTIAL` 或 `focused_status=PASS` 冒充完整 Task PASS。成功复用场景才可将 `full_task_acceptance` 改为 `PASS`。
- 补充编排回归：`reuse + all` 不调用重新建库／全库主流准备，不改变原库；允许必要的原生夹具索引扫描和受影响源主流修复，确实执行上述所有阶段；每个阶段的失败控制都返回 `FAIL`／非零；现有保留库安全、候选身份、停止边界、资源和清理负例继续通过。Developer 只运行改动文件直接影响的测试，并列出未运行的全量与真实门禁。

完成后保留同一 Task ID、Task Base、Contract Checkpoint 和 1000 项合同，提交新的实现 Head 和准确证据；B 再独立复现完整复用流程并运行最终指定门禁。不要新建 Task，不要以旧 fresh 运行或当前 focused 运行替代本修正。

单轮只使用一份 N≥1000 的真实准备库（当前 N=1004），按场景所需状态串行验证。外置证据持续保留；端口采用包验收默认的本机 18097，可在启动前用现有 JF_PROBE_PACKAGE_PORT 选择空闲端口。非本轮非空工作区、占用端口或活跃容器仍拒绝任意接管；明确交接并核验的保留库不豁免隔离规则。

只消费指定 ZIP 并验证加载负载摘要；服务器不挂源码／SDK／NuGet，不构建或补 DLL。环境写入和清理继续核验当前进程确实取得的 token、目录及容器挂载归属。场景串行，记录并暂时清除会干扰运行的原生触发器，结束恢复核验。

### 2．核验保留库与资源、超时和观测

按新服务器实际资源制定运行预算，不再使用旧服务器的 CPU／内存限额、2432 MiB 准入值、磁盘／inode 数值或整轮超时表，也不继承旧主机内存不足的 BLOCKED。保留以下可执行的准备顺序：

1. 在当前检出根目录记录 OS／架构、SDK、Docker／Compose、Node／浏览器、固定镜像 digest、CPU／内存／swap／空闲磁盘／inode及空闲端口；以 doctor 和实际依赖检查判断就绪，不依赖旧主机的已有缓存／账户／容器。
2. 在任何实机运行前，于已有证据索引记录本轮 Jellyfin／媒体服务的 CPU 与内存限制、编排进程预算、宿主余量、磁盘／inode 余量、资源中止条件，以及启动、单次 API／同步查询、建库、原生主流准备、每轮批量、全源对账、停止收尾、整轮总时长上限。所有数值与依据使用新主机资源，不得缺省为无限等待；不新增环境审批或治理对象。
3. 运行前根据现存 1004 项库的实际状态和已有准备成本记录固定预算，不设置额外 3000 级资源准入或运行义务。首次设定和换机调整可在已有授权内进行，无须再次申请 B 批准；改变参数时保留前一预算和原因。失败后的调整保留原始失败和重跑身份，交 B 审查，不改变样本数量、业务规则或验收含义。
4. 使用本轮容器资源限制时只调整本轮 Compose，复用 writer 的最小可选参数，既有入口默认行为保持；不改宿主配置或其他服务。准备原生调用仍最多 2 个同时执行；每 1 秒采样本轮服务 cgroup 内存／可用 peak／CPU／进程数、Jellyfin RSS、宿主 MemAvailable／磁盘，每 0.5 秒轮询任务状态／进度。
5. 按运行前固定的资源中止条件和超时工作：停止新增准备／批量准入，立即留证，请求原生停止，等待同步查询真实返回及已开始探测正常收尾。不以杀进程冒充取消。确需终止本轮确认归属的隔离容器时记录 FAIL／中断，保留清理前资料和工作区；不后台遗留运行，不删除唯一诊断证据。
6. 新环境实际缺依赖、超预算、超时、OOM 或结算不完整时如实 BLOCKED／FAIL，不能通过降低 1000 验收数量、跳过主流准备、隐藏首败或放松断言制造 PASS。环境适配不移动 Task／Slice Base；合同数量或安全义务改变仍交 A。

### 3．核验既有原生准备与逐项独立清单

1. 优先复用现存 N=1004 个受支持的版本 1 STRM、原生索引和已保存主流，N 是实际完整源数且须≥1000。核验唯一稳定名称、物理身份及未被自动合并的源身份，不为满足旧两级流程创建新库或重做全部主流准备。仅在准备前提失效时修复受影响部分并说明原因。夹具只用于隔离测试，不做生产生成器。插件保持只读。
2. 使用所选库与独立范围外库。所选库另加普通视频、旧 STRM、未知协议各一个对照；范围外有受支持 STRM 对照。N 是受支持物理候选数，对照与原生查询所得全部候选数 C 分别记录，不能混用。保持范围／文件静态直到指定增量轮。
3. 新建或必要补修时，从原生完整扫描任务本轮起止和 Completed 确认建库；复用时核验已索引全源身份与当前原生主流，保留准备来源，不以 POST 返回或文件数代替索引成功。关闭插件优化／自动任务时，用最多 2 个固定准备 worker 为每个受支持源取得并持久化必要主流；不得直接写 Jellyfin DB、导入伪造媒体流／NFO 流当成功信号、拷贝指纹或复用一个项目冒充 N 个项目。扫描和准备的原生调用、CPU／内存／媒体请求与耗时单列。
4. 原生 API 分页读回当前物理项目／库关系／MediaSourceId，包含 alternate versions、关闭展示聚合，与磁盘清单逐项双向核对；独立清单覆盖全部 N，不只抽样。每条记录当前 item、source_key、库、文件／URL 摘要、有效 SHA-1／Size、原生已保存地址和必要主流签名。原生返回完整对象只分页保存／处理，证据写 JSONL，可另存排序后的身份集合与摘要。
5. 进入首次信任场景前确认 N 个源均已有正确原生主流、地址且没有插件指纹，记录精确键集合；现存运行后状态不满足无指纹前提，须按上方复用要求先准备可核验的适用状态，不能用未变检查冒充首次信任；配置只选测试库、主动并发固定默认 2，重启使并发生效，再读回配置和 ZIP 身份。此后首次信任前只使用不会触发插件检查的只读 API／SQLite 查询，不能先请求 PlaybackInfo 偷建指纹。

### 4．真实完整轮次与少量增量

在这一个达到门槛的准备库上完成下列轮次；不额外要求另一规模。每轮以原生任务 Key `StrmProbeOptimizerBatchCheck`、本轮 UTC 起止／容器启动身份关联日志，不使用旧完成结果或固定 tail 丢掉完整日志。静态轮次把独立身份清单与本轮候选／结算身份对账，不能仅比较总数。

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
6. 当前库稳定后重启，重启前保存全部当前源的独立完整预期；重启后在任何播放或批量之前只读核对完整指纹集合、地址和主流。再对 16 个增量源显式选 MediaSourceId 取得 PlaybackInfo 并核对返回地址／主流与零额外探测，随后全量只读复核。不可从重启后行自身构造预期，也不靠首次播放补建基线。本流程仅需覆盖当前这一个满足门槛的完整库。

### 6．分层成本与可审查输出

对当前实际库输出一份阶段表，分别列建库／原生主流准备、原生候选查询、去重排序／集合、对象读取／消费、首次／未变／增量／停止／重跑、只读对账和清理；固定资源、样本数／间隔、缺采样区间与实际时间必须可追溯。

- 复用现有 CandidateFetchMilliseconds／AllocatedBytes／PeakBytes、CandidateSetEstimatedBytes／MeasuredCapacityBytes／RetainedBytes 和 BatchReadMilliseconds／AllocatedBytes／Count。说明 fetch 当前包含原生查询＋去重排序，当前线程累计分配可能包含其他同线程分配，进程 managed heap 前后样本不是精确临时峰值或独占归因；retained 的有 GC 前后差也不是集合独占大小。容量字段使用实际槽位数乘大小模型，不是精确堆占用。
- 如现有汇总无法单列原生查询／去重排序，增加最小只读计时／分配观测，复用已有结果与日志，不新建监控服务／接口／表。记录各库原始数量、去重数、集合 Count／Capacity、查询时间／当前线程累计分配，区分查询返回集合与排序保留集合；临时精确峰值无法测得时明确限制，以累计分配和固定间隔进程／cgroup 样本披露，不填估算成实测。
- 在真实运行记录最大请求／返回完整对象批次、活跃消费者／探测和批次数，并结合实际代码及确定性测试证明最多 128 对象一批、8 个消费者、默认 2 个主动探测，不为每个 ID 建 Task。允许每批创建固定 worker，总创建数与活跃峰值分别报告；不声称 Jellyfin 自身缓存完整对象也受 128 限制。
- 每轮完整集合／结算身份可采用现有诊断或只读诊断补充，流式记录，优先每批摘要与必要身份；不能只拿“候选数＝检查数”证明无漏重。观测有开销，记录详细日志状态和证据体积；对各轮次使用同一观测方式，不借关闭关键观测得到假比较。
- 原生准备进度、批量获取期 0%、结算期单调且最高 99%、正常收尾才 100%；检查＝跳过＋需要＋检查阶段未完成，需要＝可靠成功＋探测未完成。候选与不处理／消失／撤销／未读取／读取失败另行对账，候选总数未知时明确未知。停止分别报请求至服务确认、同步查询返回、已开始探测完成和原生 Idle 的延迟，不将内部单字段当用户端总延迟。

### 7．完成最小事实同步与交接

只更新本行为实际结果需要的 `docs/test-matrix.md`、`docs/compatibility.md`、`docs/development-environment.md`、`README.md` 等事实说明，注明资源、阶段成本、代表性媒体和适用限制；不改 Slice、Roadmap、稳定需求或扩大兼容承诺。现有文档仍有 4.1 待审／4.2 旧候选指针，以以上不可变审查快照为准，可在允许的事实文档修正，合同／Roadmap 指针留 A 最终协调。RO-4、单独 Slice Final／Closure Packet 仍未完成。

## 验收条件

- [x] AC-3：单一规模 N≥1000 的真实原生库证据，使用现存全部 N=1004 个受支持物理源；其文件／项目／源／库／主流来源全部可核对；没有直接写原生 DB、伪造媒体流或以模拟 ID 冒充。
- [x] AC-3：首次信任和未变轮次零插件实际探测、静态集合逐身份无漏重、完整五字段／地址／必要主流正确；受控 URL／内容／Size／缺流仅所需源探测且后续复查零探测，范围外及不支持对照不优化。
- [x] AC-4：原生 ID／去重排序 O(N) 成本、原生临时分配、对象读取与活动工作分别记录；128／8／默认 2 上限有实际观测及代码／确定性证据，非全库对象物化或每候选 Task。
- [x] AC-4：真实大库准备和分批阶段停止命中可核验，停止后零新准入；已开始工作有效提交、未开始旧基线保持，旧轮收尾前不能实际再运行；停止终态／进度／统计／延迟真实，重跑收敛并完成资源结算和只读重启核对。
- [x] AC-8 对应部分：最终完整 T4、同 ZIP 安装／扫描／至少 1000 项大库验收均取得真实证据，原始材料、资源与输入身份、失败与恢复／清理完整；无秘密泄露，NOT RUN／BLOCKED 不算 PASS。
- [x] 只含本 Task 的工具／测试、必要诊断、实际阻碍 RO-2 的最小产品修复与事实文档；没有合同、schema、业务规则、取消语义或额外调度／状态架构变更。

## 必要测试

High／T4：真实大库、原生查询／持久化、停止并发及安装候选，需要完整现有回归和适用实机门槛，由 B 在独立验收阶段承担。本次仅同步合同与计划，不声明下列产品测试已运行。

### 开发／修正反馈

Developer 先运行新增工具用例、已知失败和由改动文件直接影响的回归，并列出未运行的其他测试；需要真实反馈时复用现存 1004 项库并核验场景前置状态，不再升级到 3000 级；本次文档同步不启动这些运行。B 负责完整全量回归和独立验收，不通过不得通过降低 1000 数量／隐藏超时／跳过主流准备继续标绿。

```bash
python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v
bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~BatchCheckTests|FullyQualifiedName~ProbeCoordinatorTests|FullyQualifiedName~PlaybackOptimizerTests'
```

现有 Python 用例运行时必须发现非零用例。控制要驱动实际大库编排和证据输出：只有磁盘文件／不足 1000 索引／主流未准备、身份重复加缺失但数量相等、误用当前实际行为预期、缺成本字段、探测数错误、停止阶段未命中／停止后新准入、收尾期间新轮、丢旧日志、超时／OOM／资源不足及清理失败均不能 PASS。成功控制覆盖完整流程。保持已接受确定性同步查询中停止、开始竞争、8 消费者／全局许可／末项故障与不提高权限测试；不要用 1000 份测试假对象替代实机。

### 最终检查点门槛

以下完整命令清单由 B 在独立验收／最终检查点承担；Developer 开发反馈只执行改动文件直接影响的测试并报告省略项。命令从当前检出的仓库根目录、使用 SDK 10.0.401、在干净已提交实现候选上执行；下方 `<source-sha>`／`<run-id>` 须先替换为完整实际 SHA／唯一 ID，不能照抄成 shell 重定向。下表不列旧大库新建／清理命令，以免误删保留库；在现存 1004 项库上完成上文所列全部必要场景的执行方式须先核验并记录，当前 NOT RUN，不因未列命令而取消验收义务。其他入口已存在。所有修改同一实例／配置／鉴权的实机串行；大库运行期间不同时构建或运行其他实机套件。

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/package-all
python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir .git/validation-evidence/<source-sha>/<run-id>/scan-all
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py --scenario suite
python3 scripts/run_isolated_configuration_integration.py --scenario all
python3 scripts/check_governance.py
git diff --check
```

另检查本地 Markdown 文件／锚点和事实协调并保存准确命令。配置浏览器原始输出用现有 `STRM_CONFIG_EVIDENCE_DIR` 指向外置证据。最终 package／scan／large 三类必须消费同一最终 ZIP，部署负载匹配；三个开发部署回归另列。scan all 沿用已有行为覆盖，本 Task 不要求修其 P2；不能以它独自证明最终重启义务，大库独立重启核对按第 5 步执行。单独 Slice Final 仍要核对扫描的变化批量源及多版本 A／B 全部完整状态。

完整套件已覆盖聚焦用例无需机械重复。打包前保留既有发布产物与旁车文件；最后一次可执行输入改变后重新取得完整门槛，不能用开发期 1000 级或旧 4.2 运行拼成新候选最终验证。

### B 独立验证

审查真实 Task Base..Implementation Head、所有必要变化和原始证据。独立复现工具错误放行控制及单一 N≥1000 规模全流程，使用现存全部 1004 项源；独立验证当前原生候选／全源清单、完整行对账、首次／未变零探测、小集合精确探测和真实准备／分批停止与重跑的关键行为。B 负责完整 C#／Python 全量回归、Task 指定全量门槛和独立验收；可复用匹配且可核验的完整建库／准备、昂贵全轮和其他最终门槛，但不能以 Developer 的聚焦结果替代全量门槛。现存 1004 项准备库按上方用户要求在所有需要它的开发阶段持续保留，B 与 Slice Final 不是复用终点，显式人工交接并核验归属，不能让新进程仅凭旧 token 接管。完整证据持续外置落盘，确认后续开发不再需要时才统一清理。缺失或不匹配时重跑对应门槛，不自动重建准备库，不能凭报告标签复用。

B PASS 后重新核对全部 RO／Surfaces：RO-1／安装恢复和 RO-3／扫描仍检查回归及证据有效性；RO-2 达标才 PASS。RO-4 实际代理仍必要，依固定方案规划 4.4；若事实未满足不得进入 Closure Packet 或宣布 Slice 关闭。

### 证据与重跑规则

每个候选／运行索引保留在 `.git/validation-evidence/<完整源码SHA>/<唯一run-id>/` 或稳定 CI，写明仅本机可读。包含完整源码／审查 SHA、准确工作区身份、SDK／锁／镜像／配置／夹具／包／部署摘要、新主机资源限制／运行前预算与宿主样本、准确命令／cwd／退出码／计数／耗时、查询／批次／实际开始保存／五字段／地址主流／进度／终态／延迟原始记录。清单和响应流式、脱敏保存，不留完整 URL、token、Cookie、凭据或私有路径；证据目录在实例之外，归档不得混入状态库或测试资料。

保留首次失败、每次重跑、缺失与不可用；资源／超时／阶段未命中必须如实记录。准备、执行、对账和清理各自结论独立，任何必要阶段未完成不能总 PASS。测试／工具／配置／夹具／依赖或可执行输入改变时相关证据失效，最终候选重走完整 T4；纯报告后继显式比较输入后才复用并重跑文档消费检查。环境预算及调整由实施者留证、B 审查，不移动 ID／Base／Goal 或弱化 AC。旧服务器的忽略目录不随 Git clone 迁移；无法访问历史原始运行时按开发流程重跑拟复用门槛，不将历史目录存在作为启动本 Task 的条件。

## 非目标

RO-4 的实际 JellyfinProxy 联调（后续 4.4）、单独 Slice Final／Closure Packet、A 最终审查或关闭；不重复实现已接受播放／扫描能力，不为已知 P2 扩建扫描工具，不改 Slice／Roadmap／稳定需求。排除生产操作、停止其他服务、系统资源调优、插件推送／上架、生成器／OpenList API、代理改造、远程内容哈希、新 FFmpeg、持久化任务状态／独立调度器／队列、全库对象／Task、schema 或取消／共享／并发语义改变、无关重构与通用性能 SLA。

## 历史报告口径说明

以下 Developer／B 报告保留各次实际 1000／3000 项运行的数量、路径、失败和原审查结论，不回写历史。旧报告中仍要求另跑 3000 级或两级运行的后续数量义务，已由 2026-10-19 至少 1000 项、复用现存全部 1004 项的新合同替代；查询阶段停止等非数量缺口不因此消失。当前 Task 未获得新的 B PASS，尚待新 Contract Checkpoint 后的合法性重核和独立验收。

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

### 2026-10-19 大库脚本聚焦复用调整（非完整验收）

- 用户本轮授权调整大库脚本，不涉及插件实施。保留工作开始前已有的 package_environment／大库工具／测试改动，不自动推送、不改生产或共享开发实例。
- 现有脚本新增 --reuse-workspace，默认 minimum=1000／unchanged，完整使用实际 1004 项；baseline 可显式备份并移走新副本指纹库，验证首次信任→未变→重启前后完整状态。原库仅只读核验／复制，归属 token 不复用；不运行 clean bootstrap、索引扫描或全库主流准备。原库／副本独立 inode；结束恢复触发器、停止双服务并保留副本。
- 初次新入口实机运行 first-smoke 的三阶段均满足，但最终通用对账把正常指纹库／任务执行结果变化判为输入破坏，因此真实退出 1、FAIL；未改写成通过。修正为保护配置／媒体／STRM／库定义，指纹内容逐检查点独立全量对账、任务触发器独立恢复读回，任务执行结果作为预期输出；新增相应负向控制。
- 修正后 second-smoke：run=24725983e7e2，匹配 ZIP sha256=4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d（来源 b2f19c24f05d806ab75f152f36a302582e60ad67，不是本轮重建包）。真实 1004 支持源＋3 库内对照，全部 1007 候选逐身份对账；首次信任 1004／插件探测 0，未变首次信任 0／插件探测 0，均 8 个对象批次、每批≤128；重启前后完整五字段／地址／主流签名保持，重启后对账前无 PlaybackInfo，额外探测 0。
- 实测总计 116.120 秒、57 个资源样本／0 采样错误；Jellyfin cgroup peak=377401344 B、media=19951616 B。两次尝试的原库摘要均不变；修正轮双服务 exit=0、无 OOM，副本保留在 artifacts/package-env/runs/run-20261019-151346-eee3cf46，原库及既有备份未改动。
- 直接影响回归 PASS：大库 Python 52、包 Python 30、扫描 Python 74、治理 Python 26，合计 182；治理脚本和 git diff --check PASS。曾按不存在的 test_package_environment.py 发现 0 例、退出 5，不算 PASS；实际 package 归属用例位于已运行的 test_isolated_package_integration.py。
- 测试输入为 HEAD dba296a06e8f58727f2977318c93c64d39e9badf 加准确工作区 patch；私有证据 .git/validation-evidence/dba296a06e8f58727f2977318c93c64d39e9badf/large-reuse-20261019T145704Z/，包含 before.json／preexisting.patch、两次实机输入 patch／文件摘要、日志／逐源快照、checks.json。原始失败与重跑均保留，不上传数据库／凭据／运行产物。
- 本轮仅 focused_status=PASS、总状态 PARTIAL、退出 0；完整 Task／RO-2 仍 NOT RUN，既有 B FIX REQUIRED 不变。未运行：全量 Python、C# build／test／format、包／扫描／大库全场景、增量及查询／探测停止收尾恢复、显式播放、外部代理与 B 独立验收。旧 fresh 全流程只作为显式兼容入口，不能代替保留库完整验收。

### 2026-10-19 保留库增量与停止恢复补证（非独立验收）

- 本轮只复用已停止的现存 1004 项原生索引／主流，在新归属副本执行；未改 C# 产品或继续扩建通用验收工具。源码为 HEAD dba296a06e8f58727f2977318c93c64d39e9badf 加本轮开始时已有工作区 patch；scripts/package_environment.py、大库脚本及其测试摘要与开始时一致。使用原匹配 ZIP sha256=4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d，未重建包。
- 执行方式：私有证据目录 run_increment.py 调用现有 run_reuse_scenario 生命周期和既有分批停止／收尾／恢复／重启／播放序列；受控媒体／STRM 文件按写入前计划的字节摘要独立对账，不豁免整个目录。默认复用 CLI 仍只支持 baseline／unchanged／restart，本次补证不代表已新增通用 increment 参数。所有操作均在本轮新副本；原库摘要不变、既有备份未修改。
- attempt-1 在前置检查中发现旧 content 对照未各占一个不同批次，退出 1／FAIL、无夹具修改；attempt-2 在启动前因端口仍占用退出 1／FAIL。失败、输入快照和归属副本均保留；改用空闲端口 18100 后 attempt-3 成功，不把前两次改写成 PASS。早期客户端传输语法错误未执行 shell／未产生实机证据，不算测试结果。
- attempt-3 / run=5f96371602a7：原有 1004 项未变轮零探测、零首次信任；新增 4 个缺流项只通过原生扫描建立索引，扫描 Completed，扫描后原有 1004 项完整五字段／地址／主流签名不变且插件探测 0。没有重建库或重做原有全库主流准备。新增项在批量前逐项确认无主流、无指纹。
- 增量前固定独立预期：4 项同 SHA-1／Size 换 URL，4 项同 URL 内容变化，4 项同 URL 无可比 SHA-1 且 Size 改变，另有 4 项新增缺流；后两类复用已有专用路由，以本机真实 B 字节改回 A 字节（不是改原生数据库或伪造指纹）。支持源 1008、原生候选 1011（另 3 个不支持对照），仅预期 16 个 item/source 各探测一次、16 次可靠成功；后续未变轮 0 探测／0 首次信任。完整五字段、原生地址／主流及未变源签名对账通过。
- 分批停止：首批 2 项真正开始延迟探测后停止，最终 Cancelled、进度最高 12.562%（未到 100%），仅读取首个对象批次，实际探测与可靠成功均 2；收尾期间再运行请求返回 204，但日志证明旧轮收尾前仅有一次候选查询执行。恢复前完整对账证明已开始 2 项提交、后批未开始 2 项完整旧基线保持；恢复轮精确探测剩余 2 项并成功。两次恢复后未变复查均 0 探测，间隔及尾部各观察 30 秒。
- 重启后先只读全量核对 1008 源五字段／地址／主流签名，再对 16 个增量源显式选源 PlaybackInfo，均返回正确地址及主流，额外插件探测 0；这是 API 验证，不冒充浏览器真实播放或外部代理联调。
- 实测 349.217 秒，221 个资源样本、0 采样错误；计划重启观测缺口 16.303 秒单列，不假称全过程无缺口。Jellyfin cgroup 采样最大 449146880 B、RSS 采样最大 517992448 B；media 记录 cgroup peak 20832256 B。完整正常轮次均 8 批、对象请求／返回≤128、原始日志探测并发≤2；停止轮 1 批。累计分配／容量模型／采样值仍不是精确独占内存峰值。
- 收尾恢复全部原生任务触发器并读回；双服务退出 0、无 OOM，原库摘要不变，副本配置／库定义及除 36 个已计划文件变动外的媒体／STRM 完整对账 CLEAN。副本保留 artifacts/package-env/runs/run-20261019-153547-1cf17f85，不清理原有 1004 项库。
- 本机私有证据：.git/validation-evidence/dba296a06e8f58727f2977318c93c64d39e9badf/large-increment-20261019T152409Z/，含 before.json／preexisting.patch、三次输入／结果、完整日志／逐源快照、run_increment.py、focused-checkpoint.json 与 checks.json；不上传数据库、鉴权和运行产物。
- 直接影响测试重新执行：大库 52、包 30、扫描 74、治理 26，合计 182 PASS；治理检查与 diff 检查通过。误用 test_check_governance.py 发现 0 例并退出 5，原记录保留不算 PASS；随后使用正确 test_governance.py 26 例通过。
- 总状态 PARTIAL、focused_status=PASS、进程退出 0；不是完整 Task／RO-2 或 B PASS。真实批次分布如实保留：URL 0／2／4／7；content 0／1／1／6；Size 4／5／3／6，不宣称每类都占四个不同批次。查询中停止本轮 NOT RUN，完整 Python／C#／format、最终同 ZIP 包／扫描全场景、代理及独立 B 审查仍 NOT RUN；既有 FIX REQUIRED、Task／Slice Base 和状态不变。下一步只补查询阶段停止及准备独立 B 的可复现已提交检查点，不再新建大库或扩大验收工具。

### 2026-10-19 保留库查询阶段停止补证（非独立验收）

- **范围与输入**：继续只读复制原有全部 1004 项原生索引／主流／指纹到新归属副本，不建库、不扫描、不逐源准备、不修改 C# 或通用工具／测试。输入为 HEAD dba296a06e8f58727f2977318c93c64d39e9badf 加开工前工作区 patch（SHA-256 2231d29dede35692a1f410d46f2608f5173cf78be9ec526d1f73706520bdd4ca），仍用匹配既有 ZIP 4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d，不冒充新最终候选验收。
- **自然查询窗口**：私有 run_query_stop.py 复用现有生命周期与日志 watcher，不人工延迟、扩大 N 或修改原生查询／停止语义。累计最多三次自然尝试，前两次停止确认晚于每库查询返回，保持未命中；第三次严格命中。2026-10-19 UTC 顺序：查询进入 15:54:01.958712 ≤ 停止请求 15:54:01.961006 ≤ HTTP 204 确认 15:54:01.978843 < 每库查询返回 15:54:01.980938。请求到确认 17.837 ms，确认领先返回 2.095 ms；插件摘要另记 stop_query_return_ms=3.5935，不混同两种观测。
- **停止与恢复**：命中轮原生 Cancelled、进度观测全为 0，122.751 ms 内观测到 Idle；对象读取／候选准入／实际探测均 0。收集尚未完成，total_known=false、candidates=0；原生 raw ID 1007 不冒充已固定集合，不弱化正常完整轮计数检查。每次停止后、恢复前及恢复后，完整 1004 行五字段／原生地址／主流签名均与停止前独立预期一致。恢复未变轮完整处理 1007 候选（含 3 个库内对照），8 批／1004 支持项，探测 0。
- **失败保留**：run-1 因 Docker 自动地址池耗尽而启动失败，未执行查询；不清理保留网络或修改 daemon，只为新归属副本网络配置经无重叠核对的显式子网，保留 acceptance 内网隔离。run-2 实际停止后因私有过程误用完整轮摘要断言而 FAIL／exit=1；只修私有过程对不完整收集的判断，正常轮断言不变，累计尝试预算不重置。原始失败、输入版本、副本和日志均保留。事后审计首次误把起始快照的空 expected_native_sources 当作列表，修正为从首次只读原生状态建立基线后比较；原始快照与运行检查不改写，不把审计错误记为产品失败或 PASS。
- **成本与收尾**：成功 run=4227b4ac77e3，99.772 秒／55 资源样本、0 采样错误，最大采样间隔 1.493 秒；Jellyfin cgroup peak 413179904 B、RSS 采样最大 500273152 B，media cgroup peak 17981440 B。采样从启动后 20.768 秒开始，不覆盖全部复制／启动成本，也没有完整前后 30 秒空闲窗，不据此关闭成本门槛。触发器全部恢复并读回，实例对账 CLEAN；双服务退出 0、无 OOM，原库摘要不变。端口 18103 的副本 artifacts/package-env/runs/run-20261019-155237-10355c3e 已停止保留，未操作生产／共享实例。
- **证据与判定**：私有目录 .git/validation-evidence/dba296a06e8f58727f2977318c93c64d39e9badf/query-stop-20261019T154844Z/，含全部输入、失败、网络预检、逐源快照、查询时序、资源与 audited-query-checkpoint.json；成功私有输入 SHA-256 c21eb615e23084839de0f68f9ccfb60e41a8768b1cf513103d0ccfd602956f3b，result SHA-256 8e76a0e4d7689718edb718f374f563409da406ae101f8dc39474d1fe0a6aadae。查询停止聚焦 **PASS**，总结果仍 **PARTIAL／完整 Task 验收 NOT RUN**；补充前段查询缺口，不撤销 B FIX REQUIRED、不移动 Base／状态或签发审查。每类增量跨四个不同实际批次、完整成本窗、固定候选全量门禁及 B 独立复现仍待完成；RO-4／Slice Final 未完成。原始证据／凭据／运行库不上传，不自动推送。

- **本轮反馈检查**：重跑直接相关 Python：大库 52／包环境 30／扫描 74／治理 26，合计 **182/182 PASS**；治理脚本及 git diff --check PASS。一次误用不存在的 test_package_environment.py 得到 0 tests／exit=5，保留为未运行，不计 PASS；随后改用实际 test_isolated_package_integration.py，30 项通过。未运行 C#／format／全量 Python／全套实机及 B 独立门禁，本轮只新增事实文档与私有证据；开工前三个工具／测试文件哈希保持一致。精确命令／UTC／耗时／退出码见上述证据目录的 focused-check-results.json 与 focused-check-package-corrected.json。

### 2026-10-19 四批次增量与资源空闲窗补证（非独立验收）

- **本轮范围**：继续只读复制原有全部 1004 项库到新归属副本，不重建／不截取／不重做全库主流准备；没有修改 C#、通用脚本或测试。运行输入为 HEAD dba296a06e8f58727f2977318c93c64d39e9badf 加开工前 patch（SHA-256 34cea70cec52418e39c1e26776fdc3e0d921aa559c6a382c12cd352191a61c15），ZIP 仍为匹配原库的 4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d，不是最终干净候选的 B 验收。
- **补齐真实 Guid 批次覆盖**：从原生候选独立排序选取 12 个互不重叠的既有源。URL／内容 SHA-1／无可比 SHA-1 的 Size 三类各 4 个，索引新增项后重新验证，每类仍分别位于第 0／2／4／7 批；与本轮实际日志的完整 1011 个候选准入顺序逐身份一致，不靠文件名或总数判定。4 个新增缺流项单独列出，不冒充原有库准备。
- **只修复受影响准备**：为了让同 URL 内容／Size 对照各占四个不同批次，仅给 8 个源建立独立媒体 A 路由和所需初始指纹，8 次准备探测／8 次成功单列；其他 996 源不重做准备。Size 组在变化前确认 SHA-1 为空、Size 为 A 的真实字节数。新增 4 项通过一次原生扫描索引，核对当前扫描起止及 Completed、原有 1004 源完整状态不变且扫描期间插件探测 0；新增项探测前逐项确认缺主流且无指纹。
- **增量与复查**：支持源变 1008／全部候选 1011。4 个 URL 组保留同 SHA-1／Size 换地址；内容组在同 URL 把真实 A 字节换成 B 并更新有效 SHA-1；Size 组同 URL A→B、两侧 SHA-1 均空且真实 Size 改变。独立预期在执行前保存，实测精确 16 个 item/source 各探测一次并可靠成功，其他源保持；两轮未变复查均零探测／零首次信任。正常轮均 8 批、对象请求／返回≤128、原始探测日志并发≤2。8 个固定消费者上限有现有代码／确定性证据，本次未增加直接运行时消费者计数，不能把进程线程数冒充消费者峰值。
- **空闲与资源观测**：两轮未变复查前／间／后各有≥30 秒空闲窗（窗口含末尾只读核验分别 33.905／34.018／33.986 秒），每窗 24／25／24 个服务资源样本、零探测，1008 源完整状态保持。主机从复制前到收尾持续采样 304 次，双服务启动后、健康等待前开始采样 200 次，首次服务样本在运行后 5.302 秒；计划重启观测缺口 16.000 秒明确保留，最后主机样本到结束尾差 0.201 秒。全过程 303.556 秒、0 观测错误，实际限额／磁盘／inode／预算随证据保留。Jellyfin cgroup peak 496115712 B、RSS 样本最大 529313792 B；media cgroup peak 20606976 B。
- **资源解释边界**：三个空闲窗末端 Jellyfin RSS 492093440→496599040→509677568 B，线程均回到 20、进程指标均 22、句柄 564→562→562。短窗内 RSS 仍有增长，现有进程／cgroup 采样无法归因缓存、GC 或其他分配，不能据此承诺无持续泄漏；保留趋势供 B 判断。当前复用、8 源准备、4 项索引、增量与收尾成本已分层观测，历史首次全库建库／主流准备成本没有重建，不能倒填成已覆盖。候选累计分配／容量模型／采样峰值不是精确独占内存。
- **重启与收尾**：重启后任何播放／批量前先核对全部 1008 源完整五字段／原生地址／主流签名，再对 16 个增量源显式选源 PlaybackInfo；全部 HTTP 200、地址／主流正确、额外探测 0，再全量核对。14 份完整状态快照逐项审计。触发器恢复读回、32 个计划媒体／STRM 文件变动逐文件摘要对账，其余保护区 CLEAN；原库全部摘要不变，双服务退出 0／无 OOM。端口 18104 的副本 artifacts/package-env/runs/run-20261019-161238-8665af91 已停止保留，未碰生产／共享实例。
- **证据与后续**：run=8490fe83e4eb；私有目录 .git/validation-evidence/dba296a06e8f58727f2977318c93c64d39e9badf/batch-coverage-20261019T161021Z/，含独立计划、预期／实际、全日志／采样、网络预检和 audited-coverage-checkpoint.json。私有执行输入 SHA-256 973f54212c4828ddaf69adda48a4fbc8e16eed585517916e36f24bdd09bf060a；result SHA-256 a4199200f7b1b9fbbea32c5fa87409344a54c855b64f36f142a1ef0488b25f6b。本次首轮执行与事后审计通过，聚焦 PASS／总结果 PARTIAL；补充先前批次／空闲窗缺口，不将分次 Developer 补证拼成最终全阶段验收。原有查询停止／分批收尾证据另列；完整固定候选全量门禁、B 独立复现／资源判断、RO-4 与 Slice Final 仍待完成。保留既有 FIX REQUIRED／Task Base／状态，不自动推送。

- **本轮检查**：治理、git diff --check、三处新增本地链接／锚点和开工前工具／测试文件哈希核验 PASS。可执行输入未改，不机械重跑上一轮已记录的 182 项；本轮没有新 C#／Python 全量、format、全套实机或独立 B 结果。准确检查与成本表见本轮私有目录的 focused-document-checks.json、COSTS.md 和 INDEX.md。

### 2026-10-20 本地实现候选检查点（非完整验收）

- 本轮将既有工作区中与 Task 4.3 直接相关的 7 个文件做普通本地提交，候选实现 SHA 为 `4cdd174da8c7af988df4962934fc510d206fd838`；未推送、未移动 Task／Slice Base、未修改 C# 产品代码或生产／共享实例。提交内容包括保留库副本复用入口、全部实际 1004 项的下限校验、显式副本指纹重置、资源预算／服务采样／失败收尾、真实 Guid 批次选择及相应测试和事实文档同步。
- 本轮实际反馈：`python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` **52/52 PASS**；`python3 -m unittest discover -s tests -p 'test_isolated_package_integration.py' -v` **30/30 PASS**；三处 Python 文件 `py_compile`、`python3 scripts/check_governance.py` 和 `git diff --check` 均 PASS。测试与治理均针对提交前相同的可执行内容；提交后工作区保持干净。
- 这只是 Developer 本地候选，不是 B 独立审查或 Task PASS。全量 Python／C# build、test、format、完整包／扫描／批量／配置实机、独立新鲜大库门禁、RO-4 代理和 Slice Final 本轮未运行；既有 B `FIX REQUIRED`、复用库及全部失败／聚焦证据均保留。当前候选按流程交为 **READY FOR B REVIEW**；下一步由 B 审查 `Base..4cdd174` 并决定后续独立门禁，不能以本地 82 项聚焦测试替代完整验收。

## B Review Result — 1000 项复用候选 `4cdd174da8c7af988df4962934fc510d206fd838`

```text
Reviewed: a06a80fac90a86085f25116568aa24b54847c562..4cdd174da8c7af988df4962934fc510d206fd838; report-only successor 96891579493c80dc3900909fd1790b67b87451af
Contract Checkpoint: 539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO — the retained-library path is focused-only and does not implement the required increment and stop/drain rounds; the required full 1004-item run is NOT RUN
Next: extend the same Task's reuse path to execute the complete required behavior on a copied, verified 1004-item library without fresh preparation; then Developer reports affected checks and returns the same Task for B review
```

### B Findings

1. **FIX REQUIRED — the implementation cannot run the complete required scenario while reusing the retained 1004-item library.** The new `--reuse-workspace` path accepts only `baseline`, `unchanged`, or `restart`; `--scenario all` is explicitly rejected. `run_reuse_scenario` records `increment`, `query-stage-stop`, `probe-stop-and-drain`, and `explicit-playback` as `NOT RUN`. The separate `--fresh --scenario all` path creates and prepares a new library, so it is not a permitted substitute for the user's all-stage prepared-library reuse requirement. Consequently AC-3/AC-4 and the Task's required full run have no matching evidence on this candidate. Keep the same Task and make the complete increment, query-stop, in-flight stop/drain, recovery, reconciliation, and resource/cost sequence operate on the verified isolated copy; do not truncate the 1004 sources, mutate the original, or silently rebuild/re-prepare the library.
2. B independently ran `python3 -m unittest tests.test_isolated_large_library_integration -v`: 52/52 PASS (1.311 seconds). This includes the query-boundary attempt association and miss handling, overall fail-closed status, reconciliation/cleanup nonzero exit, retained-source integrity, and tests asserting the focused path does not claim full acceptance. These are tool-control results, not real Jellyfin acceptance.
3. The Task plan remains a legal complete RO-2 behavior unit under the committed 1000-item Contract Checkpoint; no Goal, Scope, AC, Base, or Slice contract change is needed. The worktree was clean at review start. `4cdd174..9689157` contains only `TASK.md`, `SLICE.md`, `docs/progress.md`, and `docs/roadmap.md`; no executable, dependency, lock, test, runtime-configuration, or package-input changes. The review ZIP manifest is bound to `9689157` with SHA-256 `a99ee508f37c52a52cc047b6833604a21e848d5d5d496bc053661d56cf8e6399` and matches the code inputs, but does not provide the missing full reuse run.
4. The specified complete C# / Python regression, format, package/scan/plugin/batch/configuration integrations and required real 1004-item full scenario are NOT RUN for this B review. Previously recorded local gates are not being re-described as newly executed. The shared development instance was observed healthy but was not started, stopped, or modified. No full run was started because the current retained-library CLI explicitly rejects the required `all` scenario; no fresh-library path was used to bypass the reuse constraint.

This is a same-Task implementation/acceptance-tool finding, not a contract question for A. Preserve the Task Base and all 1004 sources. After correction, B will review the new Base..Head, independently recheck the fixed controls, run the complete specified candidate gates, and independently verify the full reused-library behavior. RO-4, Slice Final, Closure Packet and A's final review remain outstanding; do not create the next Task until this Task receives B PASS, and do not issue `SLICE READY FOR A REVIEW` now.

## B Review Result — media-service teardown correction after `dcce752`

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

## Developer Completion Report — retained-library full-scenario correction

- Changed Files：`scripts/run_isolated_large_library_integration.py`、`tests/test_isolated_large_library_integration.py`；纯报告更新 `TASK.md`。未改 schema、业务规则、稳定需求、Slice／Roadmap、C# 产品代码、`package_environment.py` 或其它共享工具。
- Implemented（仅修 B FIX REQUIRED：复用入口必须能在已核验 1004 项副本上执行完整行为，保持原 Base／Goal／Scope）：
  - 把 fresh 路径的完整行为序列（首次信任、未变、跨真实 Guid 批次增量、真实同步查询窗口停止、已开始两项探测后停止／收尾、恢复、两轮未变、重启前后完整核对、16 个变更源显式选源 PlaybackInfo）抽成共享 `run_full_behavior(...)`，由 `run_scenario_body`（fresh）和 `run_reuse_full_scenario`（reuse）共同调用，不再保留两套逻辑。
  - 新增 `run_reuse_full_scenario(...)`：只复制并核对已核验 1004 项库，不调用 `prepare_clean_instance`／`build_fixture`／`prepare_native_streams`／`prepare_indexed_fixture`，不重建库、不重新扫描全库、不逐源重新准备已有主流。它读取副本配置与原生候选、逐身份对账，要求副本指纹库已显式清空，然后执行完整行为。
  - 复用 `assign_increment_controls` 从四个真实 Guid 批次各选 3 个源作为 12 个 URL／内容／Size 对照，仅对这 12 个改写 URL 的对照用最多 2 个 worker 做有界原生主流修复（`prepare_reuse_increment_baselines`，插件禁用期间），不触碰其余 996 源；另新增 4 个缺主流项由原生扫描索引。
  - 新增 `_REUSE_EDIT_TRACKER`／`note_owned_edit(...)`：只记录本轮有意改写的 STRM／媒体文件，`reconcile_prepared_inputs` 允许这些已独立哈希的计划内改动，任何未跟踪的副本输入变化仍使整体 FAIL。`reuse + all` 成功时 `full_task_acceptance` 才为 `PASS`，任一必需阶段未满足、失败、资源超限或清理失败仍 `FAIL`／非零退出并保留副本。
  - 删除旧的 `reuse_increment_controls` 选择（保留库现存 12 源不跨四个批次），改为按真实批次重新选择并仅修复受影响准备。
- Tests and Results（fix head `8573dfbffebb785261668f9cd5c895be937e000e`）：
  - `python3 -m unittest discover -s tests -p 'test_isolated_large_library_integration.py' -v` **58/58 PASS**（新增：`reuse + all` 执行完整流程且不重建／不扫描／不清理；`reuse + all` 全流程失败非零且保留；`run_reuse_full_scenario` 核对副本并只修复 12 对照；指纹库非空且未显式重置时拒绝；受控改写仅限已跟踪文件）。
  - `python3 -m unittest discover -s tests` **262/262 PASS**（全量 Python 发现，8.2s）。
  - `bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/…csproj --configuration Release --no-restore --filter '…BatchCheckTests|…ProbeCoordinatorTests|…PlaybackOptimizerTests'` **138/138 PASS**（约 4s；C# 未改，仅受影响回归确认）。
  - `python3 scripts/check_governance.py` PASS；`git diff --check` 干净。
  - 真实复用全场景（Developer 聚焦反馈，非 B 独立验收）：`--reuse-workspace <1004 库> --count 1000 --scenario all --reset-copied-fingerprints` 在匹配 ZIP `b-review-b2f19c2`（SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`）上 **exit 0 / status=PASS / full_task_acceptance=PASS**。首次信任候选 1007／支持 1004／跳过 1004／首次信任 1004／实际探测 0；未变 0 探测；增量候选 1011／支持 1008／实际探测 16／可靠成功 16（4 URL＋4 内容 SHA-1＋4 Size＋4 缺流）；增量后未变 0 探测；查询阶段停止第 1 次自然尝试命中（请求 03:05:30.197729Z ≤ 确认 03:05:30.219517Z）；分批停止在 2 个延迟探测实际开始后命中、终态 Cancelled、进度最高 12.56%、收尾期间重跑未进入；恢复精确 2 探测；两轮未变 0 探测；重启前后完整五字段／地址／主流签名一致，16 变更源显式 PlaybackInfo 返回正确地址且额外探测 0；副本源未变、实例对账 CLEAN、双服务 exit 0 后停止保留。
  - 未运行（明确交 B）：`format`、三个既有默认实机回归、包／扫描全场景、fresh 1000／3000、RO-4 代理、单独 Slice Final。Developer 只运行改动文件直接影响的测试；本会话遵守“测试时间 < 本轮 30%”比例。
- Decisions：B Finding 已按要求修在同一 Task 的工具／测试内；未改合同、取消语义、样本数量或验收含义。保留库现存运行后状态不满足首次信任前提，因此复用全场景要求显式 `--reset-copied-fingerprints` 并把原副本指纹库备份到副本内 `baseline-backup/`，不静默清空、不改动原库。真实复用全场景使用私有包装脚本（显式无重叠子网）绕开本机 Docker 默认地址池耗尽；包装只改写本轮生成的 compose 网络、不改产品／通用工具／保留库／外部容器，属于开发环境适配，不改变候选数量、业务规则或验收含义。
- Remaining In-Slice Work：RO-2 待 B 独立验收（含 fresh 1000 与 3000、真实大库最终候选）；RO-4 后续 4.4；单独 Slice Final、事实协调与 Closure Packet。
- Risks / Deviations：本轮复用全场景为 Developer 聚焦反馈，非 B 独立验收或 Slice Final；它复用既有准备数据，不重跑 fresh 1000／3000，也不替代最终干净候选门禁。3000 级与完整全量回归、独立复现交 B。
- Head SHA：retained-library full-scenario correction `8573dfbffebb785261668f9cd5c895be937e000e`。

可复用经验只提供少量候选供 Slice 收尾，不记录开发流水账，不作为 Task PASS 门槛。

<a id="b-review-20261020"></a>

## B Review Result — 2026-10-20 retained-library full-scenario candidate

> 历史审查：两项 P1 定级和由此要求的实施修正已被文末用途复核替代；独立复现及当轮 NOT RUN 事实保留。

```text
Reviewed Range: a06a80fac90a86085f25116568aa24b54847c562..8573dfbffebb785261668f9cd5c895be937e000e
Report-only Head: 34194161f917bd7b5986759c344bc8432725587b
Contract Checkpoint: 539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: correct SAME Task 4.3; Developer runs affected checks; B retains complete final gates and independent acceptance
```

### 合法性、真实仓库与证据审计

- 开工 `main` 工作区干净，领先 `origin/main` 53 个提交；治理检查 PASS。已阅读 AGENTS、开发流程、V4.3、scope／requirements／product-experience／architecture／roadmap、SLICE／TASK、B 经验及固定交付方案。Task 仍是已提交 ACTIVE Slice 4 内完整 RO-2 行为单元；保留 ID、Task／Slice Base、Goal、Scope、High／T4 和当前至少 1000 项合同，使用全部现存 1004 项，不要求 fresh 1000／3000，不重新规划、不启动 Task 4.4。2026-10-19 的数量合同合法性决定继续有效。
- 审查真实 Base..Implementation Head 的变化、产品诊断／共享测试工具及本次复用编排；`8573dfb..3419416` 只有 TASK 和三份事实文档，没有可执行代码、测试、锁、依赖或包输入变化。Developer run-5 的工作区 patch SHA-256 `a28acebf1dc015848f497dbf9141dc9cb2af09e2a4fffcaa8b3223d221ea87a7` 与 `git diff 1ea6ec5..8573dfb --binary` 完全一致。ZIP 实际 SHA-256 为 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`；产品／打包输入自该包来源检查点未变，但工具已变，旧最终门禁不能整体继承。
- 阅读 `.git/validation-evidence/DEV-reuse-all/run-5/` 的 INDEX、result、events、逐源快照及原始日志，核验私有网络包装只适配本轮 Compose 子网。原始观察确有首次 1004／零探测、增量 16、恢复 2、后续未变零探测；10 个状态快照中首次信任前为 1004 预期／0 指纹，其余对应阶段完整行对账相等，重启前后有全量状态。保留这些实际观察，不撤销为插件失败，也不把 runner PASS 直接认定 B PASS。下述准备方式违反当前要求，因此该运行不作为完整 RO-2 门禁复用。原始失败、成功观察、源库及副本持续保留。

### 当前阻塞项（仅本 Task）

1. **P1 BR-43-R1 — 复用准备仍执行全库扫描，并错误记录成仅 12 项重索引。** `run_reuse_full_scenario` 在首次信任前的 `scripts/run_isolated_large_library_integration.py:1958–1963` 调用 `scan.run_native_scan_completed`；该 helper 实际启动 `RefreshLibrary` 原生计划任务，没有项目／12 项过滤，不是局部准备修复。run-5 原始事件也证明 Scan Media Library 于 `2026-10-20T03:01:48.793595Z–03:02:14.075753Z` 完成，而 `scope` 却写成 `reindex only the 12 rewritten control STRMs`。这违背当前 Developer 修正指导中“不重新扫描全库”的准备库复用约束。后续为新增 4 个缺流源取得真实索引的指定行为扫描另计，不与这个首次信任前准备扫描混淆。**修正**：去掉准备阶段全库扫描；如重写 12 个对照确需原生更新，只修这 12 项的受影响准备，使用项目级原生路径或避免不必要重索引，并核对其余 992 项原生身份／地址／主流未受准备修复影响。不要为绕过断言调用别名／另一个全库 helper；更新 scope／报告与真实调用相符。新增回归应穿过 `run_reuse_full_scenario` 至真实 helper／请求边界，断言首次信任前不会启动 `RefreshLibrary` 或 `/Library/Refresh`；现有外层编排 mock 把整个内层替换，因此测试名称中的“不扫描”并未覆盖这个调用。
2. **P1 BR-43-R2 — 收尾失败后结果仍保留完整验收 PASS。** `run_reuse_scenario:2077` 在 finally 前设置 `full_task_acceptance=PASS`；`2128–2129` 遇到触发器恢复、原库完整性、副本对账或服务停止失败只改 `status/focused_status`，未撤销该字段。B 独立注入四种失败全部复现：命令退出 1、整体 FAIL，但 `full_task_acceptance=PASS` 且 `not_run` 仅剩 independent-B-review。这是相互矛盾的完整验收结果，违反本 Task“任一必要收尾失败不得标完整 PASS”的要求；**不是**声称旧的命令退出 0 缺陷复发。**修正**：完整验收状态在全部必要收尾完成后统一派生；all 场景任一执行或收尾失败均必须非 PASS，保留原诊断及副本。扩展 all 场景负向控制覆盖触发器恢复、原库完整性、副本对账、日志、sampler 和服务退出失败，检查返回码、整体状态、完整验收状态及证据 finish 输出一致；focused 场景继续 PARTIAL，不能误升级。

### 本轮实际验证与后续门禁分工

- B 独立离线复现脚本 `reproduce_controls.py` 穿过真实复用 finally 并在原生扫描 HTTP 边界拦截：4 个收尾状态矛盾及 1 个全库扫描调用均 **BUG REPRODUCED**（0.367s 命令 wall），零真实 API／容器操作；不是产品验收 PASS。
- B 运行 `python3 -m unittest discover -s tests -v`：**262/262 PASS**，退出 0，8.798s 命令 wall／8.440s unittest；已包含大库 58 项控制，不重复再跑相同聚焦套件。它未覆盖上述两个缺陷，不能替代独立复现。开工治理 PASS；本报告提交前另核对治理、Markdown 链接／锚点、差异和隐私。
- **本轮 NOT RUN**：C# locked restore／Release build／全量 test／format、重新打包、package-all／scan-all、plugin／batch-suite／configuration-all、B 独立 1004 项复用全流程、代理联调及 Slice Final。因已明确当前 P1 阻塞，按开发流程先拒绝，不启动昂贵实机门禁、不把旧结果标成本候选新 PASS。未启动／停止／接管现有容器，未清理源库、基线或副本。
- **Developer 修正反馈**：只改同 Task 的大库工具／直接相关测试及必要事实报告；运行新增失败控制和受影响大库套件，若确实改共享 helper 再运行其直接影响回归，准确列出其余 NOT RUN。无需交还其完整 C#／Python、所有实机或 Final；不改插件、合同、取消语义或新增通用框架。
- **B 最终门禁**：新实现 Head 到达后重新审查 Base..Head，独立复现两项修正与 fail-closed 控制；承担本 Task“最终检查点门槛”的完整 restore／build／C# test／format／Python／packaging／package-all／scan-all／三个既有实机回归／治理／差异／Markdown，以及使用全部现存 1004 项的独立完整复用流程。package／scan／large 消费同一固定最终 ZIP，串行操作实例；仅在输入和原始产物匹配并明确记录时复用，缺失／不匹配重跑对应门槛。不得用 Developer 聚焦结果替代，不再运行历史已取消的 fresh 1000／3000。预算继续遵守本轮测试耗时严格小于总耗时 50%，不靠空等扩大分母；有阻塞可先拒绝，未完成门禁不得 PASS。
- 本机私有证据：`.git/validation-evidence/34194161f917bd7b5986759c344bc8432725587b/b-review-20261020T033820Z/`，包含输入文件摘要、独立复现源码／原始日志、262 项完整日志、精确命令／UTC／退出码／耗时及原 run-5 审计／文件摘要；不上传原始证据、数据库或凭据。早期 shell／传输语法错误未执行预定命令，已纠正，不算测试或验收结果。

RO-2 仍未取得 B PASS；RO-4 未完成，RO-1／RO-3 保留已提交历史决定，待最终候选门禁核对。全部 RO 未满足，不造新 Task，不提交 Closure Packet 或 `SLICE READY FOR A REVIEW`，不自行关闭 Slice。若去除准备全库扫描确需改变现有合同义务，先交 A；本轮发现本身属于同 Task 工具修正，不改变范围。

<a id="b-purpose-reassessment-20261020"></a>

## B 用途复核与审查定级更正 — 2026-10-20

- **目的先行**：产品交付的是版本化 STRM 的按需原生探测与正确地址／媒体流持久化，不是取消 Jellyfin 原生扫描。`run_isolated_large_library_integration.py` 是 RO-2 的隔离验收工具：复用 1004 项已准备库，验证首次信任／未变零插件探测、少量变化精确探测、停止／收尾／恢复、重启与播放正确性及成本；它不是另一套产品或长期库管理框架。
- **BR-43-R1 撤销 P1，保留 P2 表述问题**：真实 helper 确实执行一次全库原生索引扫描，scope／docstring／完成报告却称仅 12 项或不扫描，这些描述不准确。但原生索引扫描不等于重建库、全库重新准备主流或全库插件重探测。源码只为 12 个受控变更源修复主流；run-5 证明首次信任 1004 项零插件探测、后续 16 项增量，原库未变、收尾完整。此前 B 把自身过严的不扫描指导升级为用户业务约束，不能据此否定该运行。现修订这项执行指导，不改数量、隔离、业务不变量或 RO 验收含义；不要求项目级扫描替代实现或新增扫描拦截框架。
- **BR-43-R2 降为 P2 结果字段一致性问题**：离线复现属实，收尾失败后 `full_task_acceptance` 可残留 PASS；但退出码为 1，整体及证据最终状态均 FAIL，现有代码／CI 未发现仅消费此字段放行的路径。它不是已观察到的失败验收被放行，也不是插件正确性失败。任何收尾失败仍不得接受为 PASS，B 必须同时核验退出码、整体终态与原始收尾证据，不能单读该字段；字段一致性宜最小修正，不以此要求新增一轮工具工程或先退回 Developer。若发现真实消费路径忽略整体失败，重新按影响定级。
- **证据恢复复用资格**：撤回前次仅因准备扫描而排除 run-5 的决定。先前核验的实际 patch 与 `8573dfbffebb785261668f9cd5c895be937e000e` 一致、固定 ZIP 摘要一致及原始行为／状态对账仍有效；该全场景运行可作为匹配门槛的候选证据，不因来源是 Developer 或角色变化机械重跑。262 项 B 全量 Python 及独立失败控制保持原事实，不将历史部分结果拼写成全部最终门槛通过。
- **当前交接**：同一 Task 4.3 回到 READY FOR B REVIEW，两项不再作为 P0／P1 实施阻塞，不新增 Task，不修改产品／验收工具源码。当前不签发 PASS；完整 T4 和独立关键验收中尚未满足的部分仍由 B 负责，先核对匹配证据，只补缺失／不匹配门槛，不把全量交回 Developer。RO-4 及 Slice Final 仍未完成，不能提交 Closure Packet 或宣称 SLICE READY FOR A REVIEW。
- **本轮检查**：开工工作区干净、治理 PASS；只复核文档、真实调用、结果消费者及既有原始证据，未运行产品／实机测试、未操作容器、未改保留库。提交前只做治理、TASK 本地链接／锚点与差异检查；测试／检查用时以实际命令计，不通过空等扩大本轮时间。

<a id="b-functional-review-20261020"></a>

## B 从原定功能出发的重新审核 — 2026-10-20

### 审查基准与结果边界

- 审查真实 Task Base a06a80fac90a86085f25116568aa24b54847c562 到实现 8573dfbffebb785261668f9cd5c895be937e000e，并核对纯报告后继 59d219e46aa95df1a995ed090a79873df7ee2cbc。ID、Base、Contract Checkpoint、High／T4 不变；开始时 main 干净，治理 PASS，无用户改动。
- 以 V4.3、稳定需求、用户旅程及 RO-2 的实际结果为准：已有流不全库重探测、变化才探测并保存正确、固定候选分批有界、停止只阻止未开始工作、旧轮收尾后再运行、重启与播放正确。脚本只是隔离验收入口，不是另一个库管理产品；不为框架、措辞或非阻塞可选证明追加工具开发。
- 前节撤回的两项 P1 维持非阻塞 P2：必要的原生夹具索引扫描不等于重建库／全库重新准备主流／全库插件重探测；收尾失败时嵌套成功字段不一致，但顶层 FAIL、非零退出及最终索引拒绝放行。未发现消费者仅凭该字段错误发布，不据此要求新的实施候选。

### 已独立核实的功能

- **匹配证据复用**：run-5 的 dirty 源码补丁 SHA-256 与其源码到当前实现的完整 binary diff 一致；前次 B 全量 Python 的全部登记输入与当前逐文件一致；固定 ZIP 摘要及全部 buildInputsSha256 一致。故复用匹配结果，不因角色来源或报告后继机械重跑整轮，不把历史门槛数量／PASS 改写为新证明。
- **首次信任／未变**：独立审计 run-5 全部 10 个状态快照、7 个正常轮次及原始日志。起始 1004 个支持源、1007 个候选（另含 3 个库内对照）；信任前指纹为空，首次信任恰 1004、探测 0，未变 0。候选无漏重，范围外源未混入；正常轮次全部 8 批、单批不超 128。
- **增量**：真实 Guid 批次 0／2／4／7 的 URL、内容 SHA-1、无可比 SHA-1 的 Size 各 4 项，加 4 个新增缺主流项；独立比较前后完整行，恰 12 个已有源改变、4 个新增、992 个已有源不变。原始开始／成功提交均 16，身份精确匹配，并发最高 2；随后未变 0。
- **停止／收尾／恢复**：原生日志显示查询开始 03:05:30.196217Z、停止请求 .197729Z、确认 .219517Z、返回 .220415Z；确在同步查询内停止，之后无对象读取、进度 0、结果 Cancelled。探测停止轮只启动两项并正常提交，另两项旧基线完整保留，取消进度最高 12.56181998%，收尾期间重跑未进入第二次执行；恢复只探测剩余两项，随后两轮未变 0。原始日志全流程 20 次开始／20 次提交（16＋2＋2），不是只看汇总标签。
- **重启／播放／资源**：全部 1008 源的五字段、原生地址与主流签名在重启前、重启后任何播放前、16 项显式选源 PlaybackInfo 后一致；选源地址正确、额外探测 0。资源 290 个样本、3 段明确的重启采样间隙、3 个 30 秒空闲窗，cgroup 当前值最高 469012480 bytes、峰值 483213312 bytes；仅说明本次观测，无通用 SLA 或长期无泄漏承诺。原库未变、副本 CLEAN、两服务 exit 0／无 OOM，库持续保留。
- **B 新实机复现**：新归属副本、同一 ZIP 独立运行 baseline，115.979 秒、exit 0；1007 候选／1004 支持源，首次信任 1004、首次与未变探测均 0、8 批。1004 源重启后任何播放前全部指纹／地址／主流一致；原库不变、触发器恢复、两服务 exit 0，副本停止保留。聚焦总状态准确保持 PARTIAL，不冒充完整 Task PASS。

### 门禁与证据

- 新跑 locked restore、Release build、完整 C# 202／202（skip 0）、format verify 均 PASS，保守累计 60.289 秒；完整 Python 262／262 最初按逐文件输入核验复用前次 B 原始运行，更新 TASK 后因治理测试消费文档，另实际重跑完整 Python 262／262 PASS（9.225 秒命令 wall），不是只沿用旧文档检查。打包复用 B 原构建及当前 ZIP／构建输入核验，保留原 SourceRevisionId，不以报告 SHA 重打不同字节后混用。
- 本机私有证据：.git/validation-evidence/59d219e46aa95df1a995ed090a79873df7ee2cbc/b-functional-review-20261020T042904Z/，含输入身份、实际命令／退出／耗时、本地门禁日志、独立实机证据、functional-audit.json 与 raw-log-audit.json。复用 run-5 及前次 B Python／打包目录均保留；不宣称远程可读。
- **B package-all 新跑 PASS**：377.672 秒、exit 0，同一固定 ZIP、已接受 Slice 3 基线；归档破坏控制均拒绝且合法安装不受损，干净安装 Active、五项配置页／默认无触发任务、MP4 与 MKV 原生 Web 播放均实际推进；同 SHA-1／Size 换 URL 后原生探测／提交且重启零重探测。升级保留配置／指纹、未变零探测、待处理变化提交、真实备份恢复、禁用／移除原生播放及重装恢复通过。仅新建本轮包实例；全部输入恢复 CLEAN、双服务 exit 0／无 OOM，临时包工作区按自身生命周期清理，不涉及保留大库。浏览器记录含原生 WebSocket 403／非致命 HLS 控制台告警，实际视频推进和媒体请求 200 已独立核对，不能说控制台零错误。

### B 最终决定：FIX REQUIRED（仅剩 B 门禁补齐）

- **功能审查结论**：在本 Task 的固定组合和受控大库范围内，RO-2 的首次信任、未变、精确增量、停止／收尾／恢复、重启与地址／主流持久化已有充分匹配实机证据，独立关键复现通过；真实 Base..Head 未发现新的产品 P0／P1。两项 P2 不升级，不要求先修工具文案或再扩建验收框架。
- **BR-43-G1，必要证据缺口**：scan-all、开发部署 plugin、batch suite、configuration all 四项指定最终候选实机门禁仍 NOT RUN／无匹配最终证据；这不是四项已观测产品失败，也不是环境不健康。保留完整 T4，不凭既往 Task 决定、单元测试或当前大库 PASS 代替。因尚未满足完整最终计划，Task 不能签 PASS。
- **继续方式**：B 对冻结的同一实现 8573dfbffebb785261668f9cd5c895be937e000e／ZIP 4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d 补齐上述门禁，先核对可复用输入和原始结果，再仅跑缺失项；三个开发部署回归须先核验明确隔离归属与前后恢复，按真实入口串行。不把全量交回 Developer，不要求新实现提交、不新建 Task、不移动 Base；若实测发现真实阻塞，才在同 Task 定向修正及验证受影响输入。
- RO-1／RO-3 历史接受决定保持，RO-2 功能证据不再被无关脚本要求否定；但 Task 最终门禁尚未齐备。RO-4 实际代理仍未完成，不提前激活 4.4，不进入 Slice Final／Closure Packet，不宣称 SLICE READY FOR A REVIEW 或自行关闭。
- 本轮未改插件／验收工具源码，未操作生产或共享开发服务；唯一受版控修改为本 Task 审查与验收勾选。测试耗时严格小于总耗时 50%；含 restore／build／format、独立实机、package-all 与审核检查按保守口径计，精确账目见本机 timing.json。历史证据复用不算本轮重新运行，不通过空等扩大分母；本轮不再启动另一长实机门禁以挤占预算。

<a id="b-remaining-gates-20261020"></a>

## B 剩余门禁续审 — 2026-10-20

### 基准、隔离与复用

- 用户要求 B 继续剩余工作；本轮只补 BR-43-G1，不修改插件／验收工具源码，不移动实现 Head、Base 或合同。开始时 main 干净；治理 PASS。审查对象仍为实现 8573dfbffebb785261668f9cd5c895be937e000e，纯文档起点 1530ba5deb9dddb8867e0f37940227a84c8e2dfe。
- 已逐文件核对前次 B 登记的 65 个可执行／测试／锁输入均未改变，固定 ZIP SHA-256 仍为 4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d。沿用匹配的完整 C# 202/202、打包、package-all、大库全场景及 B 关键独立复现，不把它们写成本轮重跑；消费本次文档的检查单列。
- scan-all 使用本轮新归属包实例／18106。开发回归使用新检出副本（94 个跟踪文件一致）及逐字节一致的 Release 输出（45 文件），新派生 Compose project jf-strm-probe-5a73189c02／18107；不接管共享 18096、生产 8096 或 1004 项保留库。私有适配只选择无重叠子网、设置新隔离端口／环境入口，不改场景顺序或断言；开发部署不是 ZIP 安装证明。

### 本轮实测与首次失败

- **scan-all PASS**：05:06:29Z 开始，816.477 秒、exit 0，同一固定 ZIP；独立核对 54 个证据文件摘要及 1404 个事件。完整原生扫描 05:10:06.636640～05:10:13.259762Z 同时落在播放、批量两次实际探测 05:10:06.20～05:10:26.20Z 内；三项扰动发生于重叠窗口，A 基线拒绝 B 竞态后接受 C。136 源对账、后续增项／移入发现、实际 Guid 后批删除／移出、多版本独立刷新、原生定时、共享与停止后收尾／重跑、单项失败隔离和 SQLite 修复恢复通过。触发器恢复、输入对账 CLEAN、双服务 exit 0／无 OOM；扫描工具未覆盖的完整重启集合不冒称补齐，由已匹配的大库完整证据另行承担。
- **开发部署 plugin FAIL**：成功准备后于 05:24:18.532055Z 运行原始入口，186.565 秒、exit 1。前序首次信任、重启、变化／失败恢复等断言已执行，但在 ordinary_media_delegation_check 查找唯一 fixture 时中断；不能将局部成功汇总当完整 PASS。隔离原生库的 /media/local/fixture.mp4 项目名实际是 Substitute Fixture，夹具前提不匹配，不是已观察的插件普通媒体截获。失败日志及原始服务日志已保留。
- **定向环境修复，不冒充重跑**：仅以原生 metadata API 将这一个本轮测试项目 Name 设为 fixture 并锁定 Name，Path 和 MediaStreams 不变；普通媒体聚焦检查 HTTP 200、视频流可用、本地路径且零插件事件。完整 plugin 入口尚未重跑；未改被测脚本／断言、原生数据库行或 1004 项准备库。首次收尾立即断言遇到尚未结束的扫描，后续独立核对全部任务 Idle、全部触发器及主 STRM 恢复一致，不能追改首次收尾为 PASS。
- **准备失败亦保留**：第一次启动健康检查先于 API 可用，503；第二次重试错误覆写私有测试密码，401。各次均只停止自有双服务且 exit 0；随后只修正私有准备脚本及本轮新空配置，API 就绪检查后准备成功（53.121 秒）。这些不计产品通过，不扩大超时或削减断言。
- **batch suite／configuration all NOT RUN**：串行驱动在 plugin 非零后按原定 fail-closed 停止，不能写成产品 FAIL 或 PASS。

### B 决定与后续边界

- **Decision: FIX REQUIRED**。BR-43-G1 从四项缺口缩为三个：完整 plugin 重跑、batch suite、configuration all；scan-all 缺口已关闭。未发现新的产品 P0／P1，旧两项 P2 仍非阻塞，不要求另造实施候选或框架；B 继续承担剩余完整门禁，不交回 Developer。
- **时间预算不合规**：本轮从 05:06:29Z 起的长实机与准备／检查累计已超过总耗时的 50%，不沿用前轮合规结论、不靠空等扩大分母。发现后停止新增长门禁，仅完成必要隔离收尾、事实记录和短文档检查；精确账目及计量限制见本机 timing.json。此为本轮执行偏差，不降低 T4、不把缺失门禁改为可选，后续以明确预算继续。
- RO-1／RO-3 的历史接受及 RO-2 已核验功能证据保持；RO-4 实际代理与单独 Slice Final 仍缺。不激活 Task 4.4、不关闭 Slice、不宣称完整 Task PASS；未推送 GitHub。
- 私有证据：.git/validation-evidence/1530ba5deb9dddb8867e0f37940227a84c8e2dfe/b-remaining-gates-20261020T050629Z，仅本机可读。含失败／重试、原始日志、独立扫描审计、源码／负载身份及隔离收尾；凭据、原始运行库与证据不入提交，1004 项库／基线持续保留。

- **最终短检查及安全收尾**：完整 Python 262/262 PASS（9.325 秒命令 wall），治理／diff／本 Task 7 个本地 Markdown 链接与锚点通过；私有检查器首次传输转义错误已纠正，不计产品失败。独立复核全部触发器一致、所有原生任务 Idle、核心配置默认值、主 STRM 及媒体恢复、临时库条目已清、主播放地址／视频流正确且额外探测 0；自有两服务停止 exit 0／无 OOM，9 个既有运行容器身份／启动时间／镜像不变。原始 1004 项主准备库 1170 个文件哈希与既存备份清单逐项一致（整个工作区物理 STRM 1007，strm 子目录 1006，另有范围外对照），全部保留库及基线未启动、重建或清理。


<a id="b-final-gates-20261020"></a>

## B 最后三项门禁续审 — 2026-10-20

用户明确要求 B 继续，撤销本轮先前的测试时间占比约束；历史超预算事实保留，不再以该约束停止剩余门禁。本轮先核对冻结输入与已停止专属实例归属，复用前次定向修复后的开发夹具，串行执行完整 plugin、batch suite、configuration all；不更改插件／验收工具断言，不接管生产、共享实例或重建 1004 项库。结果待实测补齐，Task 暂保持 FIX REQUIRED。


### 首次完整重跑与继续验收

- 完整 plugin 于 05:44:31.532915Z 开始，206.246 秒、exit 1；普通媒体夹具前提已通过，但在原生多版本合并后的首次 PlaybackInfo 断言中断。原始服务器日志记录 visible media source set changed／playback must retry，暂不将其归因为产品或夹具，保留失败，后续增加只读观测核实。其余前序局部结果不能冒充完整 PASS。
- finally 独立核对配置、全部触发器、库／条目、三份媒体／STRM、全部任务 Idle、主播放正确且零额外探测；自有双服务 exit 0／无 OOM。外部容器挂载摘要的初次比较误把 Docker 返回列表顺序当作身份；逐排列对照原摘要证明 9 个既有容器挂载内容未变，且启动时间／镜像／运行状态一致。原始 FAIL 不覆写，补充 order-independent 复核材料。
- 下一独立尝试先串行运行 batch suite、configuration all，再完整 plugin；只调整不同完整入口的执行次序以取得其他门禁结果，各入口内部场景顺序及断言不变，原始失败完整保留。时间占比不再是停止依据。

- batch suite 于 05:52:25.958942Z 开始，121.230 秒、exit 1：discovery／原生定时／未变与重启分支完成；stop 场景确认两项已开始探测在停止后有效提交，一项撤销，原生终态 Cancelled；但场景要求的定时／手动排队下一轮没有进入，断言失败。不能用局部停止成功或历史包／大库结果替代完整 suite。随后独立恢复检查通过，自有服务 exit 0／无 OOM，9 个外部容器未变。
- configuration all 改为独立串行尝试，避免前一入口失败令尚未执行门禁无限延期；完整入口内部不变。后续继续核实失败原因，不改原始失败状态。


### B 场景准备同步说明

- configuration all：05:56:02.397053Z 开始，277.062 秒、exit 0；完整浏览器／API 场景、finally 与独立边界恢复通过，双服务 exit 0／无 OOM，9 个外部容器未变。详细原始截图／响应保留，尚待最终独立审计；本结果不是完整 Task PASS。
- 两处失败均发生在夹具索引尚在运行时：plugin 合并前只等待项目可见；batch 定时于停止收尾期间触发后，另一个 Scan Media Library 于 05:53:52.812Z 完成，而停止轮直到 05:54:00.283Z 才 Cancelled。固定原生 TaskManager.ExecuteQueuedTasks 在任意任务完成时取出队列，仅执行当时 Idle 项；忙项不会重新入队，故不能假定触发请求必定保留到停止轮之后。先不修改插件或降低“收尾后可运行”义务。
- B 为诊断和准备明确增加两处等待：只在 multiversion_and_sqlite_failure_check 和 scenario_stop 的 wait_for_named_library_item 返回前，等待该准备扫描 Idle 且本次结果 Completed，预声明上限 120 秒；其余场景、故意并发扫描、断言、探测／停止／恢复不变。私有适配记录 scan 完整起止结果及双源 PlaybackInfo 摘要；原始脚本逐字节不变。该运行会如实注明适配，不冒称未经适配原命令通过；若仍失败则按观察继续分类，不重试至碰巧绿灯。

- 配置独立审计核对 19 份浏览器 driver result 均 exit 0、13 个 summary 场景、133 个原始文件及 57 张截图，真实范围／启停／批量旅程和恢复通过。浏览器并非零错误：原生 dashboard/plugins 路由保留 2 次 CancelledError、28 次 scrollHandler 异常及插件商店包查询 404；失败注入场景另有预期配置 400／500。插件页面加载、保存、重读和任务断言均完成，原始栈未删，按观察记为原生 Web 非阻塞诊断，不夸称全站零错误。独立审计首次自加“pageErrors 必须为空”检查失败已保留，不将此额外条件变为新产品门槛。

- 准备同步后的完整 plugin 于 06:01:40.849270Z 开始，489.345 秒、exit 1：多版本独立选源、URL／缺 SHA-1、SQLite 故障／修复重启、禁用／重启及全局并发 1／2 分支均完成；最后在 independent_native_refresh_check 的原有 elapsed < 2.5 秒断言失败，实际 3.12 秒。原始失败保留，不降低阈值、不将局部结果写成完整 PASS；最后的 core_configuration_api 尚未运行。独立 finally 恢复、双服务 exit 0／无 OOM、9 个外部容器不变均通过。继续核对这次原生刷新实际路径与媒体请求时序，区分原生刷新耗时和插件许可阻塞。

- 准备同步后的 batch suite 于 06:10:46.479832Z 开始，477.962 秒、exit 1：七个场景（discovery、scope、stop、sharing、shared-stop、mixed、failure）均返回，但最终清理仍有一项 Batch Mixed Playback 的原生索引残留，整体 FAIL；停止场景本次已确认定时触发在收尾后启动，已提交源不重复探测、撤销源恢复。三份物理输入及配置／触发器恢复一致，但独立完整项目清单检查也拒绝这一个残留，不能沿用脚本 state_restoration 标签放行。自有双服务 exit 0／无 OOM、9 个外部容器未变；下一步仅在本轮专属实例等待准备工作结束，再通过原生扫描修复残留并复核，不动保留大库。

- 原生索引残留已在同一专属实例以一次完整原生扫描移除，独立对账恢复为原始五项及三份文件；原 batch FAIL 不改写。未改断言的独立刷新诊断预先固定为三次，耗时 2.99／2.92／2.60 秒，三次均未满足原有 2.5 秒断言；新增请求／ETag 时间观测及原始探测起止材料，结果不是完整 plugin PASS。另运行最后尚缺的 core_configuration_api 分支，完成后按真实结果记录；继续使用无饱和探测的原生刷新对照辨别测试环境延迟，不凭源码猜测或盲目扩超时。

### 原生冷启动与清理的定向准备修正

- 五次无插件饱和探测的原生 FullRefresh 对照耗时分别为 3435／1132／763／748／741 ms；冷启动首次也超过 2.5 秒，不能把该阈值失败直接解释为插件许可阻塞。该对照原生配置、CPU 2／1536 MiB 及代码不变，完整恢复通过。三次饱和诊断全部失败的原始结论继续保留；core_configuration_api 已独立完成五个非法输入拒绝、详细日志／启停下一请求、配置重启持久化和恢复，不能拼成完整 plugin PASS。
- 下次完整 plugin 在独立刷新场景建立饱和探测之前，以原生 FullRefresh＋ETag 先完成一次冷路径准备，原 2.5 秒断言、3 秒慢媒体、并发 1、场景和其他断言均不改。额外原生刷新在饱和窗口前记录，不能充当并发通过证据；不提高资源或超时、不自动重试 PlaybackInfo。
- batch 的 mixed 场景在返回前发起异步原生 FullRefresh，finally 紧接着删夹具；原生工作随后读取已删除文件，与清理扫描交错。下次仅在该原生刷新返回后、删除前等待同一项目 ETag 变化，保留混合并发、原生刷新接受及所有清理断言。两项均为私有隔离准备适配、原始工具文件不变，独立报告准确命令／补充等待；若仍失败，保留失败，不宣称未经适配原命令 PASS。

- 私有适配的实现记录：plugin-warmed 启动后发现新增外层包装掩盖旧准备等待的直接调用者；修正时进程已加载文件，故不把磁盘修正当已执行，已恢复并保存进程启动时的准确源文件／摘要。该次仍有效包含预饱和原生预热，但不宣称多版本准备扫描等待生效；原始完整入口、断言和结果按实际记录。尚未启动的 batch-settled 已在执行前修正调用者转发，不更改业务或断言。

- plugin-warmed 的实际完整运行于 06:26:26.473774Z 开始，207.962 秒、exit 1，再次在未同步的多版本合并后首次 PlaybackInfo 中断；预饱和原生预热尚未到达，不能说预热已验证独立刷新。finally／独立恢复及外部实例边界通过。修正调用者转发后的准确私有适配在下一次启动前冻结，完整 plugin 将只在当前串行 batch 收尾与归属复核后执行，既有全部失败保留。

- batch-settled 完整适配套件于 06:30:23.000166Z 开始，417.110 秒、exit 0；七场景全部通过。B 另核对原始日志本轮时窗、原生停止后两项提交／一项撤销、收尾期间零新轮、定时收尾后仅一轮、双方向共享／停止共享、130 项分两批、混合并发峰值 2 与状态库故障恢复。mixed 异步原生刷新在删夹具前 699 ms 完成并观测到 ETag 变化；独立 finally 核对五项原生项目、三份输入、配置／全部触发器与运行前完全一致，双服务 exit 0／无 OOM、9 个外部容器未变。该结果明确属于私有准备同步适配，不声称未经适配的原始命令通过；既往两次 batch FAIL 保留。播放完整套件在其安全收尾后串行启动，尚未据此判定整个 Task PASS。

- plugin-prepared 完整适配套件于 06:37:49.028743Z 开始，519.730 秒、exit 0；所有原始 main 分支及最后 core_configuration_api 均完成。独立原生 FullRefresh 为 **851 ms**，保留原 <2.5 秒断言；饱和前两次原生预热分别 2202／3087 ms（第二次在并发配置重启后），均不计通过窗口。原始日志核对 pool=1、探测 06:45:29.266 实际开始、唯一慢请求 29.311→32.311 的 3 秒延迟及 33.020 成功提交；正式函数仍在唯一慢请求开始后测量独立刷新。该轮未额外记录每个刷新 HTTP 请求时间戳，不夸称毫秒级独立时序采集。多版本独立源／URL／无 SHA-1、SQLite 故障修复重启、false 权限、普通／旧／直播／禁用委托、同源共享、并发 1／2、失败／竞态与全部清理均按原断言完成。独立 finally 全状态一致、双服务 exit 0／无 OOM、9 个外部容器未变。原始未适配命令及三次诊断失败继续保留，不将它们回写为通过。

### 最终 B 裁决与证据复用

```text
Reviewed Range: a06a80fac90a86085f25116568aa24b54847c562..8573dfbffebb785261668f9cd5c895be937e000e
Report-only starting Head: 5cb81717039df627c7eafd02affd8404e08c3a9b
Contract Checkpoint: 539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3
Decision: PASS
P0/P1 Blockers: NONE FOUND
BR-43-G1: CLOSED — remaining complete B gates obtained and independently audited
BR-43-R1 / BR-43-R2: P2, nonblocking; earlier severity correction remains effective
Slice Required Outcomes all satisfied: NO
Next: B PLANS TASK 4.4 — REAL JELLYFINPROXY PLAYBACK CHAIN
```

| 必要门禁 | 最终事实与归属 |
|---|---|
| locked restore／Release build／全量 C#／format | 复用本次同候选 B 完整运行；全部 exit 0，C# 202/202、skip 0，build 0 warning／error；65 项可执行／测试／锁输入在原检出与隔离副本逐项一致。 |
| 全量 Python／治理／差异／Markdown | 最终报告修改后重新执行 262 项发现及文档消费检查，准确结果保存在本轮 final-checks.json；非零发现及全部成功才保留本裁决。 |
| 打包与 package all | 固定 ZIP SHA-256 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`；来源 `b2f19c24f05d806ab75f152f36a302582e60ad67`，buildInputs SHA-256 `362df04af4af539add03017bf129747581345e813a27ef6f0645f3da0763bbda`。打包输入及 45 个 Release 负载匹配，复用已核验打包；B 新 package-all 377.672 秒 PASS，完整安装／升级／恢复／非法包分支，不用开发部署冒充 ZIP。 |
| scan all | B 新完整运行 816.477 秒 PASS，独立审计 54 个原始文件／1404 个事件、原生扫描与播放／批量真实重叠、136 源及停止／定时／恢复；旧扫描重启检查覆盖不足仍为 P2，最终 Slice Final 要另核变化批量源与多版本 A／B 的完整重启前后状态。 |
| 全部现存 1004 项大库 | 明确复用已匹配的 run-5 全流程，并由 B 独立重核 43 个原始文件、逐身份／完整五字段／原生地址主流和实际日志；首次 1004 信任／零探测，增量 16，停止 2／恢复 2，两轮未变零探测，1008 当前源完整重启前后只读一致，16 个变化源显式选源播放零额外探测。另有 B 独立 1004 项首次／未变／重启复现 115.979 秒；其 focused PASS／overall PARTIAL 不冒充 full。 |
| 三个默认开发部署回归 | configuration all 277.062 秒 PASS（19 浏览器驱动、13 summary、133 原始文件、57 截图）；batch suite 417.110 秒 PASS；plugin 519.730 秒 PASS。三者均独立审计恢复／退出和外部边界。后两者明确经已披露私有场景准备同步执行原始完整 main／断言，不声称未经适配命令 PASS。 |
| 输入／大库保留／服务边界 | 65 项输入在两份检出一致、固定 ZIP 一致，原 1004 项准备库 1170 文件的集合／大小／mode／SHA-256 一致；自有两服务已停止、exit 0／无 OOM，9 个其他运行容器身份／启动时间／镜像／挂载不变。所有准备数据、基线及失败副本继续保留，不清理／重建或为通过而重新准备全库。 |

本轮不改变产品源码、正式工具／测试、依赖、资源、阈值、业务或取消语义。私有适配修正的是异步原生夹具前提：多版本／停止场景等待准备扫描完成、独立刷新饱和前完成冷路径、mixed 删除前等待其已排队原生刷新；所有实际重叠、原断言及独立恢复仍执行。此前原始失败不是被删除或改绿，也不因为本次通过承诺冷启动原生刷新总在 2.5 秒内。BR-43-R1 描述和 R2 局部字段一致性保持 P2；B 没有只消费单一 full_task_acceptance 标签，已核整体退出、原始结果与必要收尾。

**全部 RO／Surfaces 重核：** RO-1 保留 4.1 B PASS，当前同 ZIP package-all 再验证；RO-3 保留 4.2 B PASS，当前完整 scan-all 与三个默认回归保持，既存 Final 重启补证义务不消失；RO-2 本次满足 AC-3／AC-4 与 AC-8 对应部分，原生查询／ID O(N) 成本、128 对象／8 消费者／默认 2 探测、完整首次／增量／停止／重跑／资源结算／重启均已证实。RO-4 的实际代理／302／客户端内容仍 NOT RUN；安装与支持文档的旧指针留 Slice 最终事实协调，不因此扩张兼容声明。不能用四个 Task PASS 拼成 Final；尚不形成 Closure Packet、READY FOR A REVIEW 或 Slice 关闭。

**证据交接：** 本机续轮索引 `.git/validation-evidence/5cb81717039df627c7eafd02affd8404e08c3a9b/b-complete-gates-20261020T054244Z/INDEX.md`；前轮完整门禁与大库审计索引通过 reuse-audit.json 关联。每次命令、私有适配源码／摘要、失败、原始日志／截图、独立审计、输入及保留库核对、最终文档测试和执行账目均留本机，不声称 GitHub 可读；无凭据／运行 DB／本机原始证据入提交。用户已撤销先前时间比例限制，历史执行偏差保留，不靠空等凑比例。只提交预期审查文档，普通本地 checkpoint，不推送。

最终检查中的一次治理拒绝已保留：已通过 Task 仍作为活动首标题时，治理按既定规则拒绝 Invalid active Task status。参照 4.1／4.2 已提交通过快照，将首行改为 NO ACTIVE IMPLEMENTATION TASK，保留内部 Task 4.3／Status PASS 与所有历史，不修改治理工具或状态规则；随后重新执行全部最终文档检查。

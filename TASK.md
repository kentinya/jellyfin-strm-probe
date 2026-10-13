# Task 2.1 — 按真实媒体源持久化播放指纹与重启恢复

模板来源：[Task 模板](Task/TEMPLATE.md)。范围 authority 为已提交的 [Slice 2](SLICE.md)，流程见 [开发流程](docs/development-workflow.md)；规划／审查参考 [B 经验](docs/agent-experience/task-planner-reviewer.md)，实施先读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 2.1
Parent Slice: 2
Status: READY FOR B REVIEW
Task Base: 7e0240cd1cada74f142b7b0afd612943ca991a91
Contract Checkpoint: 7e0240cd1cada74f142b7b0afd612943ca991a91
Slice Base: 924816a84c74f5d79c107478f2d40e621cb8be8d
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

用户播放受支持版本化 STRM 时，以实际媒体源所属项目的可信历史判断首次接管、复用或原生探测；正确地址／主流和最小 SQLite 指纹在重启后仍可核对。探测失败、保存失败、STRM 再变或状态库不可用不会接受错误版本，修复后可重新检查。多版本影片分别读取自己的 STRM、使用自己的原生保存证据与指纹，不能串版本。

这是 RO-1／RO-2／RO-3 的持久播放闭环及 RO-6 的状态库故障／恢复部分，提供后续协调器和 Slice 3 可复用的检查入口。RO-4／RO-5 的运行中共享和全局并发、RO-6 的完整核心配置留在后续连贯 Task；本 Task PASS 不表示 Slice 完成。

## B 合同合法性决定

2026-10-13，开始时 `git status --short --branch` 为干净的 `main`，无已有用户改动。必读文件、实际源码／测试和固定 Jellyfin 本地源码已核对；规划前 `python3 scripts/check_governance.py` 退出 0，确认已提交的 ACTIVE 合同与 Roadmap、真实 SHA 和祖先关系合法。

决定：**在修订合同下新规划 Task 2.1**。当前没有旧活动 Task 可继续或调整；不复用已通过的 Task 1.1 ID／Base，也不沿被替代的 `ac2fcead73664cfdaf66f62954ec6b11fb303168` 取消约定实施。Slice Base 不移动，Implementation Head 仍为 NOT SET。合同及规划前无活动 Task 的快照均可从本 Task Base 读取；历史 Task／证据见 [关闭账本](docs/progress.md#slice-1-closed)。

本 Task 保留原生 token 委托及原生自身取消异常保护；公共 PlaybackInfo 的 `CancellationToken.None` 不变，不增加成功返回后的取消检查、客户端停止关联、独立执行取消源或人为取消实机门槛。后续协调器只能登记实际已开始且仍运行的探测，已开始执行不因无人等待或批量停止而取消；真实批量停止留在 Slice 3。

本轮 B 只提交计划与当前指针，不开始插件实施、不签发产品 PASS。Developer 后续在本活动 Task 内实施、必要修正、隔离验证和普通本地提交按既有授权进行。无法满足合同则交 A 判定；A 提交新合同后 B 再明确决定继续、合法调整或重规划。

## 实际缺口与实施范围

### 已有能力与缺口

- `StrmManifestReader` 已有 UTF-8／可选 BOM、64 KiB 上限、首条非注释地址、重复标记拒绝和字段规范化；`ProbeDecisionService` 已有主要分支。现有 5 项解析、6 项决策测试不足以覆盖完整矩阵；Size 决策只检查非空，未在决策入口排除负数历史值。固定原生 `ProbeProvider.NormalizeStrmLine` 会移除制表符等再选首条非空非注释行，Reader 仅 Trim，须补齐或明确安全回退，不能猜测原生探测 URL。
- `StrmPlaybackOptimizer` 固定请求 `item.Id`＋`primary`，以首个含主流的源判断且只读取请求项目的 STRM，不能证明另一版本的文件／结果身份。固定源码 `BaseItem.GetVersionInfo` 使用所属项目 ID 作为 `MediaSourceInfo.Id`，`Video.GetAllItemsForMediaSources` 枚举版本，`MediaSourceManager.GetStaticMediaSources` 按用户过滤／排序。`MediaInfoHelper` 在包装接口返回后才过滤请求的 MediaSourceId，不能假装包装接口已有选源参数。
- `InMemoryStrmFingerprintRepository` 仅提供进程内 Get／条件提交，重启丢失；无 SQLite schema、运行依赖部署或故障恢复。已有跳过不覆盖基线的能力须保留，接受另一版本时不继承旧 SHA-1。
- 四处 DI 包装、`ProbeExecutionContext` 和原生保存代理可复用，继续关联本次编码器结果、主流保存成功返回及地址保存。现有失败／取消异常、保存失败和 Manifest 竞态测试，以及 B 的同元数据保存失败控制方法可复用；旧进程内证据不能替代 SQLite 集成。
- `scripts/run_isolated_plugin_integration.py` 已有加载、信任／复用、同 SHA-1／Size 换 URL、失败／重试、Manifest 竞态、false 流入口、手动刷新、普通／旧／直播、插件禁用与地址重启链路。当前部署只复制 DLL／meta.json，重启后信任断言针对内存仓库；引入持久化后须修正场景前提和依赖部署，保持必要行为。

### 完整实施范围

1. **输入与版本判断。** 补齐版本 1 的编码／BOM／空白／重复或冲突标记／非法首地址／字段／有界读取，以及 T01～T16、T26／T27、X03／X05 的逻辑和文件矩阵。维持 http／https 支持边界，其他原生协议委托；URL 选取与固定原生读法一致，非法首条不能跳到后面地址。URL／签名变化先于 SHA-1／Size，仅双侧有效 SHA-1 或有效非负 Size 可比较，0 不等于缺失，mtime 不参与。
2. **实际媒体源身份。** 从调用者可见原生源可靠解析所属 BaseItem、源 ID 和对应 STRM；候选键为实际所属项目 ID＋稳定原生源 ID，Guid 使用一致格式，实施须源码与实机共同验证。原生版本已有独立所属项目时无需另造版本系统，但不能继续用请求 ID＋primary 代替。URL／签名变化、返回顺序和重启不改键；不持久化路径／完整 URL。逐源使用必要音频／视频主流和保存关联，维持用户可见范围、路径替换及完整响应；验证主版本入口、直接版本入口与不同 MediaSourceId。无法可靠关联的源原生委托，不接受猜测指纹；混合普通／旧／不支持源不能因别的源可跳过就抑制其原生行为，也不能用整体回退替代受支持多版本验收。
3. **SQLite 接入播放。** 插件私有数据目录建立五字段 `strm_fingerprint(item_id, source_key, url_hash, sha1, file_size)` 和项目＋源主键；schema 版本只用 SQLite 元数据，不存媒体信息或持久化执行状态。保留 Get／expectedPrevious 条件提交，事务内核对基线，首次插入竞争／过期执行不能覆盖已接受版本。验证空库初始化、版本重开、未知版本拒绝、事务失败／回滚与释放。无旧部署 schema，不编造迁移，不自动删库或重建损坏库。新增依赖须固定版本／更新锁并验证隔离部署全部运行依赖可加载。
4. **共用检查与可靠提交。** 将源检查、原生执行／本次结果验证和条件提交组织为播放及未来批量可调用的真实服务入口；原生适配留接入层，解析／决策保持纯逻辑。首次有本源必要主流且原生地址相符才信任初建，无主流／地址过期按权限探测。其他提交必须关联本源本次真实成功、必要主流、原生保存地址／结果、稳定 Manifest 和预期基线。跳过时暂缺／非法观测不抹去历史有效 SHA-1；成功接受另一版本且无有效新哈希时存空。失败、取消异常、解析错误、文件再变和提交冲突不伪报已接受；返回前核对当前版本和原生源，不返回已知错误地址。保留同元数据仍需保存成功的对照。
5. **库故障与恢复。** 初始化或运行时读取／提交异常使优化停止，尽可能原生委托；脱敏记录故障类别，保留 allowMediaProbe，不制造成功提交，不因写失败重复强制探测。旧库保留；修复访问权限／可用性后，重启＋再次播放恢复检查。损坏／未知 schema 明确失败，不把替换空库当自动恢复；隔离测试恢复原库快照和权限。运行时停止优化可持续至重启，不要求后台自动修复。
6. **验证与事实同步。** 在现有 MSTest 项目增加文件／SQLite／源身份／播放回归，按需新增测试文件，无需预建项目。扩展现有实机脚本默认入口覆盖本 Task 场景，保留既有链路并恢复隔离夹具／配置。按证据类型更新矩阵和 CURRENT 事实，不把后续部分提前标 PASS。

允许文件边界：现有插件服务、接入／注册、必要持久化代码及测试项目，确有需要的项目／依赖锁，隔离集成／本地媒体工具，与新行为直接相关的文档。类名不作为验收目标；不预建协调器空实现。

### 后续范围与配置时机

本 Task 不实现共享／全局并发。下一连贯单元候选为“实际开始边界、同源共享、独立收尾及全局上限”，再以“核心配置保存／禁用与故障恢复用户操作”闭合余下 RO-6；这是剩余工作方向，未激活其他 Task。每次 PASS 后 B 按实际结果重查全部 RO／Surfaces，已满足则停止规划并执行 Slice Final，不为凑 Task 数量继续拆分。

现有 PlaybackAutoCheck 保持下次播放请求读取生效，不在请求中途改变决策上下文。后续核心配置计划采用：启用／播放检查保存成功后的下一次检查请求生效；详细日志下一次检查操作生效；并发 1～8 下一次 Jellyfin 启动生效，保存反馈说明时机。这是 RO-6 实施方向，本 Task 不宣称已有 Enabled／DetailedLog／并发配置。Jellyfin 自身插件禁用后的注册变化仍按原生重启语义验证，区别于未来插件自有启用配置。

## 验收条件

- [ ] **AC-T1：版本判断与首次接管。** 完整逻辑／文件矩阵有逐项索引，包括原生地址已同步但历史 URL 不同、双侧哈希有效性组合、Size 0／缺失／负数／溢出、信息不足、签名变化和 mtime／重写／重放。已有主流信任零探测；无流／原生地址过期需原生处理；音频／视频必要主流不混用。对应 Slice AC-1／AC-2。
- [ ] **AC-T2：SQLite 与哈希身份。** 最小 schema／版本／重开、原子条件提交／失败事务使用真实 SQLite；过期执行和插入竞争不覆盖新基线。暂缺 SHA-1 后恢复、接受另一版本缺哈希的序列正确，无完整 URL／路径／媒体流／执行状态。对应 AC-3、T27、X06。
- [ ] **AC-T3：真实成功与失败恢复。** 同 SHA-1／Size 换 URL、同 URL 哈希变化、无可比 SHA-1 的 Size 变化实际新增探测，成功结果／地址／指纹对账。不可达失败、Manifest 竞态、同元数据但主流／地址保存失败保留基线并可重试；保留取消异常回归，不新增取消机制。对应 AC-4、T17／T18、X04／X07。
- [ ] **AC-T4：重启不掩盖失败。** 成功地址／主流和指纹重启恢复，未变化零探测且非重新 FirstTrust。另在失败后保留当前未接受的变化 STRM 重启，先确认旧指纹仍在，再修复当前目标并验证下一次允许请求实际探测／提交；不靠变回旧 Manifest 恢复，不通过重启信任失败版本。对应 T19／T22、AC-3／AC-4。
- [ ] **AC-T5：真实多版本。** 同一影片至少两个原生关联的 STRM 版本，各自主流／指纹；主入口、直接版本入口／MediaSourceId 选择及返回顺序变化时，变更一个版本只接受其结果，另一个键／指纹／地址／主流正确；用户可见范围／原生授权和重启键稳定可核验。两个无关联影片或多源回退不算 T25。对应 AC-5 身份部分；共享／上限尚未验收。
- [ ] **AC-T6：状态库故障与委托。** 读／写故障控制测试及隔离代表性不可写验证：优化停止、权限保留、无新成功指纹，修复＋重启后重查；损坏／未知版本保留原库、明确失败。普通／旧／不支持输入、直播、false 真实流入口、禁用、全接口／生命周期和手动刷新不退化。对应 AC-7 状态库／原生边界部分。
- [ ] **AC-T7：T4 证据与范围。** 完整指定门槛、新依赖部署、原始脱敏日志／计数／数据库与原生结果索引可核验；未运行／外部代理分别报告。只修改 Task 范围内文件，不改 Contract／不变量或生产数据。对应 AC-8；完整 Slice 验收仍待后续工作和单独 Slice Final。

## 必要测试

所有命令 cwd 为 `/opt/jf-strm-probe`。真实 solution 为 `Jellyfin.Plugin.StrmProbeOptimizer.sln`，插件和测试项目为 `src/Jellyfin.Plugin.StrmProbeOptimizer/Jellyfin.Plugin.StrmProbeOptimizer.csproj`、`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj`；`scripts/dotnet-local` 固定 SDK `10.0.401`／net10.0。Jellyfin 固定 `12.2.0`／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6` 与已有镜像锁，见 [环境交接](docs/development-environment.md)。本计划没有产品测试 PASS。

### 开发／修正反馈

- 实施前再次记录状态并运行 `python3 scripts/check_governance.py`。先处理已知失败，再跑新增／修改用例和受影响回归。新增依赖时先用 `bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --use-lock-file` 生成并审查锁，再 locked restore；更新锁不是最终门槛。
- 输入／决策反馈：`bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~ManifestReaderTests|FullyQualifiedName~ProbeDecisionServiceTests'`，覆盖 AC-T1；最终全套已包含这些用例，不机械重复。
- 播放／持久化反馈：`bash scripts/dotnet-local test tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests.csproj --configuration Release --no-restore --filter 'FullyQualifiedName~PlaybackOptimizerTests|FullyQualifiedName~Fingerprint'`。新增 SQLite 测试类型名称包含 Fingerprint 以纳入入口；源映射／DI／保存代理新增用例另以实际 FullyQualifiedName 运行留证，最终全套全部发现。
- 接入、身份、保存或部署边界变化时尽早运行 `python3 scripts/run_isolated_plugin_integration.py`。扩展后仍使用同一默认入口，不以假对象冒充实机；工具修改先跑相关 Python 回归，解决失败后再跑昂贵最终门槛。

### 最终检查点门槛

持久化、媒体源身份、原生刷新和播放正确性相互影响，等级 T4，最终候选保留全部既有回归及适用实机门槛：

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

C# 全套包含解析／决策、真实 SQLite、源身份及播放／保存／取消异常回归；Python 全套保护环境和治理。检查变更文档本地链接／锚点，留实际命令／结果。实机脚本默认入口保留既有链路并覆盖 AC-T1～AC-T6 新场景，不能仅生成报告字段。

真实新增场景至少包括：无指纹新项目首次有流／无流；原生旧地址；同 URL 实际本地媒体替换配合哈希／Size 变化；同内容换 URL和无可比哈希换 URL；仅 mtime／重放；成功后 SQLite＋原生源重启；失败后变化文件保持、旧基线重启存续与修复重试；两个原生关联版本的主入口／选源／直接版本和重启；SQLite 代表性不可写及恢复。音频必要主流至少以原生适配控制测试验证，实机若目标不提供相同 STRM 入口则准确报告原生限制，不能将视频实测写成音频支持。保存失败、未知 schema／事务冲突可用真实 SQLite＋原生保存控制测试；内部 Jellyfin 数据库故障实机注入不是合同门槛。

旧脚本重启后 `first_trust` 前提须调整：以新隔离项目获得无指纹前提，保留首次信任；另断言持久指纹重启后复用而非信任，不删已有库制造前提。只操作仓库专用隔离夹具，退出时恢复临时媒体、STRM、配置、权限及原生地址并验证。新增 SQLite 依赖实际复制／加载与部署产物摘要是门槛，开发机 build 不替代部署。

### B 独立验证

审查完整 `Task Base..Developer Head`、原始证据和输入身份。在匹配候选上独立运行上述播放／Fingerprint 聚焦命令与 `python3 scripts/run_isolated_plugin_integration.py`，关键复现：同元数据保存失败仍拒绝提交、真实 SQLite 过期提交保护、失败后重启恢复、同内容换 URL新增探测、多版本身份及 SQLite 不可写后恢复。默认实机入口一并包含既有场景，无需再造工具。

其余门槛按开发流程核验后可复用匹配原始运行；缺失／矛盾／不匹配重跑对应门槛，不因角色变化机械重跑全部构建。PASS 前满足全部计划；明确阻塞可先 FIX REQUIRED，未运行项如实报告。独立审查由实施者之外的角色完成，不授权自动启动其他代理。

### 证据与重跑规则

原始本机证据保留至 A 决定，索引为 `.git/validation-evidence/<implementation-sha>/<run-id>/INDEX.md`，不能仅放 `/tmp`。记录完整候选 SHA／实际被测工作区内容身份、精确命令／cwd／SDK／依赖锁／镜像／隔离配置和夹具摘要、筛选／并行／重试、产物与部署依赖摘要、退出码／耗时／通过失败跳过数及脱敏原始日志；保留首败和每次重跑。固定原生 URL 读取、版本 ID／用户过滤与保存事务源码核验写入索引。

各实机场景对账本源探测调用／成功计数、返回及已保存地址／主流、SQLite 前后五字段与重启差异；地址仅保存假夹具身份或哈希。HTTP 成功、旧流、零调用或库记录不能单独证明成功。保存失败控制测试与实机故障分别报告；不导出完整签名 URL／token／Cookie／私有路径。

最终候选后改变源码、测试、工具、依赖、运行配置或夹具输入，T4 全部门槛在新候选重跑。纯报告／文档后继提交可明确比较执行输入后复用，重新运行消费文档的治理／链接检查。Slice Final 后续单独执行，不由旧 Task 运行替代。首次信任、复用、可靠成功、未完成／冲突／库故障分别记录；外部代理、批量、运行中共享及并发配置当前 NOT RUN，不纳入本 Task PASS。

## 非目标

- ProbeCoordinator 运行中共享、全局并发和无人等待收尾实机验证；条件提交竞争测试不表示协调器完成。
- 完整 Enabled／DetailedLog／并发配置保存反馈、HTML 配置页、并发热调整；固定规则不增加关闭开关。
- IScheduledTask、分页／有界批量、原生停止／定时／进度、ILibraryPostScanTask，仍属 Slice 3。
- 大库压力、广泛格式／客户端、OpenList／JellyfinProxy 联调、发布 ZIP，仍属 Slice 4。
- 生成器、STRM 写入／移动／删除、OpenList API、下载媒体计算内容 SHA-1、代理改写、另带 FFmpeg、独立调度／持久化执行状态、路径单独更新分支、生产操作和跨版本承诺。
- 改写 Slice 1 接受结果、移动 Slice Base、弱化成功／权限／隐私门槛或修改当前 Contract；合同问题交 A。

## Developer Completion Report

### 修正轮（响应 B FIX REQUIRED R1～R3）

- Changed Files：测试：`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ManifestReaderTests.cs`、`ProbeDecisionServiceTests.cs`、`PlaybackOptimizerTests.cs`、`SqliteStrmFingerprintRepositoryTests.cs`；隔离实机入口：`scripts/run_isolated_plugin_integration.py`；交接事实：本文件、`SLICE.md` 实现指针、`docs/architecture.md`、`docs/test-matrix.md`、`docs/progress.md`。未改产品源码、依赖锁、Contract 或不变量。
- Implemented：
  - **R1**：默认实机入口新增同 URL 真实替换本地媒体并改变有效 SHA-1／Size 的成功探测、同 URL 无可比 SHA-1 且有效 Size 改变的成功探测与 Size 相同的零探测、仅 mtime／相同重写／删除重放的零探测；失败后保留未接受的失败 Manifest／URL，在同一 URL 修复本地目标并证明同一失败版本被重试、探测与提交，而不是改到第三个 URL。每步对账实际媒体读取计数、SQLite 前后五字段与已保存主流，并清理新增临时媒体。
  - **R2**：补齐解析／决策矩阵回归：未知／冲突／不支持协议不跳过非法首地址、缺失／空文件、非法 SHA-1 长度／字符、最大／零 Size、mtime／重写／重放内容哈希稳定，以及 URL 优先、双侧 SHA-1 有效／缺失／非法组合、Size 可比与不可比、无主流优先于 URL 与指纹。逐项索引见 `docs/test-matrix.md` 的 Task 2.1 证据小节。
  - **R3**：新增 repository.Get 读取故障控制回归（优化停止、原生委托、false 权限不升级、无新指纹、同一实例内闩锁且重启后修复重新检查），并新增真实损坏 SQLite 输入回归：明确拒绝且保留原文件字节、不删库／重建、不把损坏库当空库。
- Tests and Results：修正候选 `3488e6b1df48d4c142595d27694a792bb32f0aad`。T4 门禁记录在 `.git/validation-evidence/3488e6b1df48d4c142595d27694a792bb32f0aad/developer-fix-t4-20261013-221013/INDEX.md`。固定 SDK 10.0.401；locked restore PASS；Release build PASS（0 warning／0 error）；solution MSTest PASS（65 passed、0 failed、0 skipped）；format verify PASS；Python unittest PASS（30 passed）；治理、`git diff --check` 与 Python compile PASS；隔离 Jellyfin 集成脚本退出 0、JSON status PASS、耗时约 500 秒。新增场景均以 PASS 记录，夹具与临时媒体已清理、原 STRM 与 Jellyfin 地址已恢复、SQLite 不可变标志已清除。
- Decisions：只补证据与回归，不改产品行为与合同；读取故障控制用隔离假对象（不是真实 Jellyfin 数据库故障注入），损坏库用真实 SQLite 字节。
- Remaining In-Slice Work：Task 2.1 等待 B 复审。RO-4／RO-5 的运行中共享、全局并发、独立收尾与 RO-6 完整核心配置仍未实现。
- Risks / Deviations：新增同 URL 内容变化通过向合成媒体追加字节改变 ffprobe 内容指纹，隔离实机夹具为含音频和视频的媒体；未验证独立音频-only STRM。未运行外部代理／OpenList、其他 Jellyfin 版本、批量、运行中共享／并发或发布打包。测试矩阵其余行保持 NOT RUN。
- Head SHA：`3488e6b1df48d4c142595d27694a792bb32f0aad`。

### 首轮实施（B 已裁定 FIX REQUIRED，保留历史）

- Changed Files：插件实现与依赖：`src/Jellyfin.Plugin.StrmProbeOptimizer/Jellyfin.Plugin.StrmProbeOptimizer.csproj`、`Packaging/meta.json`、`ServiceRegistrator.cs`、`Services/ProbeDecisionService.cs`、`Services/ProbeExecutionContext.cs`、新增 `Services/SqliteStrmFingerprintRepository.cs`、`Services/StrmManifestReader.cs`、`Services/StrmPlaybackOptimizer.cs`、`packages.lock.json`；测试：`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/ManifestReaderTests.cs`、`PlaybackOptimizerTests.cs`、`ProbeDecisionServiceTests.cs`、新增 `SqliteStrmFingerprintRepositoryTests.cs`、测试项目 `packages.lock.json`；隔离实机入口：`scripts/run_isolated_plugin_integration.py`；交接事实：本文件、`SLICE.md` 实现指针、`docs/architecture.md`、`docs/test-matrix.md`。
- Implemented：按实际 Jellyfin 项目／媒体源关联播放检查；新增五字段 SQLite 指纹表、按项目＋源主键的版本初始化及条件事务提交；扩展输入规范化、决策校验和播放提交核对；部署并验证 SQLite 托管／原生运行依赖。隔离实机覆盖首次信任和重启复用、相同内容换 URL、失败保留／恢复、Manifest 竞态、多版本源选择、状态库写入失败及不可写故障／重启恢复，并保留旧 STRM、普通媒体、直播、false 流权限、插件启停和 FullRefresh 场景。代码实现候选为 `b99bc00b08fd3a8cad32076a220c5219fcc78ab7`，等待 B 独立审查；AC 勾选和 B 决定保持未完成。
- Tests and Results：候选 T4 门禁记录在 `.git/validation-evidence/b99bc00b08fd3a8cad32076a220c5219fcc78ab7/developer-final-t4-20261013-02/INDEX.md`。固定 SDK 10.0.401；locked restore PASS；Release build PASS（0 warning／0 error）；solution MSTest PASS（51 passed、0 failed、0 skipped）；format verify PASS；Python unittest PASS（30 passed）；治理、`git diff --check` 与 Python compile PASS；最终隔离 Jellyfin 集成脚本退出 0、JSON status PASS。隔离实例已确认临时 STRM 移除／库条目不存在、版本关系解除、原 STRM 恢复且 Jellyfin 地址同步；仅使用仓库专用隔离实例和临时夹具，未改生产 Jellyfin 或媒体。先前反馈运行失败及后续最终复验均保留在证据索引中。
- Decisions：不新增共享协调器、全局并发配置、批量任务或完整配置页；保留 SQLite 失败时停止优化并按原生权限委托的路径。最终隔离脚本新增真实不可写 SQLite 验证，使用文件系统不可变属性（`chattr +i`）触发 SQLite 写失败，并在重启恢复前清除属性。没有把整份 T01～T28／B01～B12 矩阵或完整 Slice 结果标记为通过。
- Remaining In-Slice Work：Task 2.1 等待 B 审查。Slice 2 的运行中共享／全局并发／收尾与 RO-6 完整核心配置尚未由本 Task 实现或验收；完整 Slice 审查仍待后续授权工作。
- Risks / Deviations：本 Task 的实际媒体源、多版本与 SQLite 故障链路有隔离 Jellyfin 证据；音频必要主流由原生适配控制测试覆盖，隔离实机夹具是含音频和视频的媒体，未验证独立音频-only STRM。未运行外部代理／OpenList 联调、其他 Jellyfin 版本、批量、运行中共享／并发门槛、完整产品矩阵或发布打包。测试矩阵各行继续保持 NOT RUN，等待 B 独立审查后按完整行范围核对。
- Head SHA：`b99bc00b08fd3a8cad32076a220c5219fcc78ab7`。

若产生少量可复用经验，提供候选供 A 收尾合并，不记流水账；本轮规划没有新增收尾经验。

## B Review Result

```text
Reviewed: 7e0240cd1cada74f142b7b0afd612943ca991a91..b99bc00b08fd3a8cad32076a220c5219fcc78ab7
Documentation Handoff: 443acc5133d1444df3e9c9dd4f2c782c157a9ba7
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CORRECTS TASK 2.1 AND RESUBMITS FOR B REVIEW
```

### B 独立审查（2026-10-13）

开始时 `main` 工作区干净，无已有用户改动；治理检查 PASS。审查上述完整范围，并核对后继交接提交只修改四份文档、执行输入未变。已提交 Slice 的义务可在当前 Task 内满足，**继续同一 Task 修正**；ID、Base、Goal、Scope、T4、验收与原测试计划保持有效，无须改变 Contract。以下阻塞是当前必要验收的证据缺口，不宣称已发现相应产品行为错误。

本机独立证据：`.git/validation-evidence/b99bc00b08fd3a8cad32076a220c5219fcc78ab7/b-review-20261013-01/INDEX.md`。B 独立运行播放／Fingerprint 聚焦测试，28 passed、0 failed、0 skipped；另用真实 SQLite 的审查 harness 复现相同主流元数据下流保存失败、地址仅在内存更新、项目保存失败，连续两次允许请求均拒绝并保留旧基线，false 请求保持权限。审查 harness 首次运行误用假对象累计权限标志而失败，修正观测方式后通过；原失败保留，不作为产品故障。固定原生源码的 URL 选取、源 ID／用户过滤及保存事务边界亦已核对。

Developer 的 locked restore、Release build（0 warning／0 error）、C# 全套 51 项、format、Python 全套 30 项及隔离实机原始日志已阅读，输入摘要匹配；它们覆盖已有场景，不能替代下列未执行门槛。B 独立实机复验退出 0、JSON PASS，耗时 495.108 秒，复现同内容换 URL、失败后重启、真实多版本及 SQLite 不可写／恢复；三个临时 STRM 与版本关系已移除、库条目不存在，原夹具及原生地址已恢复，数据库不可变标志已清除，隔离实例 healthy。其脚本 PASS 只表示脚本已包含场景通过，缺失场景仍为 NOT RUN。

### 当前 Task 的 P1 阻塞与修正要求

1. **R1 — 补齐默认实机入口的变化／文件与恢复场景（AC-T1／AC-T3／AC-T4）。** `scripts/run_isolated_plugin_integration.py:1341` 起只读取字节相同的两份媒体，后续验证 URL 变化；默认入口及最终 JSON 没有同 URL 实际替换本地媒体并改变有效 SHA-1、同 URL 无可比 SHA-1 且有效 Size 改变的成功探测场景，也没有仅 mtime／相同重写／删除重放的零探测场景。补齐原计划要求的场景，分别对账实际调用、新结果／已保存主流、返回及保存地址与 SQLite 前后值，恢复全部夹具。当前失败重启后恢复在 `scripts/run_isolated_plugin_integration.py:1530` 起改用第三个 URL；还须保持未接受的失败 Manifest／URL，修复该本地目标后证明同一失败版本重试成功并提交。现有换 URL 恢复证据保留。
2. **R2 — 补齐完整解析／决策回归及逐项索引（AC-T1／AC-T7）。** 现有 10 项 Reader 和 9 项 Decision 测试未形成合同要求的完整覆盖。例如未知／冲突协议、缺失／空文件、非法 SHA-1 长度／字符，以及双侧 SHA-1 有效／缺失／非法组合、URL 已同步但历史 URL 改变时的哈希／Size 分支尚缺直接回归；mtime／重写／重放也无文件回归。以实际输入／预期行为补齐覆盖，给出 T01～T16、T26／T27、X03／X05 到测试／实机场景的索引，明确各证据层与缺失项。可用参数化用例，不要求每个字段或矩阵行另造 Task；不能用总测试数或整表 NOT RUN 代替对账。
3. **R3 — 补齐状态库读故障和损坏保护回归（AC-T6）。** 现有 SQLite 测试验证正常重开、条件提交、插入竞争、事务写失败及未知／未版本化 schema；播放测试没有 repository.Get 异常控制场景，实机验证是提交写失败／不可写。补充读取故障时停止优化、后续原生委托、false 权限不升级、无新指纹及恢复重新检查的控制回归；使用真实损坏 SQLite 输入验证明确拒绝、保留原文件，不自动删库／重建。已有未知 schema 和不可写实机证据可保留，不新增内部 Jellyfin 数据库故障实机门槛。

修正形成新实现提交并更新完成报告。源码、测试或工具输入改变后，在新候选重跑原计划全部 T4 门槛，保留首次失败与重跑；B 再独立复现指定关键行为。当前未满足的 AC 不勾选，不新建 Task 2.2。

### Slice Required Outcomes／Surfaces 核对

| 项目 | 当前事实与剩余义务 |
|---|---|
| RO-1／解析与决策 surface | 主要实现及首次信任／复用存在；R1／R2 阻塞完整矩阵验收。 |
| RO-2／SQLite surface | 最小 schema、条件事务、哈希身份与重启已有匹配证据；R3 阻塞读故障／损坏保护验收。 |
| RO-3／共用检查与原生 surface | 真实源检查入口、成功／保存保护、URL 变化、多版本与失败重启已实现；R1 阻塞同 URL 变化及保持失败目标的恢复验收。 |
| RO-4／身份与协调 surface | 多版本源身份已有单元及实机证据；ProbeCoordinator、只共享实际运行、统一上限和配置 1／8 尚未实现。 |
| RO-5／正常收尾 surface | 既有原生取消异常保护保留；已开始工作无人等待仍收尾、开始边界和资源释放待协调器实施。 |
| RO-6／配置与诊断 surface | 库写失败／不可写停止优化及重启恢复已有证据；读故障／损坏保护待 R3，Enabled／DetailedLog／并发保存反馈及用户操作方法尚未完成。 |
| 固定实机／最终证据 surface | 已有场景有独立复验；缺失场景待补，完整 Slice Final 尚未运行。 |

**Slice 2 仍为 ACTIVE；不提交 Closure Packet，不宣布 Slice 关闭。** 通过本 Task 后再核对全部 RO／Surfaces，决定下一完整实施单元。可复用经验候选供 A 收尾：实机入口的 PASS 只覆盖实际断言过的场景 → 审查时将合同逐项映射到测试和原始产物，特别核对同 URL／换 URL 与恢复前提 → 适用于扩展旧集成脚本。

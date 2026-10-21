# Task 5.3 — 视频八类决策的真实播放、误判取证与失败恢复

受已提交的 [Slice 5](SLICE.md) 约束，以 [开发流程](docs/development-workflow.md) 为准。实施阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)，规划／审查阅读 [B 经验](docs/agent-experience/task-planner-reviewer.md)。

```text
Task ID: 5.3
Parent Slice: 5
Status: READY FOR B REVIEW
Task Base: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94
Contract Checkpoint: 108735e72f0028ae7763c36cc0cb143adb5cd6a9
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

完成 Slice RO-1 剩余的可控媒体前提、RO-2 的 MP4／MKV 八类决策与指定子场景、RO-3 的真实 ColorRange 三阶段取证和失败恢复。用户继续在原生 Web 点击播放；插件应准确决定是否探测，返回正确当前内容／地址／必要媒体流，可靠保存并提交指纹，再播与重启后仍正确。交付物是下表逐行的真实播放结果及可复核原始证据。

不把“同地址内容换了”概括为总能识别：没有可比 SHA-1 且大小相同／不足时按合同跳过并记录限制。大小改变也不是总跳过：有效 SHA-1 相同才忽略大小，SHA-1 不可比且双侧有效大小不同时必须探测。有效视频被误拒绝仍为 FAIL；查明问题不等于产品行为通过。

本 Task 仅规划测试／必要采集与受控媒体准备，不授权修改插件成功判定或新增插件诊断。若现有产品缺陷阻塞，保留证据与未完成项，由 B 给 FIX REQUIRED、交 A／用户决定产品修正；修正继续同一 Task，不删场景、不另建“工具完善 Task”。全部 RO 满足后停止造 Task，另做 Slice Final／Closure Packet 交 A，不自行关闭。

## 已接受检查点与实施事实

- 规划前工作区干净，main 超前 origin/main 25 提交；`python3 scripts/check_governance.py` 通过。Task Base 是真实 Task 5.2 B PASS 检查点，Slice Base 不移动。
- Task 5.1 的 CI 修复／匹配远端结果、Task 5.2 的完整合同／报告／B PASS 分别保存在 `4c75761982bc16dd1c6bae09bee1c3561da2c178:TASK.md`、`f17fb1fc90dda242eeff9fac7b4f21576b5e6f94:TASK.md`。5.2 接受两行视频首次信任／再播／只读重启后实播，不证明 P01～P08、ColorRange 探测或整个 Slice PASS。
- 已核对当前 Slice、[执行设计](docs/slice-5-playback-test-plan.md)、必读文档和真实源码。以下展开是对合同的细化，未改变 Required Outcomes、授权或历史决定；音频 STRM 按用户授权不执行，视频音轨及“缺 Video 仍有 Audio”保留。
- 规划时播放入口只有 `--scenario baseline` 与 B01～B03；本 Task 已在同一入口实现固定 `--scenario matrix` 行注册。当前 baseline 只有 B01 MP4／B02 MKV，默认行集合由这两行生成，B03 音频 STRM 在创建工作区前拒绝；音频 STRM 专属夹具、库及读取路径已随用户范围决定撤出。严格 Web 驱动保留真实 Play、至少 5 秒差值、视频解码帧、截图、源 ID／URL hash 和媒体请求采集。完整原生读回／探测原文仍需 RO-3 三阶段取证。
- 规划时 `isolated_media_server.py` 尚无显式 Range 实现；当前实现已覆盖 GET／HEAD 单区间、206／416 及相应响应头，并保留查询参数、404 和既有路径。固定 URL 可通过本轮拥有文件的原子替换控制；没有新增控制面 API／路由管理器。
- `ProbeExecutionContext.RecordResult`、`RecordPersistedMediaStreams`、`IsPersistedProbeResult` 已存在；保存代理在原生 SaveMediaStreams 成功返回后才记录保存信号。当前警告只记录布尔结果；PrimaryStreamIdentity 包含 ColorRange 等字段，尚无本次三阶段字段取证，不能预填根因。

## 实施范围与最小准备

复用现有包隔离、FFmpeg、顺序入口和 Web 驱动。允许的直接修改仅为：

| 位置 | 为交付结果所需的工作 |
|---|---|
| `scripts/run_isolated_playback_integration.py` | 在现有顺序入口加入下方固定视频行；准备／切换前提，串行调用原生 Web Play，保存完整原生状态、指纹、原始日志及逐行结果；保留 baseline 行为。 |
| `scripts/package_playback_driver.mjs` | 仅补现有响应的必要原文／失败截图采集；正常视频始终至少推进 5 秒；保持旧 2 秒包回归模式。 |
| `scripts/isolated_media_server.py` | 为真实媒体读取补必要的 GET／HEAD 单区间 Range，明确 206／416、Content-Range／Length；保留旧文件、slow／delay／independent 路径和原计数格式。不给测试增加控制 API。 |
| 对应现有 Python 测试模块 | 按实际修改验证 Range 字节及响应头、旧路径兼容和真实证据缺失拒绝；假对象只证明采集控制，不冒充产品故障。 |

`package_environment.py`、旧 package／scan／large／plugin／batch／configuration 入口原则上保持；确需修改先由 B 记录实际原因、调用影响和回归追加，沿用本 Task。不为泛化、整理历史音频辅助代码或扩大工具测试覆盖而修改。`src/`、C# 测试、依赖、镜像锁、工作流、治理工具及产品诊断均不在实施授权内。

准备要求：

1. 固定 Jellyfin 12.2.0／源码 ca0f16eb7c195f720a1493ed469a27c4657db0c6、Linux x64、SDK 10.0.401 和镜像锁。新归属小型视频实例、随机新凭据、仅本机端口；记录实际主机 CPU／内存／磁盘及工具版本、镜像 ID、ZIP／sidecar／部署摘要、Active、原生任务默认无触发，并发默认 2。只安装指定 ZIP，服务器不挂源码／SDK／构建目录。
2. 用 Jellyfin 自带 FFmpeg 生成至少 20 秒 H.264＋AAC 的 MP4／MKV，A／B 画面有明确标记；记录实际 SHA-1、Size、生成命令、ffprobe 原文。准备逐字节别名、合法容器 padding 的等长异内容对、不同长度对，以及明确 limited／full／未返回 ColorRange 的实际输出对照。参数／文件名不代表实际字段值，padding 后仍须原生可探测、可解码。不得伪造内容 SHA-1。
3. 只在测量前以 `os.replace` 等原子替换本轮媒体文件，形成同一 URL 下的 A→B；播放期间不异步改写。查询参数别名使用既有普通文件路径。404 使用该服务内确实缺失的本轮文件，损坏媒体用拥有的受控文件；恢复仍用同一目标 URL。记录服务端字节摘要、HTTP Range／无缓存响应及画面内容，不能靠缓存旧内容通过。
4. 除 P01 指定缺流前提外，在插件停用时原生准备地址／主流；启用后通过首次信任建立该行所需的真实历史指纹。无效／缺失可选字段在当时 STRM 中形成，旧指纹保存的是解析后的 null，不能直接捏造数据库中存在非法哈希／Size。仅在本轮副本为 P01 有界移除流；先确认固定数据库实际 schema／目标 item，停止服务、备份、参数化限定目标，启动后先只读核验，禁止猜表名或改共享库。
5. 每行拥有独立项目／源和冻结前提，固定预期来自下方清单和实际媒体身份，不从插件结果反推。隔离实时监控／扫描／批量任务；不得先请求目标变化的 PlaybackInfo 或刷新消费变化。媒体服务可先单独核对文件字节，不能预热该行 Jellyfin 播放。

## 固定场景清单

以下是完整必要行，不以八条汇总代表已覆盖全部子场景。规范 ID 为 `MP4.P02.01`／`MKV.P02.01` 等，两种格式逐行执行相同展开。每个正常行都执行目标首次播放、再次播放、重启先读后播放；首个窗口期望见表，接受成功后另两个窗口均为 0。重启可按小批次统一进行，先冻结该批全部项目，重启后在任何 PlaybackInfo 前只读核验全部项目，再播放。

符号：V=该版本实际有效的 40 位 SHA-1；Ø=未提供；L=39 位错误长度；X=40 位含非十六进制字符。N=实际非负有效字节数；非法 Size 明确写原字符串。P03～P08 的 URL 均不变。哈希不可比是新旧至少一侧非 V，不把 URL 的哈希当内容 SHA-1。

### P01 缺少 Video（每种格式 4 行，首窗 ffprobe=1）

| 尾号 | 历史指纹 | 保存的媒体流 |
|---|---|---|
| 01 | 无 | 无 Video／Audio |
| 02 | 有 | 无 Video／Audio |
| 03 | 无 | 只有 Audio、无 Video |
| 04 | 有 | 只有 Audio、无 Video |

均须本次探测保存正确 Video／地址、满足条件才初建／更新指纹并实播；不能沿首次信任跳过，不能以仍有 Audio 认定主流齐全。

### P02 URL 变化（每种格式 8 行，首窗 ffprobe=1）

| 尾号 | 实际输入变化 |
|---|---|
| 01 | 新路径指向相同字节；V→V 相同，Size 相同 |
| 02 | 新路径指向 B；V→V 不同，Size 不同 |
| 03 | 双侧无 SHA-1；新路径相同字节，Size 相同 |
| 04 | 双侧无 SHA-1；新路径 A→B，Size 不同 |
| 05 | 双侧 SHA-1／Size 均缺失；新路径相同字节 |
| 06 | 仅旧侧有效 SHA-1；新路径相同字节、Size 相同 |
| 07 | 仅新侧有效 SHA-1；新路径相同字节、Size 相同 |
| 08 | 只有查询参数变化；相同字节、V 相同、Size 相同 |

所有行当次源／原生保存／新指纹均关联新 URL，重启后继续使用新 URL；不能把相同内容当作只改路径的理由。

### P03 相同有效 SHA-1（每种格式 5 行，首窗 ffprobe=0）

| 尾号 | 新旧 SHA-1／Size 前提 |
|---|---|
| 01 | V 相同，Size 相同 |
| 02 | V 相同，新 Size=N+1；明确只是 Manifest 元数据扰动，媒体字节未变 |
| 03 | 仅有效 SHA-1 十六进制大小写变化，Size 相同 |
| 04 | V 相同；旧 Size=N，新 Size 缺失 |
| 05 | V 相同；旧 Size=N，新 Size 为非法负数 |

沿用原生流和旧五字段，不因 Size 或哈希大小写重新探测。

### P04 不同有效 SHA-1（每种格式 3 行，首窗 ffprobe=1）

| 尾号 | 固定 URL 原子切换 A→B |
|---|---|
| 01 | 两个真实有效 SHA-1 不同、实际字节数相同（合法 padding 后重新计算） |
| 02 | 两个真实有效 SHA-1 不同、实际字节数不同 |
| 03 | 两个真实有效 SHA-1 不同；旧 Size 有效，新 STRM 不提供 Size，实际 B 大小另记 |

当次必须播放 B，保存 B 的主流／内容哈希和实际可用元数据；Size 不可比不能压过有效 SHA-1 变化。

### P05 不可比较 SHA-1、有效 Size 相同（每种格式 5 行，首窗 ffprobe=0）

| 尾号 | 旧 STRM SHA-1 → 新 STRM SHA-1 |
|---|---|
| 01 | V → Ø |
| 02 | Ø → V |
| 03 | Ø → Ø |
| 04 | V → L |
| 05 | X → V |

媒体实际字节保持 A，双侧 Size=N；保留旧五字段，旧有效 SHA-1 不因暂缺／非法字段被抹去。不声称能识别无可比哈希的同 URL／同大小替换。

### P06 不可比较 SHA-1、有效 Size 不同（每种格式 10 行，首窗 ffprobe=1）

固定 URL 切换真实不同长度媒体；逐行沿用 P05 的五种 SHA-1 方向，尾号固定为 `01.up`、`01.down`、`02.up`、`02.down`、`03.up`、`03.down`、`04.up`、`04.down`、`05.up`、`05.down`。up 为新实际 Size 大于旧值，down 为小于旧值，Manifest 与实际字节数同步；新侧 V 时填写真实 B 哈希。

每行保存／播放 B 并提交新版本。新侧没有有效 SHA-1 时，新指纹 sha1=null，不携带旧版本有效哈希；新侧有效时提交该新真实值。

### P07 信息不足（每种格式 6 行，首窗 ffprobe=0）

| 尾号 | SHA-1 方向 | 旧 Size → 新 Size |
|---|---|---|
| 01 | V→Ø | Ø→N |
| 02 | Ø→V | N→Ø |
| 03 | Ø→Ø | Ø→Ø |
| 04 | V→X | N→`-1` |
| 05 | X→V | `not-a-size`→N |
| 06 | Ø→Ø | N→`9223372036854775808`（Int64 溢出） |

媒体字节保持 A；记录信息不足、复用可用主流并保留旧五字段。缺失／非法不当作 0；合法 0 的解析由已有解析控制核验，不能把空文件列为正常实播视频。

### P08 仅 Modified 变化（每种格式 3 行，首窗 ffprobe=0）

01=仅文件 mtime；02=仅可忽略 Modified 注释；03=原字节内容重写／重放。分别执行，媒体字节、URL、有效 SHA-1／Size 保持 A，不得用其中一项代表另外两项。

P01～P08 合计每种格式 44 行、两种格式 88 行。上表覆盖执行设计列出的必需输入方向；非法值按已列独立行执行，不额外要求与无关维度做全排列。任何新增必要行由 B 据实际缺口记录，不能静默减少现有行。

### C：ColorRange 真实回归（每种格式 6 行）

固定尾号为 `C02.limited`、`C02.full`、`C02.unspecified`、`C06.limited`、`C06.full`、`C06.unspecified`，完整 ID 加 MP4／MKV 前缀：

- C02 固定为 URL A→B、两个实际有效 SHA-1 不同、Size 不同；C06 固定为同 URL 的 A→B、旧有效 SHA-1→新缺失 SHA-1、实际 Size 减小。三种 ColorRange 只改变目标 B 的受控输入，分别核验真实身份；均预期首窗探测 1 次、有效视频正常播放，新结果保存且指纹提交，再播／重启为 0。
- limited／full 依据实际本次 ffprobe 视频字段为 tv／pc；unspecified 依据本次输出缺少该字段，不能只是不传生成参数。各行保留独立三阶段字段资料及正常／失败截图。
- 若某 C 行与一个 P 行具有完全相同的候选／媒体／原生及指纹前提、动作和观测，可用该次原始运行同时覆盖两个 ID，事前注明别名对应；不能仅凭规则相似复用。否则 12 个 C 行独立执行。正常主矩阵仍保持 88 个规范 ID。

### D：权限与原生委托对照（两种格式均执行）

| ID 尾号 | 前提／动作 | 必须结果 |
|---|---|---|
| D01 | 已有主流、无旧指纹的首次接管 | 使用 baseline B01／B02 的三阶段真实旅程，零探测、初建指纹，不计探测成功；同次结果可同时覆盖 D01，不重复运行。 |
| D02 | 禁用整个插件后正常播放版本化 STRM | 原生播放正确、无插件检查／提交，不把原生探测数硬定为 0；配置与旧指纹前后核验。 |
| D03 | 只关闭播放自动检查 | 原生播放正确、无播放优化提交；不推断批量也关闭。 |
| D04 | 普通 MP4／MKV 媒体文件 | 原生播放正确，无 STRM 指纹或优化接管。 |
| D05 | 无版本标记的旧 STRM | 原生播放正确，无受支持版本优化提交。 |
| D06 | 已有主流／旧指纹，STRM 改为相同字节的新 URL，然后请求既有原生 `GET /Videos/{id}/stream?static=true` | 这是已核对的 allowMediaProbe=false 入口，插件不提高权限、不探测、不接受变化；保留原响应契约和旧指纹。随后第一次正常 Web Play 才探测 1、保存新 URL／提交，再播及重启为 0。 |

D02～D05 的正常播放同样有至少 5 秒截图、再播和重启，计数报告原生实际值，不套用优化零探测义务。D06 的原生直读是权限对照，不能替代随后三次 Web 实播，也不能虚构 PlaybackInfo 的 false 参数。只读状态继续用既有 `GET /Items/{id}?Fields=MediaSources,MediaStreams,Path`。

### F：失败、旧基线保护与恢复（每种格式 2 条完整旅程）

- F01：从已接受 A 改到本地服务的缺失目标 URL（真实 404），由 Web Play 触发一次匹配探测并失败，保存响应、报错截图及旧五字段。再次失败重试仍可探测、无新指纹；保留失败 URL 重启后先只读核对旧五字段，再在同一目标 URL 放入有效 B，正常 Web Play 重新探测、保存并提交，随后再播／重启复用。Manifest 内容哈希来自本轮预备的真实 B，不捏造另一视频的内容标记。
- F02：固定 URL 的 A 被原子替换为真实损坏／截断字节，Manifest 如实记录该受控输入的 SHA-1／Size，触发探测失败；完整保存旧五字段、当次原生地址／流及报错截图。修复同一 URL 为有效 B，并把 Manifest 更新为实际 B 身份后重试，探测／提交／至少 5 秒实播，再播和重启无重复探测。

失败窗口实际 ffprobe、原生返回及保存状态如实记录；不能假定 Jellyfin 数据库与指纹同时回滚，也不能用恢复旧 URL 代替修复目标 URL。ColorRange 有效媒体失败绝不放进 F 类当“预期失败通过”。

## RO-3 三阶段取证与边界

同一次 C 行实际播放中，需要对应项目／源／探测调用的：①原生编码器返回 Video；②SaveMediaStreams 成功返回时的完整流入参；③原生重读／返回 Video。包含 PrimaryStreamIdentity 的全部字段，逐字段列明保留、缺失和规范化，关联当次 ffprobe、原生地址及旧／新指纹。

优先使用固定版本现有原文日志和原生只读响应。当前源码没有完整①②日志，现有布尔值及另跑一次独立 ffprobe 均不能代替①②。允许在本轮独立诊断实例使用一个标准 .NET 外部调试器只读观察现有方法参数：`RecordResult(requestedPath, result)`、原生保存成功后调用的 `RecordPersistedMediaStreams(itemId, streams)`、`IsPersistedProbeResult(stream)`；关联当前 ProbeExecutionContext 的项目／源／URL。不能改对象、求值有副作用函数、调用探测方法、跳过异常、改变返回值或安装另一插件。

规划时主机尚无上述调试器；不编造安装／附加命令为现成能力。首个聚焦取证前记录实际工具来源／版本、按其真实帮助固定命令、PID／容器归属及只读参数清单。调试暂停的时序单列；诊断运行只用于字段定位，不能充当未附加调试器的正式播放／成本门槛。主验收仍为固定原始 ZIP／镜像，额外调试资料只存本机忽略目录。

若现有观察加标准只读调试仍无法取得①②，记录缺失并交 B／A；不得用重新探测的相似结果补写，不自动授权插件或 Jellyfin 诊断构建，不为采集建设框架。发现有效媒体误拒绝时保留 FAIL、五项判定和完整实际保存状态，交 A／用户决定产品修改；范围／授权未落定前不盲跑整个昂贵矩阵和 Final。

## 验收条件

- [ ] RO-1 的 Range／固定 URL 原子切换／查询别名／404 与损坏恢复输入均由实际字节及原生播放核验；媒体、STRM、镜像、ZIP／sidecar／部署、归属及资源可复核。
- [ ] MP4／MKV 全部 88 个 P 行及 C／D／F 必需行有明确前置状态、实际结果和原始证据；别名复用有完全输入匹配说明。缺失／NOT RUN／BLOCKED 不计 PASS。
- [ ] 每次正常原生 Web Play 的截图起止实际推进至少 5 秒，视频有解码帧和正确 A／B 标记、成功媒体请求；执行者及 B 均逐张实际打开并记录，HTTP 200／advanced=true／图片路径不代替检查。
- [ ] P／C 测量窗口实际目标 ffprobe 为预期的 0 或 1；准备期先以非零计数验证日志，原始启动／完成及完整日期／会话／目标 URL 可重数，FFmpeg 转码另列；原生委托对照不强套零探测。
- [ ] 每行核对 MediaSourceId→当前 URL→必要 Video／Audio、完整原生保存及五字段；首次信任不称成功探测，跳过不覆盖旧指纹，接受新版本缺有效 SHA-1 不继承旧版本哈希。
- [ ] 每项成功后再播不重复探测；重启前冻结该批完整原生源／媒体流和指纹，重启后所有项目先只读相等再开始任何 PlaybackInfo／播放，禁止补建掩盖丢失。
- [ ] ColorRange 三阶段实际字段与对照、失败旧基线保护及同目标恢复均可复核；有效媒体预期播放成功，未授权产品修复或缺证据保持 FIX REQUIRED，不改断言／预期失败完成合同。
- [ ] B 完成下方固定候选完整门禁及独立关键复现、Task Base..Head 审查；配置、触发器、临时输入、服务正常退出与只清理本轮资源对账，现存全部 1004 项及适用基线保留。Developer 交 READY FOR B REVIEW，不自行 PASS。

## 必要测试

### 开发／修正反馈（Developer）

只运行本次新增／修改和直接受影响反馈，先跑首个可达视频／ColorRange 对照，发现已知产品阻塞先保留证据，不反复全量重跑。反馈按改动选少量完整旅程，不要求 Developer 代 B 跑完全部 P／C／D／F 实机行；交接逐 ID 列已测及 NOT RUN，由 B 在固定候选补齐或核验匹配证据。下列模块均已存在，按改动选择；discovery 必须发现实际用例：

```bash
python3 scripts/check_governance.py
python3.11 -m unittest discover -s tests -p test_isolated_playback_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_media_server.py -v
python3.11 -m unittest discover -s tests -p test_isolated_package_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_scan_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_large_library_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_batch_integration.py -v
python3.11 -m unittest discover -s tests -p test_isolated_configuration_integration.py -v
python3.11 -m compileall -q scripts tests
node --check scripts/package_playback_driver.mjs
git diff --check
```

改顺序入口跑 playback；改共享驱动加 package 和 Node；改共用 HTTP 服务则跑 media_server、playback 及其直接消费者上述 package／scan／large／batch／configuration 工具控制。Python 编译限实际修改／直接导入文件，列表全覆盖不是要求每次编辑都全跑。没有 C# 改动不要求 Developer 跑 C# 或无关全量；报告未运行全量，B 承担最终真实回归。

提交可审阅实现后，用现有 `python3 scripts/package_plugin.py --configuration Release --output-dir <本轮包目录>` 生成候选 ZIP，记录完整实现 SHA／tree、SourceRevision、build inputs、锁和负载摘要。不得将脏脚本或不同 ZIP 的结果合成最终通过。

**已实现入口与执行命令：** 当前基线命令为：

```bash
python3.11 scripts/run_isolated_playback_integration.py --package <指定ZIP绝对路径> --scenario baseline --rows B01,B02 --evidence-dir <新基线证据目录>
```

`--scenario matrix` 已实现固定行集合，并保留 `--workspace`／`--keep-workspace` 与 `JF_PROBE_PACKAGE_PORT` 的归属规则。B 的完整矩阵命令仍使用 `python3.11 scripts/run_isolated_playback_integration.py --package <同ZIP> --scenario matrix --rows <上表完整ID逗号清单> --evidence-dir <新证据目录>`；行选择只接受固定 ID，不增加外部场景配置／DSL。本 Developer 轮实际只尝试了 MP4.C02.limited 与 MP4.C02.unspecified，因隔离 Jellyfin 未扫描首个项目在播放前退出，未覆盖任何 C02 测量行；精确 argv 与首败见本报告证据目录。主机没有 `python3.11` 可执行文件，该实机编排使用 Python 3.13.5；单元测试仍使用锁定 Python 3.11.17。此环境差异留给 B 审查，不能写成完成了三阶段取证。

### 最终检查点门槛（B）

B 固定完整候选、干净输入和同一 ZIP 后负责所有指定全量；不得交回 Developer。完整套件已含聚焦，不机械重跑聚焦。SDK 固定 10.0.401，Python 3.11 记录实际补丁版本／路径：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3.11 -m unittest discover -s tests -v
python3.11 -m compileall -q scripts tests
node --check scripts/package_playback_driver.mjs
python3 scripts/check_governance.py
git diff --check
```

Python 完整 discovery 在独立干净候选检出，不复制忽略的 artifacts／数据库／凭据；两项既有归档缺失 skip 如实列出、不计 PASS。工具及单元绿灯不代表实机通过。

同一 ZIP 必须取得全部矩阵／C／D／F 及 baseline B01／B02 的原始证据，按下方 B 独立复现补齐。共享媒体服务变化影响所有使用它的真实入口，故本 Task 明确追加下列原有完整门禁；若最终不改共享服务，需 B 先记录实际输入比对和影响判断再决定复用，Developer 不能自行省略：

```bash
python3.11 scripts/run_isolated_package_integration.py --package <同ZIP> --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir <包证据目录>
python3.11 scripts/run_isolated_scan_integration.py --package <同ZIP> --scenario all --evidence-dir <扫描证据目录>
python3.11 scripts/run_isolated_large_library_integration.py --package <同ZIP> --reuse-workspace <经核验已停止的现存1004项准备库绝对路径> --count 1000 --scenario all --reset-copied-fingerprints --evidence-dir <大库新证据目录>
python3.11 scripts/run_isolated_plugin_integration.py
python3.11 scripts/run_isolated_batch_integration.py --scenario suite
python3.11 scripts/run_isolated_configuration_integration.py --scenario all
```

前三个是包部署，后三个是原有开发部署，结果分别报告。后三个使用同候选的隔离检出／本轮拥有的新开发实例，按 [环境文档](docs/development-environment.md) 准备；用现有 `JF_PROBE_PORT`、新口令和只指向合成文件的两个库，不能接管当前主检出的旧 dev-env。配置图像通过现有 `STRM_CONFIG_EVIDENCE_DIR` 保存在本批忽略目录。命令本身没有 `--package`／`--evidence-dir` 时不得编造参数，stdout／stderr 在进程外完整留存。

大库使用既有复用入口：源库已停止／归属与前后摘要核验，保留全部 1004 项、不截取、不使用 `--fresh`；只在新副本归档／重置其指纹以形成首次信任前提，受影响项目局部修复，不重建原库或全库准备。默认保留复用副本和适用基线，不因 Task PASS 清理。`--count 1000` 是最低门槛，不是只测 1000 项。

镜像／源码／包及运行配置身份匹配才能复用；5.2 的旧输入不能自动证明新 HTTP／矩阵行为。Task 5.1 的远端 CI 决定保留，本 Task 不新增远端成功门槛、不自动推送。若触及插件共用链，先停止越界交 A／用户；后续保留以上完整原生播放／批量／扫描／安装及全部 1004 项，不借工具范围削减门槛。

### B 独立验证

B 审查完整 `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..Head`、候选／ZIP／运行身份和全矩阵原文，逐张打开全部必需截图，独立重数目标 ffprobe、核对源／地址／完整媒体流／五字段和重启先读后播。匹配完整的 Developer 实播可复用为矩阵结果，但不能代替 B 的全量责任或仅凭自报 PASS。

B 另在新归属视频实例独立复现：每种格式的 P01.04、P02.01、P03.02、P04.01、P05.01、P06.01.up／01.down、P07.01、P08.01／02／03、D06、F01／F02 完整旅程，以及 C02／C06 的 limited／full／unspecified 全部 12 个格式展开行。每项同样有实播／错误截图、原始计数、完整保存及重启核验；与全矩阵相同输入的这次运行可同时覆盖该行，不重复第二遍同样旅程。对“只改文件时间”“同 URL／同大小未知内容”的限制不作超合同的识别承诺。

若某必要行真实 FAIL 或无授权可解阻塞，B 可先 FIX REQUIRED，其余门槛 NOT RUN；修正保留 Task ID／Base，不能以发现问题为本 Task PASS。全部要求满足才 PASS，再重核全部 RO；满足则执行独立 Slice Final，提交一份 Closure Packet／SLICE READY FOR A REVIEW，A 最终决定前不关闭。

### 证据、预算与重跑规则

`.git/validation-evidence/<完整实现SHA>/<run-id>/INDEX.md` 保存版本／候选、精确 argv／cwd／环境／退出码／耗时、固定行清单和预期、每行前置快照、实际 ffprobe／转码、原始响应／媒体读取／完整原生流、五字段、全部原图及逐张查看结论、首败与恢复、归属／配置／触发器和正常退出。先归档原始日志／状态再清理本轮可清理资源，不能重复 5.2 的旧反馈缺原始服务器日志问题。完整签名 URL／token／Cookie／凭据／数据库与媒体不进普通提交。

本矩阵允许在**同一 Task 的多个真实工作轮**分批完成，不能把固定行数包装为一次短 smoke。每批明确列出的行用独立证据目录和可核验前提，不覆盖旧行；纯预算分批不改变同一最终候选和完整行集合。需要重新生成前提时只准备本批小型合成输入，现存全部 1004 项持续复用。固定候选证据完整时不再复制相同运行；新可执行输入依 T4 重取指定证据，纯报告后继只检查输入匹配并重跑文档消费检查，不机械重跑 Final。

Developer 每真实轮初始总上限 60 分钟／测试 15 分钟；B 为 90 分钟／测试 25 分钟，均非要求耗满。**每轮实际测试墙钟并集／实际总时间严格小于 50%**，构建、夹具、工具验收、等待健康／扫描／播放／重启及重试均计测试，重叠只计一次；调试器安装准备实耗另记、诊断运行计测试。启动前依据已发生的必要非测试工作留足余额；按 5.2 每次浏览器调用约 22～25 秒加准备／重启成本估算本批，优先少量完整旅程、先做关键误判对照。不得空等凑分母、将等待／排障测试改记审查或靠预借未来工作时间开跑。余额不足停止新测试、保存首败／状态，下一真实工作轮继续本 Task，不减少行或让 Developer 代跑 B 全量。

## 非目标

不修改插件成功条件／诊断／并发／指纹算法，不创建管理框架、独立调度器／运行按钮、通用场景引擎或新的验收生命周期；不扩大到音频 STRM、生产、JellyfinProxy／OpenList、跨版本／全格式／全客户端兼容、远端发布或重写历史。不把合法媒体误拒绝降为预期失败，不恢复旧 URL 冒充同目标恢复，不为非阻塞工具润色延长 Task。

## Developer Completion Report

- Changed Files：`scripts/run_isolated_playback_integration.py`（固定矩阵入口与视频专属 baseline；保留并纳入原工作区已有的电影库去重改动）、`scripts/isolated_media_server.py`、`scripts/package_playback_driver.mjs`、`tests/test_isolated_playback_integration.py`、`tests/test_isolated_media_server.py`、`TASK.md`。Task Base 至候选还包含先前同 Task 提交 `ef48e19d00310d2c8cdf1e3013a8ae0439ef596a`、`0a0342fbb22543c9083e91f6d299118a6af247f8`、`c134f0cfea1d627a8f3f45b9b5fea6e778eae732` 的矩阵／Range／驱动采集、D06／F01 账务和等长 MP4 合法 padding 实现；本报告不将 Slice 合同修订归为 Developer 改动。
- Implemented：baseline 仅保留 MP4／MKV 视频 STRM，默认 B01／B02；音频 STRM 专属夹具、音乐库、原生读取与 B03 接受路径退出当前合同，未知 B03 在任何工作区／容器副作用前拒绝。已实现固定视频决策矩阵、媒体 Range、浏览器原始观测及相关回归测试。未改 C# 成功条件、指纹算法或诊断，也未修改 Slice 合同。
- Tests and Results：实施前及交接文档更新后 `python3 scripts/check_governance.py` 均通过；Python 3.11.17 下 7 个受影响模块共 264 项通过（playback 59、media server 9、package 31、scan 74、large library 58、batch 24、configuration 9）；CI-F1／F2／F3 已知失败的聚焦回归通过。受影响 Python 文件 `compileall`、`node --check scripts/package_playback_driver.mjs`、入口 `--help` 与 `git diff --check` 通过。候选 Release ZIP 构建成功并经 `package_plugin.py --verify` 验证，SHA-256 `351d164753858ce39777e7e5d7c56f10f19e140d6de980706c4856ed435d99b4`。
- Tests and Results（真实反馈）：对候选 `f55c2d0d9b9e5489790b48c380908d3ef0460086` 运行 `MP4.C02.limited,MP4.C02.unspecified`，运行器退出码 1、耗时 291.9 秒；在 `prepare_matrix_rows` 扫描首个 STRM 项目阶段报 `The package instance did not scan the item 'Matrix MP4 C02 limited'.`，未进入 C02 实际测量／Web Play。两行均未测，不能算产品 PASS 或产品 FAIL；没有该轮实播截图，未进行看图。摘要保留于 `.git/validation-evidence/f55c2d0d9b9e5489790b48c380908d3ef0460086/run-20261021-01/matrix-c02/`；矩阵 JSON 未包含逐行结果，容器与本轮工作区正常退出／清理。未重试同一失败前提。
- Decisions：遵守用户撤出音频 STRM 与代理验收的授权；保留视频音轨和既有通用音频观察／播放代码。首败先交 B 判断，不把隔离扫描失败推断成插件行为，不放宽验收或自行扩展到产品修复。
- Remaining In-Slice Work：B 审查并处理首个真实矩阵前提失败；后续取得 C02 有效媒体实际播放、截图／逐张查看与三阶段①②③字段证据，再按合同完成其余 P／C／D／F 必需行。B 负责完整 C#／Python／部署／扫描／大库／批量／配置回归及独立验收；Developer 不自行 PASS。全部 RO 满足后才进入独立 Slice Final／A 审查；RO-4 继续按既有决定处理。
- Risks / Deviations：本机无 `python3.11`／LLDB／GDB／vsdbg／netcoredbg／dotnet-sos；矩阵编排用 Python 3.13.5，单元测试用 Python 3.11.17。当前 `scan_and_wait` 将项目查询的具体异常收敛为超时文案；本次 cleanup 前未保留 Jellyfin 原始日志，因此原因未定位。失败发生在播放前，不能据此验证 ColorRange 或 RO-3；完整矩阵、C# 全量、B 独立复现与远端 CI 均 NOT RUN，交 B 按合同处理。
- Candidate Package Source SHA：`f55c2d0d9b9e5489790b48c380908d3ef0460086`；Git tree `40cdea8e7230daa974d150102eda44d015a5c140`；ZIP SHA-256 `351d164753858ce39777e7e5d7c56f10f19e140d6de980706c4856ed435d99b4`。此处是实际构建／测试的完整候选，不代表 Task 或 Slice PASS。
- Head SHA：候选源码提交 `f55c2d0d9b9e5489790b48c380908d3ef0460086`（本报告随后以单独文档提交更新）。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO
Next: B REVIEWS THE DEVELOPER HANDOFF FOR TASK 5.3; ANY FIX REQUIRED CONTINUES THIS TASK
```

本检查点是 B 计划，不是产品 PASS 或 Slice Ready。实施后 B 只给 PASS／FIX REQUIRED；修正继续同一 Task，范围问题交 A。

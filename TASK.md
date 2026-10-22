# Task 5.3 — 视频八类决策的真实播放、误判取证与失败恢复

受已提交的 [Slice 5](SLICE.md) 约束，以 [开发流程](docs/development-workflow.md) 为准。实施阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)，规划／审查阅读 [B 经验](docs/agent-experience/task-planner-reviewer.md)。

```text
Task ID: 5.3
Parent Slice: 5
Status: FIX REQUIRED
Task Base: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94
Contract Checkpoint: 68e7bf01e7796fe9972838dfc0d8ed8283aacedd
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## B 合同重判与继续决定（2026-10-21）

B 已检查真实干净仓库、运行治理检查，并核对 A 已提交合同 `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`。决定 **CONTINUE WITH ADJUSTED SCOPE**：继续同一 Task 5.3／Base，保留 B FIX REQUIRED 及全部未完成行，按下方更新范围实施；不是产品 PASS。原 A 交接和 B 审查历史保留于上述合同及 `76adf423b70649624a75d6830482fc3f1ca70bba:TASK.md`。

实施先补最小同次字段诊断与必要入口修正，通过现有矩阵／原生 Web Play 取得真实字段后再修正已证实原因。不得直接删除 ColorRange 或其他字段来换取通过。先做 MP4.P02.01／MP4.C02.limited 的可达取证及修正反馈，必要时按真实预算分批；旧 FAIL、字段差异和每次重跑均保留，完整 116 行与所有最终门禁仍由 B 承担。

用户本轮要求开始执行，B 计划检查点提交并治理通过后由当前代理转 Developer 实施。实现者不得签发自己的独立 B PASS；交接真实实现 SHA／聚焦结果为 READY FOR B REVIEW，由独立 B 完成余下全量及审查。

## Goal

完成 Slice RO-1 剩余的可控媒体前提、RO-2 的 MP4／MKV 八类决策与指定子场景、RO-3 的真实 ColorRange 三阶段取证和失败恢复。用户继续在原生 Web 点击播放；插件应准确决定是否探测，返回正确当前内容／地址／必要媒体流，可靠保存并提交指纹，再播与重启后仍正确。交付物是下表逐行的真实播放结果及可复核原始证据。

不把“同地址内容换了”概括为总能识别：没有可比 SHA-1 且大小相同／不足时按合同跳过并记录限制。大小改变也不是总跳过：有效 SHA-1 相同才忽略大小，SHA-1 不可比且双侧有效大小不同时必须探测。有效视频被误拒绝仍为 FAIL；查明问题不等于产品行为通过。

本 Task 按 A 修订合同纳入同次字段取证、基于证据的有界产品匹配修正、必要最小脱敏诊断和已列入口修正；保留所有失败与未完成项，修正继续同一 Task，不删场景、不另建“工具完善 Task”。全部 RO 满足后停止造 Task，另做 Slice Final／Closure Packet 交 A，不自行关闭。

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
| `Services/ProbeExecutionContext.cs`、`Services/StrmPlaybackOptimizer.cs` 及直接必要的既有接入／保存代理 | DetailedLog 默认关闭；对同次编码器／保存成功入参／原生返回记录完整 PrimaryStreamIdentity，按确证的固定版本往返差异修正匹配；保留源、实际成功和保存／Manifest／条件提交保护。 |
| 对应现有 C# 测试 | 新增真实差异的回归；保持相同元数据保存失败、错误源／主流、权限、失败／取消／变化及恢复控制。 |
| 对应现有 Python 测试模块 | 按实际修改验证 Range 字节及响应头、旧路径兼容和真实证据缺失拒绝；假对象只证明采集控制，不冒充产品故障。 |

`package_environment.py`、旧 package／scan／large／plugin／batch／configuration 入口原则上保持；确需修改先由 B 记录实际原因、调用影响和回归追加，沿用本 Task。不为泛化、整理历史音频辅助代码或扩大工具测试覆盖而修改。上述有界产品接入与对应 C# 测试已纳入；依赖、镜像锁、工作流、治理工具、并发／指纹算法重构和通用诊断系统仍不在范围。

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

使用固定版本原文日志、原生只读响应及新授权的既有方法字段诊断；只在 DetailedLog 开启时记录必要字段和脱敏关联，不写完整 URL／凭据／私有路径，不增加探测。现有布尔值及另跑一次独立 ffprobe 均不能代替①②。允许在本轮独立诊断实例使用一个标准 .NET 外部调试器只读观察现有方法参数：`RecordResult(requestedPath, result)`、原生保存成功后调用的 `RecordPersistedMediaStreams(itemId, streams)`、`IsPersistedProbeResult(stream)`；关联当前 ProbeExecutionContext 的项目／源／URL。不能改对象、求值有副作用函数、调用探测方法、跳过异常、改变返回值或安装另一插件。

规划时主机尚无上述调试器；不编造安装／附加命令为现成能力。首个聚焦取证前记录实际工具来源／版本、按其真实帮助固定命令、PID／容器归属及只读参数清单。调试暂停的时序单列；诊断运行只用于字段定位，不能充当未附加调试器的正式播放／成本门槛。主验收固定本次真实提交生成的正式 ZIP／镜像，必要诊断包含在同一正式候选中按既有配置开关，旧失败 ZIP 保留；额外调试资料只存本机忽略目录。

同次资料必须在现有方法内捕获；不能用重新探测的相似结果补写或另建诊断框架。保留真实 FAIL、五项判定及可读取的失败状态，取得实际差异并对照固定源码后才有界修正；超出 A 授权的需求交 A。未解决阻塞前不盲跑整个昂贵矩阵和 Final。

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

C# 接入改变时使用 SDK 10.0.401，Developer 执行：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore --filter 'FullyQualifiedName~ProbeExecutionContextTests|FullyQualifiedName~PlaybackOptimizerTests'
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
```

若改到代理则加其直接影响的现有测试类；聚焦回归覆盖新增诊断脱敏／开关、实际往返差异及旧失败保护，不用假对象宣称实机通过。本机 Python 3.11 可用绝对路径 `/opt/py311/python/bin/python3.11`，记录真实补丁版本；示例 python3.11 可替换为该实际解释器，不虚报 PATH 缺失为不可用。

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

镜像／源码／包及运行配置身份匹配才能复用；5.2 的旧输入不能自动证明新 HTTP／矩阵行为。Task 5.1 的远端 CI 决定保留，本 Task 不新增远端成功门槛、不自动推送。本次已经 A 授权并触及插件共用链，以上完整原生播放／批量／配置／扫描／安装及全部 1004 项成为必需门槛，不借工具范围削减；新的正式候选按 T4 核验，不能自动沿用旧实现结果。

### B 独立验证

B 审查完整 `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..Head`、候选／ZIP／运行身份和全矩阵原文，逐张打开全部必需截图，独立重数目标 ffprobe、核对源／地址／完整媒体流／五字段和重启先读后播。匹配完整的 Developer 实播可复用为矩阵结果，但不能代替 B 的全量责任或仅凭自报 PASS。

B 另在新归属视频实例独立复现：每种格式的 P01.04、P02.01、P03.02、P04.01、P05.01、P06.01.up／01.down、P07.01、P08.01／02／03、D06、F01／F02 完整旅程，以及 C02／C06 的 limited／full／unspecified 全部 12 个格式展开行。每项同样有实播／错误截图、原始计数、完整保存及重启核验；与全矩阵相同输入的这次运行可同时覆盖该行，不重复第二遍同样旅程。对“只改文件时间”“同 URL／同大小未知内容”的限制不作超合同的识别承诺。

若某必要行真实 FAIL 或无授权可解阻塞，B 可先 FIX REQUIRED，其余门槛 NOT RUN；修正保留 Task ID／Base，不能以发现问题为本 Task PASS。全部要求满足才 PASS，再重核全部 RO；满足则执行独立 Slice Final，提交一份 Closure Packet／SLICE READY FOR A REVIEW，A 最终决定前不关闭。

### 证据、预算与重跑规则

`.git/validation-evidence/<完整实现SHA>/<run-id>/INDEX.md` 保存版本／候选、精确 argv／cwd／环境／退出码／耗时、固定行清单和预期、每行前置快照、实际 ffprobe／转码、原始响应／媒体读取／完整原生流、五字段、全部原图及逐张查看结论、首败与恢复、归属／配置／触发器和正常退出。先归档原始日志／状态再清理本轮可清理资源，不能重复 5.2 的旧反馈缺原始服务器日志问题。完整签名 URL／token／Cookie／凭据／数据库与媒体不进普通提交。

本矩阵允许在**同一 Task 的多个真实工作轮**分批完成，不能把固定行数包装为一次短 smoke。每批明确列出的行用独立证据目录和可核验前提，不覆盖旧行；纯预算分批不改变同一最终候选和完整行集合。需要重新生成前提时只准备本批小型合成输入，现存全部 1004 项持续复用。固定候选证据完整时不再复制相同运行；新可执行输入依 T4 重取指定证据，纯报告后继只检查输入匹配并重跑文档消费检查，不机械重跑 Final。

Developer 每真实轮初始总上限 60 分钟／测试 15 分钟；B 为 90 分钟／测试 25 分钟，均非要求耗满。**每轮实际测试墙钟并集／实际总时间严格小于 50%**，构建、夹具、工具验收、等待健康／扫描／播放／重启及重试均计测试，重叠只计一次；调试器安装准备实耗另记、诊断运行计测试。启动前依据已发生的必要非测试工作留足余额；按 5.2 每次浏览器调用约 22～25 秒加准备／重启成本估算本批，优先少量完整旅程、先做关键误判对照。不得空等凑分母、将等待／排障测试改记审查或靠预借未来工作时间开跑。余额不足停止新测试、保存首败／状态，下一真实工作轮继续本 Task，不减少行或让 Developer 代跑 B 全量。

## 非目标

不修改已授权匹配修正之外的成功不变量、并发／指纹算法，不创建通用诊断／管理框架、独立调度器／运行按钮、通用场景引擎或新的验收生命周期；不扩大到音频 STRM、生产、JellyfinProxy／OpenList、跨版本／全格式／全客户端兼容、远端发布或重写历史。不把合法媒体误拒绝降为预期失败，不恢复旧 URL 冒充同目标恢复，不为非阻塞工具润色延长 Task。

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

## Developer Correction Report（FIX REQUIRED 轮，2026-10-21）

- Changed Files：仅 `scripts/run_isolated_playback_integration.py` 与 `tests/test_isolated_playback_integration.py`（8 个实现提交：`41d55bf3ac2026a96b7f30055900cc935d8a8ee4`、`287b5736ee7dcc782848290d41b34d93b5071b23`、`62e7fa724e3491ce789bd30cdd5c99c8422c7417`、`cb324cb8bdc225c2fce7d5c777d4b906b72d5bc3`、`56945291e747f90bbb4ab4820b96a30908cc886b`、`ecf7865ea6dd8f668ef50963e9742f2a3238a0fe`、`12b6ef5555244a5498b27985b6ade09b6460ae36`、`772f1be6c2ea642473bdb8fb02eca1cf0769d6f7`、`1864cdcc7e33d7a8c582c0d941ff4a38d159480c`、`a5cc0a49ffc2f218edada99a46cac3fe16c12d34`、`4e235f569dbe050f818bb206d1273e762940250f`）。未改任何 C#、插件成功判定、依赖、镜像锁或工作流。
- B53-1：新增 `raw_item_query` 保留每次原始查询响应／条目列表／匹配与服务器日志尾，替换把失败收敛为超时文案的 `pkg.scan_and_wait`；D06 `native_static_stream_read` 未定义的 `contentType` 已修；插件配置改回既有已验证的无版本段 `/Plugins/{id}/Configuration` 路由；每次驱动运行后重新登录，消除浏览器登录撤销 API token 导致的观察查询 500。
- B53-2：manifest 重写改用显式 token 语义（`DELETE` 明确删除、缺席保留旧值），修正 P03.03 大小写变化、P03.04／P05.01／P07 的真实删除方向、P04.03 尺寸删除、P06 每方向写入其实际服务的伙伴字节哈希、C02 改为 URL A→B（`manifest-url`，观察新 URL 文件）、F01 失败窗口保留预备真实 B 身份、P02.02／02.04 观察各自新 URL 的文件。
- B53-3：固定 URL 的 switch／F02 换字节改为经本行拥有的 staging 副本原子替换，共享 partner 文件不再被消耗；每行旅程前 `reset_row_media` 重建该行 A 基线并移除 404 目标残留。
- B53-4：以固定镜像 FFmpeg 实测确定生成方案（MP4 tv 需完整 bt709 VUI 三元组；unspecified MKV 必须经 VUI-less MP4 编码 remux），新增 `require_actual_color_range` 在生成后核验实际 ffprobe 输出，错配夹具直接终止运行；fix11 实测 limited 输出 `color_range: tv`、unspecified 输出为 null。
- B53-5：`finally` 收尾先于 reconciliation／cleanup 归档原始 ffprobe 行、完整 Jellyfin 服务器日志与媒体容器日志到证据目录；重启对账快照保留完整原生流对象（不再 11 字段投影）；P01 数据库备份改为直接写入证据目录（归属保护保持不变）。
- 行定位：原生库命名剥离行名尾词（"… C02 limited" 索引为 "Matrix MP4 C02"），行定位改为按每行唯一 STRM 路径匹配，不依赖条目名；矩阵准备前显式触发一次原生库刷新。
- Tests and Results：`python3 scripts/check_governance.py` 每次提交前通过；Python 3.13.5（宿主无 python3.11）`unittest test_isolated_playback_integration` 73 项通过（含 14 项新增矩阵前提／staging／诊断／路由用例），`test_isolated_media_server` 9 项通过；`compileall`、`node --check`、`git diff --check` 通过。未运行其他模块、C# 全量与完整矩阵，交 B。
- 真实反馈（候选 `4e235f569dbe050f818bb206d1273e762940250f`，ZIP SHA-256 `10b789a97537080c6bc5514db5fdd99d566b00f26231446896515779349e0347`）：`--rows MP4.P02.01,MP4.C02.limited` 退出码 1、462.3 秒。两行首次信任均成功（ffprobe delta 0、推进 5.39／5.38 秒、FirstTrust 事件、五字段指纹与 A 身份一致，截图执行者逐张打开：MP4 A 标记、时间码 00:00:05.667）。测量窗口触发产品阻塞：插件 1 次原生探测成功（ffprobe 原文、媒体服务 206 全区间）、encoder primary True、persisted primary True、address persisted True，但 `returned primary matches probe False`，插件拒绝有效结果并使 PlaybackInfo 返回 500（`Jellyfin did not save a usable media source for the current STRM version`），Web 客户端弹出原生播放错误对话框；两行失败截图已逐张打开核对（原生「播放错误／处理请求时发生错误」）。即 Slice 5 已知返回主流误判在真实有效媒体上复现。证据与完整原始日志保留于 `.git/validation-evidence/4e235f569dbe050f818bb206d1273e762940250f/run-20261021-fix11/`（含 `DEVELOPER-FINDING.md` 与完整 `server-logs/`）；fix1～fix10 诊断轮各目录附 `DEVELOPER-RUN-NOTE.md`。
- Decisions：按合同停止昂贵矩阵（有效媒体误拒绝属 RO-3／AC-4 领域，产品修正须 A／用户授权）；不修改 C#，不放宽断言，不把产品 FAIL 写成工具问题。矩阵前提修正与真实复现证据一起交 B。
- Remaining In-Slice Work：B／A／用户决定产品误判的处置；处置前其余 P／C／D／F 行 NOT RUN。B 负责完整回归与独立验收；Developer 不自行 PASS。
- Head SHA：修正候选源码提交 `4e235f569dbe050f818bb206d1273e762940250f`（本报告随后以单独文档提交更新）。

## B Review Result

以下保留上一固定候选的独立 B **FIX REQUIRED**，未因下方 Developer 修正报告变为 PASS。最新修正候选与未完成门槛见文末；下一步由独立 B 审查。

```text
Reviewed: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..f7ee96539f81c0a80640482b7d2d959f2a8feb69
Implementation Candidate: 4e235f569dbe050f818bb206d1273e762940250f
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: A / USER DECIDES PRODUCT REPAIR SCOPE; CORRECTIONS REMAIN IN TASK 5.3; B RETAINS ALL FINAL GATES
```

### 复审身份与范围（2026-10-21）

开始时真实工作区干净，main 超前 origin/main 44 个提交；治理检查 PASS。AGENTS／必读维护文档／Slice 合同与上一轮已读版本相同，本轮重新核对流程及当前交付；修正仅改变顺序入口、对应 Python 测试和 Task 报告。完整 Base..Head 仍为 7 个改变文件；复审实际修正差异并保留完整 Task 差异。源码候选至报告 Head 的可执行／测试／依赖／锁／工作流输入完全相同，未改 C#。Slice／Task ID、Base、目标和验收保持。

上一轮 B 决定及 B53-1～B53-5 原文保留于 `5e71de5eedc87e652f26d78feeef1161995f9130:TASK.md`。下述为当前结论，不将原失败和缺日志记录改写成 PASS。

本轮本机索引：`.git/validation-evidence/4e235f569dbe050f818bb206d1273e762940250f/b-rereview-20261021T145548Z/INDEX.md`。包含输入及证据摘要、完整差异、干净候选、完整 Python 原文、逐图查看结论和独立日志重数。将 `/tmp/pkg53` 中原 ZIP／manifest／sha256 复制到本索引下稳定 `package/` 保留；仍是原 ZIP，SHA-256 `10b789a97537080c6bc5514db5fdd99d566b00f26231446896515779349e0347`，SourceRevision 与候选相同。资料只在本机，不随 Git 发布。

### 已核验的真实交付与限制

B 已打开 Developer fix11 的完整原始服务器日志、矩阵 JSON、原始浏览器输出／首次信任响应和全部 6 张截图，按项目／源／完整日期和目标 URL 独立对账；未仅凭报告标签接受。

| 对象 | 本次独立核验 |
|---|---|
| 扫描 | P02.01 按唯一 STRM 路径在 3.5 秒找到，C02.limited 在 0.1 秒找到。列表实际显示后者名称为 `Matrix MP4 C02`，STRM 路径仍包含 `limited`，证实该样本按名称查找会失配；路径匹配解决了本次前提。不能据此倒填旧轮缺失日志。 |
| 首次信任 | 两行 ffprobe before=after=2、delta=0；FirstTrust／calls=0；项目／源和五字段对应真实 A（SHA-1 `adb64ff6503f355ac209e5cd06029dd19b2655f4`，Size 1660446）。实际推进 5.393645／5.383535 秒、88 解码帧、320×180；四张图均打开，MP4 A 画面从 00:00:00.333 到 00:00:05.667。 |
| P02.01 换地址 | 原日志 14:35:35.102 启动目标 `switch-copy-mp4.mp4` 的 1 次 ffprobe；14:35:38.520 对应项目出现五项判定 `1 / True / True / True / False`，随后原生 POST PlaybackInfo 500；媒体日志为对应文件完整区间 206。浏览器 advanced=false，失败图已打开，显示原生“播放错误／处理请求时发生错误”。本行 FAIL。 |
| C02.limited 换地址 | 原日志 14:38:05.299 启动目标 `baseline-mp4-limited.mp4` 的 1 次 ffprobe；14:38:06.440 同样五项判定及 PlaybackInfo 500；对应文件完整区间 206。失败图已打开，显示相同原生错误。本行 FAIL。 |
| ColorRange 输入 | 本轮记录的两种格式 C02／C06 共 12 个目标均分别为 tv／pc／null，limited／unspecified 错配已在该次夹具记录中纠正；不是 12 条播放或三阶段取证 PASS。 |
| 原日志与收尾 | 新轮完整服务器日志／原始 ffprobe 行及媒体日志实际存在；总共 4 次目标 ffprobe（准备 A 两次、换地址各一次），不是每行 4 次。归档发生在清理前；JSON 记录双服务 exit 0、无 OOM、归属对账 CLEAN、本轮工作区 CLEANED。B 未再次操作任何实例或现存全部 1004 项库。 |

这是现有 `--scenario matrix --rows MP4.P02.01,MP4.C02.limited`→原生 Web Play→原生 POST PlaybackInfo 的真实可达失败。P02.01 只是给有效 A 内容换地址，属于“URL 变化即探测且当次可播放”的必要需求；C02.limited 对应显式 ColorRange 的实际输入。该结果已越过旧扫描阻塞，属于产品拒绝结果造成的播放 FAIL。

**已知的是失败条件，具体差异字段仍未知。** 服务器诊断证明本次存在匹配探测、必要主流和保存／地址信号，源码在 `returnedPrimaryMatchesProbe` 不成立时抛出异常，早于新指纹提交。日志没有①编码器返回／②保存成功入参／③返回主流的完整同次字段对照，不能直接认定根因就是 ColorRange，也不能用生成夹具时另一次 ffprobe 代替。失败窗口在 console 错误检查处提前退出，没有生成失败后的 observation／完整原生状态／五字段，因此旧指纹保护和原生保存的实机最终状态仍未独立闭合。

### 当前阻塞与同一 Task 的修正边界

1. **P1 产品阻塞，交 A／用户决定。** RO-2／RO-3、AC-2／AC-4 的有效媒体实际播放失败，Task 不能 PASS。当前 Slice 明确不授权修改插件成功判定，B 本轮不扩大授权。提交给 A 的事实为上述两条可达失败、固定候选／ZIP、原始日志和已查看图像；由 A／用户决定是否在同一 Task 5.3 内授权查明字段往返及产品修正。修改仍须保留真实成功、原生保存、当前 URL／主流、Manifest 稳定和条件提交，不以删除断言、关闭匹配、预期失败或伪造流完成合同。三阶段缺口一并交接，不能声称根因已闭合。

2. **P1 必要失败状态仍在采集前被断言丢弃（B53-5 未完全关闭）。** `play_once` 在 921 行遇到 500 即抛出，早于 930～947 行计数、原生状态及指纹读取／保存；fix11 两个 window 目录确实均无 observation.json。应在现有入口尽可能先保留响应、计数、只读状态及每项读取错误，再保留原 FAIL 并抛出。无需再造采集框架，也不能放宽正常播放断言或补写已删除的数据库状态。

3. **P1 P07.04／P07.05 仍偏离固定输入（B53-2 部分未修）。** 1697～1698 行继续用 39 位 L，合同两行明确为 40 位非十六进制 X；新增 `test_p07_keeps_the_contract_directions` 也在断言 L。恢复合同输入并验证实际写出的 STRM。其余已修的删除语义、哈希方向、C02 URL 变化和 F01 身份保留有效；本轮不降低行集合或把测试断言当成合同修改。

4. **P1 D04 正常入口选择了 STRM，普通文件对照不能成立。** `scenario_matrix` 为 D04 也写版本化 STRM（2575～2579 行）；`prepare_matrix_rows` 对所有行走只匹配 `/media/strm/<name>.strm` 的查询（2504 行），不会选择新普通文件库中的 `/media/local/regular-*` 文件；D04 的准备分支还在建立 sourceKey 前 continue（2527 行），随后 `play_once` 必读 sourceKey。按 D04 已有普通文件路径／真实原生源完成定位与重启地址对账；不能以同名 STRM 的播放证明普通媒体委托。此项来自既有固定 D04 调用链的静态审查，尚未新跑实机，不是新增场景。

5. **P1 新增 auth 字段会进入成功行的结果日志。** `play_once` 在 948 行把完整 Authorization 字符串加入返回 observation，`trust_play` 将其整体交给正常旅程的 firstTrust（2208 行），成功结果最终写入 matrix-result.json 并打印（1309／1313 行）。现有成功矩阵行会因此输出 token，违反日志不含凭据的约束。删除证据对象中的凭据传递；重新认证可以留在局部变量，不需要通过 observation 返回。本轮两条失败结果丢弃 firstTrust，未在其最终 JSON 中观察到该字段，不宣称发生了远端泄露；结论为正常成功路径的静态阻塞，不输出任何实际凭据。

已修正的稳定 STRM 名称、D06 变量、原生配置路由、staging 复制及逐行 A 复位、完整流快照和原日志归档均予以保留。P01／D06／多行完整旅程尚未实机验收，不签发其 PASS。修正限当前入口交付所需行为，不增加管理系统、通用框架或非阻塞润色 Task。

### 固定候选门禁、复用与下一步

- B 新运行候选独立干净检出的 Python **3.11.10** 完整 discovery：345 项，343 PASS、0 FAIL、2 SKIPPED（缺忽略发布包的两个 assembly-version 控制，保留 SKIPPED）。compileall、Node 语法、原 ZIP／sidecar 核验、输入一致性、治理及差异检查通过；精确 argv／cwd／时序／退出码及原文日志见本轮索引。
- 原 fix11 的匹配失败证据已独立核验并用于拒绝候选；不是本轮 B 新运行的实机，也不代替 PASS 所需的 B 关键独立复现。依据流程“已有明确阻塞时可先拒绝”，本轮不为确认同一未授权产品阻塞再次运行同批实机；完整 C# 门禁、B 新实机关键复现、其余矩阵／baseline、package／scan／全部 1004 项 large、plugin／batch／configuration 与 Slice Final 均 NOT RUN。责任仍属 B，产品修正后按固定新候选补齐全部指定门槛，不交回 Developer。
- Developer 可在现授权内修正上列必要入口问题，运行修改／直接影响的反馈及少量完整旅程，明确省略项。产品修改和扩大诊断构建须先有 A／用户授权；不盲跑其余昂贵矩阵。若需要三阶段观察，仍按现合同从实际 Web Play 触发并使用已授权标准只读调试方案，不能猜构造入口或调用内部探测函数。
- RO-1 部分交付，RO-2／RO-3 存在上述真实 FAIL 与证据缺口，RO-4 保留 Task 5.1 既有决定。保持同一 Task 5.3／Slice 5／Base；本轮不规划新 Task、不出 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭。待全部 RO 真正满足后才提交 A 最终审查。
- 每轮测试墙钟并集须严格小于本轮实际总时间 50%；本轮未人工等待凑分母，账务见本机 timing-ledger.json。仅 Task 审查文档形成普通本地提交，提交后再核验治理与干净状态；不推送、不改历史、不操作生产或准备库。

## Developer Repair Report（A 授权后的同 Task 修正，2026-10-21）

- **交接状态：READY FOR B REVIEW。** 当前代理按已提交 B 计划实施，不能签发自己的独立 B PASS；Task／Slice ID、Base、合同检查点及历史 FAIL 不变。最终实施候选为 `316e7ebd756ce2cb685ab44fd453a03c6c777b8f`，报告后继仅修改 Markdown。
- **修改范围：** `ProbeExecutionContext.cs`、`StrmPlaybackOptimizer.cs`、对应 `ProbeExecutionContextTests.cs`、既有 `run_isolated_playback_integration.py` 与其测试。必要字段诊断受既有 DetailedLog 控制，默认不开启；只记录 33 个身份字段及项目／源／URL 哈希。修正失败时先存 observation 再断言、P07.04／05 恢复 40 位非十六进制输入、D04 按真实普通文件路径和源定位／重启核验、移除返回对象中的 auth；未修改本轮共享驱动、媒体服务、依赖、镜像锁或工作流。
- **原因及有界产品修正：** 诊断提交 `b94618464408dbdb89f72b5594587c9b7e2313e9` 从现有 `MP4.C02.limited` 原生 Web Play 取得同一次编码器／成功保存入参／返回主流的完整 33 字段。①与②完全相同，③仅 `ColorRange` 从 `tv` 变成 null；固定原生源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6` 的 `MediaStreamRepository.Map` 双向均未映射该字段。产品修复提交 `82551cf2278535c4daac8e02cbe49ec85d60db3a` 仅允许已精确成功保存后读回缺失此字段，其他 32 字段仍相等；非空异值、宽度／索引变化、无精确保存及错误项目均不放行。保留原地址／保存／Manifest 稳定和条件提交门槛，无额外探测或成功旁路。
- **聚焦反馈：** SDK 10.0.401 锁定 restore、Release build（0 warning／error）、format verify 通过；直接受影响 C# context／playback 49 项通过；实际 `/opt/py311/python/bin/python3.11` 为 Python 3.11.10，最终 playback 工具 77 项通过，修改文件 py_compile、治理与差异检查通过。未用聚焦结果代表完整套件。
- **诊断运行的限制：** b946184 的 C02 因 300 秒预算发 SIGINT，退出 -2，含收尾 301.67 秒；三阶段字段已取得，但旅程未完成，原 matrix-result 的空状态／缺行结果保留，归类 BLOCKED／不计 PASS。仅首次信任的两张截图可用并已打开；不补写未完成的失败 observation／截图。
- **修复后真实反馈（82551cf）：** 同一既有入口只选 `MP4.C02.limited`，234.64 秒、退出 1。首次信任／URL 变化窗口／再播的目标 ffprobe 分别 0／1／0，实际播放推进 5.403／5.352／5.360 秒，无控制台或状态读取错误。三阶段再次只有上述字段差异，本次原生探测被接受；当前 URL、Video＋Audio 已保存，新五字段为目标真实 SHA-1／Size，随后再播保持相同。全部 6 张原图已实际打开：首次为 MP4 A，后两阶段为 MP4 LIM，每对画面时间推进至少 5 秒；服务器另有 3 次原生转码启动，不混入 ffprobe 数。
- **该次整体仍为 FAIL：** 再播后、重启前 `freeze_state` 使用被浏览器登录撤销的旧 token，原生只读查询被拒绝；没有完成重启先读／重启后播放，因此该 C02 行仍未通过。最终提交 316e7eb 在既有冻结方法内重新认证后读取，补充新 token 使用和读取失败仍拒绝的控制测试；不把 token 写入结果。该入口修正的真实重跑为 **NOT RUN**：本轮剩余测试余额不足以再做完整准备／播放／重启，不预借未来时间。B 在固定最终候选首先复核该完整行，再完成其余门禁。
- **固定交接包：** 从干净 316e7eb 构建 `candidate-package/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，SourceRevision 为上述完整 SHA，ZIP SHA-256 `a34b73957118a29c177ec4e3d06886690ff6b3b634b6d7f4fcdea8617ac77c97`，buildInputs SHA-256 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`。它尚无真实安装／播放验收；82551cf 的原始实播仅作对应输入反馈，不升级为最终包完整结果。
- **证据：** 本机 `.git/validation-evidence/43b9ff9/developer-20261021T152940Z/INDEX.md`，含 commands／环境、两个原始实机结果、服务器日志／ffprobe 原文、完整三阶段字段、33 字段差异及固定源码摘要、五字段／完整原生状态、截图逐张查看记录、三个独立包与 sidecar、资源对账及时间账本。两次新归属容器均正常退出 0、无 OOM、CLEANED，对账 CLEAN；生产实例和现存全部 1004 项准备库未操作、未重建。
- **B 保留的完整责任：** 当前无完整矩阵 PASS；其余 115 个规范 ID 及 baseline B01／B02 本轮 NOT RUN。最终候选完整 C#／Python、baseline／全部 P／C／D／F、package／scan／现存全部 1004 项 large、plugin／batch／configuration、独立关键复现、全部截图核验及完整 `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..Head` 审查均由独立 B 承担。匹配证据按实际输入复用；本轮未运行这些全量，不交回 Developer，不签发 Task PASS／Slice Closure／A 最终决定。

## 交付复核决定（2026-10-21，FIX REQUIRED）

用户要求开始审核后，核对真实干净仓库、必读文档、已提交合同、完整 Task Base..Head 差异和原始交接资料。**本轮由上一轮实现者做交付复核，不能冒充独立 B 审查或签发独立 B PASS**；上一独立 B 的 FIX REQUIRED 保留，独立 B 完整门禁与关键复现仍待完成。已发现确定的必需场景阻塞，当前 Task 改为 FIX REQUIRED，修正继续同一 Task／Base，不新建 Task。

```text
Reviewed Range: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..ed56eaf94bf6cee39bcad9c2588158e485790a58
Implementation Candidate: 316e7ebd756ce2cb685ab44fd453a03c6c777b8f
Decision: FIX REQUIRED (delivery self-review; independent B decision still pending)
```

### 当前阻塞项

| ID／级别 | 真实入口与原因 | 是否满足当前需求／修正边界 |
|---|---|---|
| DR53-1／P1 | 已注册的 MP4／MKV.P08.03 经 `prepare_matrix_rows` 第 2525 行将 `row["item"]` 替换为原生项目字典；`apply_matrix_change` 第 1931 行仍用字符串加该字典构造 staging 路径，必然抛 TypeError。该分支由正常扫描、首次信任后进入，不是假造内部调用。 | 不满足原字节重写／重放不触发探测的完整旅程。沿用已有稳定 `strm_name` 等真实路径身份，补覆盖扫描后实际 row 形态的直接控制，不另造工具框架。当前为源码确定错误，未声称本轮实机复现。 |
| DR53-2／P1 | D02 在第 2400 行重新启用插件、D03 在第 2428 行恢复 PlaybackAutoCheck=true 后，才调用 `d_row_restart`；两者也没有禁用状态下的 second-play。MP4／MKV 都受影响。 | 即使修正鉴权后显示 PASS，也不能证明合同要求的禁用／关闭检查状态下再播和重启后播放。保留该行前提直到要求的再播、冻结、重启先读及实播结束，再按既有范围恢复配置并核验。 |
| DR53-3／P1 | `play_once` 第 926 行只更新自身局部 auth；D04／D05 随后第 2445／2465 行仍把外层旧 auth 传给 `current_source_key`，D02／D03 的恢复请求同样使用旧 auth。最终提交只补了 `freeze_state` 的认证，未覆盖这些已注册路径。 | 不满足委托行的后续只读核验／完整旅程。既有原始 C02 日志已证明浏览器登录撤销旧会话；本项是沿相同登录链的源码审查，不冒充新 D 行实机结论。修正必要请求边界并覆盖成功读取和真正读取失败仍拒绝，不把凭据加回结果。 |

### 已核验结果与保留门禁

- 固定 ZIP 实际 SHA-256 与 sidecar／报告一致：`a34b73957118a29c177ec4e3d06886690ff6b3b634b6d7f4fcdea8617ac77c97`；316e7eb 到审查 Head 只改 SLICE.md／TASK.md。核对了原诊断服务器日志及固定原生源码摘要；同次 33 字段仅 ColorRange 丢失的依据成立，窄范围产品修正未见本次新增的确定错误，但不据此宣称 RO-3 全部通过。
- **本轮实际完整回归：** C# 205 passed／0 failed／0 skipped；Python 3.11.10 在独立干净 Git archive 候选检出下发现 349 项，347 passed、2 SKIPPED（`test_assembly_version_mismatch_is_rejected`、`test_read_assembly_version_reads_a_real_assembly`：发布归档不存在），跳过不计 PASS。未复制忽略的 artifacts／数据库／凭据。clean compileall、Node 语法与差异检查通过；治理在审查前及报告提交后核验。没有新增测试或修改实现。
- 原 Developer 诊断中断仍为 BLOCKED／未完成，82551cf 的 C02 整体仍为 FAIL；旧截图与字段资料只用于其匹配输入的历史反馈，不合并成最终包 PASS。本轮没有新实机播放／截图，不声称独立关键复现已完成。
- 按合同“已有明确阻塞可先拒绝”停止昂贵门禁；最终候选 C02 完整重启、baseline／全部 116 行、package／scan／现存全部 1004 项 large、plugin／batch／configuration、独立关键复现和 Slice Final 均 **NOT RUN**。这些最终责任仍属 B；修正后 Developer 仅提交改动直接影响的控制与选定完整旅程，B 在固定最终候选完成／核验复用全部门槛，不把全量交回 Developer。
- 本机索引：`.git/validation-evidence/ed56eaf94bf6cee39bcad9c2588158e485790a58/delivery-review-20261021T231318Z/INDEX.md`；精确命令、源码可达路径、原始测试输出／跳过原因、候选和历史结果核验及时间账务均保留。未启动或操作任何容器、生产实例或现存 1004 项准备库；不推送、不改历史。当前仍有 RO-2／RO-3 阻塞，不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。

## Developer Correction Report（DR53-1～4 修正，2026-10-21／22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94`，保留上一轮 FIX REQUIRED 与全部历史 FAIL／NOT RUN；本代理不签发独立 B PASS。实现提交：`95265a229d1362e1a8c3de053f6543d79ff16c8a`、`292a369207d7a24d28d132d66434eeb4acb37919`；报告随后以单独文档提交。
- **Changed Files：** 仅 `scripts/run_isolated_playback_integration.py` 与 `tests/test_isolated_playback_integration.py`。未改 C#、共享驱动、媒体服务、依赖、镜像锁、工作流或治理工具；未改 Slice 合同。
- **DR53-1（P08.03 重写）：合同描述的 TypeError 不可复现，但确有真实缺陷。** `"rewrite"` 同时列在 `if kind in ("manifest", "manifest-url", "comment", "rewrite", "d06")` 元组中，因此专用 `elif kind == "rewrite"` 分支是**不可达死代码**，扫描后 `row["item"]` 为字典也不会被使用。以修正前源码 `git show 7eb9626:…` 实测：规范 manifest 往返字节相同；带 `# Modified:` 注释行的 manifest 被重建后**字节改变**，却仍记录 `contentSha256Unchanged: true`。修正为让 `rewrite` 走自己的可达分支：复制当前精确字节经本行拥有的 staging 文件 `os.replace`，校验 SHA-256 未变，并记录结果 STRM 身份（`path`／`url`／`sha256`）；`mtime` 分支同样记录身份。新增 `RewriteApplyTests`（2 项）使用非规范 manifest（size 行在 sha1 前、含额外注释行）在修正前失败、修正后通过。真实运行 `MP4.P08.03`（`run/`，退出 0，墙钟 271.0 秒／报告 269.5 秒）首窗／再播／重启后 ffprobe 全为 0，推进 5.357／5.385 秒，`apply.kind=rewrite`、`contentSha256Unchanged=true`、重写摘要与冻结指纹一致，对账 CLEAN；8 张截图已逐张打开（MP4 **A** 标记，00:00:00.600→00:00:05.933）。该实跑**不能**区分修正（规范 manifest 修正前后皆往返相同），判别证据是上述单元控制。
- **DR53-2（D02／D03 禁用态旅程）：** 两行现于插件禁用／`PlaybackAutoCheck=false` **期间**完成第二次原生播放、`freeze_state`、重启、只读比对与重启后播放，之后才恢复配置并核验恢复结果；D02 在重启旅程后再核一次插件状态，D03 在恢复前再核一次 `PlaybackAutoCheck` 仍为 false。控制：`test_the_delegation_journeys_read_after_the_playback_boundary`、`test_d02_and_d03_restore_the_configuration_only_after_the_restart_journey`。D02／D03 真实行本轮 **NOT RUN**（预算）。
- **DR53-3（真实播放后的鉴权边界）：** 新增单一局部 `refresh_auth()`，在所有真实 Web Play 之后的原生请求边界使用（`play_once`、`freeze_state`、窗口后指纹读取、重启只读、D02～D06 恢复调用）；token 只作局部值，不进入 observation／结果，不序列化任何凭据，真实读取失败仍抛出。控制覆盖新 token 确被使用、失败读取仍拒绝、D02～D06 内不再出现 `pkg.api_auth()` 旧边界。受影响的 D 行真实重跑本轮 **NOT RUN**（预算）。
- **DR53-4（D04 普通媒体）：** 新增 `native_item_path(row)` 使定位决策显式可测：D04 解析 `/media/local/<普通文件>`，其余行走版本化 STRM（`None`），同名 STRM 条目不能顶替普通媒体对照。真实运行 `MP4.D04`（`run-d04/`，退出 0，墙钟 246.0 秒／报告 244.5 秒）：3.0 秒按真实文件路径定位，原生已备 `['Audio','Video']`，原生播放／再播／重启后均推进 5.351／5.340 秒、插件事件 0、ffprobe 0，`strm` 身份记为 `ordinaryMedia: true`，无指纹行，对账 CLEAN；6 张截图已逐张打开（MP4 **A** 标记、00:00:05.933、原生播放器、无错误框）。
- **测试与结果：** 实施前、提交间及交接后 `python3 scripts/check_governance.py` 通过；Python 3.11.10（`/opt/py311/python/bin/python3.11`，宿主无 `python3.11`）`unittest discover -p test_isolated_playback_integration.py` **85 项通过**；两个改动文件 `py_compile`、`node --check scripts/package_playback_driver.mjs`、`git diff --check` 通过。**未运行**：C# restore／build／test／format（本轮无 C# 改动）、其他 Python 集成模块（无共享输入改动）、其余 114 个矩阵行、baseline B01／B02、package／scan／现存 1004 项 large／plugin／batch／configuration、B 独立关键复现及 Slice Final；这些仍属 B。
- **候选包：** 从干净 `292a369` 构建 `dev-fix-round/package/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，sourceRevision `292a369207d7a24d28d132d66434eeb4acb37919`，buildInputsSha256 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`，ZIP SHA-256 `677f50fe8a82ad257017e18128b92087a81a6b341fcc8745cf2f4fdcb8f39544`。两个真实行均使用同一 ZIP。
- **证据与预算：** 本机 `.git/validation-evidence/292a369207d7a24d28d132d66434eeb4acb37919/dev-fix-round/INDEX.md`、`commands.json`、两个原始运行目录与日志、截图。本轮总时长约 41 分钟，测试墙钟并集约 9.5 分钟（两次真实矩阵 271＋246 秒、两次打包 12＋7 秒、单元／编译／治理／差异约 2 秒，两次运行无重叠），约 23%，低于 30% 上限；未空等凑分母。两轮新归属容器均正常退出 0、无 OOM、CLEANED、对账 CLEAN；生产实例、现存 1004 项准备库与既有 dev-env 未操作。
- **Remaining In-Slice Work：** 本 Task 仍未 PASS：D02／D03／D06 与其余 P／C／F 行、完整 116 行、C02／C06 三阶段与失败恢复、baseline、完整 C#／Python、package／scan／1004 large／plugin／batch／configuration 及独立关键复现均由 B 在固定最终候选上完成或核验复用。RO-3 仍受上一轮产品修正的真实重跑限制约束。不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。

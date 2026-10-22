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

最新 B 复核（2026-10-22 13:17 UTC 轮）：**FIX REQUIRED**，继续同一 Task 5.3。实现 `4b4d0cca33f37308842710b2a0a70b1919cd0a58` 的就绪归属修正通过本轮完整入口验证；B53-20261022-5 的真实错误正文也已验证落盘／交接。B 新跑完整 Python **408 PASS＋2 SKIPPED／410 项**；plugin-full **FAIL（211.738 秒）**，在原生合并版本后首次 PlaybackInfo 重现源集合变化 500。该窗口确有本轮原生 post-scan 仍在执行，不能将其认定为已稳定的多版本旅程。新记录 **B53-20261022-8**，只补这一既有旅程的稳定前提和必要失败状态，保留原断言；稳定后仍失败则交 A，不授权产品源集合规则修正。其余完整门禁仍归 B；正式 ZIP、205 C# PASS 和匹配 3／116 独立矩阵证据复用。见文末最新决定。

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

**2026-10-22 用户明确“时间要求完全放宽，优先完成剩余门禁”。** 从此续验起，取消此前每轮总时间、测试时间及测试占比低于 50% 的执行预算限制，连续完成同一 Task／固定候选的剩余完整门禁；既往实际耗时、停止与审查记录仍保留。此调整仅涉及执行时间，不改变任何行、业务断言、固定输入、完整门槛、B 独立审查责任或 A 关闭权限；逐项保存原始首败／重试、真实耗时与资源观察，不因无时间上限而机械重跑匹配证据。

本轮执行预算以当前用户指令为准：测试墙钟并集必须严格小于本轮实际总时间 **50%**；上方“时间完全放宽”只保留为历史执行安排，已被本轮明确指令覆盖。全部行和 B 最终门禁保持，不据预算删减验收；允许按本 Task 既有规则分真实工作轮完成。

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
- **DR53-1（P08.03 重写）：合同描述的 TypeError 不可复现，但确有真实缺陷。** `"rewrite"` 同时列在 `if kind in ("manifest", "manifest-url", "comment", "rewrite", "d06")` 元组中，因此专用 `elif kind == "rewrite"` 分支是**不可达死代码**，扫描后 `row["item"]` 为字典也不会被使用。以修正前源码 `git show 7eb9626:…` 实测：规范 manifest 往返字节相同；带 `# Modified:` 注释行的 manifest 被重建后**字节改变**，却仍记录 `contentSha256Unchanged: true`。修正为让 `rewrite` 走自己的可达分支：复制当前精确字节经本行拥有的 staging 文件 `os.replace`，校验 SHA-256 未变，并记录结果 STRM 身份（`path`／`url`／`sha256`）；`mtime` 分支同样记录身份。新增 `RewriteApplyTests`（2 项）使用非规范 manifest（size 行在 sha1 前、含额外注释行）在修正前失败、修正后通过。真实运行 `MP4.P08.03`（`run/`，退出 0，墙钟 271.0 秒／报告 269.5 秒）首窗／再播／重启后 ffprobe 全为 0，推进 5.357／5.385 秒，`apply.kind=rewrite`、`contentSha256Unchanged=true`、重写摘要与冻结指纹一致，对账 CLEAN；8 张截图已逐张打开（MP4 **A** 标记，00:00:00.600→00:00:05.933）。该实跑**不能**区分修正（规范 manifest 修正前后皆往返相同），判别证据是上述单元控制与证据目录中的 `prefix-reproduction.txt`／`post-fix-control.txt` 实测对照。
- **DR53-2（D02／D03 禁用态旅程）：** 两行现于插件禁用／`PlaybackAutoCheck=false` **期间**完成第二次原生播放、`freeze_state`、重启、只读比对与重启后播放，之后才恢复配置并核验恢复结果；D02 在重启旅程后再核一次插件状态，D03 在恢复前再核一次 `PlaybackAutoCheck` 仍为 false。控制：`test_the_delegation_journeys_read_after_the_playback_boundary`、`test_d02_and_d03_restore_the_configuration_only_after_the_restart_journey`。D02／D03 真实行本轮 **NOT RUN**（预算）。
- **DR53-3（真实播放后的鉴权边界）：** 新增单一局部 `refresh_auth()`，在所有真实 Web Play 之后的原生请求边界使用（`play_once`、`freeze_state`、窗口后指纹读取、重启只读、D02～D06 恢复调用）；token 只作局部值，不进入 observation／结果，不序列化任何凭据，真实读取失败仍抛出。控制覆盖新 token 确被使用、失败读取仍拒绝、D02～D06 内不再出现 `pkg.api_auth()` 旧边界。受影响的 D 行真实重跑本轮 **NOT RUN**（预算）。
- **DR53-4（D04 普通媒体）：** 新增 `native_item_path(row)` 使定位决策显式可测：D04 解析 `/media/local/<普通文件>`，其余行走版本化 STRM（`None`），同名 STRM 条目不能顶替普通媒体对照。真实运行 `MP4.D04`（`run-d04/`，退出 0，墙钟 246.0 秒／报告 244.5 秒）：3.0 秒按真实文件路径定位，原生已备 `['Audio','Video']`，原生播放／再播／重启后均推进 5.351／5.340 秒、插件事件 0、ffprobe 0，`strm` 身份记为 `ordinaryMedia: true`，无指纹行，对账 CLEAN；6 张截图已逐张打开（MP4 **A** 标记、00:00:05.933、原生播放器、无错误框）。
- **测试与结果：** 实施前、提交间及交接后 `python3 scripts/check_governance.py` 通过；Python 3.11.10（`/opt/py311/python/bin/python3.11`，宿主无 `python3.11`）`unittest discover -p test_isolated_playback_integration.py` **85 项通过**；两个改动文件 `py_compile`、`node --check scripts/package_playback_driver.mjs`、`git diff --check` 通过。**未运行**：C# restore／build／test／format（本轮无 C# 改动）、其他 Python 集成模块（无共享输入改动）、其余 114 个矩阵行、baseline B01／B02、package／scan／现存 1004 项 large／plugin／batch／configuration、B 独立关键复现及 Slice Final；这些仍属 B。
- **候选包：** 从干净 `292a369` 构建 `dev-fix-round/package/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，sourceRevision `292a369207d7a24d28d132d66434eeb4acb37919`，buildInputsSha256 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`，ZIP SHA-256 `677f50fe8a82ad257017e18128b92087a81a6b341fcc8745cf2f4fdcb8f39544`。两个真实行均使用同一 ZIP。
- **证据与预算：** 本机 `.git/validation-evidence/292a369207d7a24d28d132d66434eeb4acb37919/dev-fix-round/INDEX.md`、`commands.json`、两个原始运行目录与日志、截图。本轮总时长约 41 分钟，测试墙钟并集约 9.5 分钟（两次真实矩阵 271＋246 秒、两次打包 12＋7 秒、单元／编译／治理／差异约 2 秒，两次运行无重叠），约 23%，低于 30% 上限；未空等凑分母。两轮新归属容器均正常退出 0、无 OOM、CLEANED、对账 CLEAN；生产实例、现存 1004 项准备库与既有 dev-env 未操作。
- **Remaining In-Slice Work：** 本 Task 仍未 PASS：D02／D03／D06 与其余 P／C／F 行、完整 116 行、C02／C06 三阶段与失败恢复、baseline、完整 C#／Python、package／scan／1004 large／plugin／batch／configuration 及独立关键复现均由 B 在固定最终候选上完成或核验复用。RO-3 仍受上一轮产品修正的真实重跑限制约束。不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。


## B 独立复核决定（2026-10-22，FIX REQUIRED）

已读取必读文档与 B 经验，检查真实干净 main（起始超前 origin/main 56 提交）、已提交合同及完整 Task 差异，治理检查通过。保留同一 Task 5.3／Slice 5／Base／Contract Checkpoint；本轮不改产品或测试代码，不新建 Task。

```text
Reviewed Range: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..283f14d2de05849ca2b81d397eda0bd14d6f3af5
Implementation Candidate: 292a369207d7a24d28d132d66434eeb4acb37919
Decision: FIX REQUIRED
```

### 当前阻塞与同 Task 修正边界

**B53-20261022-1／P1：P06 全部 Size 增大行实际使用较小文件。** 既有 `--scenario matrix` 的 `generate_matrix_fixtures` 按 `matrix_extra_specs` 生成 28 秒 smptebars，然后 `build_matrix_rows` 将其分配给每种格式的五个 `P06.*.up`。B 本轮通过该真实入口重新生成的原始媒体表，与交付数据一致：MP4 A 为 1,660,446 字节、up 为 381,375；MKV A 为 1,669,928、up 为 378,331。时长变长不能证明字节数增大；十行即使实播显示 PASS，也只证明减小方向，遗漏已固定的增大义务。这是实际输入／合同不匹配，不是猜测的内部调用或插件缺陷。

修正现有播放脚本的必要夹具生成与方向前提，使 up 的真实字节数大于 A、down 小于 A；重新计算实际 SHA-1／Size，确认正常可探测／解码，并在测量前拒绝方向错误。保留规范 ID、固定预期和真实 Manifest，不能把 down 改名充当 up，也不改插件决策／成功规则或增加框架。Developer 仅改直接相关代码／测试，运行受影响 playback Python 控制、修改文件编译及少量完整 up 旅程，明确省略项；没有 C# 改动无需因此重跑 C#。全部最终门禁仍由 B 承担。F02 截断文件本次准备数据仍可被 ffprobe 读出 Video／Audio，但尚无有效失败窗口实播；只记待 B 核验的失败前提，不据此要求插件拒绝可探测结果或预填产品 FAIL。

### 本轮通过、匹配复用与未完成项

- **完整回归新跑：** SDK 10.0.401 locked restore／Release build（0 warning／error）／format 通过，C# 205 passed、0 failed、0 skipped。Python 3.11.10 在独立干净 Git archive 检出发现 357 项，355 passed、2 SKIPPED（两项 assembly version 控制因发布归档缺失）；跳过不计 PASS。compileall、Node 语法通过；未复制忽略的 artifacts／数据库／凭据到干净检出。原始命令、cwd、时刻和输出均在本轮索引。
- **交付复核：** 当前审查 Head 相比 292a369 只改 TASK.md；ZIP 实际 SHA-256 `677f50fe8a82ad257017e18128b92087a81a6b341fcc8745cf2f4fdcb8f39544` 与交接包／sidecar 一致。逐张实际打开 P08.03 的 8 张、D04 的 6 张原图，均为 MP4 A，画面时间推进超过 5 秒，无可见错误。结合原始 ffprobe 日志、完整原生源／流和五字段重启相等证据，接受 `MP4.P08.03`、`MP4.D04` 两行的匹配结果；不冒充 B 另跑的独立关键播放或整个矩阵通过。
- **既有修正：** P08.03 的原 TypeError 说法确实忽略了旧专用分支不可达，Developer 对此纠正成立；真实修正依据是非规范 Manifest 的精确字节保留。D02／D03 源码现将再播／重启旅程放在恢复配置之前，但真实门禁仍未完成。已核验原同次 33 字段、三条原日志与固定原生源码摘要，编码器＝成功保存，返回仅 ColorRange 缺失；有界修正仍保留其他身份和保存门槛。以上不能代替 12 个 C 行和 RO-3 全体验收。
- **B 编排失败如实保留：** 本轮误将 C02 与 F02 在同检出并行运行；18112／18113 独立端口仍共用 ROOT 派生 Compose 项目，准备相互干扰。C02 中断退出 -2（161.58 秒），F02 退出 1（83.32 秒）；随后串行 F02 仍因残留容器网络关联错误在准备阶段退出 1（54.27 秒）。均归类 **BLOCKED（B 编排问题）**，没有有效行播放／截图，不计产品 FAIL／PASS。原始结果的 FAIL／空状态与 cleanupError 不改写。保存完整 inspect 并逐挂载核对归属后，仅移除本轮两个已停止容器；保留其 exit 143／137、无 OOM、部分工作区及所有证据，不称这些轮次 CLEAN。
- **保留门禁：** 发现明确 P1 输入阻塞后停止昂贵全量。baseline、其余 114 个规范行、B 完整关键播放、同 ZIP package／scan／现存全部 1004 项 large、plugin／batch／configuration 和 Slice Final 本轮 **NOT RUN**；C02／F02 尝试不构成完成其中任何一行。B 在修正后的固定候选核验可复用输入并补齐指定全量、独立复现、全部截图和完整 Base..Head 审查，不把全量交回 Developer。同检出包入口串行执行即可，本次编排错误不新增共享工具实施要求。
- **证据与收尾：** `.git/validation-evidence/283f14d2de05849ca2b81d397eda0bd14d6f3af5/b-review-20261022T002144Z/INDEX.md`，含完整差异、输入方向原文、回归日志／skip、14 张图逐张核验、同次字段来源、失败／重试、归属与清理。时间按命令墙钟并集核算（含所有失败尝试），最终值见 `timing-ledger.json`；测试低于本轮实际总时间 50%，未空等凑分母。生产实例与现存全部 1004 项准备库未操作／重建，不推送、不改历史。

RO-1 部分满足；RO-2／RO-3 仍有上述输入阻塞与完整验收缺口；RO-4 保留 Task 5.1 既有接受决定。当前不具备 Closure Packet／SLICE READY FOR A REVIEW 条件，不关闭 Slice。下一步仅修正同一 Task 的必要输入，交独立 B 继续最终门禁。

## Developer Correction Report（B53-20261022-1／P1 修正，2026-10-22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与已提交 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`；保留 B 的 FIX REQUIRED 和全部历史 FAIL／NOT RUN，本代理不签发独立 B PASS。实现提交 **`dd05f7425f97212b77675843e058a8117c269360`**，本报告随后以单独文档提交。
- **Changed Files：** 仅 `scripts/run_isolated_playback_integration.py` 与 `tests/test_isolated_playback_integration.py`（+79／−8）。未改 C#、共享驱动、`isolated_media_server.py`、依赖、镜像锁、工作流、治理工具或 Slice 合同；未改插件决策／成功／指纹规则，未改规范 ID、固定预期或 Manifest 格式。
- **DR53-P1（P06 up 实际更小）：** 确认 B 的结论。修正前 `p06up` 只是把静态 `smptebars` 从 24 秒延长到 28 秒；本轮用固定镜像重新生成，复现出 B 记录的 381,375（MP4）与 378,331（MKV），远小于 A 的 1,660,446／1,669,928。修正为在**该夹具的滤镜链**加入真实逐帧噪声 `noise=alls=40:allf=t+u`（`fixture_ffmpeg_args` 只在 spec 声明时前置滤镜，其余夹具不变），实测 MP4 8,834,168／MKV 8,814,734 字节，均由固定 Jellyfin FFmpeg 正常解码、ffprobe 仍为 H.264 yuv420p 320x180 `color_range=tv`。生成时记录的 SHA-1 来自实际产出的文件：MP4 `26c3b17b0d0f7844428d9e2a323704b1373958cd`；MKV 两次相同参数编码得到同一 Size 8,814,734 但 muxer 写入的文件标识字节不同（首个差异在第 221 字节），故实跑记录 `049f2449a585c9fbe5d745c2b73242fb57c0c5bd`，不预填。
- **方向前提不再靠标签：** 新增 `require_p06_directions(...)`，在 `generate_matrix_fixtures()`（编码后读取真实字节）与 `build_matrix_rows()`（用记录的真实 Size，早于构造任何行与播放）各校验一次：up 必须 `> A`，down 必须 `< A`，否则立即拒绝并说明该行“实际会是另一方向”。因此把 down 改名冒充 up 会在测量前失败。控制为 `P06DirectionTests` 3 项：真实生成规格的字节方向、错误方向在任何行构建前抛错、up 滤镜含逐帧噪声而 down 不含。
- **真实播放（同一固定 ZIP）：** `--scenario matrix --rows MP4.P06.02.up,MP4.P06.02.down`，退出 0，runner `elapsedSeconds` 538.6，插件 Active、payload 与归档一致、原生任务无触发器，工作区对账 CLEAN。
  - `MP4.P06.02.up`：首次信任时该 URL 仍是 A（1,660,446／`sha1=null`）→ 以原子替换把同一 URL 换成 8834168 字节（`apply.switchSha256=19d36e4a…429af2`，与 `matrix-mp4-p06up.mp4` 的 SHA-256 相同），STRM 写入 `strm-probe-sha1:26c3b17b…`／`strm-probe-size:8834168`。窗口 ffprobe **+1**、`address persisted True`、指纹提交为 8834168／`26c3b17b…`；播放 `duration=28`、320x180、解码 90 帧、`currentTime` 5.93 秒；再播与重启后各 0 次探测、`reason Sha1Matches`。
  - `MP4.P06.02.down`：同一旅程换成 212,433 字节（`switchSha256=b25429d0…7848`），窗口 ffprobe **+1**、地址持久化、指纹 `212433`／`0a279b25…`；播放 `duration=16`、解码 86 帧、`currentTime` 5.52 秒；再播与重启后 0 次探测。
  - 两行四个阶段 `readErrors`／`consoleErrors` 均空，原生源仍指向同一 item／source key 的已保存地址，重启后读取为只读且无 ffprobe。16 张截图本轮逐张打开：up 行显示 `MP4 P06UP` 标记（00:00:00.667→00:00:06.000），down 行显示 `MP4 P4B` 标记，均推进超过 5 秒且无错误框。
- **测试与结果：** 提交前后 `python3 scripts/check_governance.py` 通过；Python 3.11.17（`/opt/py311/python/bin/python3.11`）`unittest discover -p test_isolated_playback_integration.py` **88 项通过**（墙钟 0.097 秒）；两个改动文件 `py_compile`、`node --check scripts/package_playback_driver.mjs`、`git diff --check` 通过。**未运行**：C# restore／build／test／format（本轮无 C# 改动）、其他 Python 集成模块（无共享输入改动）、其余 114 个矩阵行、baseline B01／B02、package／scan／现存 1004 项 large／plugin／batch／configuration、F02 失败窗口实播、B 独立关键复现与 Slice Final；均仍属 B。
- **候选包：** 从干净 `dd05f74` 构建 `developer-p06-fix/package/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，sourceRevision `dd05f7425f97212b77675843e058a8117c269360`，buildInputsSha256 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`，ZIP SHA-256 `ccb991891fa9562adb600cdb1dc60efa90d1845f447e57d56870af6e85334f46`；两行真实播放均使用该 ZIP。
- **证据与预算：** `.git/validation-evidence/dd05f7425f97212b77675843e058a8117c269360/developer-p06-fix/INDEX.md`、`summary.json`、`run-p06.log`、`run-p06/` 原始 JSON 与 16 张截图、`fixture-direction/` 的修正前／后原始媒体、编码 stderr、ffprobe JSON 与 `tests-focused.log`。本轮总时长约 49 分钟，测试墙钟并集约 9.5 分钟（真实两行 538.6 秒、六个对照夹具编码约 30 秒、单元 0.1 秒、编译／语法／差异／治理约 3 秒），约 19%，低于 30% 上限；未空等凑分母。打包约 30 秒另计。生产实例、现存 1004 项准备库与既有 dev-env 未操作，未推送、未改历史。
- **Remaining In-Slice Work：** 本 Task 仍未 PASS。每种格式的 P06 仍有 8 行（4 up／4 down）及全部其余 P／C／F 行、完整 116 行、C02／C06 三阶段与失败恢复、baseline、完整 C#／Python、package／scan／1004 large／plugin／batch／configuration 和独立关键复现均由 B 在固定最终候选上补齐或核验；本次仅证明修正后 MP4 `P06.02.up`／`P06.02.down` 两行的真实方向、探测、保存、再播与重启，不覆盖 MKV 或其他 P06 子行。不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。


## B 独立复核决定（2026-10-22 02:19 UTC 轮，FIX REQUIRED）

起始仓库干净、main 超前 origin/main 59 提交，治理通过；已读必读文档，复核同一 Task 5.3／Slice 5／Base／合同检查点，未改变范围或插件／测试源码。

```text
Reviewed Range: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..f485a30f2cd101ae49a5eac412c111e06e707a1e
Implementation Candidate: dd05f7425f97212b77675843e058a8117c269360
Decision: FIX REQUIRED
```

- **上一 P1 已解除：** P06 方向修正及提前拒绝控制符合授权。核对真实保留媒体摘要与两行全部原始 observation／日志／原生源、指纹、重启只读快照，逐张打开 16 张截图，接受同 ZIP 的 `MP4.P06.02.up`／`MP4.P06.02.down`：A 1,660,446→8,834,168／212,433 字节，首信任／窗口／再播／重启 ffprobe 为 0／1／0／0，各阶段媒体钟推进超过 5 秒，内容为 A→P06UP／P4B，完整重启快照相等。P06UP／P4B 图无嵌入时间码，推进依据为原始配对媒体钟观测，不沿用报告中的可见时间码说法。旧 292a369 ZIP 的 P08.03／D04 结果保留历史，不自动算作当前同 ZIP 全矩阵。
- **当前阻塞 B53-20261022-2／P1：F02 夹具未产生要求的原生探测失败。** B 使用已有 `--scenario matrix --rows MKV.F02`、固定 dd05f74 ZIP 与新归属实例独立复现（18114，串行，无其他包入口并行）。正常首次信任后，将同 URL 的 A 按既有逻辑截取前三分之一；该 556,642 字节输入仍能被原生成功探测／保存，播放推进 **5.362982 秒、90 帧、无 media error**，指纹实际更新为该输入的 SHA-1 `e76db0e6d536bd9b9bbdfe709ce73e4738fa063b`／Size 556642。原生同次编码器＝成功保存，返回仅缺 ColorRange；窗口目标 ffprobe 为 1。原断言正确报 `the corrupted target must not produce an advancing playback`，整行 **FAIL**；不能证明预期的失败旧基线保护和恢复，也不能据此认定插件接受了失败探测。恢复／再播／重启段本次 NOT RUN。4 张本轮原图已逐张打开：均为 MKV A，画面计数推进，无错误框。
- **同 Task 必要修正：** 在现有 `generate_matrix_fixtures` 的 F02 受控损坏生成与直接相关测试内，使输入确实无法由固定原生探测取得有效主流，并在测量前核验失败前提；如实计算新字节 SHA-1／Size，保留同 URL 修复有效 B 的旅程和全部失败／旧基线／恢复断言。不要求插件拒绝所有截断文件，不放宽成功判定，不把 F02 改成成功场景，不扩充框架。Developer 仅运行直接受影响的 playback Python 控制、修改文件编译及少量完整 F02 修正反馈，报告省略项；没有 C# 改动无需因此跑 C#。最终全量与两种格式的完整失败恢复仍由 B 承担，不交回 Developer。
- **当前候选完整回归新跑：** SDK 10.0.401 locked restore／Release build（0 warning／error）／format 通过，C# **205 passed、0 failed、0 skipped**。Python **3.11.10** 在独立干净 Git archive 检出发现 **360 项，358 passed、2 SKIPPED**（两项 assembly version 控制缺发布归档）；skip 不计 PASS。compileall、Node 语法通过。报告中的 3.11.17 不用作本轮环境证据。dd05f74 后继只改 TASK.md；实际 ZIP／sidecar 一致，SHA-256 `ccb991891fa9562adb600cdb1dc60efa90d1845f447e57d56870af6e85334f46`，build inputs 保持 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`。
- **剩余门禁及停止决定：** 本轮真实 F02 退出 1、墙钟 210.676 秒；对账 CLEAN、双服务正常退出 0／无 OOM、既有入口清理本轮工作区 CLEANED，生产／共享 dev-env／现存全部 1004 项库未操作。明确 P1 后停止昂贵全量；当前包只有上述两条 P06 行获匹配接受，F02 未通过，其余 113 个规范 ID、baseline、其他独立关键旅程、12 个 C 行、package／scan／全部 1004 large／plugin／batch／configuration 与 Slice Final 本轮 NOT RUN。B 保留这些完整责任，修正后核验输入复用并补齐，不机械重跑匹配 Final。RO-1 部分满足，RO-2／RO-3 未齐，RO-4 保留 Task 5.1 既有决定；继续同一 Task，不造新 Task，不提交 Closure Packet／SLICE READY FOR A REVIEW，不关闭 Slice。
- **证据与时间：** `.git/validation-evidence/f485a30f2cd101ae49a5eac412c111e06e707a1e/b-review-20261022T021921Z/INDEX.md`，含完整差异与范围复核、精确命令、环境、原始完整回归、F02 响应／计数／原生保存／五字段和失败、全部 20 张图查看记录、匹配复用边界及正常收尾。测试墙钟并集计入失败实跑并保守计入文档检查，最终值见 `timing-ledger.json`，严格低于本轮实际总时间 50%，未空等凑分母。仅提交本审查文档，不推送、不改历史。

## Developer Correction Report（B53-20261022-2／P1 修正，2026-10-22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`；保留 B 的 FIX REQUIRED 和全部历史 FAIL／NOT RUN，本代理不签发独立 B PASS。最终实现 HEAD **`494302f5520912201e10b0559cd883fad83789d5`**；真实 F02 反馈使用的可执行候选为 `78063d38b10f5fc23c908cba36a39d3ee306ed45`，其后只改 docstring 和聚焦测试／测试类位置。
- **Changed Files：** `scripts/run_isolated_playback_integration.py`、`tests/test_isolated_playback_integration.py`。未改 C#、共享驱动、`isolated_media_server.py`、依赖、镜像锁、工作流、治理工具或 Slice 合同；F02 旅程、失败／旧基线／恢复断言及 manifest 语义未改。
- **B53-20261022-2 已确认：** 旧的“前三分之一”截断仍保留前置 moov／Matroska 元数据，B 的 MKV.F02 中 556,642 字节截断文件仍被原生探测并播放。修正为把真实 A 文件截成严格前 **512 字节**；`generate_matrix_fixtures()` 在构建任何行之前用固定镜像的 ffprobe 核验损坏文件，要求探测失败且无 Video 流，否则立即拒绝；fixture 的 SHA-1／Size 仍从实际写出的字节计算并写入失败窗口 Manifest。新增 `F02CorruptionTests` 与 F02 行身份控制，覆盖真实截断、短源拒绝、成功探测／Video 流拒绝及 corrupt/recovery 身份；未把 F02 改成成功场景。
- **真实 F02 反馈（MP4，测试候选 `78063d3`）：** 同一既有入口只选 `MP4.F02`，退出 0，runner `elapsedSeconds` 415.3，墙钟 417 秒；目标 ffprobe 在首次信任／失败窗口／恢复／再播／重启后分别为 **0／1／1／0／0**。生成 fixture 实际为 MP4 512 字节 `67fedff42564fabfda22ad78e92fad833a43d98b`（ffprobe `End of file`）、MKV 512 字节 `6ce7ab1ef6a006ca213033c530a6f426b315448c`（ffprobe `File ended prematurely at pos. 512`），两者在测量前均不可探测。失败窗口原生日志为 `ffprobe failed - streams and format are both null`，PlaybackInfo HTTP **500**、无推进播放、旧指纹 `adb64ff6503f355ac209e5cd06029dd19b2655f4`／1,660,446 保持；服务实际读取 `Range 0-511/512`。恢复写入真实 212,433 字节 P4B 后指纹为 `0a279b25307caac08f27406df60355a9379c8c1b`／212,433，恢复播放推进 5.266 秒，再播 5.294 秒且 0 探测，重启后先只读比对完整原生源／五字段再实播 5.291 秒且 0 探测。全部 9 张原图已逐张打开：首次信任为 MP4 A（00:00:00.733→00:00:06.067），失败窗口为原生“播放错误／处理请求时发生错误”，恢复／再播／重启为 MP4 P4B；无凭据或 token 进入证据。
- **测试与结果：** `python3 scripts/check_governance.py` 通过；Python **3.11.10**（`/opt/py311/python/bin/python3.11`）`unittest discover -s tests -p test_isolated_playback_integration.py` 最终 **92 项通过、0 失败、0.10 秒**；两个改动文件 `py_compile`、`node --check scripts/package_playback_driver.mjs`、`git diff --check` 通过。新增 F02 行身份测试首次放入无 fixture setup 的类，实际报 `KeyError`；已移入 `MatrixPreconditionTests` 后通过，未删除或放宽断言。**未运行**：C# restore／build／test／format（本轮无 C# 改动）、其他 Python 集成模块（无共享输入改动）、`MKV.F02` 真实旅程及其余矩阵行、baseline、package／scan／1004 large／plugin／batch／configuration、B 独立关键复现与 Slice Final；仍属 B。
- **候选包：** 测试包 `package-tested/` 从干净 `78063d3` 构建，sourceRevision `78063d38b10f5fc23c908cba36a39d3ee306ed45`，ZIP SHA-256 `312435b8cb66334ee4b6e2accea096968afdd6c7de9fa9fc70444bf09397cdec`；最终 HEAD 包 `package/` sourceRevision `494302f5520912201e10b0559cd883fad83789d5`，ZIP SHA-256 `a8a57cad5587980a9451f2cd0a74b06f259537498feb56de1f2f22b8e4e86f54`，尚未作为新实机候选运行。最终包与测试包之间的 C# 源码、Python 可执行逻辑和测试输入一致，差异仅为构建来源标识及 docstring／测试类位置；B 的最终门禁应使用最终包重新核验。
- **证据与预算：** `.git/validation-evidence/78063d38b10f5fc23c908cba36a39d3ee306ed45/developer-f02-fix/`，含 `DEVELOPER-RUN-NOTE.md`、`run-mp4-f02/` 原始 JSON／服务器与媒体日志／9 张截图、测试包与最终包、fixture ffprobe 原文及命令。本轮真实 F02 运行前后均无其他包入口并行；容器正常退出 0、无 OOM、工作区 CLEAN、对账 CLEAN；生产实例与现存全部 1004 项准备库未操作。本轮从 03:15:44Z 开始；测试墙钟并集约 8.5 分钟（其中唯一必需的真实 F02 完整旅程 417 秒，92 项聚焦测试 0.10 秒，受控截断核验约 1.5 分钟），未运行全量、未空等凑分母；精确命令与时序见证据目录。
- **Remaining In-Slice Work：** `MKV.F02` 的真实失败／恢复旅程、其余 P／C／D／F 行、完整 116 行、C02／C06 三阶段、baseline、完整 C#／Python、package／scan／1004 large／plugin／batch／configuration、B 独立复现和 Slice Final 均仍由 B 完成或核验；本轮只证明修正后的 F02 输入前提及 MP4 完整失败恢复行，不覆盖 MKV 或整个矩阵，不提交 Closure Packet／SLICE READY FOR A REVIEW，不关闭 Slice。


## B 独立复核决定（2026-10-22 03:43 UTC 轮，FIX REQUIRED：完整门禁未齐）

- **Reviewed Range：** `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..46a53d3777d4b52392a3c09967bd947ac3a188c7`，最新实现 `494302f5520912201e10b0559cd883fad83789d5`。开始时工作区干净、main 超前 origin/main 65 提交，治理检查通过；已读必读文档／B 经验并审查完整累计差异及上次 B 后增量。Slice 5／Task 5.3、两个 Base、Contract Checkpoint 不变，无范围变更／新 Task。
- **Decision：FIX REQUIRED，仅因完整验收未齐；本轮没有新增 Developer 源码修正项。** 接受本次 F02 必要修正，解除 **B53-20261022-2／P1**：改为实际 A 的前 512 字节，并在生成前提核验固定原生 ffprobe 失败且无 Video；如实计算字节身份。原失败、旧基线、同 URL 修复、再播和重启断言未放宽，没有要求插件拒绝所有截断文件。下一步是 B 继续余下门禁，不交回 Developer 代跑全量。
- **固定正式候选：** 最终 ZIP sourceRevision `494302f5520912201e10b0559cd883fad83789d5`，SHA-256 `a8a57cad5587980a9451f2cd0a74b06f259537498feb56de1f2f22b8e4e86f54`；build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`、依赖锁 `2a523bb1f62b9c72bebb5bcc1f81cf78c78b8973fb42f6aab5c28aa355eeb00e` 与当前实际输入一致，9 个归档条目摘要匹配；实现后到审查 Head 只改 TASK.md。后续纯审查文档不重建 ZIP、不机械重跑匹配门槛。
- **Developer 交付核对：** MP4.F02 原始记录实际为 0／1／1／0／0，失败 HTTP 500、旧指纹保留，修复同 URL 后正常播放和重启完整读回相等；已读原始响应／日志／原生全字段／五字段，逐张打开全部 9 张原图，恢复编码器与成功保存 33 字段完全相同，返回仅 ColorRange tv→null。`78063d3` 与最终播放入口去 docstring 后执行 AST 相同。但报告引用的 `package-tested/` 实际为空，旧 ZIP `312435b8...` 无法重新打开，且它与正式 ZIP 不同；该 MP4 反馈只支持聚焦修正事实，**不计当前同 ZIP 全矩阵 PASS**。P4B 无嵌入时间码，推进依据为配对原始媒体钟，不把静态标记图写成可见时间码推进。
- **B 独立真实复现：MKV.F02 PASS。** 仅使用已有 `--scenario matrix --rows MKV.F02`、上述正式 ZIP、新归属工作区 `run-20261022-035310-5d1e5543` 与本机 18115；无并行包入口／调试器／预热变化后 PlaybackInfo。退出 0，runner 413.2 秒、完整墙钟 **414.864 秒**。首次信任 0 探测、推进 5.393401 秒；实际 512 字节损坏体 SHA-1 `cf53c2f1bedfd78de3d6a9082584e739c11b42a1`，已独立逐字节核对为真实 A 前缀并保留样本。失败窗口目标 ffprobe +1、原生日志 `streams and format are both null`、HTTP 500／无推进／错误截图；旧 SHA-1 `614ce5852a91459226d17bec49a3054af0edec7a`／Size 1669928 保持，旧原生流仍在，不宣称原生数据库回滚。媒体服务实际返回 `0-511/512`。
- **同 URL 恢复与重启：** 有效 MKV P4B 实际 SHA-1 `3231b9c7405ef41f73483034c61f0c43026d3e0b`／Size 213145；恢复探测 +1、保存 Video＋Audio、编码器＝成功保存全部 33 字段、返回仅缺 ColorRange，新五字段提交。恢复／再播／重启后分别推进 **5.318248／5.280757／5.278577 秒**、解码 87／89／91 帧，后两窗各 0 探测；重启在播放前只读完整源／流／地址、STRM 摘要、五字段与 probe count 均与冻结快照相等。独立重数目标原始 ffprobe 共 3 次（含准备 1 次），本轮自身 9 张原图全部打开：首次 MKV A 计数推进、失败原生错误框、恢复／再播／重启均 MKV P4B 无错误。连同 Developer 图共实际查看 18 张。
- **完整回归由 B 新跑：** SDK 10.0.401 locked restore／Release build（0 warning／error）／format 通过，C# **205 passed／0 failed／0 skipped**。Python **3.11.10** 在独立干净 Git archive 检出发现 **364 项，362 passed、2 SKIPPED**；两项 assembly-version 控制因无发布归档跳过，不计 PASS。compileall、Node 语法通过；精确 argv／cwd／版本／时序和原始日志保留。未修改任何可执行源码。
- **正常收尾：** 当前正式 ZIP 部署负载匹配、插件 Active、原生任务默认无触发。双服务正常退出 0／无 OOM，实例对账 CLEAN／无 disturbed 项，现有入口仅清理本轮工作区 CLEANED；实际夹具字节与原始证据已留在外部忽略目录。生产／共享 dev-env／现存全部 1004 项准备库未操作，未推送或改写历史。
- **剩余完整门禁仍归 B：** 当前正式 ZIP 已接受 **1／116 行（MKV.F02）**，其余 **115 行含 MP4.F02**、baseline B01／B02、其余独立关键旅程及全部 12 个 C 行、同包 package／scan／现存全部 1004 large、plugin／batch／configuration 本轮 NOT RUN。旧其他 ZIP 的 P06／P08／D04 等保留历史，不自动提升；下一实际 B 工作轮优先同 ZIP MP4.F02 与 C02／C06，按已实现入口串行分批补齐。Developer 仅在出现新的具体受影响修正项时跑该项直接反馈；B 的完整门槛不下放。RO-2／RO-3 与 Slice Final 未齐，RO-4 保留 Task 5.1 既有决定；不提交 Closure Packet／SLICE READY FOR A REVIEW，不关闭 Slice。
- **证据与测试比例：** `.git/validation-evidence/46a53d3777d4b52392a3c09967bd947ac3a188c7/b-review-20261022T034312Z/INDEX.md`；包含完整差异／输入清单、全回归、独立运行命令、原始服务器与媒体日志、响应／完整状态、真实夹具、18 张图查看记录、复用限制和收尾。04:01:39 UTC 检查点实际总时间 **1107.198 秒**，全回归与真实运行的测试墙钟并集加保守检查额度为 **495.065 秒（44.71%）**。当时已发生时间余额仅 117 秒，不足下一完整实播旅程，停止启动新测试并保留本轮结果；未空等凑分母、未预借未来审查时间。后续报告／提交只增加实际非测试工作，最终精确比例见 `timing-ledger.json`。

NEXT ACTION: B CONTINUES REMAINING TASK 5.3 FULL GATES ON THE FIXED FORMAL ZIP; NO NEW DEVELOPER CORRECTION REQUESTED IN THIS ROUND.


## B 完整验收续验记录（2026-10-22 04:18 UTC 轮）

- **固定身份／审查／复用：** 工作区开始干净、main 超前 origin/main 66 提交；治理通过。Reviewed Range `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..0cb9c70211f8f28cdcbd52fef54e3b9c590eda43`，相对已完整审查候选仅 TASK.md 后继；逐文件核对本 Task 全部 8 个可执行／测试输入摘要不变。继续正式 sourceRevision `494302f5520912201e10b0559cd883fad83789d5` 的 ZIP `a8a57cad5587980a9451f2cd0a74b06f259537498feb56de1f2f22b8e4e86f54`，无重建或源码改动。复用上一轮已核验的完整 C# 205／Python 362 passed＋2 archive 缺失 skip、restore／build／format／compileall／Node，以及独立 MKV.F02；匹配原始索引可读，不机械重跑，不把 skip 计 PASS。Slice／Task Base、合同和 ID 不变。
- **本轮新实跑：MP4.C02.limited PASS。** 使用已有 `--scenario matrix --rows MP4.C02.limited`、上述同 ZIP、本机 18116、新归属 `run-20261022-042408-c40b7d76`，包入口保持串行。退出 0，runner 276.7 秒、完整墙钟 **278.372 秒**。真实限定范围 Video 为 tv、H.264＋AAC／24 秒，目标 SHA-1 `0d42b467afae22b06a6e9cb50ab12b17105e6f4d`／Size 1679710，区别于 A 的有效 SHA-1／Size；实际原生 Web Play 换到新 URL，未预先请求变化后 PlaybackInfo。
- **三阶段与正确性：** 首次信任／换址窗口／再播／重启后 ffprobe **0／1／0／0**；独立重数新目标原始启动 1 次，另有不同旧目标准备 1 次。推进 **5.445799／5.361679／5.390558／5.379121 秒**，解码 95／90／93／94 帧，HTTP 200、正确 source `1ea937306d7d9ce520a2eaa5c4ec65f1`／最新地址／Video＋Audio，媒体 GET 为 1／2／1／1。同次编码器 04:27:20.948→保存成功 04:27:21.230→返回 04:27:24.327，关联相同项目／源和新 URL hash；33 字段编码器＝保存，返回仅 ColorRange tv→null，其余 32 字段一致。新保存的视频 BitRate 为 460010，旧值 453588；不是只凭旧主流存在接受。新五字段提交，重启前冻结完整原生源／媒体流、STRM 摘要、五字段和计数与任何播放前的只读快照精确相等；随后实播不重复探测。
- **截图／收尾：** 8 张原图已逐张实际打开：首次 MP4 A 嵌入计数 00:00:00.733→00:00:06.133；换址／再播／重启均 MP4 LIM，分别 00:00:00.400→00:00:05.733、00:00:00.600→00:00:05.933、00:00:00.667→00:00:06.000，无可见错误，配对原始媒体钟也均大于 5 秒。部署负载匹配、插件 Active、原生任务无默认触发；双服务 exit 0／无 OOM，对账 CLEAN／无 disturbed 项，仅本轮工作区 CLEANED，原始日志／响应／状态和原图已外置保留。
- **后续完整门禁的准备事实：** 已从旧实跑入口确认原始准备库 `artifacts/package-env/runs/run-20261019-104647-796ca45c`。只读重核其 1170 文件完整摘要仍为 `189b67c66e608833b27fa818de24bb1611788565c87eeffc0568b9eefe958bd2`，与原记录一致；无运行挂载重叠，SQLite immutable／read-only quick_check 均 ok，1006 个 STRM 夹具文件（含对照）保留。这只是准备资料核验，**不代替新候选全部 1004 原生支持源的大库验收**。未启动、复制、改写、清理原库；生产／共享 dev-env 未操作。安装／扫描／大库及开发部署门禁的既有网络、隔离和准备适配已复核，尚未冒充执行。
- **Decision：FIX REQUIRED（完整验收未齐）；无新增产品 P0／P1 或 Developer 修正请求。** 当前同 ZIP 接受 **2／116**，其余 **114 行**（含 MP4.F02、其余 11 个 C 行）、baseline B01／B02、全部指定独立关键复现及 package／scan／现存全部 1004 large／plugin／batch／configuration 仍须 B 补齐；本轮这些项目 NOT RUN。RO-2／RO-3 未齐，RO-4 既有决定保持，不造新 Task、不交回 Developer 代跑全量、不提交 Closure Packet／SLICE READY FOR A REVIEW、不关闭 Slice。
- **时间与证据：** `.git/validation-evidence/0cb9c70211f8f28cdcbd52fef54e3b9c590eda43/b-full-gates-20261022T041834Z/INDEX.md`；包括输入复用、完整累计差异、本轮精确命令／退出／时序、原始服务器与媒体日志／响应／原生全状态、8 张图实际查看记录、33 字段逐项表、原准备库只读核验及收尾。本轮仍按用户测试低于 50% 规则执行；实际已发生 797.995 秒时，新测试余额 221.25 秒，低于下一完整旅程估计 300 秒，故停止启动新测试并完成本轮取证与报告，未空等凑分母。真实运行 278.372 秒、其他检查保守计 10 秒，未运行的旧复用门禁不计新测试耗时，最终比例见 `timing-ledger.json`。未收到放宽比例的答复，不将未答复视为授权。

NEXT ACTION: B CONTINUES THE FIXED-ZIP REMAINING FULL GATES IN TASK 5.3; NO DEVELOPER FIX REQUEST OR SLICE CLOSE.


### 同一 04:18 UTC 轮追加：MP4.C02.full 与 baseline B01

- **预算复核及身份：** 先前 797.995 秒时不足下一完整旅程的决定保留；完成必要的逐字段表、旧／新源与码率关联、原库来源核验及报告后，实际追加测试余额达到 421.782 秒，B 才启动估计 300 秒的 `MP4.C02.full`。随后按实际余额 288.387 秒，串行启动估计 240 秒的 baseline B01。两次准入均来自已经发生的非测试工作；始终同一 04:18:34 UTC 起始轮，不重置分母、不放宽 50%、不空等。后继 `3ffb1fd7315daea22f70a618c87ea7221b5d98ba` 只改 TASK.md，正式 ZIP／所有可执行输入不变，Reviewed Range 累计至该真实 Head。
- **MP4.C02.full PASS：** 退出 0，runner **272.3 秒**／完整墙钟 **273.954 秒**；新归属 `run-20261022-043512-c7e1f929`，本机 18116，原有矩阵入口。目标真实 ffprobe Video 为 **pc**，H.264＋AAC／24 秒，实际 SHA-1 `98d84ea8833499fef0c66e51a3c9e411d15af562`／Size 1782146；首次信任／换址／再播／重启计数 **0／1／0／0**，推进 **5.407864／5.400618／5.353649／5.322814 秒**，解码 95／89／88／91 帧。独立重数新目标实际 ffprobe 1 次、不同旧目标准备 1 次。正确源 `105c3f9923e6a5038f09b43593b06d6a`、新 URL 与新五字段，Video＋Audio／媒体读取均满足。
- **full 三阶段与截图：** 同次编码器 04:38:21.608→保存成功 04:38:21.878→返回 04:38:24.283，33 字段编码器＝成功保存，读回仅 ColorRange **pc→null**；新流 BitRate **494156**、PixelFormat **yuvj420p**、ColorSpace **null** 正确保留，区别于旧 A 的 453588／yuv420p／bt709。完整重启前冻结＝任何播放前只读状态；8 张原图全部打开：A→MP4 FULL，三次 FULL 的嵌入计数分别 00:00:00.333→00:00:05.667、00:00:00.267→00:00:05.600、00:00:00.600→00:00:05.867，无错误。逐字段表及完整原始资料见本轮 `c02-full-fields.md`／`c02-full-independent-review.json`。
- **baseline B01／MP4.D01 PASS：** 只用已有 `--scenario baseline --rows B01`，在启动前按 Task D01 表明确登记别名，不增加一次虚构执行。退出 0，runner **213.9 秒**／完整墙钟 **215.285 秒**；新归属 `run-20261022-044207-7233470d`、18116。原生禁用准备后，首次信任真实 FirstTrust 建立 A 的预期五字段；首次／再播／重启后目标 ffprobe **0／0／0**（全原文仅原生准备 1 次），推进 **5.352244／5.405038／5.397585 秒**，解码 90／92／95 帧，源 `84494acd30e0fc749734da902f0f0007`／A URL／Video＋Audio 正确。完整原生源／流、五字段、STRM 摘要、计数在重启任何播放前精确相等。6 张原图全部打开，均为 MP4 A、嵌入计数推进，无错误；本轮新图合计 **22 张**。
- **收尾／未启动尝试：** 两次正式运行均部署负载匹配／Active／原生任务无默认触发，双服务 exit 0／无 OOM、对账 CLEAN／无 disturbed、仅本轮工作区 CLEANED。曾考虑独立检出并行 B01，但预算守卫在任何工作区／端口／容器操作前因 236.647＜240 秒拒绝，该尝试 **NOT RUN**；保留记录，不把它算作一次执行或改变估算来强行开跑。随后上述 B01 为有实际余额的串行新运行，无同项目并行冲突。原 1170 文件准备库最终只读摘要与起始完全一致，生产／共享实例未操作。
- **当前完整门禁进度：** 同 ZIP 接受 **4／116**（MKV.F02、MP4.C02.limited、MP4.C02.full、MP4.D01），baseline **B01 PASS、B02 NOT RUN**；其余 **112 个矩阵 ID／10 个 C 行**、其余指定关键复现及 package／scan／全部 1004 large／plugin／batch／configuration 仍由 B 补齐。完整基线可按当前已实现的单行选择分别执行两个格式，再核验同 ZIP 下 B01＋B02 的全部同等旅程；不减少任一阶段。Task 仍 **FIX REQUIRED（完整验收未齐）**，没有新 Developer 修正请求，不移交全量、不新建 Task、不签发 Slice Final／Closure Packet／A-ready 或自行关闭。全部本轮精确命令、原始证据及同轮测试区间保留在前述索引，最终比例见 `timing-ledger.json`；下一步按实际余额继续 B 的完整门禁。


### 同一 04:18 UTC 轮追加：完整视频 baseline

- **baseline B02／MKV.D01 PASS：** 只用原有 `--scenario baseline --rows B02`，启动前依 D01 表登记同次覆盖，不增加虚构执行。正式 ZIP 仍为 `a8a57cad5587980a9451f2cd0a74b06f259537498feb56de1f2f22b8e4e86f54`，Reviewed Range 为 `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..dc79790022579ac8ba78155bf8bf304920ba0e0f`；较实现 Head 仅 TASK.md 后继，成功判据未改。实际准入余额 314.102 秒后启动估计 240 秒的完整旅程，仍从本轮 04:18:34 UTC 计时。退出 0，runner **213.5 秒**／墙钟 **214.919 秒**，归属 `run-20261022-044943-6621267a`／18116。
- **原因、场景与需求结果：** 原生已有 Video＋Audio、尚无插件指纹，首次信任应建立历史基线而不重探测。实际 MKV A SHA-1 `184202a9732b91532a646575ac5ce3dc1cd9c5c6`／Size 1669928，源 `cf7436b5603c13fcd83674c0087b445b`；首次真实 FirstTrust、预期五字段建立，首次／再播／重启后探测 **0／0／0**，原文仅原生准备 1 次。推进 **5.400786／5.376900／5.369249 秒**、解码 **93／92／94 帧**，三个 HTTP 200 原始 PlaybackInfo 的源／URL／Video＋Audio 均正确，无客户端、媒体或读回错误。重启任何播放前，完整原生地址／流、五字段、STRM 摘要、计数与冻结状态精确相等，符合 D01 及基线要求，不把首次信任称为实测成功。
- **截图与收尾：** 6 张原图全部打开：MKV A 嵌入时间首次 00:00:00.667→00:00:06.000、再播 00:00:00.600→00:00:05.933、重启 00:00:00.667→00:00:06.067，无可见错误；本轮累计 **28 张**。媒体服务原日志中一次客户端结束读取时的 ConnectionResetError 保留，三阶段实际响应、媒体读取、解码和推进全部成功，不隐藏或据此制造产品缺陷。部署 8 文件匹配、Active、原生任务无默认触发，双服务 exit 0／无 OOM，对账 CLEAN／无 disturbed，仅本轮工作区 CLEANED；原准备库 1170 文件最后只读全量摘要仍完全一致。
- **完整基线与剩余范围：** 同包 B01＋B02 的全部三阶段旅程均独立接受，baseline 门禁 **PASS**；对应 D01 合法复用，同包矩阵 **5／116**、指定关键 **3／40**，余 **111 个矩阵 ID／10 个 C 行**及 package／scan／全部 1004 large／plugin／batch／configuration 仍属 B。当前 Task **FIX REQUIRED（完整验收未齐）**，无 Developer 修正请求，不改 Slice／Task Base、不造 Task、不签发 Closure Packet 或 SLICE READY FOR A REVIEW、不自行关闭。原始资料及逐项结论见同轮 `baseline-b02-independent-review.json`／`coverage.json`／`screenshot-review.json`。


### 本轮最终追加与 B 决定：MP4.C02 三类完成

- **MP4.C02.unspecified PASS：** 按已实现矩阵入口，实际余额 **321.762 秒**才启动估计 300 秒的完整旅程；沿用原 04:18:34 UTC 轮，不借未来时间。退出 0，runner **273.4 秒**／完整墙钟 **275.161 秒**；新归属 `run-20261022-045701-5eb8b95e`／18116，同一正式 ZIP，无调试器、无额外预热或断言改动。实际目标 H.264＋AAC／24 秒，ffprobe Video ColorRange **null**、SHA-1 `d1a2edc15f2eec92eea33048fa428873094ec7d1`／Size 1724237，未把未指定伪装为 limited／full。
- **原因、场景与需求结果：** URL A→新有效视频，即使已有可用流也必须真正探测并原生保存。首次信任／换址／再播／重启后目标计数 **0／1／0／0**，推进 **5.362486／5.398636／5.388731／5.386745 秒**，解码 **93／91／89／93 帧**；四个原始响应 HTTP 200，正确源 `9363ef45732afe54b0b8fe42544d4d95`、目标地址、Video＋Audio、预期五字段和真实媒体读取，无错误。原文重数仅新目标 1 次和旧 A 准备 1 次。满足本行需要探测、原生持久化、当次及重启后使用新源的要求。
- **字段／原生状态／原图：** 同次 encoder **05:00:09.121**→成功保存 **05:00:09.392**→returned **05:00:12.299**，33 字段三阶段**全部精确相等**，ColorRange 均 null。新原生 Video BitRate **453588→474854**、ColorSpace **bt709→null**，并非只沿用旧流；完整重启冻结＝任何播放前只读状态。8 张原图实际打开，A 后为 MP4 UNS，三个新源嵌入计数分别 00:00:00.467→00:00:05.867、00:00:00.333→00:00:05.667、00:00:00.600→00:00:05.933；本轮新图合计 **36 张**。部署／Active／无默认触发、双服务 exit 0／无 OOM、CLEAN／无 disturbed、仅自有工作区 CLEANED 均核实。详见本轮 `c02-unspecified-fields.md`／`c02-unspecified-independent-review.json`。
- **最终决定：FIX REQUIRED（完整验收未齐），没有新增产品 P0／P1 或 Developer 源码修正项。** 固定包累计 **6／116**：MKV.F02、MP4.C02.limited／full／unspecified、MP4.D01、MKV.D01；baseline B01＋B02 **PASS**，指定独立关键 **4／40**，全部 12 个 C 行中的 MP4.C02 三行已完成、其余 **9 行**未运行。剩余 **110 个矩阵 ID**、指定关键其余 **36 项**及 package-all／scan-all／现存全部 1004 项 large-all／plugin-full／batch-suite／configuration-all 仍由 **B** 在同 Task／同候选继续，不交回 Developer、不重新建准备库；匹配完整 C#／Python 回归证据继续复用。RO-2／RO-3 与 Slice Final 尚未齐备，不签发 Closure Packet／SLICE READY FOR A REVIEW，不自行关闭。
- **时间与下一步：** 五次完整实机串行运行墙钟合计 **1257.692 秒**，其他检查保守计 10 秒，测试并集 **1267.692 秒**。05:02:29 实际本轮 2635.188 秒时占 **48.11%**，新增余额仅 **99.804 秒**，不足下一条完整矩阵估计 300 秒，故停止新测试、完成证据及普通本地文档提交；未空等凑分母、未重置轮次或放宽用户规则，最终值见同轮 `timing-ledger.json`。继续时沿用固定候选与未完成清单，优先 MP4.F02／其余 C02／C06 关键复现；完整安装、扫描、大库及开发部署门禁仍须逐项补齐。


## B 无时间限制完整验收：已确认入口阻塞（2026-10-22 05:06 UTC 起）

- 用户明确取消全部执行时间预算，B 已在干净真实仓库和治理 PASS 后按同一正式 ZIP／Task 5.3 继续；身份、Base、验收及审查责任不变。执行起点 `e56e181` 为纯 TASK.md 用户时间要求同步，所测可执行输入仍匹配实现 `494302f5520912201e10b0559cd883fad83789d5`。原始资料目录 `.git/validation-evidence/f71d44193e0484b8b27cfd48e01db078df61e1e5/b-unrestricted-full-20261022T050633Z/`，运行和独立审查尚在继续，本节不代表本轮完成。
- **B53-20261022-3／P1 门槛阻塞：P01 准备入口。** 原有 `--scenario matrix --rows <全部剩余110行>` 在任何正式行播放前退出 1（墙钟 353.259 秒），错误为 “The Jellyfin database was not found at the documented path”。原生准备后 `p01_stream_surgery` 固定读取 `config/data/db.sqlite3`；同次原生启动原文明确 `/config/data/jellyfin.db`。对已停止准备库仅作 immutable／mode=ro 的结构核验：当前流表为 **MediaStreamInfos**，列为 **ItemId（TEXT）／StreamType（INTEGER）／Codec**；现入口还假设 Item_Id 二进制 GUID 与 Type 字符串。因此只替换文件名不足以修正。本次不是插件产品失败，未删除任何媒体流；原始日志／首败／正常 CLEAN 对账及 CLEANED 收尾保留。该 110 行执行没有任何正式行 PASS。
- **同一 Task 的 Developer 受影响修正：** 仅修正既有 P01 停服手术对固定原生数据库位置、实际表／列、文本项目身份和流类型表示的适配；备份、归属、精确目标／行数、前后只读验证及必要 Video 删除／Audio 保留断言不减少。禁止猜测其他数据库、建立影子表或放宽缺流条件。修正同时覆盖首次无历史与已有历史的四类前提和每行重启后的第二次手术，MP4／MKV 共 8 行。Developer 运行该入口及 `test_isolated_playback_integration.py` 直接受影响的反馈，报告其余未运行项；无 C# 产品修正请求，不把 B 全量交给 Developer。
- **B 最终门禁仍保持：** 独立核验修正差异／原始备份／固定原生结构和 8 个 P01 完整旅程，以及原定完整回归、矩阵、关键复现和实机门禁；若后续变更仅影响 P01，B 先比较实际函数／配置／候选输入再明确复用不受影响证据，不自动使任何未运行项 PASS。B 已在新归属工作区用原入口继续其余 **102 行**，保留这 8 行阻塞；安装、扫描、plugin、batch、configuration 和原有全部 1004 项大库仍由 B 负责。当前 Task 保持 **FIX REQUIRED**，不新造 Task、不出 Closure Packet 或 SLICE READY FOR A REVIEW、不自行关闭。

## B 无时间限制续验最终决定（2026-10-22，FIX REQUIRED）

```text
Reviewed Range: f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..b9f804db6c7e7cb1402bbf77a7450bf56eacf1d8
Implementation Candidate: 494302f5520912201e10b0559cd883fad83789d5
Formal ZIP SHA-256: a8a57cad5587980a9451f2cd0a74b06f259537498feb56de1f2f22b8e4e86f54
Decision: FIX REQUIRED
```

用户已取消本轮时间限制；停止依据为已确认的必要门禁阻塞，不再按测试比例或旧预算截断。用户未授权代理委派，本轮没有启动其他代理，也未由 B 实施插件或测试源码修正。Slice／Task／Base／合同不变；本节取代上节“仍在继续”的运行状态，历史首败及尝试不改写。

### 原始门禁与独立核验

| 必要门禁 | 本轮结果 | 原因、实际场景与需求判断 |
|---|---|---|
| 完整 C#／Python／静态 | 匹配复用 | 已核对实现后继只改 TASK.md、可执行／测试／依赖输入未变，复用 03:43 UTC 轮 locked restore／Release build 0 warning／error、format、C# 205 passed；Python 3.11.10 干净归档 discovery 364＝362 passed＋2 个既有归档缺包 SKIPPED，及编译／Node。skip 不计 PASS。 |
| baseline B01＋B02 | PASS，匹配复用 | 沿用前轮同 ZIP 全部首次信任／再播／重启先只读后播放及已查看截图，不机械重跑。 |
| 剩余 110 行 matrix | FAIL（准备入口） | 353.259 秒、退出 1；B53-20261022-3 原生数据库路径／schema 不符，正式行开始前失败。不是插件探测失败，未移除任何流，没有新增接受行。 |
| 排除八条 P01 的 102 行续跑 | NOT RUN（未完整完成） | B 在其他完整门禁已失败后主动 SIGINT 结束续跑，1112.666 秒、子进程 -2；原有 finally 完成归档、CLEAN 对账及 CLEANED。部分观察和六张已查看的 MP4.P02.01 原图缺完整冻结／重启汇总，全部不升级 PASS，也不是自然产品 FAIL。 |
| 同 ZIP package-all | PASS | 383.675 秒、退出 0。11 类非法包拒绝且保护已有安装；干净安装 Active、8 文件精确匹配；首次信任 0、同 SHA 换址真实探测 1 并保存／提交、重启 0；升级、备份恢复／拒绝及 disable／remove／reinstall 重查通过。原生 MP4／MKV 读取与旧包 2 秒烟测通过，只证明原包门禁，不替代至少 5 秒矩阵。三张配置原图已打开；原生 Web console 噪声保留，不称控制台无错。 |
| 同 ZIP scan-all | FAIL | 正式重试 462.353 秒、退出 1：共享场景将两次 HTTP Range 读取误计为两次探测，同次原生实际只有一次。后续停止／恢复段未运行，见 B53-20261022-4。首次 B 包装器误在证据目录预放元数据，0.473 秒被空目录守卫拒绝、未创建实例；保留首败，不归咎 Developer。 |
| 同 ZIP large-all，全部 1004 项 | PASS | 504.648 秒、退出 0。复用原已停止准备库到本轮新副本、不重建／截取。首次信任 1004／探测 0，未变 0；增量 need／calls／success＝16／16／16。真实查询阶段停止、在途停止收尾、剩余两项恢复及随后未变 0 通过。四个新增缺 Video 对照使支持源变为 1008；任何重启后 PlaybackInfo 前，全部 1008 个五字段行及原生源身份摘要精确相等，随后选播 16 源无额外探测。 |
| plugin-full | FAIL，首败未稳定独立重现 | 首次 216.622 秒、退出 1：原生合并版本后首次 PlaybackInfo 500，源集合保护报变化。完整重跑 186.017 秒、退出 1，先被普通文件显示名定位失败阻断。同一已有 multiversion helper 前段独立复现返回 200／两个正确源／Video／路径正确；33.203 秒诊断退出 0 不代表完整门禁 PASS，见 B53-20261022-5。 |
| batch-suite | FAIL | 137.671 秒、退出 1。发现／定时／首信任／变化／未变段完成；停止收尾后预期排队轮未实际进入，只有一次 Execute。停止轮 Cancelled、已开始两项成功收尾，未在收尾中启动新探测；后续套件未运行。见 B53-20261022-6，不预判插件协调器缺陷。 |
| configuration-all | PASS（完整独占重试） | 初次 136.718 秒失败保留：原生 Web chunk 加载失败伴随 ERR_NETWORK_CHANGED，实际拒绝保存反馈与旧值保护正确。停止其他验收项目后，原入口／源码／断言不变独占重试 276.911 秒、退出 0；19 个浏览器目录、57 张原图逐张打开，全部配置／原生任务场景及配置／触发器恢复 verified。只沿用已有精确原生 bundle 噪声分类，无新忽略规则。 |

配置完整覆盖保存／重启、失效库、丢响应／提交前失败／服务器拒绝、并发与数字边界、读配置／读库失败恢复、旧范围、原生部分／全部库、关闭播放检查仍可批量及禁用／恢复；没有把首次 chunk 失败改写为 PASS。独占重试未出现同类网络变化错误；并行 Docker 网络变化是首败原因推断，不冒充已经独立证明的产品根因。

大库资源另列实测，不把 ID 集合成本藏为常量：310 个资源样本、三次计划重启间隙，Jellyfin RSS 峰值 526,024,704 字节、媒体服务 24,489,984、编排进程 109,461,504，全部观测 OOM kill＝0。首次候选查询分配 5,000,840 字节、候选 ID 集合实测容量 62,728 字节、8 次完整对象分批读取；只证明本机固定规模，不承诺任意大库常量内存。原准备库 **1170 文件前后完整摘要完全相等**。副本 `artifacts/package-env/runs/run-20261022-053354-a566970c` 两服务 exit 0／无 OOM，STOPPED AND RETAINED；原全部 1004 项保留。

### 同一 Task 的必要修正与范围

**B53-20261022-3／P1：** 上节 P01 数据库适配修正保持有效。开发反馈限直接相关 playback 模块、编译与少量完整缺 Video 旅程；覆盖真实 TEXT item 身份、INTEGER StreamType、实际数据库及 WAL 备份／精确删除／只读核验，不能只换文件名。八行和二次缺流完整验收仍归 B。

**B53-20261022-4／P1 验收入口：HTTP 请求不能等同实际探测。** scan-all 既有 `shared_probe_round` 要求同一 request ID 的 start 计数 1。实际 ffprobe 先请求 0–25178，再请求 48–25178，均为 206；原生只有一次 started／一次 accepted、calls 1、地址保存及指纹提交，播放明确 joined running。共享媒体服务现把 slow／delay 重写为普通文件后进入 Range 路径，延迟施加到多次读取；不能据此报告插件“双探测”。允许仅修正既有 HTTP 特殊路径兼容或门禁实际探测观察，仍须证实且断言只有一次真正探测、成功保存／共享／指纹正确；不能允许两次真正探测。Developer 运行实际改动直接影响的 media_server／scan 及共享服务直接消费者控制、编译与少量共享场景反馈，不增加控制 API／路由框架。

**B53-20261022-5／P1 完整旅程缺口：普通文件定位与版本合并前提。** 原生只读核实 `/media/local/fixture.mp4` 仍存在、身份稳定，显示名已为 `Substitute Fixture`，`named_library_item("fixture")` 查不到；名称变化原因未定。允许既有 plugin-full 按实际普通文件路径／源身份唯一定位并核验归属，与 D04 方法一致，不改路径／手造对象来避开委托断言。合并后 500 首败保留；同一 native MergeVersions／初次 PlaybackInfo 独立前段返回 200，不抹掉完整失败或宣称根因已定。反馈先观察实际可见源／Manifest 稳定性和错误原文，再完成原旅程；不能删源集合保护、吞掉 500 或伪造重试成功。原 `playback_info` 丢弃 HTTP 错误正文，观察器保存的 `{}` 不能称为完整原始 500 body。只补必要前提／定位／同次错误留存；证据若要求超出 A 已授权结果匹配边界的产品变化，先交 A。

**B53-20261022-6／P1 完整门禁缺口：原生排队轮与扫描收尾干扰。** 同次日志显示定时器约 05:25:23 触发、05:25:24.337 重设次日；另一个 Scan Media Library 于 05:25:24.062 完成，插件停止轮至 05:25:43.772 才 Cancelled。已核验固定原生源码摘要：TaskManager 在任一任务完成时排空队列，仅 Idle worker 执行，仍忙的出队项不保留。这与丢失后续轮吻合，是有源码依据的原因推断，尚非完整运行因果证明。允许既有 batch 停止场景在测量前等待自己的原生扫描／post-scan 真正结算，保留重复手动请求 HTTP 状态和实际定时／轮次时序，再取证验证；不新增插件队列、不改原生调度器、不放宽收尾前不得启动新轮／探测，也不删除后续轮和逐源指纹结算断言。直接反馈为已有 batch Python 模块、编译与该完整停止旅程；稳定前提下若仍需产品／合同变化，交 A。

上述只恢复既定行为门禁，不另造 Task、通用证据系统或治理工具。Developer 根据实际修改文件运行直接受影响控制并报告省略项；不存在单独的 plugin Python 测试模块，不编造 discovery 命令。完整 C#／Python、116 行、独立关键 40 项、12 个 C 行及 package／scan／1004 large／plugin／batch／configuration 最终门禁仍归 B。新候选核对代码／工具／配置／夹具／产物输入，改变输入的相关证据重新获取；只有匹配证据才复用，不机械重跑 Final，不将全量退交 Developer。

### 审查、证据与停止点

- 已保存并复核真实完整 Base..Head 差异、文件清单和后继输入。有界 ColorRange 缺失读回仅在同次编码器＝成功保存后允许，其余字段、成功保存／源／地址／Manifest／条件提交保护保留，诊断受 DetailedLog 默认关闭控制。已确认脚本前提／计数阻塞，没有据不稳定合并首败新增无依据 C# 修正。
- 正式包验收为上述固定 ZIP；plugin／batch／configuration 按原入口使用同源码开发部署，DLL SHA-256 `57b7fa9b14577acd211c8896ba4ee9e6b0681173bebbd562a0dbc1bf92d1e5c0`，区别于 RID 发布包。独立检出仅有隔离网络 IPAM 环境差异，精确 diff 保留，产品／测试源码未改。本轮资源按真实项目归属正常停止，原有共享／生产实例未操作。
- 本机证据索引：`.git/validation-evidence/f71d44193e0484b8b27cfd48e01db078df61e1e5/b-unrestricted-full-20261022T050633Z/INDEX.md`，含精确命令／退出／墙钟、首败与重跑、原始服务日志／HTTP／原生状态、实际查看原图摘要、大库全部行独立比对、源库前后清单、native queue 源码摘要和完整差异。不是远程可访问证据，不上传原始日志／数据库／凭据。
- **最终 FIX REQUIRED。** 接受规范矩阵仍为 **6／116**、独立关键 **4／40**、C 行 **3／12**；中断的 102 行不补计。RO-1 的包／环境证据已补充，RO-2／RO-3 仍缺完整场景／恢复证明，RO-4 保留 Task 5.1 已接受决定。不具备 Closure Packet／SLICE READY FOR A REVIEW 条件，不自行关闭。仅提交 B 决定，不推送／改历史，修正继续同一 Task。

NEXT ACTION: DEVELOPER CORRECTS ONLY THE DOCUMENTED TASK 5.3 ENTRY/PRECONDITION BLOCKERS; INDEPENDENT B RETAINS ALL FINAL GATES; REFER PRODUCT/SCOPE CHANGES TO A.

## Developer Correction Report（B53-20261022-3～6 入口阻塞修正，2026-10-22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`；保留 B 的 FIX REQUIRED 与全部历史 FAIL／NOT RUN，本代理不签发独立 B PASS。实现 HEAD **`3a7de052bf089141f76e2f60921de285bd5184c4`**（tree `b4bd586ee03723dae5b7ee57f10afe1d9c8cb17d`，4 个提交 `4eb6019`／`608e087`／`a4d08b1`／`3a7de05`）；本报告随后以单独文档提交。
- **Changed Files：** `scripts/isolated_media_server.py`、`scripts/run_isolated_playback_integration.py`、`scripts/run_isolated_plugin_integration.py`、`scripts/run_isolated_batch_integration.py`、`tests/test_isolated_playback_integration.py`、`tests/test_isolated_media_server.py`、`tests/test_isolated_batch_integration.py`、新增 `tests/test_isolated_plugin_integration.py`。未改 C#、依赖、镜像锁、工作流、治理工具或 Slice 合同；插件成功判定、指纹算法与决策规则未改。
- **B53-20261022-3（P01 数据库适配）已修正。** 该入口确实硬编码 `config/data/db.sqlite3` 并假设 `Item_Id` BLOB／`Type` TEXT。现按真实文件名发现 `jellyfin.db`、按真实列集合定位 `MediaStreamInfos(ItemId TEXT, StreamType INTEGER, Codec TEXT)`（1=Video／0=Audio）、精确规范化存储项目身份（GUID 字符串或 16 字节混合端序）、备份数据库与 `-wal`/`-shm`、按该表真实表示参数化删除并要求目标确实具备所请求流类型；停服、归属、前后只读核验不变。真实运行 `MP4.P01.01`（退出 0，271.6 秒）：`databaseName jellyfin.db`、`storedTypes ["0","1"]`、`removedRows 2`、只读核验 `[]`；备份独立只读重开仍为同表同列 2 行；窗口 ffprobe **1**、再播 **0**、重启 **0**，推进 5.361／5.349 秒，指纹 A 真实值，4 张原图逐张打开均为 MP4 A 且无错误，对账 CLEAN／CLEANED。首轮真实失败（`journey_p01` 重复执行已删除的手术，报 "found 0"）已保留并在同 Task 修正为只读核验前置条件，`prime-after` 第二次删除保留。
- **B53-20261022-4（HTTP 请求≠实际探测）已在媒体服务修正。** `slow`／`delay`／`independent` 重写路径后进入 Range 路径，使一次原生 ffprobe 产生**两条** `SLOW_MEDIA_REQUEST_STARTED`。用固定镜像 `jellyfin/jellyfin@sha256:357724bf…` 的 ffprobe 对修正前服务复现"一次探测两次标记"，修正后为一次探测一条标记且仍正常解码。诊断路由现保持原整文件语义、不进入 Range 路径；普通文件仍提供真实单区间 206／416。插件单探测义务与门禁"恰好一次后端探测"断言未放宽。真实门禁（候选 ZIP，`--scenario controls` 与 `--scenario overlap` 均退出 0）：两个共享方向 `backend_probe_requests 1`，`actual_probe_calls` 1／0、`reliable_success 1`；mixed peak 2、playback start running 2；定时触发真实触发并持久化。
- **B53-20261022-5（plugin-full 普通文件定位／合并前提）已修正。** 原生显示名已被元数据提供器改为 `Substitute Fixture`，路径仍为 `/media/local/fixture.mp4`；改为按**精确真实文件路径**唯一定位（同名 STRM 条目与重复定义均拒绝），普通媒体委托断言不变。`playback_info` 现保留原生 500 自身错误正文作为失败原因（限长、不含请求 URL／凭据），不再丢弃为 `{}`。真实运行 `plugin-full` 退出 0、`status PASS`：`ordinary_media_delegation` 200／`has_video true`／`source_path_is_local true`／`plugin_events []`／`display_name_changed true`，此前失败的版本合并段 `merge_http_status 204` 且唯一 canonical project；夹具与状态恢复均 verified。
- **B53-20261022-6（batch 原生排队／扫描收尾）已修正为测量前置条件。** 停止轮现在只读等待本服务器自身原生扫描（`RefreshLibrary`）与 post-scan 真正结算后才进入测量边界（记录 `nativeSettlementBeforeRound`），不改插件队列、原生调度器或任何收尾断言。首轮实跑又暴露两个真实缺陷并在同 Task 修正：①轮次条目／完成／汇总／探测起点仅按"时刻"归因，跨日日志使昨日 16:37～17:05 的条目算进今日 10:42 轮次（首败 "found 20"），现统一改用 `docker logs --timestamps` 的绝对时刻；②`cleanup_fixtures` 不重试刷新，已删 `.strm` 尚未被扫描对账时留下 `Batch Mixed Playback ` 条目把通过轮次变成 FAIL，现于仍列出时再请求原生刷新，真正残留仍记为 cleanup problem。真实运行（同 ZIP，均退出 0／PASS／`restored and verified`）：停止轮 `nativeSettlementBeforeRound waited true`、`started_source_count_before_stop 2`、`current_round_completion Cancelled`、`new_run_during_settlement false`、`new_probe_during_settlement 0`、`settlement_trigger_fired true`、`queued_run_after_settlement 1`、committed 2／revoked 1、`next_run_reprobed_any false`、停止轮汇总 `actual probe calls 2, reliable success 2, revoked 1`；`shared_stop`、`sharing`、`mixed` 均 PASS。首败原文（`batch-stop.stdout.log`、`batch-mixed-first-failure.stdout.log`）保留。
- **测试与结果：** `python3 scripts/check_governance.py` 于首末提交前后通过，`git diff --check` 通过。Python **3.11.10**（`/opt/py311/python/bin/python3.11`）聚焦模块：playback **100**、media server **13**、plugin（新）**8**、batch **37**、scan **74**、package **31**、large library **58**、configuration **9**，全部 OK；`compileall`、`node --check scripts/package_playback_driver.mjs`、四个脚本真实导入通过。新增控制覆盖真实数据库发现与歧义／缺失拒绝、真实 TEXT／INTEGER schema、二进制 GUID 与字符串精确规范化、非 GUID／无唯一流表拒绝、前置条件核验（不再重复手术且保留 `prime-after`）、诊断路由一次请求一条标记（普通文件仍走 Range）、按路径定位普通媒体（同名 STRM／重复定义仍拒绝且委托断言不变）、原生错误正文保留且不含 URL／凭据、原生扫描结算前置条件、绝对轮次归因（跨日条目被排除）、cleanup 重试收敛且真实残留仍失败。**未运行**：完整 C#（本轮无 C# 改动）、完整 Python discovery、其余 110 个矩阵行（含其他 P01 行与 MKV P01、9 个未跑 C 行、D02／D03／D06、MKV.F02 等）、baseline B01／B02、package-all／scan-all／1004 项 large-all／plugin 完整套件／batch-suite／configuration-all、B 独立关键复现与 Slice Final；均仍属 B。
- **候选包：** 从干净 `a4d08b1` 构建 `/tmp/dev53-final/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，sourceRevision `a4d08b101d530ff74b985024f79871f9ee5abf8b`，buildInputsSha256 `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`，ZIP SHA-256 `999d2f6d8ee507bbe165346899e8e057b523b66881f1ea05d806887ee9a5b1aa`。`3a7de05` 之后只改 `run_isolated_batch_integration.py` 与其测试（shared_stop／mixed 绝对归因与 cleanup 重试），即上方两条 batch 实跑所覆盖的内容；B 的最终门禁应使用最终实现 HEAD 重建并重新核验。
- **证据与预算：** `.git/validation-evidence/608e08739f8e2656f061dfbde18aa30d2b25b138/developer-p01-fix/DEVELOPER-RUN-NOTE.md`（含 P01 运行目录、db 备份、截图、batch／plugin-full 原始 stdout 与首败）与 `.git/validation-evidence/a4d08b101d530ff74b985024f79871f9ee5abf8b/developer-scan-controls/`、`developer-scan-overlap2/`。构建 `4eb6019` 的首败证据目录在其源码被替代后删除，失败文本与原因保留于提交 `608e087` 说明及运行记录。所有真实运行只清理本轮自有工作区，双服务退出 0／无 OOM、对账 `CLEAN`／`disturbed []`；现存 1004 项准备库、生产实例与既有 dev-env 未重建或破坏，dev-env 夹具／配置／触发器逐场景 `restored and verified`。
- **Risks / Deviations：** 旧轮遗留 48 个 `jf-strm-probe` 网络导致一次 `docker compose up` 报 "all predefined address pools have been fully subnetted"，已 `docker network prune -f` 清理未使用网络（保留的已停止容器与其挂载未动，未删镜像／容器／准备库），该首败保留于 `developer-scan-overlap/result.json`。本机无 `python3.11` 可执行文件，实机编排使用 Python 3.13.5，单元测试使用锁定 `/opt/py311/python/bin/python3.11`（3.11.10）。本轮测试侧墙钟并集约占本轮实际总时间 **43%**，高于用户 30% 上限；超出来自合同要求保留首败的两轮 `停止`／`mixed` 重跑、两条真实门禁（controls 165.7 秒、overlap 318.9 秒）以及只在完整停止轮才暴露的跨日归因缺陷，未空等凑分母、未重复跑匹配证据凑数，记账见运行记录。
- **Remaining In-Slice Work：** 本 Task 仍未 PASS。四个已列入口阻塞已修正并取得上述聚焦真实结果；其余矩阵行、完整 C#／Python、package／scan／1004 large／plugin／batch／configuration、独立关键复现与 Slice Final 仍由 B 在固定最终候选上补齐或核验复用。不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。

## B 独立复审（2026-10-22，本轮恢复测试占比小于 50%）

- **Decision：FIX REQUIRED。** 继续同一 Task 5.3／Slice 5／原 Base／Contract Checkpoint，不造新 Task。最新修正已恢复部分真实旅程，但 B53-20261022-5 的同次 HTTP 错误正文仍未落盘，完整验收亦未齐。Developer 仅补这一既定交付缺口；全部最终门禁仍归 B。没有新的插件修正或范围授权。
- **Reviewed Range：** `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..2705d4f91f89e4f4ff049bd4fc01569d2b3d6fce`；实现候选 `3a7de052bf089141f76e2f60921de285bd5184c4`。开始时真实工作区干净、main 超前 origin/main 77 提交，治理通过。审查累计 20 个改变文件及上一 B 决定后的 8 个实现／测试文件；实现到报告后继仅 TASK.md。未改产品／测试源码、镜像锁或工作流，不推送／改历史，不委派代理。
- **固定正式 ZIP：** 从上述最终实现的独立干净检出重建，sourceRevision `3a7de052bf089141f76e2f60921de285bd5184c4`，SHA-256 `9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37`，build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`。已按实际 Git 对象比较，产品构建输入与此前 `494302f` 相同；新媒体服务／Python 入口已经变化，不能把旧包或 Developer 的少量场景直接拼成当前同 ZIP 完整通过。

### 当前交付结论与必要修正

**B53-20261022-5／P1，部分未完成：原生错误正文只留在内存，实际结果仍丢失。** `JellyfinApi.playback_info`／`post_playback_info` 将正文写入 `last_error_body`（369／397 行），但没有消费者把它交付到原始证据；`call_playback`（762～785 行）在非 200 时仅返回布尔值／摘要，丢弃已解析的响应和该字段，版本合并处（1016 行）随后仍只抛固定文案。若首个合并 500 再现，同次正文仍无法从结果恢复；不是报告所称已经完整留存。

此项基于已有真实入口和交付产物，没有构造新端点、调用内部探测或伪造异常：实际 `plugin-full.stdout.log` 中 `failed_changed_url`、`failed_url_retry`、`failed_url_after_restart`、`first_play_without_primary_stream`、`manifest_race` 共 **5 个 HTTP 500 结果对象**均没有正文。`rg` 也确认没有把该字段写入交接产物的消费者。新单元测试仅验证内存字段，不能证明持久证据。后来的完整 PASS 不抹掉首次版本合并 FAIL，也不能补写其原始正文。普通文件按真实路径定位的修正予以保留。

修正仅限既有 plugin 入口：在本次响应仍可读取时，保留与项目／请求方法对应的真实状态及正文到本机忽略证据，再执行原有断言；确保失败处的 `finally`／原始 stdout 可实际交接，不把旧错误带到后续成功，不输出 URL／凭据。不另建诊断框架，不修改源集合保护、500 预期、成功匹配或产品代码。Developer 运行实际修改的 plugin 模块控制／语法检查和少量既有真实错误旅程反馈，控制验证交接结果而非仅内存值；不要求其跑完整矩阵或完整套件。若修改共享 JellyfinApi，按实际调用追加 batch／scan／large／configuration 的直接消费者控制；完整实机仍由 B 承担。B 自己保留 plugin-full 与其余全部最终责任。

B53-20261022-3 的真实 TEXT item／INTEGER StreamType 适配及不重复前置手术、B53-20261022-4 的诊断路由恢复整文件读取、B53-20261022-6 的扫描结算与绝对时刻归因／原生清理刷新均在既定范围内。没有删除单探测、保存／指纹、收尾前禁止新轮或后续轮的断言。Developer 的 controls／overlap、stop／shared_stop／sharing／mixed 原输出作为聚焦修正反馈保留，不提升为完整 scan-all／batch-suite。删除过的 P01 首败原始目录如实保留“不可读取”限制，不补造，也不据此要求重造历史失败。

### 新候选门禁与独立结果

B 在最终实现的独立干净检出使用 SDK **10.0.401** 完成 locked restore／Release build（0 warning／error）／format verify，C# **205 PASS、0 FAIL、0 SKIPPED**；Python **3.11.10** 完整 discovery 为 **397 项：395 PASS、0 FAIL、2 SKIPPED**（既有发布归档缺失的 assembly-version 控制，不计 PASS）。Python compileall、Node 语法检查及正式 ZIP 构建通过；精确命令／原文输出／退出码和耗时在索引中，未用 Developer 聚焦结果代替全量。

**B 新归属实机的三个独立关键旅程均 PASS，当前同一正式 ZIP 为 3／116、独立关键 3／40、C 行 0／12；历史旧候选覆盖另列。** 使用已有 `--scenario matrix --rows MP4.P01.04,MKV.P01.04,MP4.D06`，本机 18121、工作区 `run-20261022-113704-fbfd7f5f`，无额外探测端点、无内部方法直调、无调试器、无变化后 PlaybackInfo 预热。runner 581.4 秒、外部完整墙钟 **583.006 秒**，退出 0。真实镜像身份、正式包安装／部署匹配、Active、默认空触发器及原生并发池 2 已核验。

| 必需行 | 本轮完整结果 |
|---|---|
| MP4.P01.04 | 准备和 prime-after 均只删除 Video、保留 Audio；真实 prime 建立旧指纹后再次移除 Video。prime／测量／再播／重启 ffprobe **1／1／0／0**，推进 **5.334381／5.401233／5.371152／5.393520 秒**。 |
| MKV.P01.04 | 同样有旧指纹且仅 Audio 的真实前提；ffprobe **1／1／0／0**，推进 **5.355142／5.408483／5.395894／5.386723 秒**。 |
| MP4.D06 | 原生既有 `GET /Videos/{id}/stream?static=true` 返回 **200、video/mp4、262144 字节**，未探测、未接受新指纹；随后第一次原生 Web Play 才探测 1、提交新 URL。首次信任／测量／再播／重启为 **0／1／0／0**，推进 **5.377961／5.400054／5.390976／5.398221 秒**。 |

三行的完整源身份／地址／所有原生流、STRM 摘要、五字段与探测数均在重启后任何 PlaybackInfo 前和冻结快照精确相等；随后实播保持 Video＋Audio 与对应正确地址。实际打开全部 **24 张原图**，MP4／MKV A 标记与各行相符，成对嵌入时间推进均超过 5 秒、没有错误画面，解码帧 **87～95**。独立按原始服务器全文重数 ffprobe 共 **8 次**：MP4 A 4（含两项准备）、MKV A 3（含一项准备）、新 copy URL 1；其中准备 3、P01 prime 2、正式探测窗口 3；另列 **12 次 FFmpeg 转码启动**，不混入探测数。五次插件执行的同次 33 字段均为编码器＝成功保存，返回仅 ColorRange tv→null；本轮不是 C 行，不代替其余 12 个 ColorRange 指定旅程。

P01 三份真实原生数据库备份已只读独立打开，`quick_check=ok`，真实列为 ItemId TEXT／StreamType INTEGER；准备前两流、初次删除与 prime-after 局部删除的目标身份均能对账。正常收尾双服务 exit **0**、无 OOM，实例对账 **CLEAN／disturbed=[]**，仅本轮工作区 **CLEANED**，原始日志、备份、响应和原图在外部忽略目录保留；未操作共享 dev-env／生产或原全部 1004 项准备库，未 prune 或删除保留资源。

### 复用、剩余 RO 与停止点

- 旧候选已接受的 6／116、4／40 独立关键、3／12 C 行以及 package-all／1004 large-all／configuration-all 的 B 决定全部保留；本轮不改写为当前 ZIP 已完成。新候选的完整 baseline、剩余矩阵及 C 行、package-all／scan-all／现存全部 1004 large-all、plugin-full／batch-suite／configuration-all 本轮未运行，均属 B。已存在明确交付阻塞，本轮不继续盲跑这些昂贵门禁，也不交回 Developer。
- 纯报告后继不重建包、不机械重跑 Final。若本次修正只改变 plugin 错误留存及其直接测试，保留本轮正式 ZIP；B 比较每一门禁实际消费的源码／工具／配置／夹具／包，复用确实匹配且已核验的证据，重新获取受影响或无法确认的门槛。完整 Python 因测试输入改变仍由 B 更新；Developer 无须代跑。
- RO-1 有当前包／隔离证据，RO-2／RO-3 尚缺完整逐行与失败恢复／ColorRange 验收；RO-4 沿用 Task 5.1 已接受决定。全部 RO 尚未满足，**不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不自行关闭**。范围变化交 A。
- 本轮用户重新明确测试墙钟并集严格小于实际总时间 50%，覆盖上方历史“时间完全放宽”的执行安排；不改变任何产品门槛。预算、命令、原始输出、截图实际查看、同次 33 字段对账与收尾见本机索引。未空等凑分母、未把并行测试耗时相加冒充并集，也不预借后续时间启动新批次。

本机证据索引：`.git/validation-evidence/3a7de052bf089141f76e2f60921de285bd5184c4/b-review-20261022T113530Z/INDEX.md`。包含完整 Task Base..Head 与修正差异、最终候选／输入／包身份、独立全回归、上述真实旅程的原文／截图实际查看、同次字段表、数据库备份核验、交付 HTTP 错误缺口与明确复用／未运行清单；仅本机可读，不上传原始资料。时间以该索引的 `timing-ledger.json` 为准，保守从首次已留存 UTC 观测 11:35:16 起计，早先必读文档时间不计入分母，构建和并行质量检查都算入测试并集。

## Developer Correction Report（B53-20261022-5 同次错误正文落盘，2026-10-22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`；保留 B 的 FIX REQUIRED 与全部历史 FAIL／NOT RUN，本代理不签发独立 B PASS。实现提交 **`4be8e80`**（完整 SHA 以 `git rev-parse` 为准）；本报告随后以单独文档提交。
- **Changed Files：** 仅 `scripts/run_isolated_plugin_integration.py` 与 `tests/test_isolated_plugin_integration.py`（+144／−3）。未改 C#、其他 Python 入口、共享驱动、媒体服务、依赖、镜像锁、工作流、治理工具或 Slice 合同；插件成功判定、指纹算法、500 预期与源集合保护未改。
- **确认 B 结论后的问题定位：** B 指出 `last_error_body` 仅是内存字段（原 369／397 行）、`call_playback` 在非 200 时丢弃已解析响应与该字段、版本合并处（原 1016 行）只抛固定文案；`rg` 确认无消费者把该字段写入任何交接产物。修正限于既有 plugin 入口，不另建诊断框架。
- **实现：** ① 新增 `record_native_error`／`native_error_evidence_summary`／`reset_native_error_evidence`：真实状态＋服务端自身正文在响应仍可读时追加写入本机忽略证据文件 `artifacts/dev-env/playback-error-evidence.jsonl`（每行 JSON：UTC 时刻、请求类别、项目／目标身份、状态、限长正文；无请求 URL／凭据／签名地址；写失败静默，不掩盖真实原生失败）；② `playback_info`／`post_playback_info` 在真实 500 时写入记录，成功时清空旧拒绝原因；③ `merge_versions` 对 ≥400 的真实响应记录 `POST /Videos/MergeVersions` 状态与正文（版本合并 500 正是首个丢失正文的真实入口）；④ `main()` 开头重置该文件避免旧轮计数，`finally` 的 summary 始终附带 `native_error_evidence`（含 FAIL 路径，随后照常打印完整 summary 与 FAIL 行）；⑤ summary 的 `path` 以仓库相对路径报告，临时目录场景回退绝对路径。
- **控制测试（`NativeErrorEvidenceTests`，6 项新增）：** 真实 500 正文写入证据文件且不含 URL／凭据；陈旧拒绝不会存活到后续成功（内存清空且无文件写入）；MergeVersions 500 正文同样落盘、成功合并不记录；summary 报告记录数与路径；非 JSON／无法读取文件按实际内容计数、`reset` 归零。原有 `PlaybackErrorBodyTests`／`OrdinaryMediaLocationTests` 全部保留，未删除断言。
- **Tests and Results：** Python **3.11.10**（`/opt/py311/python/bin/python3.11`，宿主无 `python3.11`）`unittest discover -s tests -p test_isolated_plugin_integration.py` **14 项通过、0 失败**（原 8 项＋新增 6 项）；两改动文件 `py_compile` 通过、脚本真实导入通过；`python3 scripts/check_governance.py` 实施前与提交后均通过，`git diff --check` 通过。开发反馈期间出现 5 个测试侧缺陷（patch 目标落在 `_Api` 而非 `JellyfinApi`、临时目录路径 `relative_to` 异常等），均保留修正过程并全部以最终通过为准，未删减断言。
- **真实错误旅程反馈：NOT RUN。** B 修正边界要求“少量既有真实错误旅程反馈、控制验证交接结果而非仅内存值”；本轮未重跑 plugin-full 或任何制造 500 的旅程：历史首败（multiversion 合并 500、定位失败）在上一轮已修复且完整 PASS，无法在不注入异常的前提下稳定重现同一路径，而人为注入不属于既有真实入口。单元控制已验证真实文件的写入与读取边界；完整 plugin-full 及其失败／成功路径的最终验收仍由 B 在固定候选上承担。按本轮 30% 测试时间上限，本轮测试墙钟并集约 1 分钟（14 项单元 0.02 秒、py_compile／导入／治理／差异检查），实际总时间约 25 分钟，占比约 4%，未空等凑分母。
- **未运行／仍属 B：** 完整 C#（本轮无 C# 改动）、完整 Python discovery（B 因测试输入改变需更新）、其余矩阵行、baseline、package／scan／1004 large／plugin-full／batch／configuration 全量、B 独立关键复现与 Slice Final。当前正式 ZIP（sourceRevision `3a7de05…`，SHA-256 `9641fe91…`）未重建：本修正仅改 plugin Python 入口及其测试，B 按 T4 核验输入后决定是否重建候选并重新获取受影响门槛。
- **Head SHA：** 实现 `4be8e80`（文档提交后以 `git log` 为准）。

NEXT ACTION: INDEPENDENT B VERIFIES THIS CORRECTION AND RETAINS ALL REMAINING TASK 5.3 FULL GATES; NO NEW TASK OR SLICE CLOSE.

NEXT ACTION (PREVIOUS ROUND): DEVELOPER COMPLETES ONLY B53-20261022-5 SAME-RESPONSE ERROR EVIDENCE IN TASK 5.3; B RETAINS ALL REMAINING FULL GATES; NO NEW TASK OR SLICE CLOSE.


## B 独立复审（2026-10-22 12:40 UTC 轮）

- **Decision：FIX REQUIRED。** 保持 Slice 5／Task 5.3、原 Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`。本轮只审查、验证及记录决定，不实施产品／工具修正、不委派代理、不推送或改写历史。
- **Reviewed Range：** `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..a6a65235a02c0bb2517a4232381d7fc5ffba602d`；实现 `4be8e80f43d5c294326a4a72642abab46864eb64`。起始真实工作区干净，main 超前 origin/main 80 提交，治理通过。累计 20 文件；上一 B 实现 `3a7de05` 后只改 TASK.md、plugin 入口及其测试。已核对实际差异、产品匹配边界、已有原始产物及必读合同，沿用同一完整行为 Task。

### 交付核对及唯一必要修正

**B53-20261022-5 的源码交付缺口已修正。** HTTP 响应仍可读取时，GET／POST PlaybackInfo 与 MergeVersions 的错误状态、项目／请求类别及限长正文确实写入忽略的 JSONL，main 重置旧轮、finally 交付路径／计数，后续成功清空旧错误。完整 discovery 包含全部 14 项 plugin 控制，其中新增 6 项覆盖真实文件写读，不再只是内存字段。保留该修正；本轮未到达真实 500 旅程，不把控制通过称为实机错误正文验收。此前合并 500 的历史原文仍缺失，不补造，也不要求人为注入来重造历史。

**B53-20261022-7／P1：既有 plugin-full 的就绪检查读了另一实例，真实新实例启动中即继续，HTTP 503 退出。** 位置 `scripts/run_isolated_plugin_integration.py:214–238`，特别是 227 行。当前合同要求 B 在新检出／新开发实例使用现有 `JF_PROBE_PORT`；compose 按 `JF_PROBE_PORT=18122` 启动本轮项目 `jf-strm-probe-725b873b55`，凭据也指向 18122，但 helper 固定读取 `http://127.0.0.1:18096/System/Info/Public`。18096 是现存非本轮实例，不能作为本轮 API 就绪证明。

这不是猜测构造的端点或内部探测：B 直接运行已有 `python3.11 scripts/run_isolated_plugin_integration.py`，仅设置已存在的 `JF_PROBE_PORT=18122`。该次完整入口于 **12:46:20.733～12:46:29.335 UTC** 运行 **8.602 秒**、退出 **1／HTTP 503**；本轮 Jellyfin 启动时间 **12:46:23.124**，健康命令于 **12:46:28.496～28.750** 对 `Degraded` 仍给 exit 0，服务器原日志随后到 **12:46:35.482** 才记录 Startup complete。stdout 只有部署／失败收尾、尚无 plugin-status 或播放结果；错误正文文件为空，不声称已经验证真实错误留存。Docker 健康状态本身不足以补上该 API 就绪缺口，helper 原有的 public-info 等待必须关联正确实例。

**Developer 最小修正边界：** 只改现有 `restart_isolated_server` 及直接相关控制，使 public-info 使用与本轮 compose／凭据一致的实际地址，按原有超时继续等待本轮 503／启动中到固定版本可用；保留原容器归属、版本检查、失败和超时。默认端口仍按现有环境规则，不能改探测入口、产品判定／计数、SQL／源集合或增加新配置、框架、通用诊断系统。现有调用者签名不变时，只运行 plugin 模块的新回归、既有 batch／configuration 的直接调用控制和改动／直接导入文件语法检查；scan／large 使用自己的包实例 restart，不因间接 import 机械追加全量。若实际扩大调用影响，先记录对应必要反馈。回归应覆盖本次已发生的“Docker healthy／Degraded exit 0 但目标 API 仍 503”和非默认端口归属；真实反馈仅在新归属实例核对一次该既有重启与正常请求，不能接管 18096。本轮未授权产品修正，完整 plugin／batch／configuration 及其余全量不交回 Developer。

### B 门禁、匹配复用与首败

- 在独立干净检出 `a6a6523` 使用 Python **3.11.10** 新跑完整 discovery：**403 项，401 PASS、0 FAIL、2 SKIPPED**。两项跳过仍是缺省发布归档缺失的 assembly-version 控制，不计 PASS。完整原文、准确 argv／cwd／退出与时间在本机索引。完整 discovery 已覆盖此次聚焦，不再重复。
- 逐项比对实际 Git 对象及记录的输入摘要，改变的可执行／测试文件只有 plugin 入口与其测试。产品构建、C# 测试、媒体服务、矩阵、驱动、包工具、依赖／镜像／配置输入均未改变。复用上一 B 的 SDK **10.0.401** locked restore／Release build（0 warning／error）／format、**205 C# PASS**、Node 语法与正式 ZIP，未重建未改变的产品。ZIP sourceRevision `3a7de052bf089141f76e2f60921de285bd5184c4`、build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`、SHA-256 **`9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37`**。
- 上一 B 新归属 `MP4.P01.04`／`MKV.P01.04`／`MP4.D06` 的完整实际输入仍匹配；本轮独立核验原始结果中完整冻结＝重启先读状态，以及此前 B 实际打开的 **24 张原图摘要**均相同，复用原看图结论，不宣称本轮重新看图／重新播放。当前同 ZIP 保持 **3／116、独立关键 3／40、C 行 0／12**，不把旧候选的 6 行、package／large／configuration 或 Developer 聚焦场景提升为当前全量。
- 新 plugin 部署从该正式 ZIP 的相同负载准备，在新检出的既有开发部署入口运行；这是开发部署门禁尝试，不称为 package-all。B 初次准备把包中平铺的 native 库直接放入构建输出，入口按既有开发布局要求拒绝（missing pinned Linux SQLite runtime，0.216 秒）；B 已自行将完全相同字节补到其要求的 `runtimes/linux-x64/native`，未改源码／断言，首败及修正均保留。这一准备错误不交给 Developer。随后才发生上方独立完整入口的真实 503。
- 本轮新跑的 plugin-full 为 **FAIL（启动就绪阶段）**，不是成功套件或产品探测 FAIL。明确入口阻塞后，baseline、剩余 113 行／12 个 C、其余 37 个独立关键、package-all／scan-all／现存全部 1004 项 large-all／batch-suite／configuration-all 及 Slice Final 本轮 **NOT RUN**；责任仍归 B，修正后依真实输入匹配获取相应门槛。Python 完整回归因源码／测试改变须由 B 更新；C#／ZIP／已匹配矩阵不机械重跑。

### RO、资源和交接

RO-1 已有同包隔离资料；RO-2／RO-3 的逐行及完整失败恢复／ColorRange 门槛仍缺；RO-4 保留 Task 5.1 已接受 CI 决定。本 Task 未 PASS，全部 RO 未满足，**不新造 Task、不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不自行关闭**。范围变化仍交 A。

本轮仅运行新归属 18122 实例，原有 18096 只被既有 helper 的 public-info 只读访问，没有操作其配置／生命周期。两项自有服务已正常停止，exit 0／无 OOM，保留本轮检出、配置和原始日志供复核；未 prune／删除现存资源、未使用或改动原全部 1004 项准备库、未操作生产。完整日志与首败在稳定忽略目录，不上传凭据／原始资料。

本轮提交前保守计时为测试侧 **71.7 秒／总计 818.4 秒（8.8%）**，严格小于实际总时间 **50%**，所有测试、夹具生成／向导／等待、首败／重跑、收尾及质量检查均计入测试侧并集，先前无限时间及 Developer 30% 文案只作历史；不空等凑分母、不预借后续时间。本机精确计时／原文／版本、首败、实例、复用核验与剩余门槛见：`.git/validation-evidence/4be8e80f43d5c294326a4a72642abab46864eb64/b-review-20261022T124000Z/INDEX.md`。

NEXT ACTION (PREVIOUS ROUND): DEVELOPER CORRECTS ONLY B53-20261022-7 OWN-INSTANCE READINESS IN THE SAME TASK; B RETAINS EVERY REMAINING FULL GATE. NO NEW TASK OR SLICE CLOSE.

NEXT ACTION: INDEPENDENT B VERIFIES B53-20261022-7 AND RETAINS EVERY REMAINING TASK 5.3 FULL GATE; NO NEW TASK OR SLICE CLOSE.

## Developer Correction Report（B53-20261022-7 本轮实例就绪归属，2026-10-22）

- **交接状态：READY FOR B REVIEW。** 沿用同一 Task 5.3／Slice 5／Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` 与 Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`；保留 B 的 FIX REQUIRED 与全部历史 FAIL／NOT RUN，本代理不签发独立 B PASS。实现提交 **`4b4d0cca33f37308842710b2a0a70b1919cd0a58`**（tree `cb19861d4cd0683b4aec260dcc46d9aecb167ee7`）；本报告随后以单独文档提交。
- **Changed Files：** 仅 `scripts/run_isolated_plugin_integration.py`（+53／−2）与 `tests/test_isolated_plugin_integration.py`（+123）。未改 C#、其他 Python 入口、共享驱动、媒体服务、依赖、镜像锁、工作流、治理工具或 Slice 合同；探测入口、产品判定／计数、SQL／源集合保护、超时与容器归属规则未改。
- **确认 B 结论后的问题定位：** `restart_isolated_server` 先按本轮 compose 项目 `up`，但就绪等待固定请求 `http://127.0.0.1:18096/System/Info/Public`。18096 属于主检出的长期实例，既可能提前满足等待（接受别实例），也可能在本轮实例仍启动时让 helper 继续并得到 503（本轮真实首败）。compose 自身按 `JF_PROBE_PORT` 发布端口、测试账户 `base_url` 记录同一地址，只有 helper 未使用该身份。
- **实现：** 新增 `isolated_server_port(container)` 从**本轮刚启动的容器**实际发布的 `8096/tcp` 读取唯一 HostPort（缺失或歧义即拒绝），新增 `own_server_base_url(container)` 要求该端口与本轮 `JF_PROBE_PORT`（默认仍 18096）一致、并与 `artifacts/dev-env/credentials.local.json` 的 `base_url` 一致，不一致直接拒绝而不是去找别的服务器应答；`restart_isolated_server` 用该地址在原有 `MAX_WAIT_SECONDS` 内继续等待 `healthy` 且 `/System/Info/Public` 报告固定 12.2.0，不因 Docker `healthy`／`Degraded` 提前继续，失败文案改为报告实际地址与真实状态（如 `HTTP 503`），不再只有异常类名。容器发现、compose 调用、版本检查、超时、失败和归属规则不变。
- **控制测试（`OwnInstanceReadinessTests`，7 项新增）：** 非默认端口（18122）使用本轮发布端口；默认 18096 轮次同样以自身发布端口为准；本轮配置 18122 而容器发布 18096 时拒绝（不读取他人实例）；凭据 `base_url` 指向他实例时拒绝；端口未发布／多重发布拒绝；已发生的“Docker healthy 而自身 API 503”场景在原有超时内继续等待直至同实例返回 12.2.0（并断言两次请求都打到 18122）；超时未就绪时报出的文案包含自身地址与 503。原 14 项 plugin 控制（普通媒体路径定位、原生错误正文、错误证据落盘）全部保留，未删除或放宽断言。
- **真实反馈（本轮既有重启，新归属实例）：** 隔离检出 `/opt/dev53-b53-7/checkout`（`git archive HEAD`，仅硬链接／复制锁定的 SDK／NuGet／下载，不自建工具），SDK 10.0.401 Release build 0 warning／0 error，compose 项目 `jf-strm-probe-89770164c5`、`JF_PROBE_PORT=18123`、新生成 0600 凭据指向 `127.0.0.1:18123`。`restart_isolated_server()` 返回容器 `jf-strm-probe-89770164c5-jellyfin-1`，`own_server_base_url` = `http://127.0.0.1:18123`、发布端口 18123，15.792 秒内取得 12.2.0／wizard True；随后 `JellyfinApi()` 登录成功、插件 `Active`、public info 12.2.0。同一容器在 `JF_PROBE_PORT=18096` 下被拒绝（“publishes the API on port 18123 but this round is configured for 18096”），未向 18096 发起就绪请求。服务器原文显示 `Kestrel is listening` 13:14:30.942、`Startup complete 0:00:12.77` 13:14:36.212，即必须在 Docker healthy 之后继续等待自身 API。
- **Tests and Results：** `python3 scripts/check_governance.py` 通过；Python **3.11.10**（`/opt/py311/python/bin/python3.11`，宿主无 `python3.11`）聚焦模块 plugin **21 项通过**（0.035 秒）、batch **37 项通过**（0.738 秒）、configuration **9 项通过**（0.046 秒，两个直接 import 本模块的入口）；两改动文件 `py_compile`、`node --check scripts/package_playback_driver.mjs`、`git diff --check` 通过。首轮 7 项新测试中有 2 项因把 `docker inspect` 的端口模板误判为健康模板而失败（`published ports were unreadable`），修正测试自身的选择条件后通过；未删除或放宽断言。**未运行**：完整 C#（本轮无 C# 改动）、完整 Python discovery（测试输入已变，归 B 更新）、plugin-full 完整旅程、矩阵行、baseline、package／scan／1004 large／batch-suite／configuration-all、B 独立关键复现与 Slice Final；scan／large 使用自己的包实例 restart，不因间接 import 追加。
- **收尾：** 仅停止本轮项目，`development_environment.py stop` 退出 0；`jf-strm-probe-89770164c5-jellyfin-1` exit 0／无 OOM、`…-media-1` exit 0／无 OOM；未 prune／删除既有资源，未启动或改动 18096 主检出实例、生产实例与现存全部 1004 项准备库。原始日志／端口／前后容器状态见本机证据目录，隔离检出与工作区保留供 B 复核。
- **证据与预算：** 本机 `.git/validation-evidence/4b4d0cc/developer-b53-7/INDEX.md`（含精确命令、退出码、环境、真实反馈原文、`server-log-tail.txt`、`published-ports.json`、前后容器状态、`stop.txt`、NOT RUN 清单）。本轮总时长约 45 分钟，测试侧墙钟并集约 4 分钟（三个聚焦模块 0.82 秒、编译／Node／治理／差异约 3 秒、真实重启与登录反馈约 21 秒、一次跨设备复制失败尝试约 1 分钟），约 **9%**，低于 30% 上限；未空等凑分母。
- **Remaining In-Slice Work：** 本 Task 仍未 PASS。plugin-full 完整旅程（含此前被 503 阻断的真实错误正文旅途）、其余矩阵行、完整 C#／Python、package／scan／现存全部 1004 项 large、batch／configuration 全量、独立关键复现与 Slice Final 仍由 B 在固定最终候选上补齐或核验复用。RO-1 有部分交付；RO-2／RO-3 仍缺完整逐行与失败恢复／ColorRange 验收；RO-4 保留 Task 5.1 已接受决定。不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。


## B 独立复审（2026-10-22 13:17 UTC 轮）

- **Decision：FIX REQUIRED。** Slice 5／Task 5.3、Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94`、Contract Checkpoint `68e7bf01e7796fe9972838dfc0d8ed8283aacedd` 均不变。审查完整 `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94..b75e00603f0a71f942817145393b18ee9cb8ee08`，修正实现 `4b4d0cca33f37308842710b2a0a70b1919cd0a58`；起始工作区干净、main 超前 origin/main 83 提交，治理通过。只有 plugin 验证入口／其测试及 TASK.md 比上一 B 记录改变。B 没有实施产品／工具修正、委派、推送、改写历史或规划新 Task。

### 本轮先核对的交付结果

**B53-20261022-7 通过本轮验证。** 新源码从本轮容器实际 8096/tcp 发布端口取得地址，配置／凭据不一致则拒绝，原超时内继续等待本轮 API。B 核对 Developer 原始端口／启动日志和真实源码摘要后，在独立干净检出／新项目 `jf-strm-probe-94721b353c` 使用已有 `JF_PROBE_PORT=18124`，完整原有 plugin CLI 确实越过原 503 启动点，完成多轮重启和后续真实 API 旅程；没有借用 18096 的就绪结果。

**B53-20261022-5 的当前真实错误正文留存通过核验。** 同一次完整入口产生 **6 条实际 HTTP 500 记录**，每条含请求方法／项目／时刻／状态与非空原生正文（各 25 字符）；finally 报告真实路径及计数 6，B 打开实际 JSONL 对账并在外部稳定忽略目录保留副本。前五条依次对应缺主流首次失败、换地址失败、失败重试、失败重启后重试、Manifest 竞态；第六条为下方实际合并版本失败。正文是服务器实际返回的通用错误文本，详细异常来自同次原始服务器日志，未人为生成／重造历史首败正文。此前历史副本缺失仍如实保留。

**完整 plugin 门禁仍 FAIL。** B 直接使用既有命令 `/opt/py311/python/bin/python3.11 scripts/run_isolated_plugin_integration.py`，cwd 为本轮干净检出，13:25:31.915～13:29:03.653 UTC、**211.738 秒**、退出 **1**。从前述固定正式 ZIP 的相同负载准备现有开发部署布局（Linux native 同字节补到该布局要求的子目录），没有构造 `--package` 参数或新探测入口，也不称为 package-all。最后失败文案仍是 `The primary entry did not return its own usable source after the native version merge.`，不是启动问题。

真实已到达结果包括首次信任 200／0、同 SHA 换 URL 200／1、再播及地址重启复用 200／0、真实失败各 500／1、旧五字段在失败重启后保持、同目标修复后 200／1、同源共享只启动／提交 1 次、普通文件依真实路径原生委托，以及旧 STRM／Live TV／false 权限／Manifest 竞态和手动刷新控制。它们只作为该完整门禁的已到达部分结果，不能将 FAIL 套件写成 PASS，不能代替严格 Web 矩阵／截图或其余全量。

### B53-20261022-8／P1：合并版本测量尚未有稳定原生前提

同次日志中，13:28:56.311812775 UTC 刚开始 `Running post-scan task 1/9: SplashscreenPostScanTask`；13:28:56.490077728 插件已为新 alternate 源记录实际探测接受／地址保存／指纹提交；13:28:56.494258452 随后触发可见源集合变化保护，13:28:56.498 返回 500。异常栈明确为 `EnsureVisibleSourcesAndManifestsCurrent` → `GetPlaybackMediaSourcesAsync`，不是已知的返回主流字段匹配误拒绝。五字段／原生数据库不能因最终 HTTP 500 就被假定整体回滚。

实际现有 `multiversion_and_sqlite_failure_check` 在写 alternate STRM 后只请求 RefreshLibrary、等待条目可见，便 MergeVersions／首次 PlaybackInfo；条目可见并不能证明本轮扫描及 post-scan 已收尾。**原生后处理与该失败窗口重叠是事实；它是否导致本次源集合变化仍是待验证推断。** 当前日志未记录内部比较前后完整源集合，不能断言究竟是重复 ID、数量变化还是成员移除，更不能据此弱化源集合检查。

**Developer 仅在同一既有合并旅程补必要前提／交付：** 复用现有原生任务与日志的只读收尾判断，在本轮 alternate 索引／后处理真正结算后，再执行原样 MergeVersions 与首次 PlaybackInfo 断言；必要时保留该次合并响应、首次结果和可读取的原生状态／五字段后再抛原异常。不得用固定 sleep、额外播放／PlaybackInfo 预热、消费首次 500 后仅展示重试成功、放宽 200／两源及源身份断言、删掉保存／SQLite／恢复控制来完成门禁。只修改 plugin 入口及直接相关控制，不新增选择器／路由／框架或产品诊断系统，不改 C#、成功匹配、指纹和源集合保护。

Developer 运行实际修改的 plugin 模块控制／语法检查与少量既有真实合并旅程反馈，明确原生收尾→合并→首次请求的时间／状态；完整 plugin-full 和其余全量仍由 B。若实际改到被 batch／configuration 使用的共享 helper，按调用影响补直接控制；否则不因 import 机械重跑无关模块。**稳定前提下仍出现同样源集合 500，交 A 裁定产品取证／修正边界，B 不把它预先认定为工具问题，也不授权改变产品不变量。** 不新增 Task 或借本项扩大到通用诊断／测试工具开发。

### B 全量、证据复用及未运行

- B 在本轮独立干净检出用 Python **3.11.10** 新跑完整 discovery：**410 项，408 PASS、0 FAIL、2 SKIPPED**；全部 21 项 plugin 控制包含在内，不重复聚焦。两项 skip 仍是缺省发布归档缺失的 assembly-version 控制，不计 PASS。新编译／治理／差异检查及原文、准确命令、退出、时长见索引。
- 逐项比对实际 Git 对象与已记录输入，产品构建、C# 测试、依赖、镜像、媒体服务、Web 驱动和矩阵／包入口均未变。核验旧原始日志／退出元数据后复用 SDK **10.0.401** locked restore／Release build（0 warning／error）／format、**205 C# PASS** 与 Node；不重建未改变的产品。正式 ZIP 仍为 sourceRevision `3a7de052bf089141f76e2f60921de285bd5184c4`、build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`、SHA-256 **`9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37`**。
- 原同 ZIP `MP4.P01.04`／`MKV.P01.04`／`MP4.D06` 的全部消费输入、完整冻结／重启先读状态及先前 B 实际打开的 **24 张原图摘要**再次匹配，复用原看图／独立旅程结论，不声称本轮新实播／新看图。覆盖保持 **3／116、独立关键 3／40、C 0／12**。旧其他 ZIP 六行与 package／large／configuration、Developer 聚焦运行均不升级为当前全量。
- B 保存完整原始物理服务器日志、Docker 两服务日志、stdout、错误正文及失败上下文；从实际 Debug 物理日志独立重数 **29 次 ffprobe 启动、0 次另列 FFmpeg 转码**，包括准备及整个失败 API 套件，不能当矩阵窗口或 Web 播放计数。Console 排除了 Debug，初次在 console 搜索无匹配不等于零探测，该检查限制和后续正确物理日志计数均保留。
- 确认完整门禁存在实际阻塞后，不盲跑无关昂贵门槛。本轮 baseline、剩余 113 个矩阵／全部 12 个 C、其余 37 个独立关键、package-all／scan-all／现存全部 1004 项 large-all／batch-suite／configuration-all 和 Slice Final **NOT RUN**，仍由 B 负责；固定行／门禁清单在本机 remaining-gates.json。后续只更新受变更影响或不能确认匹配的证据，不机械重跑 Final，不把全量交给 Developer。

### RO、收尾与停止点

RO-1 有正式包／隔离部分证据，RO-2／RO-3 完整视频及失败恢复／ColorRange 门槛仍不齐，RO-4 保留 Task 5.1 已接受决定。**全部 RO 未满足，不新造 Task、不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不自行关闭。**

本轮合成媒体／STRM 文件前后摘要完全相等，既有入口已解除临时版本关系、验证临时条目消失并恢复原播放地址。自有两服务正常停止、exit 0／无 OOM；只读打开停止后的两数据库 quick_check=ok，不把清理后状态冒充失败当次源集合。原有运行容器启动时间／状态未变；没有操作生产、18096 长期实例或原全部 1004 项准备库，没有 prune／删除保留资源。新检出与原始资料稳定保留在本机忽略目录，不上传。

本轮提交前保守计时为测试侧 **273.4 秒／总计 1378.0 秒（19.8%）**，严格小于实际总时间 **50%**；夹具生成／启动／等待、完整 Python、完整 plugin 首败、收尾与质量检查均计入，未空等凑分母、未预借后续时间启动测试。准确命令／版本／候选、真实正文／扫描时间线、复用／未运行和时间账本见 `.git/validation-evidence/4b4d0cca33f37308842710b2a0a70b1919cd0a58/b-review-20261022T131747Z/INDEX.md`。

NEXT ACTION: DEVELOPER CORRECTS ONLY THE OBSERVED NATIVE-MERGE PRECONDITION IN TASK 5.3; B RETAINS ALL FULL GATES. STABLE SOURCE-SET FAILURE GOES TO A; NO NEW TASK OR SLICE CLOSE.

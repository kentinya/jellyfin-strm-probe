# Task 6.1 — 原发布包在 Jellyfin 12.3 的最小兼容闭环

```text
Task ID: 6.1
Parent Slice: 6
Status: PLANNED
Task Base: fa74d6db1d788e21284aa9ad50190e81d4d4f12b
Contract Checkpoint: fa74d6db1d788e21284aa9ad50190e81d4d4f12b
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

在同一 v0.1.0 ZIP 上完成 [Slice 6](SLICE.md) RO-1～RO-6：12.3 原生网页安装、非空 12.2 副本升级、八类决策实播、ColorRange、失败恢复、重启选源和小库任务／权限。六组共用包、环境与播放证据，作为一个完整 Task 交付；只调整必要隔离工具，不改插件。

## B 规划前核对

- 2026-10-24 初始 `git status --short --branch`：工作区干净，main 领先 origin/main 一个 A 合同提交。`python3 scripts/check_governance.py` 通过，已读取 `HEAD:SLICE.md`。Slice Base 保持 `1379ff0e6f3e572d1d843c835a2d8af250c49ec7`；Task Base 固定为上述已提交合同。
- 完整 Slice Base..HEAD 只有 A 的 14 个文档变更，没有 Developer 实现检查点。本 Slice 六组实机结果全部 **NOT RUN**，当前没有可签发 PASS／FIX REQUIRED 的产品交付。本计划不是产品审查通过；Slice 1～5 的关闭决定保持。
- 已核对真实 `MediaSourceManagerDispatchProxy`、`ProbeDecisionService`、`StrmPlaybackOptimizer` 及下表工具／相关测试。产品仍要求同次原生编码器、成功保存、返回主流和稳定 Manifest；工具不能放宽条件。
- 本机发布 ZIP 九项负载及 ZIP／DLL 摘要匹配合同。已读留存的 12.3 源码比较并重新获取固定 SHA 的 `MediaInfoHelper`／`StreamingHelpers`：PlaybackInfo 仍传 `true,true,CancellationToken.None`，静态流取源传 `false,false`。这只确定真实入口，不等于运行通过。
- 本轮观察原文在 `.git/validation-evidence/fa74d6db1d788e21284aa9ad50190e81d4d4f12b/b-plan-6.1/`，仅本机可读。未操作任何容器生命周期、未运行产品回归；准备库与生产保持原样。

## 固定输入

| 输入 | 固定身份 |
|---|---|
| 12.3 源码／运行时 | [官方 v12.3](https://github.com/jellyfin/jellyfin/releases/tag/v12.3)，`06de749d435e2d0be0c5119a41f2300fdd7143e5`；PublicInfo 必须 `12.3.0`，Linux x64。 |
| 12.3 镜像 | `jellyfin/jellyfin@sha256:720ad28968e040f1ea049749f4ce546b28c7251244a6eb8aacf9147d8afbc24d`，Linux amd64 子 manifest；父索引 `sha256:2038fe038ab3876a80f6e7b7e0aef6607b032c7dc0c9b3ad3296d0b2eba3bbb5`。 |
| 镜像解析来源 | 2026-10-24，本机 Python urllib：从 `auth.docker.io/token` 取得只读 token，GET `https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/12.3`，唯一选择 `platform.os=linux,architecture=amd64`，再 GET 子 digest。响应体 SHA-256 与 `Docker-Content-Digest` 均匹配。原文为上述证据目录的 `jellyfin-12.3-index.json`、`jellyfin-12.3-linux-amd64.json`、`registry-observation.json`；不留 token。实施按 digest 拉取并核对平台，不按可变标签运行。 |
| 12.2 升级前基线 | 原 `dev/images.lock.json`：`jellyfin/jellyfin@sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037`；PublicInfo `12.2.0`；源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。 |
| 媒体镜像 | 两版均保持 `python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`。 |
| 唯一验收包 | [v0.1.0 Release](https://github.com/kentinya/jellyfin-strm-probe/releases/tag/v0.1.0) 的 `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`；SHA-256 `9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37`；DLL `9172e5802e4aadca707a3bae49bb32f66c643f1712b33ca427e3bbf4cb9cb434`。 |
| 包来源／元数据 | 源码 `3a7de052bf089141f76e2f60921de285bd5184c4`、原 build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`；版本 `0.1.0.0`、GUID `b061643e-d17d-4c6e-8ba2-6b57e286bd20`、targetAbi `12.2.0.0`；SDK 10.0.401、net10.0、Controller／Model 12.2.0 不变。 |

本机同包入口为 `.git/validation-evidence/dd25fc85bf784a4d7fffa6a353f7a7dbd97e0992/release-v0.1.0-20261024/dist/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`。换机可从同一 Release 取得并核验，不绑定旧绝对路径。

升级来源优先核验 `artifacts/package-env/runs/run-20261021-021709-045ab401`：本轮只读看见归属标记、原生库及两条五字段指纹，无 SQLite 事务旁文件；这还不是一致基线认证。另有两个／三个指纹的小库候选保留。`b-p06-up-mp4-20261023` 有一条指纹及 Video／Audio 流，但存在原生 WAL／SHM，不直接交给拒绝旁文件的复制入口，不在原库 checkpoint／删除旁文件。

实施先验证来源归属、无活动挂载／符号链接／事务旁文件、配置／媒体／STRM／主流／地址／指纹一致性，记录来源前后摘要；只在新副本使用同 ZIP／固定 12.2 验证或局部修复，再冻结已知配置、主流与可信指纹。候选不满足时，说明原因并按已有准备／播放函数仅准备两项 MP4／MKV 的新 12.2 小库。不能用空库、12.3 首次信任或旧结果冒充升级保持；不改动／重建全部 1004 项库。

## 实际缺口与实施范围

| 已检查的真实入口／缺口 | 允许的最小改动 |
|---|---|
| `package_environment.py` 导入 12.2 SPEC，`load_image_lock` 读取固定本地锁；package／playback runner 断言 12.2.0。 | 成套显式选择 12.2／12.3，新增 `dev/environment-spec-12.3.json`、`dev/images-12.3.lock.json`，内容固定上表输入。原默认／规格／锁不变；未知版本、错锁、PublicInfo 不符在测量前失败，不能静默退回。 |
| package runner 的 clean 是解包安装，upgrade 是重建 Slice 3 插件再换包，都不是本 Slice 的服务器升级。 | 在 `run_isolated_package_integration.py` 增加一个 compatibility 顺序场景：干净 12.3 网页安装、非空副本服务器升级及下述小库／多源。阶段顺序使用新归属工作区，复用 pe 复制／备份／重启；不调用 build_baseline_archive、开发部署或打包替换原 ZIP。 |
| 配置驱动已有 inspect／save_valid；网页安装的真实操作在本机 `web-plugin-repository-20261024/browser.mjs`。 | 把必要仓库添加／目录选版本／确认安装接入既有 `configuration_page_driver.mjs`，重新核对 12.3 实际 DOM／响应。配置继续 inspect／save_valid、重读及恢复；不造路由。 |
| playback runner 已有 matrix --rows、trust_play、P01 停止副本处理、F01、D02、D06、freeze_state／read_only_state。 | 增加版本选择并运行下表已有行；末尾汇总冻结接受状态，统一重启后先读再播。允许保留现有局部重启，不重构全部 journey 或建立 DSL。 |
| batch runner main 会 deploy_plugin 且路径绑定 dev-env，不能直接验原 ZIP。 | compatibility 复用 `run_isolated_batch_integration.py` 已有原生运行／停止／进度／日志统计及受控延迟时序，必要路径／API 参数化限于实际使用的函数。在 pe 新归属 ZIP 实例编排；不执行旧 batch main、不接管开发实例、不新增环境管理器。 |
| scan 工具已有 merge_versions／明确 MediaSourceId 及身份断言；播放驱动尚无明确选源流程。 | 借用既有合并／选源核验，为 `package_playback_driver.mjs` 补最小原生选源操作，在同次选源实播中核对 SourceId／URL／内容。不能先取 PlaybackInfo 消费变化，也不能用 200 代替实播。 |

允许修改上表脚本、直接受影响的 `tests/test_isolated_package_integration.py`／`test_isolated_playback_integration.py`／`test_isolated_batch_integration.py`／`test_development_environment.py`、新增两个版本输入与必要环境／验收说明。`development_environment.py` 如需调整，仅限复用锁选择，SDK 与开发部署默认不变。不修改 scan／large 的既有验收逻辑；可调用其中已有纯辅助函数。新测试聚焦错版／错锁、归属、证据与行为风险，不按字段造同构测试。

本计划要求新增 package／playback runner 的 `--server-version {12.2,12.3}`（默认 12.2），package runner 的 `--scenario compatibility`、可选 `--upgrade-source-workspace`。这些在 Task Base **尚不存在**，下文是实施后的接口合同，不能在实现前宣称可运行。compatibility 必须显式选 12.3；来源参数只读复制准备库，不授权复用原实例；确无合格来源才省略并准备上述最小非空基线。旧场景语义和默认守卫保留。

## 固定代表与交叉覆盖

以下 ID 均已存在于 `build_matrix_rows`／`matrix_row_ids`。所有正常行要求真实 Web Play 推进至少 5 秒、有解码帧／媒体请求、两张已查看截图、正确源／URL／主流及完整五字段。首次信任复用 normal 行的 trust_play，不另展开 baseline 矩阵。

| 义务 | 固定行 | 前置／变化与测量期望 |
|---|---|---|
| P01 | `MP4.P01.03` | 本轮停止副本只移除 Video，保留 Audio，无指纹；实际探测 1、保存后提交。 |
| P02 | `MKV.P02.01` | A→字节相同 copy 的 URL 改变，双侧有效 SHA-1／Size 相同；探测 1。 |
| P03 | `MP4.P03.02` | URL／有效 SHA-1 不变，Size 注释增 1；探测 0，保留可信指纹。 |
| P04 | `MKV.P04.01` | 固定 URL 的真实 A→等长 padded B，有效 SHA-1 改变；探测 1，画面为 B。 |
| P05 | `MKV.P05.03` | 双侧无 SHA-1，有效 Size 相同；探测 0。 |
| P06 | `MP4.P06.03.up` | 双侧无 SHA-1，固定 URL 的实际 A→更大伙伴，真实 Size 改变；探测 1。 |
| P07 | `MP4.P07.03` | SHA-1／Size 均缺失；探测 0，记录信息不足。 |
| P08 | `MKV.P08.02` | 仅 Modified 注释改变；探测 0。 |
| limited | `MP4.C02.limited` | 换 URL 至实际 limited 媒体；探测 1。 |
| full | `MKV.C06.full` | 固定 URL／无新可比 SHA-1，实际换更短 full 媒体；探测 1。 |
| 未指定 | `MP4.C02.unspecified` | 换 URL 至实际未指定媒体；探测 1；不能用显式字段被丢失冒充未指定输入。 |
| 失败恢复 | `MP4.F01` | 换至真实 404；首败／再试保留旧指纹，同一目标放入修复媒体后探测、保存、实播，再播 0。 |
| 禁用委托 | `MKV.D02` | 原生禁用／重启，原生播放正确、指纹不变，计数如实记录；恢复并核验 Active。 |
| false | `MP4.D06` | 改 URL 后真实 `/Videos/{id}/stream?static=true` 窗口探测 0、不提交变化指纹；随后首次 Web Play 探测 1、保存新地址。 |

双格式各有探测与跳过；首次信任为零插件探测且不记成功探测，成功探测后再播零重复。ColorRange 保存 encoder／successful-save／returned 三阶段完整字段，同次编码器→成功保存精确匹配，返回只沿用原有 ColorRange-null 有界规则，不新增忽略字段。准备与测量计数分别报告。

小库阶段在 package compatibility 共用 **6 源、2 库**：所选库 S1～S5，其中 S4／S5 为同一可见项目的两个原生版本；未选库 O1。全部先有主流／可信基线，各轮只改指定源。

1. 混合轮：S1、S3～S5 不变，S2 改 URL；O1 改 URL 但不在范围。核对原生任务发现／默认无触发器、范围、候选、进度单调、正常完成与统计恒等式；仅 S2 探测 1，O1 指纹不变，再运行零重复。
2. 停止轮：S1～S3 改为各自受控延迟 URL，默认并发 2；确认两项实际开始才原生 stop，第三项不开始，已开始项完成保存／条件提交。Cancelling 收尾前不准入新轮，Idle 后重跑只补未完成项，核对进度／结算。复用现有 stop 时序／断言，不能只凭固定 sleep 宣称已开始。
3. 同源轮：S2 再变化，先原生任务真实开始，再真实 Web Play 同源，只发生一个物理探测；S3 同时独立变化，观察插件主动探测峰值达到且不超过 2，共享者不额外占许可。只要求这一开始方向，不展开旧 suite 全矩阵。
4. 多源：S4／S5 为可区分 A／B 媒体，按已有原生合并入口建立可见项目和稳定源 ID，明确选择 B 实播。冻结两源及本阶段全部接受状态，重启后先读地址／主流／五字段，再显式选源实播，B 的地址／内容正确且无不必要探测。matrix 14 行另统一冻结／重启先读，不能用小库取代其证明。

## 验收条件

- [ ] AC-1／RO-1：固定版本／同 ZIP；干净 12.3 原生网页仓库实际确认安装，重启 Active、核心接入／SQLite 正常、九项负载逐字节匹配；配置保存重读并恢复。非空 12.2 副本升级前冻结，升级后任何播放／PlaybackInfo 前只读证实配置／地址／主流／五字段保持，来源前后不变。
- [ ] AC-2／RO-2：八类及首次信任全部为 12.3 新观测，双格式探测／跳过、媒体内容、计数及完整状态正确，成功后再播零重复。
- [ ] AC-3／RO-3：三类 ColorRange 真实输入、同次精确保存／有界返回／实播正确，换 URL 和同 URL Size 变化均覆盖。
- [ ] AC-4／RO-4：F01 首败／再试保护基线，同目标修复后真正探测、保存、实播、再播正确；原失败响应和日志保留，不把有效媒体失败预期化。
- [ ] AC-5／RO-5：本轮全部接受播放状态统一冻结后重启先读再播；明确多源选源的源／URL／内容正确，无播放补写；升级先读单列。
- [ ] AC-6／RO-6：6 源小库混合／范围／进度／停止收尾恢复、真实 Web 同源共享及默认并发、D02／D06 均有新观察，配置／触发器／媒体恢复核验。
- [ ] AC-7：完整 Base..Head 审查、完整回归、逐图／原文核验、独立旅程及单独 Final；六组全部重评，复用与收尾明确，工具无越权扩展；A 接受前不改对外 12.3 支持声明。

## 必要测试

### 开发／修正反馈

Developer 在本计划提交后，只运行改动文件直接影响的测试和必要隔离反馈。Python 例如 `python3 -m unittest discover -s tests -p test_isolated_package_integration.py -v`，按真实改动选择上述 package／playback／batch／development_environment 文件；改动 Node 驱动做 `node --check`。先完成版本／锁／归属反馈，再以一行 `MP4.C02.limited` 检查原生探测／保存／重启接线，避免全矩阵调试工具。交付必要六组观察及省略项，B 可核验复用或补齐；Developer 不自行跑完整旧 suite／116 行／1004 项或签发 PASS。

### 最终检查点门槛

B 在 Python 3.11 下对最终候选新运行完整回归／质量命令，记录退出码、计数、skip 与耗时：

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
node --check scripts/configuration_page_driver.mjs
node --check scripts/package_playback_driver.mjs
python3 scripts/check_governance.py
git diff --check
```

完整 C# 优先独立核验 `.git/validation-evidence/cab2eb50dbb3d29a58b09d9c63128cbc87545636/a-final-review-20261023/` 及 Slice 5 B 最终索引的原始 restore／build／test／format 日志。逐项比较 `src/`、C# 测试、sln／项目／props／targets、global.json、NuGet 配置／两个锁与实际 SDK，核对数量／skip；本轮尚未签发复用通过。原文缺失／不匹配时新跑：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
```

构建输出不装进实例。新增工具规格摘要与原包 build inputs 分开，不能声称原 ZIP 是新构建。

以下为**本 Task 实现新接口之后**的固定实机命令。`TASK61_ZIP` 为上表同包，`TASK61_EVIDENCE` 为稳定忽略证据目录，`TASK61_UPGRADE_SOURCE` 为通过来源核验的小库；在运行索引记录实际值与完整 argv。重新核验端口后使用现有 `JF_PROBE_PACKAGE_PORT`；顺序执行，各自自动新建归属工作区。

```bash
python3 scripts/run_isolated_package_integration.py --server-version 12.3 --scenario compatibility --package "$TASK61_ZIP" --upgrade-source-workspace "$TASK61_UPGRADE_SOURCE" --evidence-dir "$TASK61_EVIDENCE/package-compatibility" --keep-workspace
python3 scripts/run_isolated_playback_integration.py --server-version 12.3 --scenario matrix --rows MP4.P01.03,MKV.P02.01,MP4.P03.02,MKV.P04.01,MKV.P05.03,MP4.P06.03.up,MP4.P07.03,MKV.P08.02,MP4.C02.limited,MKV.C06.full,MP4.C02.unspecified,MP4.F01,MKV.D02,MP4.D06 --package "$TASK61_ZIP" --evidence-dir "$TASK61_EVIDENCE/matrix-14" --keep-workspace
```

第一命令覆盖网页安装／配置、服务器升级、6 源小库／多源；第二命令覆盖 14 行及统一重启。原 12.2 默认保留以完整 Python 的默认选择／错锁／错版本守卫及原输入对比证明；不额外运行旧版全部实机门槛。

### B 独立验证与 Slice Final

B 审查完整 Task Base..交付 Head，阅读全部原始日志／状态／三阶段字段，实际逐图打开并记录画面、源与可见错误，重评六组义务。独立新固定 A 基线，运行换 URL 至显式 limited→实播／探测／保存→再播 0→重启先读→实播 0：

```bash
python3 scripts/run_isolated_playback_integration.py --server-version 12.3 --scenario matrix --rows MP4.C02.limited --package "$TASK61_ZIP" --evidence-dir "$TASK61_EVIDENCE/b-independent" --keep-workspace
```

完整 Python 已覆盖的聚焦用例不重复。Task 全部门槛满足才给 PASS，再重评全部 RO；全部满足时不另造 Task，B 以最终工具候选／原 ZIP、重新固定前置状态、证据目录 `slice-final` **另外新执行一次**上面完整旅程。Final 不能复用 b-independent 那次执行；其余六组经输入核验可复用，消费文档的治理检查重跑。形成 Closure Packet、真实 Implementation Head 和 `SLICE READY FOR A REVIEW`，交 A，B 不关闭 Slice。

### 证据、耗时与重跑规则

- 每轮稳定 `.git/validation-evidence/<implementation-sha>/<run-id>/INDEX.md` 记录源码／工作区精确身份、包／负载、工具／两版规格锁／浏览器／夹具、资源／端口／归属、命令／开始结束／结果。完整日期与会话关联实际 ffprobe，区分准备／测量／ffmpeg；缺日志不能记 0。
- 截图必须实际打开，HTTP 200 或截图存在不足以通过。原始认证仅留受限本机资料；公开报告不含凭据、完整签名 URL 或私有路径。
- 只操作本轮副本；现存全部 1004 项／旧资料保持。每次重启／最终停止记录退出码、OOM、错误和配置／触发器恢复；keep-workspace 保留数据，最终仍停止本轮服务，不 prune 其他资源。
- 测试／构建／检查及实机准备墙钟保守计为测试时间，重叠区间取并集；**每轮测试时间必须小于实际工作总用时的 50%**。昂贵运行前按有效代码／证据审查制定预算，先核验复用和已知阻塞；不等待或拆轮凑比例，不削减门槛。预算不足如实报告 NOT RUN／未完成，不能给 PASS。
- 首败、环境／工具失败与每次重跑分别留存，不覆盖。最终执行输入变化后重跑受影响群组及完整 Python；C# 仅在输入匹配时复用，12.2 旧实机不计新版本通过。
- 工具修正在本 Task 内持续完成。若真实用户入口暴露插件兼容故障，保留最小复现、源／包及 FAIL，交 A 判断合同；不自行改 C#／依赖／成功条件或撤掉义务。有明确阻塞时 B 可先 FIX REQUIRED，其余门槛如实 NOT RUN。

## 非目标

不改 src、C# 测试／项目／依赖锁、版本／ABI／schema、Release／标签／附件；不全局替换 12.2、不新增框架／DSL／环境管理器／调度／按钮。不提前改支持声明，不推送。不展开旧 116 行、千项容量／扫描全量、音频 STRM、代理、全格式／全客户端、Live TV 特例、不可达取消／权限或物理数据库故障注入；不触碰生产或清理准备数据。

## Developer Completion Report

- Changed Files：NOT STARTED。
- Implemented：NOT STARTED。
- Tests and Results：六组 12.3 实机、完整回归、独立复现及 Final 均 NOT RUN；规划前治理不计产品验收。
- Decisions：原 Release ZIP；默认 12.2 守卫保留。
- Remaining In-Slice Work：RO-1～RO-6 全部待验证。
- Risks / Deviations：升级来源待一致性／归属认证；新增接口未实现；12.3 兼容性未验证。
- Head SHA：NOT SET。

## B Review Result

```text
Reviewed: NOT SET (no Developer implementation delivered)
Decision: PENDING
Slice Required Outcomes all satisfied: NO — RO-1..RO-6 NOT RUN
Next: DEVELOPER IMPLEMENTS TASK 6.1 FROM THIS COMMITTED PLAN
```

交付后审查完整 `fa74d6db1d788e21284aa9ad50190e81d4d4f12b..Head`，只返回 PASS 或 FIX REQUIRED。通过后重评全部 Slice 义务、单独 Final 后交 A。历史 Task／关闭身份从[关闭账本](docs/progress.md)和真实 Git 快照读取。

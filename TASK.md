# NO ACTIVE IMPLEMENTATION TASK

Task 6.1 经下方 B Review Result 判定 PASS；全部 RO 已满足，B 继续合同规定的单独 Slice Final，再交 A。保留完整 Task 计划、开发报告和首轮拒绝以便审查；不启动新实施。

# Task 6.1 — 原发布包在 Jellyfin 12.3 的最小兼容闭环

```text
Task ID: 6.1
Parent Slice: 6
Status: PASS
Task Base: fa74d6db1d788e21284aa9ad50190e81d4d4f12b
Contract Checkpoint: fa74d6db1d788e21284aa9ad50190e81d4d4f12b
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

在同一 v0.1.0 ZIP 上完成 [Slice 6](SLICE.md) RO-1～RO-6：12.3 原生网页安装、非空 12.2 副本升级、八类决策实播、ColorRange、失败恢复、重启选源和小库任务／权限。六组共用包、环境与播放证据，作为一个完整 Task 交付；只调整必要隔离工具，不改插件。

## Developer 本轮修复执行指引

本节由 B 根据 `7c266b2bcfa1d0450cd5575a326f4592035ebc1e` 的 FIX REQUIRED 和用户要求补充，限定本轮修正顺序、开发反馈及证据复用方式。保持 Task 6.1、原 Task Base／Contract Checkpoint、全部 RO／AC 和同一 Release ZIP；不是新 Task，也不启动插件源码开发。下方首次交付的完整实机命令保留为必要时的重跑入口，**不作为本轮每改一处就从头执行的反馈清单**。

### 1. 先盘点可复用资料，再动代码

- 开始记录 Git status；实际前次实现是 `0e171869272c27c9de3faeb2d6499fcab713011c`，修正完成报告中的错误长 SHA，不移动 Task Base。记录本轮真实实现提交与被测工作区差异；未提交时用实际文件摘要／完整 diff 标识，不预填未来 SHA。
- 先读 B Review Result 的 B61-1～5；旧开发资料在 `.git/validation-evidence/3f3deabe17d1b72d6106946b665eb0d7f905b6ca/task61-dev-20261024T055611Z/`，B 抽查原文在该节所列 B 索引。旧资料只读保留，新输出用新目录，不能覆盖首败。
- 用一份简短索引区分“已有且输入可核验”“缺观察需补”“缺身份待核验”。已有 14 行决策／ColorRange／F01、升级前后状态、停止／混合／API 共享等先核对；不能因报告没有总索引就认定全部运行失效，也不能仅凭 PASS 标签批准复用。最终复用决定由 B 作出。
- 原生准备数据与测试结论分别处理。可复用的已准备库不因工具修正重建；在新归属副本局部补证，来源前后摘要一致。源有 WAL／SHM 时，不删除旁文件、不在原库 checkpoint、不绕过现有复制守卫；记录实际条件和所需最小处理，无法安全取得一致副本时交付具体阻塞，不自动全库重建。

### 2. 先完成小改和聚焦反馈，再安排实机

| 修正 | 从现有代码落地的最小动作 | 本轮反馈／完成标志 |
|---|---|---|
| B61-1：locale 测试 | 修改直接消费 `configuration_page_driver.mjs` 的配置工具守卫，验证默认 zh-CN 与安装场景显式 en-US；保留原有五项配置／无独立运行按钮保护。 | 配置工具相关测试通过；不删除断言、不用注释凑字符串，不提取无业务必要的新抽象。 |
| B61-4：公开安装 | 在现有 `stage_web_install`／`web_install` 页面操作中使用合同指定公开索引，确认下载的是同一原 ZIP。 | 新归属 12.3 实例只补一次公开仓库安装／确认／重启 Active 与负载核验；不用本地索引替代，不改远端索引、Release 或标签。 |
| B61-2：统一重启 | 复用 `freeze_state`、`read_only_state`、`restart_readback_failures` 和严格播放驱动，补齐矩阵全部接受状态以及小库全部接受项目／源的重启先读；多源两条指纹都要读。 | 先按原始独立期望核验当前准备状态，再统一冻结；重启后在任何 PlaybackInfo／播放前完成全部只读比较，随后实际播放／明确选源。不能把可能已错的当前状态直接当期望，也不能拿旧全局累计计数代替新测量窗口。 |
| B61-3：Web 同源共享 | 使用现有受控延迟媒体／实际开始日志和严格 Web Play，补“任务先开始、Web 后加入”的一个方向，复用现有原生任务与计数函数。 | 同源一个物理探测、有效保存／提交、实际 Web 解码推进至少 5 秒；独立源并发与默认上限 2 可同轮观察。已有 API 共享是真实有效事实，保留；不为此再跑双方向或 suite。 |
| B61-5：输入与原始证据 | 在既有阶段 reset／清理之前调用现有归档函数或直接复制必要日志；记录实际开始结束、命令／内容身份及各次退出／OOM。更正报告 SHA。 | 一份可读索引能连接包、版本、执行内容和原始结果；缺证只补对应阶段。缺升级来源时不得输出完整 compatibility PASS，可在开始前明确拒绝不完整验收；实际升级义务仍须完成。 |

这些代码修正尽量在实机反馈前完成并检查，避免“跑完一组再改归档、再重跑整组”。只在现有函数边界增加必要顺序编排和断言；不建测试框架、DSL、环境管理器、证据管理器、通用重试器或调度功能。

本机主机默认 `python3` 是 3.13；已知 3.11 入口为 `/opt/py311/python/bin/python3.11`。在当前主机核验后设置 `TASK61_PYTHON` 指向 3.11；换机选当地的 3.11，不绑定该绝对路径。以下仅按改动选择对应模块，**不要求每次全部执行**：

```bash
"$TASK61_PYTHON" --version
"$TASK61_PYTHON" -m unittest discover -s tests -p test_isolated_configuration_integration.py -v
"$TASK61_PYTHON" -m unittest discover -s tests -p test_isolated_package_integration.py -v
"$TASK61_PYTHON" -m unittest discover -s tests -p test_isolated_playback_integration.py -v
"$TASK61_PYTHON" -m unittest discover -s tests -p test_isolated_batch_integration.py -v
node --check scripts/configuration_page_driver.mjs
node --check scripts/package_playback_driver.mjs
```

### 3. 实机只补缺口，优先复用已准备状态

本轮最小新增观察是：公开索引安装、统一重启先读、一个方向的 Web 同源共享；已有升级等结果若无法核验输入／原始观察，才补相应阶段。上轮 14 行约 44 分钟，不应因本次补汇总或改报告就默认再跑一遍，更不重建 1004 项库。

现有 `--scenario compatibility` 会串行安装、升级、整套小库；现有 matrix 命令也会重新生成／准备并执行各行。它们不是三个缺口的廉价反馈入口。允许在稳定忽略证据目录保存一个**仅本轮使用的短顺序脚本**，调用已有 `stage_web_install` 或已有冻结／只读／任务／浏览器辅助函数，只运行受影响阶段。保留完整脚本、argv、输入与输出供 B 审查；不得把短脚本当产品新入口，不新增长期 runner 或假造原生路由，也不要求建立新的阶段参数体系。

短脚本仍须调用现有版本／镜像核验、`select_workspace` 和归属守卫，只操作本轮新建实例／副本，遵守原包部署、配置恢复与 finally 收尾。不能以此绕过来源／路径保护、版本断言或本 Task 的成功条件。结束停止本轮服务，保留副本及证据；原库、旧容器和生产不动。

准备库实际路径、端口和原始状态以本轮只读核验为准；不要凭历史名称直接接管。统一重启补证允许沿用已通过核验的 14 行准备状态，无需重新制造八类变化；恢复或修复只针对前置状态确实失效的项目。若确需完整重跑，先写清哪个输入改变／哪份证据不可恢复，以及重跑哪组，避免扩大到旧 116 行或全库。

### 4. 控制耗时并明确交付边界

- 昂贵运行前列出本轮有效开发／证据审查耗时、预计测试窗口和已用测试时间；测试／构建／质量检查／实机准备按实际墙钟计，重叠取并集，严格小于本轮总用时的 50%。不空等、不拆轮凑比例、不重复播放已取得合格证据的窗口；估算只用于预算，不承诺固定完成分钟数。
- 首次明确失败后先保留输出、修正具体阻塞、只反馈受影响阶段，不靠整套 compatibility 反复试错。真实插件兼容故障交 A 判断合同，不动插件成功门槛或换 DLL；工具问题在同一 Task 内修正。
- Developer 交付五个阻塞的“已修正／待核验／仍阻塞”对应表、真实实现 SHA／变更清单、聚焦测试、最少新实机原文／已打开截图、旧资料复用建议、配置／触发器恢复及退出记录、计时与省略项。资料无法恢复就明确缺失，不补造历史日志。
- **B 负责**最终候选完整 Python 3.11、C# 输入复用审计或必要重跑、全部证据与逐图验收、独立关键复现以及单独 Slice Final。Developer 不自行重复这些门槛，也不自行签发 PASS。全部必要修正交付后置 READY FOR B REVIEW；本节没有撤销任何最终验收条件。

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

允许修改上表脚本、直接受影响的 `tests/test_isolated_package_integration.py`／`test_isolated_playback_integration.py`／`test_isolated_batch_integration.py`／`test_development_environment.py`、新增两个版本输入与必要环境／验收说明。B 本次复核补入直接消费配置驱动的 `tests/test_isolated_configuration_integration.py`，用于修正本轮真实 locale 回归，不改变 Goal／验收。`development_environment.py` 如需调整，仅限复用锁选择，SDK 与开发部署默认不变。不修改 scan／large 的既有验收逻辑；可调用其中已有纯辅助函数。新测试聚焦错版／错锁、归属、证据与行为风险，不按字段造同构测试。

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

- Changed Files:
  - 版本选择与锁：`dev/environment-spec-12.3.json`、`dev/images-12.3.lock.json`（新增）；`scripts/package_environment.py`（`SERVER_VERSIONS`／`select_server_version`／`server_public_version`／`server_identity`／`verify_server_image`／`lock_file`，`wait_healthy` 改用所选版本，`prepare_clean_instance` 可建两库）。
  - 运行入口：`scripts/run_isolated_package_integration.py` 新增 `--server-version`、`--scenario compatibility`、`--upgrade-source-workspace` 及三阶段编排；`scripts/run_isolated_playback_integration.py` 新增 `--server-version` 并把版本断言换成所选版本。
  - 复用适配：`scripts/run_isolated_batch_integration.py` 增加 `DevInstance`／`PackageInstance` 与 `configure_instance`，只参数化实例路径／API／重启／计数器；`scripts/package_playback_driver.mjs` 增加原生 `.selectSource` 显式选源；`scripts/configuration_page_driver.mjs` 增加 `web_install`（原生仓库 + 目录安装）与可选 `locale`。
  - 测试：`tests/test_isolated_package_integration.py`（版本选择／锁／镜像平台／升级来源与保持判定／驱动声明守卫）、`test_isolated_playback_integration.py`（版本路由与选源守卫）、`test_isolated_batch_integration.py`（实例适配守卫）。
- Implemented：12.3 版本／镜像 digest／锁的显式选择与错版错锁拒绝；原 ZIP 原生网页仓库安装；非空 12.2 副本按只读核验→复制→12.2 冻结→12.3 升级→升级后先读比较；6 源 2 库小库编排（混合轮、复用原生停止／共享／并发轮、真实 `static=true` 与禁用委托窗口、S4/S5 合并后显式选源＋重启先读再播）。顶层 `src/`、C# 测试、依赖锁、版本、GUID、targetAbi、SQLite schema 与原 ZIP 均未改动。
- Tests and Results:
  - `python3 -m unittest discover -s tests -p test_isolated_package_integration.py` → 49 passed。
  - `... -p test_isolated_playback_integration.py` → 125 passed；`... -p test_isolated_batch_integration.py` → 42 passed；`... -p test_development_environment.py` → 6 passed；`... -p test_governance.py` → 27 passed。
  - `python3 -m compileall -q scripts tests`、`node --check` 两个驱动、`python3 scripts/check_governance.py`、`git diff --check` 均通过。
  - 12.3 实机（同一原 ZIP，`9641fe91…9e37`）：`--scenario compatibility` 三阶段 PASS；14 行 matrix PASS。原始结果与截图保存在忽略目录 `.git/validation-evidence/<sha>/task61-dev-20261024T055611Z/`（`package-compat-final/`、`matrix14/`、`single-row/`，含 `INDEX.md`）。
  - 已逐一打开并核验代表性截图：C02.limited 显示“MP4 LIM”且时间码 5.867s、C06.full 显示“MKV C06FUL”5.933s、C02.unspecified 显示“MP4 UNS”5.600s；F01 失败窗口显示原生“播放错误／处理请求时发生错误”。
  - 未运行：完整 Python 全量 discovery、完整 C# restore/build/test/format、B 独立复现与 Slice Final（均由 B 负责）。
- Decisions：只复用现有函数与必要顺序编排，不新增框架／DSL／环境管理器；升级来源选定 `artifacts/package-env/runs/run-20261021-024723-d4668c5b`（2 条可信指纹、无事务旁文件、无符号链接）；被检出的两条 12.2 来源因存在 `jellyfin.db-wal/-shm` 被拒绝，且工具改为只读副本读取指纹库，不再在原库创建旁文件。native 安装后的负载比较按固定 12.3 `InstallationManager` 的真实目录布局读取。
- Remaining In-Slice Work：B 的完整回归、独立复现、逐图／原文核验与 Slice Final；A 最终审查。
- Risks / Deviations：小库阶段使用已验收的 24 秒合成样本（包内 2 秒样本不足以完成 5 秒进度门槛）；小库混合轮候选为 5（所选库 5 个源），另有 1 个未选库源用于范围对照；`MKV.C06.full` 为 `yuvj420p`／颜色范围 `pc`，属真实输出；显式 `MP4.C02.unspecified` 三阶段字段中 `ColorRange` 为 `null`，符合既有有界返回规则。首轮实机尝试的失败与重跑记录保留在同一证据目录（`web-install*`、`diag*`）。
- Head SHA：`0e171869272c27c9de3faeb2d6499fcab713011c`（实现提交；本报告为紧随其后的文档提交）。上一版报告写的 `0e17186d31d1f47cbfebee9f85c2ba5cfabcb4e0` 不可达，已按真实 Git 身份更正。

## Developer Correction Report（B61-1～5，同一 Task 6.1）

本轮从 `c11017a`（B 的修复指引）开始，Task Base／Contract Checkpoint／同一 Release ZIP 均未移动。实现检查点：`966800e`（五个阻塞项）与 `947f703`（Web 共享计数窗口，见下）。证据索引在忽略目录 `.git/validation-evidence/dev-fix-611/INDEX.md`，计时账本同目录 `timing-ledger.json`。

- Changed Files（本轮）：`scripts/run_isolated_package_integration.py`、`scripts/run_isolated_playback_integration.py`、`tests/test_isolated_package_integration.py`、`tests/test_isolated_playback_integration.py`、`tests/test_isolated_configuration_integration.py`。未改 `src/`、C# 测试／项目／依赖锁、版本／ABI／schema、Release／标签／附件。
- **B61-1 locale 守卫**：`test_driver_declares_the_five_editable_fields_and_no_second_run_entry` 改为断言驱动真实默认 `locale: cfg.locale || 'zh-CN'`；新增 `test_only_the_install_scenario_overrides_the_default_locale` 固定“只有安装阶段显式 en-US”。未删断言、未用注释凑字符串。
- **B61-2 统一重启**：`run_isolated_playback_integration.unified_restart()` 由 `scenario_matrix` 在 14 行全部 PASS 后调用：逐行 `freeze_state`（地址、完整主流集合、五字段指纹、ffprobe 计数）→ 一次 `pkg.restart()` → 全部行 `read_only_state` + `restart_readback_failures` 先读比较 → 之后才逐行 `play_once`，要求 `ffprobe delta 0`、指纹不变、真实媒体请求。小库侧新增 `small_library_unified_restart()`：冻结 S1、S2、S3、S4（合并项目**两条**源与两条指纹）、O1 及配置 → 一次重启 → 全部先读 → 再显式选源实播且 `probe delta 0`。测试守卫固定“一次 restart、先读在所有 `play_once` 之前”。
- **B61-3 Web 同源共享**：新增 `stage_web_sharing()`：受控延迟源改地址 → 原生任务真实开始（观察到该延迟请求开始）→ 真实 Web Play 加入同一源 → 插件自身日志出现 `Native STRM probe started` **1** 次且 `Joined a running native probe` **1** 次 → 批摘要 `need probe 1 / reliable success 1` → 新地址已提交 → Web 实际推进 ≥5 s。随后 `stage_sharing_concurrency()` 让两个独立变化源同轮运行并核对峰值 = 2、各探测恰好一次。API 级 `scenario_sharing` 结果单独记录为 `"PlaybackInfo HTTP call, not a Web Play"`，不再充当 Web 证据。
- **B61-4 公开安装**：删除本地索引发布器，新增 `fetch_public_catalog()` 先读并校验公开索引（guid、版本、ABI、下载地址、MD5），`stage_web_install` 用 `https://raw.githubusercontent.com/kentinya/jellyfin-strm-probe/main/manifest.json` 完成原生仓库添加／确认安装／重启 Active／负载比对。未改远端索引、Release 或标签。
- **B61-5 输入与原始证据**：`run_compat_stage` 在每阶段结束时（含失败路径）把该阶段自己的服务器日志、ffprobe 行与容器状态写入 `server-logs-<stage>/` 与 `server-ffprobe-lines-<stage>.log`，早于下一阶段 reset；顶层新增 `invocation`（argv、字面命令、解释器、cwd、开始时间）与 `toolInputs`（脚本及 12.3 规格／两版锁摘要），并写 `elapsedSeconds`／`startedAt`／`finishedAt`。`--upgrade-source-workspace` 缺失时在任何实例启动前拒绝，不再把升级记 SKIPPED 后整体 PASS。新增结构守卫发现并修掉 `nativeInstall` 记录多余尾逗号（曾使 JSON 变成单元素数组），同时新增“记录必须是映射”的 AST 守卫。
- 实现细节修正：`947f703` 把 Web 共享的 start／join 计数改为**本轮事件增量**（此前读整份日志，在小库前序阶段也已探测的实例上会多计）。
- Tests and Results（Developer 聚焦，Python 3.11.10）：
  - `-p test_isolated_configuration_integration.py` → 10→11 passed；`-p test_isolated_package_integration.py` → 49→55 passed；`-p test_isolated_playback_integration.py` → 125→126 passed；`-p test_isolated_batch_integration.py` → 42 passed；`-p test_development_environment.py` → 6 passed。
  - `python3 -m compileall -q scripts tests`、两个 `node --check`、`scripts/check_governance.py`、`git diff --check` 通过。
  - 12.3 实机（同一原 ZIP `9641fe91…9e37`，镜像 digest `720ad289…`）：公开索引安装 PASS（158.8 s）、12.2→12.3 升级保持 PASS（46.5 s）、14 行统一重启 PASS（513.5 s）、Web 共享＋多源＋小库统一重启 PASS（497.7 s，最终工具上重跑 `dfc1d475…` 再 PASS 520.5 s）。每次运行都记录 `instanceReconciliation: CLEAN`、容器 `exited 0 / oom_killed false`。
  - 已实际打开核验截图：共享窗口 `MP4 A` 色条 + 时间码、小库统一重启 `MKV A` 5.8 s、矩阵 `MP4 LIM` 5.733 s、F01 恢复后 `MP4 P4B`、公开安装的 Available／确认对话框／安装成功页。
  - 未运行（B 负责）：完整 Python discovery、完整 C# restore/build/test/format、B 独立关键复现与单独 Slice Final。
- 复用边界（交 B 决定）：14 行与 12.2 升级的实机观察来自本轮新工作区；矩阵 12.3 工作区按只读复制并在前后比较摘要。播放工具摘要在所有运行中均为最终提交值 `90923c1d…`；package 工具最后两处改动只影响安装记录形状与共享计数窗口，因此 `47ffad27…` 那次安装结果与 `6d7cdc33…` 那次的升级结果**未**在最新摘要上重跑，是否复用请 B 明确判断（未默认声称有效）。
- Risks / Deviations：本轮第一个缺口序列有 4 次失败重跑（692 s）与一次因计数窗口缺陷的整体重跑（521 s），因此测试／实机墙钟约占总用时 **42%（按实际开工 11:03Z）至 53%（按证据标记 11:23:35Z）**，**高于用户本轮要求的 30%**，按标记口径也略高于 Task 的 50%；超出部分全部为上述失败／重跑，没有削减任何门槛。发现计数缺陷后未再启动新的昂贵运行。
- 结论：B61-1～5 均已有对应修正、聚焦测试与实机／原文证据；“升级来源缺失即拒绝”为新增硬性拒绝，公开安装为本轮真实新证据。其余（License 一致、失败保留、收尾）如实列出。
- Head SHA：`966800e`（五个阻塞项）、`947f703`（计数窗口修正）；本报告为紧随其后的文档提交。

## B 首轮 Review Result（历史 FIX REQUIRED）

```text
Reviewed: fa74d6db1d788e21284aa9ad50190e81d4d4f12b..ceb2ad3200e08a942dc7720ff2aad6f55ef9d5e8
Implementation Head reviewed: 0e171869272c27c9de3faeb2d6499fcab713011c
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER CORRECTS THE SAME TASK 6.1; BASE / CONTRACT / ORIGINAL ZIP UNCHANGED
```

### B 2026-10-24 独立复核与当前阻塞

初始工作区干净，main 领先 origin/main 4 个提交。B 审查上述完整范围的 16 个文件，包含计划／指针、全部工具及测试；实现至交付 Head 仅 TASK.md 不同。插件源码、C# 测试／依赖、版本／ABI／schema、原 Release ZIP 未改动；没有发现需要扩大到插件修正的实机故障。本次不移动 Slice／Task Base，不新增 Task 或框架，不推送。

| ID | 当前 Task 阻塞与实际依据 | 同一 Task 的必要修正 |
|---|---|---|
| B61-1（P1，AC-7） | 完整 Python 3.11.10 discovery **458 项，457 PASS／1 FAIL／0 SKIP，exit 1**。`test_isolated_configuration_integration.ConfigurationScriptGuardTests.test_driver_declares_the_five_editable_fields_and_no_second_run_entry` 第 121 行仍要求 `locale: 'zh-CN'`，驱动第 733 行已改为 `cfg.locale || 'zh-CN'`。Developer 的聚焦集合漏了直接受影响的配置工具回归。 | 保持默认 zh-CN 与安装场景 en-US 的行为，更新对应守卫以验证这两项语义；不删除 locale 保护、不加无效注释凑字符串。Developer 只跑改动直接影响的 configuration／package／playback 等反馈；B 在最终候选再跑完整 3.11。 |
| B61-2（P1，RO-5／AC-5） | `scenario_matrix` 第 3154～3157 行在逐行结果汇总后结束；交付 `matrix14/matrix-result.json` 只有各行 frozen/readOnlyAfterRestart，没有 14 行接受状态统一冻结后的重启先读。小库 `stage_multi_source` 只冻结一个可见项目的一条所选源指纹，也未覆盖该阶段全部接受状态／两源全部指纹。 | 以现有 freeze/read_only、原生重启和严格 Web Play 顺序补齐统一观察：任何取源前先读全部冻结项目／源的地址、完整主流、五字段，之后实播／选源。优先在保留准备库的新归属副本补证，不因缺汇总再准备全库或机械重跑全部变化旅程；不建立重启框架。 |
| B61-3（P1，RO-6／AC-6） | package 第 1657 行复用 `batch.scenario_sharing`；其中第 1213 行是 `base.call_playback`，原文 sharing.playback 是 HTTP PlaybackInfo 数据，无浏览器播放进度／解码帧／截图。之后单独 Web Play 不能补成同源重叠的真实 Web 旅程。 | 仅补计划中的一个方向：原生任务实际开始后，在同源真实 Web 点击播放，观察共享日志／一个物理探测、当前源与保存／提交、至少 5 秒解码播放；同时按既有时序核对独立变化源与默认并发 2。保留已有 API 共享事实，不把它外推为 Web 实播；不再展开另一方向或 suite。 |
| B61-4（P1，RO-1／Required Surface） | `publish_local_repository`／`stage_web_install` 和交付 published.repositoryUrl 均使用 `http://media:8080/manifest.json`。合同与计划要求原生仓库页添加固定公开索引；本地同包安装不能替代该 Surface。 | 沿用已做好的原生页面操作，从 `https://raw.githubusercontent.com/kentinya/jellyfin-strm-probe/main/manifest.json` 选定同一版本并确认安装，核对同 ZIP／负载／重启 Active。无需改公开索引、发布包或另建安装基础设施；原本地安装结果保留其真实归属。 |
| B61-5（P1，AC-7／输入与收尾） | 报告写的实现 SHA `0e17186d31d1f47cbfebee9f85c2ba5cfabcb4e0` 不可达；真实实现是上方 `0e171869…`。交付 package-compat-final 结果缺 elapsedSeconds／evidenceArchive，索引为 Elapsed None，目录无其声明的 server-logs／server-ffprobe-lines.log；最终源码 main 已会写这些字段，现有运行无法直接认作最终工具候选。各阶段索引也缺精确命令／被测工具内容、每次退出／OOM及时间比例的可核验记录。全阶段共用目录且 reset 清掉前阶段 config，末尾一次归档也无法保住安装／升级原始日志。 | 更正真实检查点，补一份简洁索引及实际输入／命令／时间／原始日志／生命周期归属；在各阶段 reset 前留存必要原文，最终正常停止并保留副本。能从现存原文恢复并验证者复用；无法绑定最终候选或缺原始观察者只补受影响阶段，不默认重跑旧全量。不得重造已丢失日志或为此开发证据管理系统。 |

`--upgrade-source-workspace` 当前省略时会将升级记为 SKIPPED，但顶层仍可 PASS（第 1911～1914 行及 main）。这与既定无合格来源时准备最小非空基线的接口合同不符；在 B61-4／5 的既有 compatibility 路径内明确拒绝不完整验收或完成该基线，不能把 SKIPPED 当整组通过；无需探测其他假造入口。

### 全部 Slice 结果重评

| 结果组 | 本次核对事实与剩余义务 |
|---|---|
| RO-1 | 同 ZIP 的本地原生安装／Active／配置与 12.2→12.3 前后状态原文已存在；公开索引尚缺，输入／日志闭包按 B61-4／5 修正。升级前两条视频可信指纹仍在，新旧状态相等；不把历史 Audio 项纳入本次验收。 |
| RO-2 | 14 行结果均标 PASS，B 逐行核对窗口／再播／重启的计数记录，八类预期相符，D02 原生计数另列。尚未完成全部逐图／最终输入认证，不签发本组独立 PASS；修正后的复用按实际输入判断。 |
| RO-3 | B 从三个 C 行的实际窗口原文解析 33 字段：encoder==saved；limited=tv、full=pc 重读只 ColorRange 变 null，未指定三阶段均 null，各窗口实际 ffprobe 增量 1。实际打开 limited／full 推进图，分别显示 MP4 LIM 5.867s／MKV C06FUL 5.933s，无错误。保留这些观察，完整接受仍需候选身份及其余图片核验。 |
| RO-4 | F01 原文保留首败／再试及同一 missing-f01-mp4.mp4 目标修复、提交和再播 0。B 实际打开原生播放错误图及恢复后的 MP4 P4B 图；独立全旅程尚未新跑，不把抽查当完整 B PASS。 |
| RO-5 | 多源两次原始 PlaybackInfo 确实返回选中 S5 的源 ID、MKV 地址及 Video／Audio，进度均超过 5 秒；markerMatched=false 是名称提示不匹配，未据此认定选源错误。统一全状态／全部指纹先读仍缺，见 B61-2。 |
| RO-6 | 混合轮五个所选源：4 跳过／1 探测并可靠成功，再跑 0；停止／结算、API 共享、默认并发与 false／禁用原文存在。真实 Web 同源共享缺口按 B61-3 补齐，生命周期与输入另核验。 |
| AC-7 | 完整 Python FAIL；C# 匹配复用审计、B 独立换地址＋显式 ColorRange＋重启关键复现、单独 Slice Final 及全量逐图均未完成。已有确定阻塞，按开发流程先退回，其余保持 NOT RUN／未完成，不签发 Closure Packet。 |

### 本次执行、复用与后续检查

- 正式完整 Python 使用 `/opt/py311/python/bin/python3.11 -m unittest discover -s tests -v`，31.224 秒，失败如上。初次命令误用了主机默认 Python 3.13.5，27.672 秒、同一失败；该输出保留为辅助运行，不替代合同 3.11。下一轮先核对解释器，避免重复这一无效配置。
- compileall、两个 Node 语法、治理、git diff --check 通过。未执行 C#／原生安装／播放／任务／独立关键复现／Final；明确阻塞后不再启动昂贵门槛。只读 Docker inventory 确认没有本轮测试实例在运行，未改变生产或原有实例生命周期。
- B 原始完整 diff、两版 Python stdout/stderr／精确命令、检查元数据、逐行／三阶段／失败抽查与四张实际打开图片记录在 `.git/validation-evidence/0e171869272c27c9de3faeb2d6499fcab713011c/b-review-20261024T105140Z/INDEX.md`，只在本机，不上传。最终计时在同目录 timing-ledger.json；两次完整套件和质量检查均计入，严格低于本轮 50%。
- 同一 Task 修正范围仅上述五项及直接受影响的必要反馈。保留 Base／Goal／RO／AC／原 ZIP／准备数据和首败；Developer 不承担 B 的完整回归／Final，也不要求另跑 116 行、1004 项、其他格式、代理或音频 STRM。全部满足后 B 再完整重评并决定 PASS／FIX REQUIRED；不把本次拒绝变成新 Slice／Task。

历史 Task／关闭身份从[关闭账本](docs/progress.md)和真实 Git 快照读取。

<a id="b-review-result"></a>
## B Review Result

```text
Reviewed Range: fa74d6db1d788e21284aa9ad50190e81d4d4f12b..35e6eb459c5c1477eb7a69bb9f4bdb48b755bc9d
Implementation Head: 947f70319ef290300814d1019875a65f42f39a74
Decision: PASS
P0/P1 Blockers: NONE FOUND
```

B 于 2026-10-24 独立审阅完整累计 17 文件差异及原始资料。五个首轮阻塞均关闭：locale 守卫和完整回归已恢复；矩阵 14 行及小库全部六源（合并项目两条指纹）统一冻结、重启先读后实播；原生任务先开始、真实 Web 加入同源，实际 start=1／join=1／可靠成功=1，独立源峰值为 2；公开索引安装与同包负载、Active 已核验；真实 SHA、阶段归档、缺升级来源即拒绝及正常退出均有原文。未改插件源码、C# 输入、依赖、ABI、schema 或发布附件。

| 完整结果 | B 判定依据 |
|---|---|
| RO-1／AC-1 | 接受最终工具 run2/gaps 的公开原生仓库安装：确认 POST 204、同 ZIP／八项负载与 meta 身份、重启 12.3.0 Active、首次信任 0 与配置保存恢复。中间工具升级摘要未直接作为最终候选证明；B 仅补跑最终工具升级 42.3 秒：非空 12.2 副本两条视频可信指纹、完整源／配置，升级后任何播放前先读一致，来源前后摘要相同。 |
| RO-2／AC-2 | 原 14 行八类决策与首次信任的旅程／计数／解码与源身份逐项核对；现有函数与最终工具输入按阶段比较，新增统一重启另取新证据。MP4／MKV 均有跳过和探测。71 份原始 observation 的成功窗口检查未见问题，失败窗口另按预期核对。 |
| RO-3／AC-3 | 三类窗口 33 字段 encoder==saved；limited=tv、full=pc 仅返回 ColorRange 为 null，未指定三阶段均 null。换 URL 与同 URL Size 改变都有实际探测。B 自己的 limited 换 URL 窗口也核验同次三阶段，探测 1、提交成功、实播推进 5.416 秒。 |
| RO-4／AC-4 | F01 首败／再试各探测一次且保留旧五字段；同一 missing-f01 目标原地恢复为 P4B，成功保存／提交后再播 0。原始错误图与恢复内容均实际查看，未把失败改成通过。 |
| RO-5／AC-5 | 独立比较 14 行冻结指纹／源与先前各行正确结束状态；新统一重启全部先读且重播均 0。小库五个可见项目、六条源及合并项目两条指纹／配置完整相等，明确选择 S5 返回 MKV 正确地址并解码。 |
| RO-6／AC-6 | 混合轮 4 跳过／1 探测成功、下一轮 0；选库、进度、停止后已开始工作收尾、旧轮空闲再恢复原文成立。最终工具真实 Web 共享推进 5.412 秒，独立双源峰值 2；真实静态流 false 窗口不探测／不提交，后续允许 Web 处理；禁用原生委托单列。 |

- 完整 Python 3.11.10：`/opt/py311/python/bin/python3.11 -m unittest discover -s tests -v`，466 passed，0 failed／skipped，墙钟 32.464 秒。compileall、两个 Node 语法检查通过。
- C# 复用：与 `cab2eb50dbb3d29a58b09d9c63128cbc87545636` 的 39 个源码／C# 测试／项目／锁／SDK／构建脚本输入逐字节一致；独立读取原始 restore／Release build／test／format 日志，SDK 10.0.401，全部命令 0、205 passed、无跳过。新增环境规格不充当原包构建摘要。
- B 实际打开 43 张带路径标注的静态四图审阅页，覆盖 170 张交付 PNG；图片原字节和映射／摘要留档，未只核对文件存在。F01 原生错误按失败场景保留；其余未见异常可见错误。部分画面标记被原截图裁切，同时以原始 source ID／URL、解码与进度核验。B 独立起播／推进图另实际打开：A→MP4 LIM，重启后仍为 LIM。
- 独立运行的首次命令在统一重启末段收到 SIGTERM（143），无完成报告，不计整次 PASS；已完成窗口 0／1／0／0 的原文保留。续跑遇到容器 DNS 别名丢失（media→127.0.1.1，FFmpeg 连接拒绝），本轮短脚本还遗漏 sourceKey，记 FAIL。修正短脚本的行身份并仅重建本轮容器／网络、保留准备数据后，新统一重启先读／Web 播放 0／指纹不变 PASS，最终两容器 exit 0、OOM false。没有修改候选工具或产品来绕过失败。
- 本机 B 原文：`.git/validation-evidence/947f70319ef290300814d1019875a65f42f39a74/b-review-20261024T124707Z/INDEX.md`；包含完整 diff、输入审计、C# 复用日志指针、全量回归、逐图映射、独立续跑／升级新跑和首败。原始资料仅本机，不随 Git 上传。
- Developer 历史耗时偏差保持：自报实际开工口径 42.4%，证据标记口径 53.1%，超过其报告的 30% 要求；账本顶层总秒数使用标记口径，与 start 字段不同。B 不替其改写历史或以重跑补成合规。B 本轮另记实际墙钟并计入失败、检查、准备和收尾，最终数值见 Closure Packet／本机 timing-ledger.json。

全部 RO 重新评估已满足，不新增 Task；单独 Final 尚待本次新执行完成，Task PASS 不代替 A 的 Slice 最终接受或对外 12.3 支持声明。

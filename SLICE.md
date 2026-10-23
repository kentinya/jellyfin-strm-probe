# Slice 5 — 真实播放决策全场景验证与 CI 修复

~~~text
Slice ID: 5
Name: 真实播放决策全场景验证与 CI 修复
Owner: A
Status: ACTIVE
Base SHA: 323a3f310100c38c373ce078767d50f4135e8cf1
Implementation Head: NOT SET
~~~

## 用户目标与激活边界

2026-10-20 用户要求在下一 Slice 规划八类决策的真实播放测试，自行准备媒体与 STRM、部署 Jellyfin 并安装插件，同时规划 GitHub Actions 失败修复。本合同承接新增需求，详细场景与执行设计见 [播放测试及 CI 计划](docs/slice-5-playback-test-plan.md)。

2026-10-20 用户在规划及实播约束确认后明确要求激活 Slice。A 据此将本合同激活，保留全部 Required Outcomes、八类决策、简化工具与截图实际查看门槛。该激活检查点提交后，下一步由 B 核对真实仓库并规划首个 Task；工作包建议不代替 B 计划或独立审查。本轮只激活合同及同步入口，不建立活动实施 Task、不修改插件／测试／工作流、不部署或操作现存实例、不推送。

Base 为规划前干净 main 的真实 HEAD，不随后续文档提交移动。此前四个 Slice 的关闭结论和 Base／Implementation Head 保留，Slice 4 合同、Closure Packet、A Final Review 与旧 Task 入口见 [关闭账本](docs/progress.md#slice-4-closed)。新发现的问题不改写成旧验收已经覆盖。

前序只读调查及后续真实播放已出现 calls 1、encoder primary True、persisted primary True、address persisted True、returned primary matches probe False，并导致原生 PlaybackInfo 500。此前合同只授权测试／工具与 CI 修复；用户现授予 A 权限处理该阻塞，A 按下方 Material Contract Change 将有证据支持的产品修正纳入当前 Slice。实际差异字段仍需取证，原失败保留，不能直接认定根因是 ColorRange。

## 用户明确撤出音频 STRM（Material Contract Change，2026-10-21）

用户明确“音频不在考虑范围内，后续不会使用 strm 形式”。撤出本 Slice 的音频 STRM 基线、缺 Audio 主流及音频 P01～P08 子场景、专用音频库／夹具与音频实播验收；历史 B03 的 FAIL／BLOCKED 原样保留，后续按用户授权不执行，不计 PASS、不承诺音频 STRM 支持。此变更保留 Slice／Task Base、既有实现和审查历史。MP4／MKV 的八类决策、缺 Video 主流（含仍有音轨）、ColorRange、失败恢复、重启、完整 C#／Python 及适用包验收均不减少；视频音轨仍按原生播放要求核验，不删除通用主流规则或产品分支。A 提交本合同后，由 B 重判同一 Task 5.2 的视频范围及最终门禁，不自动通过。

## A 授权产品误拒绝取证与修正（Material Contract Change，2026-10-21）

用户在 B 提交真实播放阻塞、说明需由 A 决定产品修正范围后，明确“给你 A 的权限开始工作”。A 核对已提交 B 决定 `76adf423b70649624a75d6830482fc3f1ca70bba`、固定候选和匹配原始证据，决定在同一 Slice 5／Task 5.3 内纳入产品取证与修正。修改了原“仅测试、不改产品”的实施边界，属于实质合同变更；八类决策、Required Outcome／Surface 身份及用户结果保持，RO-3 明确纳入修正，业务正确性及验收门槛不降低。Slice Base `323a3f310100c38c373ce078767d50f4135e8cf1`、Task Base `f17fb1fc90dda242eeff9fac7b4f21576b5e6f94`、ID、历史实现／审查／FAIL／NOT RUN 不变。

**授权范围：**

1. 从现有矩阵／原生 Web Play／PlaybackInfo 链路取得同一次探测的①编码器主流、②原生保存成功后的完整主流入参、③原生重读／返回主流，关联项目、实际 MediaSourceId、调用及 URL 身份；覆盖完整 PrimaryStreamIdentity 字段。依据实际字段差异和固定 Jellyfin 源码确认原因后，修正插件对有效结果的误拒绝。允许调整现有 `ProbeExecutionContext`、`StrmPlaybackOptimizer` 及直接必要的既有接入／保存代理和对应 C# 测试；不预定删除 ColorRange 或其他字段。
2. 标准外部只读调试器仍可使用；为取得上述资料，也明确授权在既有接入方法补必要的、默认关闭并受既有 DetailedLog 控制的字段诊断。只记录本次结果的必要字段及脱敏关联，禁止完整 URL、token、Cookie、凭据或私有路径；不新增配置开关、独立诊断插件、状态库、框架或控制 API。诊断不能改变入参、保存／异常顺序、返回值、探测次数或取消语义，不为取证另跑一次探测补写同次结果。
3. 同一 Task 继续修正 B 已列的必要入口问题：失败时先保留原始响应／计数及可读取的原生状态／五字段，再保留 FAIL；P07 输入恢复固定合同；D04 定位真实普通文件及源并完成重启对账；移除结果对象的凭据传递。仅改当前顺序入口及直接相关测试／驱动；不为非阻塞润色扩大工具范围。

**成功边界：** 修正必须保持本次真正探测成功、对应项目／源、原生主流和最新地址确已保存、Manifest 未再变化和条件提交。只有证据证明是固定版本的合法表示／持久化往返差异，才允许有界规范化；不能无条件忽略字段、只看“有主流”或把旧流／其他源当作本次结果。保留相同元数据下保存失败的拒绝／旧基线／重试控制，以及缺 Video、失败／原生取消、未知源、地址保存失败和探测中变化的保护。禁止直接提高 allowMediaProbe=false 权限、仅更新路径、预期失败化有效媒体或放宽真实播放断言。

**取证与正式包：** 原失败候选／ZIP 和原始证据继续保留。修正后从真实提交生成新的正式候选 ZIP，记录源码、build inputs、锁、负载和部署身份；同一最终 ZIP 完成全矩阵及正式门禁。必要诊断随该正式候选按现有日志配置开／关，不另用修改判定的诊断构建冒充正式包。调试器暂停的诊断运行单列，正式播放／计数／成本门槛使用未附加调试器的正式候选；字段取证须说明与正式候选的完全输入匹配。任何诊断或修正都不等于 RO-3 已通过。

**交接：** A 本轮只提交合同及同步文档，不实施插件、不运行产品验收或关闭 Slice。Task 5.3 保持 FIX REQUIRED；原计划和 B 决定保留，当前 Task 范围需在本合同提交后由 B 明确重判为继续／调整，并固定真实 Contract Checkpoint、受影响开发验证与全部最终门禁，Developer 才能按新范围实施。不得用工作区合同或本次授权直接绕过 B 的计划检查点。

## 实施方式与实际播放约束

复用现有 package_environment.py、run_isolated_package_integration.py 和 package_playback_driver.mjs 的隔离部署、指定 ZIP 安装与原生 Web 播放能力；用 Jellyfin 自带 FFmpeg 生成少量媒体，再写入对应 STRM，串行切换输入。重复操作最多补一个直接调用现有函数的简单顺序脚本，必要时小改现有浏览器驱动以采集截图／视频进度；结果保存为表格、日志和截图。不另建通用测试框架、调度器、场景 DSL、管理界面或独立证据管理系统，真实播放也不塞入现有轻量治理 CI job。

以下为本 Slice 必须执行的八类决策；详细子场景只能细化，不能减少这些要求：

| ID | 场景 | 目标源测量窗口内实际 ffprobe |
|---|---|---|
| P01 | 缺少必要主媒体流 | 1 |
| P02 | URL 变化，含 SHA-1／Size 相同 | 1 |
| P03 | URL 不变，双侧有效 SHA-1 相同 | 0，忽略 Size 差异 |
| P04 | URL 不变，双侧有效 SHA-1 不同 | 1 |
| P05 | URL 不变，无可比较 SHA-1，双侧有效 Size 相同 | 0 |
| P06 | URL 不变，无可比较 SHA-1，双侧有效 Size 不同 | 1 |
| P07 | URL 不变，SHA-1、Size 都无法比较 | 0，记录信息不足 |
| P08 | 仅 Modified 注释或文件 mtime 变化 | 0 |

每个正常媒体子场景必须通过真实浏览器打开 Jellyfin 原生 Web 客户端并点击播放；不能先请求一次 PlaybackInfo 消费掉目标变化。保留开始播放及随后实际播放时间至少推进 5 秒的截图，执行者逐场景打开截图检查画面／播放器状态、A／B 内容标记及可见错误，同时记录播放时间推进、视频解码帧和实际媒体请求。失败场景同样留存报错截图；恢复后重新取得成功播放截图。

截图、ffprobe 计数、PlaybackInfo 的源／地址／主流、原生保存及五字段指纹必须按同一场景 ID／会话对应。截图检查和进度／日志／状态核验都是必要证据，单一 HTTP 200、播放器元素存在、自动化成功标志或未打开查看的截图均不能判 PASS。B 独立验收须审阅逐行截图及对应结果；正常、ColorRange、失败恢复、再次播放和重启后的实播均遵守上述要求。截图在保存前避开凭据及敏感地址，随本轮忽略的证据保留。

## Required Outcomes

| ID | 完整结果 |
|---|---|
| RO-1 | 可复现的隔离环境：自行合成本地媒体、计算真实内容 SHA-1／Size、写版本 1 STRM，部署固定 Jellyfin 并从指定 ZIP 安装插件；来源、归属、配置、产物与基线可核验，不依赖旧夹具或旧 token。 |
| RO-2 | 八类决策逐项执行真实原生 Web 播放，同时核对实际 ffprobe、MediaSourceId→URL、必要主流、原生保存、五字段指纹、再次播放及重启；视频含 MP4／MKV，缺主流覆盖缺 Video 的视频项目。不能仅凭 HTTP 200 或决策日志判 PASS。 |
| RO-3 | 已知返回主流误判具有真实媒体回归：含明确 ColorRange 的媒体与未指定该字段的对照，取得同次探测结果／保存入参／重读返回的完整字段差异，基于证据修复误拒绝，并验证失败、旧基线保护与恢复。有效媒体正常播放，仍误拒绝则报 FAIL。 |
| RO-4 | GitHub Actions 三个已知失败在干净检出、固定 Python 3.11 下修复；测试自备临时输入，保持隔离及不可变镜像锁验证，完整 Python 回归／语法／治理／差异检查通过，取得匹配候选的远端 workflow 成功结果。 |

## Required Surfaces

- 固定 Jellyfin 12.2.0／源码 ca0f16eb7c195f720a1493ed469a27c4657db0c6、Linux x64、SDK 10.0.401，镜像／依赖沿用仓库锁定身份；实际主机与端口运行前记录。
- 独立包安装实例、本地可控 HTTP 媒体服务、视频临时库、真实版本化 STRM、原生 Web 客户端、Jellyfin 自带 FFmpeg／ffprobe。
- 原生进程／编码器调用、媒体流与地址保存、PlaybackInfo 选源、SQLite 指纹、客户端播放进度、已打开检查的浏览器截图、完整会话日志、重启前后只读状态。
- quality.yml、三个失败用例涉及的测试及必要工具、干净检出和远端 job。Python 工作流绿灯与真实播放结果分别报告。

## 业务不变量与用户约束

1. 八类预期保持 [稳定需求](docs/requirements.md) 的优先级：缺主流要求探测；URL 改变优先于 SHA-1／Size；双侧有效 SHA-1 相同忽略 Size、不同探测；不可比时仅双侧有效 Size 不同触发；信息不足与仅 Modified 变化跳过。
2. 主矩阵使用受支持 STRM、允许探测、已有主流与历史指纹；缺主流显式改变前提，首次信任另列。allowMediaProbe=false 不提高权限；禁用、普通媒体、旧 STRM 保留原生委托，不能要求原生也零探测。
3. 实际探测成功、主流及最新地址已保存、Manifest 稳定和条件提交不可弱化。失败、取消、竞态、未知返回源或保存失败保护旧指纹；不接受旧流或仅更新路径。
4. 测试脚本可在专用临时目录生成媒体／STRM、计算夹具哈希；插件只读，不生成 STRM、不下载远程媒体算哈希，不新增状态机、调度器或成功旁路。
5. 只操作明确归属的隔离实例。现存全部 1004 项准备库跨阶段保留，需要回归时核验后复用；新小型播放环境独立准备，不销毁／重建原库或接管运行中实例。
6. 可公开日志／证据不含凭据、token、Cookie、完整签名 URL 或私有路径。原始本机资料留在稳定忽略目录，首败与重跑均保留。
7. JellyfinProxy／OpenList 联调、生产操作、跨版本／全格式／全客户端兼容、线上发布排除。V4.3 原方案继续退出治理和上传范围。

## Slice 验收

| ID | 必要证据 |
|---|---|
| AC-1 | RO-1：记录媒体生成命令、真实 SHA-1／Size／流信息、STRM 内容身份、镜像、源码及 ZIP 摘要；仅从 ZIP 安装并确认 Active、部署文件匹配归档。准备与测量阶段分开。 |
| AC-2 | RO-2：P01～P08 及指定子场景全部有独立前置状态和预期／实际对账；探测行实际 ffprobe=1、跳过行=0，日志缺失不能当 0。逐行真实浏览器点击播放，保留开始及播放时间至少推进 5 秒后的截图，执行者打开检查并记录内容标记／播放器状态／错误；视频有解码帧及至少 5 秒播放推进，实际媒体请求及正确源／地址／主流、持久化与指纹均满足合同。 |
| AC-3 | RO-2：视频缺主流、规则优先级、首次信任／权限／委托对照、同 URL 替换、信息不足、Modified 注释与 mtime 分别覆盖；成功接受后再播不重复探测。重启后先只读核验再播放，不能用播放补写状态掩盖丢失。 |
| AC-4 | RO-3：显式 ColorRange 与对照媒体经原生探测、数据库往返和客户端播放，取得同次完整三阶段字段、定位差异并验证修正，有效结果不误拒绝；错误 URL／损坏媒体、相同元数据保存失败等控制不接受无效结果或新指纹，修复后重新探测并播放。诊断和正常候选身份可核验，不删断言或标预期失败掩盖。 |
| AC-5 | RO-4：CI-F1～CI-F3 原失败保留，干净检出可复现并修复，Python 3.11 完整 discovery 与语法检查通过，不依赖忽略的 artifacts、数据库或 Docker；远端对应修复候选的 Repository quality 必要步骤全部成功。 |
| AC-6 | 最终候选完整 C#／Python 回归及受影响真实回归、同 ZIP 本矩阵取得可核验结果；B 独立验收并审阅逐行截图及对应播放／探测／保存证据，明确复用／新跑范围。实施复用现有工具、仅作必要小改及简单顺序编排，未另建测试框架。归属、资源、失败、恢复和收尾齐全，缺失／BLOCKED／NOT RUN 不计 PASS。 |

## 最终验证

播放、原生刷新／持久化及安装验证按 T4 管理。Developer 只跑新增／修改与直接影响的测试，B 负责完整回归及独立验收；本次激活不表示下列产品门槛已经执行。

    bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
    bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
    bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
    bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
    python3 -m unittest discover -s tests -v
    python3 scripts/check_governance.py
    git diff --check

Python 完整回归另在 Python 3.11 干净检出执行。现有 `scripts/run_isolated_playback_integration.py --scenario baseline`／`--scenario matrix` 是已实现入口，准确参数、全部固定视频行、预算和证据目录由 B 在同一 Task 固定。本次授权触及插件共用探测链，B 必须承担完整 C#／Python、真实原生播放／批量／配置，以及同一最终 ZIP 的 baseline／全部视频矩阵／package／scan／现存全部 1004 项 large 门禁和独立关键复现；Developer 仅跑改动直接影响的反馈。任务已列的完整门槛不因授权调整而省略，匹配证据按流程核验复用，文档后继不机械重跑 Final。按用户 2026-10-23 最新指示“不考虑时间预算了，继续跑剩余验证”，本次续验取消此前整个 Task 测试占比及外部预算收束限制；原生超时、正确性断言、全部验收和审查责任保持。既往累计计时及预算阻断保留为历史，不改写为通过。

证据绑定源码与工作区内容身份、SDK／Python／镜像／锁／浏览器、媒体／STRM、ZIP 与部署摘要，保留精确命令、退出码、时序、逐行计数、响应／状态／播放进度、截图及实际查看结论、首败与重跑。状态恢复与只清理本轮专用资源单列；远端发布／运行以届时明确授权为准，本规划不自动推送。

## Closure Packet

NOT RUN。完整视频矩阵及 Slice Final 尚未完成，不具备最终审查条件；已有 Task 候选／CI 的分层结果见 TASK.md 与固定 Git 快照，本次范围修订不构成产品验收。

## A Final Review

    Reviewed Range: NOT SET
    Decision: PENDING
    P0/P1 Blockers: NOT ASSESSED

NEXT ACTION: B CONTINUES TASK 5.3 FIXED-CANDIDATE VIDEO MATRIX AND SPECIFIED FULL GATES; ALL 12 COLORRANGE ROWS ACCEPTED (SEE TASK.md)

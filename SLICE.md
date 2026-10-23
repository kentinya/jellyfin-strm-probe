# Slice 5 — 真实播放决策全场景验证与 CI 修复

~~~text
Slice ID: 5
Name: 真实播放决策全场景验证与 CI 修复
Owner: A
Status: PASS / CLOSED
Base SHA: 323a3f310100c38c373ce078767d50f4135e8cf1
Implementation Head: cab2eb50dbb3d29a58b09d9c63128cbc87545636
~~~

## 用户目标与激活边界

本节及下方合同变更保留激活／修订时的决定；实际完成范围、证据复用与最终裁定见 Closure Packet 和 A Final Review。

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

**B Decision：SLICE READY FOR A REVIEW（2026-10-23）。** 当前合同全部RO与验收义务已有可核验证据；B停止造Task，将最终审查／关闭交A。不是A PASS或Slice关闭。

| 身份 | 检查点 |
|---|---|
| Slice／Base | 5／`323a3f310100c38c373ce078767d50f4135e8cf1`，不移动 |
| Implementation Head | `cab2eb50dbb3d29a58b09d9c63128cbc87545636`，实际最新工具实施；插件实现检查点`4b4d0cca33f37308842710b2a0a70b1919cd0a58` |
| 当前合同／Task5.3 Base | `68e7bf01e7796fe9972838dfc0d8ed8283aacedd`／`f17fb1fc90dda242eeff9fac7b4f21576b5e6f94` |
| Task5.3 B PASS | `fc71beacdfe7d0d1ca890326f801c7fb6b72a0fe`；无活动Task入口修正后`e5b7c5064b68454d884f2828cafe4ae7edeaa462`治理通过 |
| Final实际运行源码 | 干净`e5b7c5064b68454d884f2828cafe4ae7edeaa462`；与429项回归及独立矩阵候选`bdbb4ee1955fb87076ac48f9257821cb31e248e5`仅SLICE／TASK报告不同，95项其余跟踪输入完全匹配 |
| 唯一正式ZIP | SourceRevision `3a7de052bf089141f76e2f60921de285bd5184c4`；SHA-256 `9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37` |
| 包／构建身份 | DLL `9172e5802e4aadca707a3bae49bb32f66c643f1712b33ca427e3bbf4cb9cb434`；build inputs `f394eabc06a7e5423adefeed0aed34b18078be80d0a7ac9143f46340bb8d98ef`；工具修正未重构包 |

### Required Outcomes与用户结果

| RO／验收 | B完成状态与证据 |
|---|---|
| RO-1／AC-1 | 满足。自备可控MP4／MKV、真实SHA-1／Size／ffprobe、版本1 STRM、Range／固定URL替换／查询别名／真实404及损坏输入；固定Jellyfin12.2.0／Linux x64，仅指定ZIP部署且Active，归属、原生任务默认无触发及负载摘要核对。Final再次干净安装、生成当次媒体并核对五字段与实际生成记录。 |
| RO-2／AC-2、AC-3 | 满足。88个P行＋12个C行＋12个D行＋4个F行＝116／116义务接受；独立关键40／40。实际ffprobe、原生Web实播及逐图查看、当前源／URL／Video＋Audio、原生保存／五字段、再播与重启前冻结后先只读核验均齐；D01与B01／B02为已固定的同次别名。计数按规则；原生委托不强求零探测。 |
| RO-3／AC-4 | 满足。两格式C02／C06的limited／full／unspecified共12／12；同次编码器→成功保存精确匹配，完整33字段返回仅固定版本ColorRange丢失，依据固定版本往返实证有界接受返回null，其他身份字段及探测／保存／地址／Manifest保护保持。相同元数据保存失败、错误／未知源、缺Video、失败／原生取消／变化与恢复的单元及原生门禁保持；有效视频不再误拒绝。 |
| RO-4／AC-5 | 满足，保留Task5.1已提交B PASS：三个真实Base失败已复现并修复，干净Python3.11、不可变锁／隔离断言保持；已授权修复候选`0d7162c56c3a2ea9a4fa7ffbdfc0e5c9e49bf482`的[Repository quality run 39521097113](https://github.com/kentinya/jellyfin-strm-probe/actions/runs/39521097113)全部必要步骤成功。当前后续提交未推送／未跑新远端，不借此声称cab2eb5有远端绿灯；本Task不新增发布授权或远端门槛。 |
| AC-6／完整回归、独立审查与收尾 | 满足。B完成完整Task Base..Head审查、指定全量及独立复现；本轮最后一行新完整PASS关闭原停服137缺口。原生成功／失败条件、20秒宽限和探测取消语义保持；无新增框架或未来工具Task。以下Final新跑与匹配复用共同构成本合同最终证据。 |

### Task索引

- Task5.1 PASS：`4c75761982bc16dd1c6bae09bee1c3561da2c178:TASK.md`，CI三处失败修复与匹配远端结果；不证明播放矩阵。
- Task5.2 PASS：`f17fb1fc90dda242eeff9fac7b4f21576b5e6f94:TASK.md`，指定ZIP隔离安装、MP4／MKV真实基线与重启。
- Task5.3 PASS：上述B检查点及当前[TASK.md](TASK.md)，完整116义务／独立40／C12、产品误拒绝取证修正、失败恢复／配置恢复／客户端退出与完整门禁。普通后继提交修正无活动Task标题；首次治理失败记录保留，未改治理工具或产品。

### 当前合同Final及完整门禁

**Final新跑：PASS，运行器exit0，含收尾344.078秒。** Task PASS后从上述干净提交执行既有`run_isolated_playback_integration.py --scenario baseline --rows B01,B02`，指定同一ZIP，18151／B专属项目，新工作区；原生准备与测量分开。两行首信任／再播／重启均0／0／0；原生准备另有2次真实ffprobe，完整物理日志与观察计数一致。六个成功窗口推进5.349～5.470秒、87～94解码帧、实际媒体请求成功；12张原图全部逐张实际打开，正确A标记、时钟／帧与运动，无错误。六份原始PlaybackInfo的当前唯一源／正确URL／完整Video字段一致，Audio技术字段一致，仅本地化展示文字差异；完整原生源／流、五字段、STRM与计数的重启先读状态等于冻结状态。六次实际原生Stop204、媒体元素消失，无退出错误或回退路径。部署负载匹配、Active、原生批量任务triggers=[]。只读Docker事件覆盖7次Jellyfin＋7次media退出，全部0／无OOM；最终CLEAN／CLEANED，两服务exit0。既有68容器生命周期／镜像／完整排序挂载保持，未操作生产、共享实例、原1004库或旧失败工作区。

| 完整门禁 | 最终接受证据／复用依据 |
|---|---|
| C# locked restore／Release build／test／format | 205项全部通过，SDK10.0.401；src／C#测试／构建／锁输入完全匹配，原始B完整结果可读，复用，不交回Developer。 |
| 完整Python3.11 | 当前工具候选干净检出429项＝427 PASS＋2既有归档缺失SKIP，exit0；Final纯报告后继输入核对，消费文档的治理另新跑。Node／compileall／diff／提交空白／正式包verify通过。 |
| 视频全部矩阵／baseline | 116义务、独立40、C12满足。strictPlay测量函数、产品和行决策／状态保护相同，复用已接受逐行测量／原始图片与持久化证据；本轮新独立D03／高码率P06／损坏恢复三行完整1003.796秒PASS，并新跑上述Final。不是当前驱动单次116行，也不声称旧行都有新Stop204；旧FAIL保持。 |
| package-all | 完整380.501秒PASS；旧2秒非严格消费配置及执行分支逐字节相同，新增Stop／finally均受strict.enabled保护；按分支输入复用。严格Final另按5秒执行。 |
| scan-all | 完整841.456秒PASS，136源／135项目／128＋8批、完整五字段／原生保存及原触发器恢复；消费输入完全匹配。物理ffprobe原文未观测，不冒充0。 |
| 现存全部1004项large-all | 完整484.107秒PASS，现存1004候选首次信任／再轮零探测、保存、重启先读与16项播放／选源等原断言满足；消费输入完全匹配。原库和验收副本继续保留，不重建。 |
| plugin-full／独立合并与SQLite | 带已披露且已接受的原生扫描完成／FullRefresh预热准备适配，完整516.139秒PASS；独立合并＋SQLite151.369秒PASS。原函数／断言／2.5秒阈值不变；不推导冷启动SLA、不称未经适配CLI PASS，不重开已接受的准备决定。 |
| batch-suite／configuration-all | 完整466.212秒／277.621秒PASS；停止与收尾、双向共享、范围／定时、并发、状态库故障恢复及配置／触发器恢复；57张配置图已全部实际查看。消费输入完全匹配。 |

原库完整1170文件摘要`189b67c66e608833b27fa818de24bb1611788565c87eeffc0568b9eefe958bd2`保持；所选支持版本1源1004，两条旧／不支持及一条库外控制不混计。原1004项、已接受大库副本和旧C／E失败工作区持续保留，未经确认后续不再需要前不清理。

### 业务不变量、限制及交接

完整决策／解析／权限／指纹／保存／源集合／共享与并发控制、原生失败恢复均由C#及实机门禁保持。首次信任不宣称当次探测成功；URL改变仍要求原生探测与保存，失败／取消／变化不覆写可信基线，缺新有效SHA-1不套旧身份。插件只读STRM，SQLite只保存最小历史指纹，未加入生产依赖、控制接口、调度器或新取消关联。

**非阻塞事实与明确排除：** 历史Cast错误、预算中断、旧原生收尾137及所有整体FAIL保留，不反写为PASS；本轮全部正常停服不证明旧阻塞的唯一内部await。beforeunload回退为人工dispatch事件，正常实播全部只走osd-back；失败未伪造停止。Web非JSON500正文未由驱动保存，真实状态／原生日志／错误截图与API完整门禁的5次500正文分别留存，不补造历史。两归档缺失SKIP不计PASS，scan物理ffprobe为NOT OBSERVED。音频STRM和JellyfinProxy按用户已提交范围决定不执行／不计PASS，不承诺其支持；跨版本／全客户端／生产及新远端发布排除。无当前B P0/P1阻塞，无新增延期实施Task。

**稳定本机索引：** `.git/validation-evidence/bdbb4ee1955fb87076ac48f9257821cb31e248e5/b-exit-review-20261023T170342Z/INDEX.md`，含完整Task／Slice差异、输入与ZIP摘要、各全量精确命令／退出码／原文索引、116行映射、两角色50张及Final12张逐图记录、完整字段／物理日志／每次重启收尾审计。旧全量与首败原始索引继续可读；本机原始资料不随Git上传，不声称远程可访问。

**B交接时的文档协调：** B保留A最终审查和关闭职责；本次A决定与已完成协调见下方，不改写B交接时尚未关闭的事实。

**SLICE READY FOR A REVIEW。**

## A Final Review

    Reviewed Range: 323a3f310100c38c373ce078767d50f4135e8cf1..cab2eb50dbb3d29a58b09d9c63128cbc87545636
    Decision: PASS / CLOSED
    P0/P1 Blockers: NONE FOUND

**A独立最终决定（2026-10-23）：接受RO-1～RO-4及AC-1～AC-6，关闭Slice 5。** 审查checkout为`cae260cf8bbeea3be97d66f912bb013f72d77eec`，工作区初始干净；以上真实Base与Implementation Head均可达且为祖先，Head之后只有SLICE／TASK报告变化。本次A未参与被审产品实现，不移动Base、不把关闭文档当作实现，也不启动后续Task。

- **完整实现范围：** 审查Slice全范围的产品、测试、工具及合同差异，并核对B各Task决定。CI修复自备临时输入并保留锁／隔离断言；播放仍由原生Web点击Play、实际PlaybackInfo／静态流／原生计划任务入口触发。固定视频行的顺序编排、Range读取、身份定位、配置恢复及测量后客户端退出服务于这些实际旅程，没有新增运行时接口、控制API、调度器或通用测试框架；没有使用猜造入口取得产品结论。
- **产品修正与不变量：** A独立读取固定版本原生事务与双向Map源码，摘要与B取证一致；逐行重算全部12个C场景的同次33字段，编码器与成功保存完全一致，明确range重读只丢失ColorRange，未指定对照完全一致。接受仅返回null的有界适配；其他32字段、同源／同URL、实际成功保存、Manifest稳定及条件提交保持，失败与未知源不因此获准提交。DetailedLog沿用默认关闭的脱敏字段诊断，不改变探测或取消语义。
- **真实用户结果：** A从正式116行索引追到原始观测、完整PlaybackInfo与结果，重新核对454个成功窗口及6个预期失败窗口的进度／解码、ffprobe、当前源／URL／Video＋Audio、五字段及全部重启前冻结与重启先读状态；914张关联原图可读且摘要留存。接受B完整逐行看图记录，A另实际打开8张ColorRange／失败恢复／Final重启原图抽核，未将摘要核验冒充全部逐图查看。各类变化、无Video、跳过、委托、失败旧基线与同目标恢复均满足合同。
- **完整门禁与Final复用：** 独立核对97项跟踪输入，B当前工具候选仅SLICE／TASK报告不同、其余95项一致；正式ZIP完整verify及摘要匹配。读取并核验13项原始门禁命令／日志及输入闭包，接受上方package／scan／现存全部1004项large／prepared plugin与独立合并／batch／configuration证据及所披露准备适配。按执行阶段接受既有矩阵测量证据，另接受当前驱动三行完整独立复现及Task PASS后的单独Slice Final；没有将历史整体FAIL改为PASS，也没有宣称当前驱动单次跑完116行。A独立重读Docker事件，三行与Final的22／14次双服务退出全部0、无OOM，原20秒收尾门槛不变；没有再次启动实机验收。
- **A新运行：** 固定SDK的locked restore、Release build、C# test **205／205、0跳过**、format全部exit0；Python3.11完整discovery **429／429、0跳过**、exit0。本工作区具备两项归档测试输入，B干净检出的2项既有SKIP保留原结论，不倒写为B通过。A结果不替代B干净检出或原生验收；文档协调后的治理与链接／空白检查另行核验。
- **CI与发布边界：** A读取留存的远端原始workflow／job结果，确认Task5.1修复候选`0d7162c56c3a2ea9a4fa7ffbdfc0e5c9e49bf482`对应run39521097113及必要步骤成功；接受RO-4，不声称当前Head有远端绿灯。本次无推送、上架或生产操作。

**非阻塞问题与限制：** B旧行索引中的`formalAcceptedCompleteRows=115`及`remainingGates`是保留的收尾前字段；A以同文件新增的116行事实、最后一行新完整PASS与已完成Final原文裁定，无剩余合同义务。旧Cast／137／预算中断及整体FAIL、Web非JSON500正文缺失、scan物理ffprobe未观测保持历史事实；人工beforeunload回退不称受信浏览器事件，本次接受的正常退出均为osd-back。上述属于证据措辞／工具P2，不延长Slice。音频STRM与代理按用户范围不执行、不计PASS；其他版本／平台／格式／客户端、OpenList专有行为、物理原生数据库保存故障实机注入、镜像整体构建溯源、通用性能及新远端发布未作支持承诺。

**A本机证据：** `.git/validation-evidence/cab2eb50dbb3d29a58b09d9c63128cbc87545636/a-final-review-20261023/INDEX.md`，含完整Slice差异、逐行原文／字段／摘要核验、源码／包／CI／收尾审计、8张实际看图记录和A新运行精确命令／原始输出；只在本机，不随Git上传。首次私有字段审计未识别日志中的JSON字符串引号，修正读取器后核验通过，初次输出保留；不是原生运行失败或另跑探测。

## Closure Reconciliation

- SLICE记录A最终决定并保持Base／Implementation Head；TASK保留B PASS与历史报告、首行为无活动实施任务。Roadmap／Progress同步本次关闭，README入口指向已接受结果，没有自动激活新Slice。
- CURRENT架构与兼容性写明有证据的ColorRange适配；测试矩阵区分Slice 5新增证据与旧Slice关闭时的NOT RUN；范围／安装／执行设计移除当前尚待实施的误导指针。稳定需求与用户旅程逐项复核，无业务规则或验收含义变更。
- 三份角色经验均已复盘，只补充可复用方法；未提交凭据、原始日志、数据库或构建产物。原1004项准备库、验收副本与失败资料继续保留，不清理。
- 当前已授权开发范围全部交付，没有待规划的大版本Slice；停止，等待新增需求。小版本bug不自动触发A规划或新Slice。

Next Action: NONE (CURRENT DEVELOPMENT SCOPE COMPLETE)

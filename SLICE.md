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

前序只读调查发现返回主流匹配可能因原生持久化字段变化而误拒绝；用户补充的现场日志为 calls 1、encoder primary True、persisted primary True、address persisted True、returned primary matches probe False。该现象必须纳入真实回归，具体差异字段仍需取证。用户此前要求产品代码等决定再改；本规划包含测试／工具与 CI 修复，不授权修改插件成功判定。若产品问题阻塞播放，保留 FAIL 并交用户决定，不能通过放宽断言完成本 Slice。

## 用户明确撤出音频 STRM（Material Contract Change，2026-10-21）

用户明确“音频不在考虑范围内，后续不会使用 strm 形式”。撤出本 Slice 的音频 STRM 基线、缺 Audio 主流及音频 P01～P08 子场景、专用音频库／夹具与音频实播验收；历史 B03 的 FAIL／BLOCKED 原样保留，后续按用户授权不执行，不计 PASS、不承诺音频 STRM 支持。此变更保留 Slice／Task Base、既有实现和审查历史。MP4／MKV 的八类决策、缺 Video 主流（含仍有音轨）、ColorRange、失败恢复、重启、完整 C#／Python 及适用包验收均不减少；视频音轨仍按原生播放要求核验，不删除通用主流规则或产品分支。A 提交本合同后，由 B 重判同一 Task 5.2 的视频范围及最终门禁，不自动通过。

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
| RO-3 | 已知返回主流误判具有真实媒体回归：含明确 ColorRange 的媒体与未指定该字段的对照，记录探测结果／保存入参／重读返回的差异，以及失败、旧基线保护与恢复。有效媒体预期正常播放，误拒绝须报 FAIL。 |
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
| AC-4 | RO-3：显式 ColorRange 与对照媒体经原生探测、数据库往返和客户端播放，三阶段差异可定位，有效结果不误拒绝；错误 URL／损坏媒体不提交新指纹，修复后重新探测并播放。遇到未授权产品修复需求保留 FAIL，不删断言或标预期失败掩盖。 |
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

Python 完整回归另在 Python 3.11 干净检出执行。新播放矩阵入口尚未实现，不编造已有命令；B 在正式 Task 固定准确命令、场景展开清单、预算和证据目录。既有 plugin／batch／configuration 开发部署回归及同 ZIP 的 package／scan／large 验证按变更影响明确归属；若改到插件共用探测链，不能省略完整原生播放／批量／扫描／安装及现存全部 1004 项回归。

证据绑定源码与工作区内容身份、SDK／Python／镜像／锁／浏览器、媒体／STRM、ZIP 与部署摘要，保留精确命令、退出码、时序、逐行计数、响应／状态／播放进度、截图及实际查看结论、首败与重跑。状态恢复与只清理本轮专用资源单列；远端发布／运行以届时明确授权为准，本规划不自动推送。

## Closure Packet

NOT RUN。完整视频矩阵及 Slice Final 尚未完成，不具备最终审查条件；已有 Task 候选／CI 的分层结果见 TASK.md 与固定 Git 快照，本次范围修订不构成产品验收。

## A Final Review

    Reviewed Range: NOT SET
    Decision: PENDING
    P0/P1 Blockers: NOT ASSESSED

NEXT ACTION: B PLANS THE NEXT COMPLETE VIDEO MATRIX TASK (SEE TASK.md)

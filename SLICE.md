# Slice 5 — 真实播放决策全场景验证与 CI 修复

~~~text
Slice ID: 5
Name: 真实播放决策全场景验证与 CI 修复
Owner: A
Status: PLANNED
Base SHA: 323a3f310100c38c373ce078767d50f4135e8cf1
Implementation Head: NOT SET
~~~

## 用户目标与规划边界

2026-10-20 用户要求在下一 Slice 规划八类决策的真实播放测试，自行准备媒体与 STRM、部署 Jellyfin 并安装插件，同时规划 GitHub Actions 失败修复。本合同承接新增需求，详细场景与执行设计见 [播放测试及 CI 计划](docs/slice-5-playback-test-plan.md)。

本次只建立规划检查点：不激活 Slice、不建立活动实施 Task、不修改插件／测试／工作流、不部署或操作现存实例、不推送。A 后续提交 ACTIVE 合同后，B 才能按真实仓库规划实施 Task；工作包建议不代替 B 计划或独立审查。

Base 为规划前干净 main 的真实 HEAD，不随后续文档提交移动。此前四个 Slice 的关闭结论和 Base／Implementation Head 保留，Slice 4 合同、Closure Packet、A Final Review 与旧 Task 入口见 [关闭账本](docs/progress.md#slice-4-closed)。新发现的问题不改写成旧验收已经覆盖。

前序只读调查发现返回主流匹配可能因原生持久化字段变化而误拒绝；用户补充的现场日志为 calls 1、encoder primary True、persisted primary True、address persisted True、returned primary matches probe False。该现象必须纳入真实回归，具体差异字段仍需取证。用户此前要求产品代码等决定再改；本规划包含测试／工具与 CI 修复，不授权修改插件成功判定。若产品问题阻塞播放，保留 FAIL 并交用户决定，不能通过放宽断言完成本 Slice。

## Required Outcomes

| ID | 完整结果 |
|---|---|
| RO-1 | 可复现的隔离环境：自行合成本地媒体、计算真实内容 SHA-1／Size、写版本 1 STRM，部署固定 Jellyfin 并从指定 ZIP 安装插件；来源、归属、配置、产物与基线可核验，不依赖旧夹具或旧 token。 |
| RO-2 | 八类决策逐项执行真实原生 Web 播放，同时核对实际 ffprobe、MediaSourceId→URL、必要主流、原生保存、五字段指纹、再次播放及重启；视频含 MP4／MKV，缺主流另覆盖真实音频项目。不能仅凭 HTTP 200 或决策日志判 PASS。 |
| RO-3 | 已知返回主流误判具有真实媒体回归：含明确 ColorRange 的媒体与未指定该字段的对照，记录探测结果／保存入参／重读返回的差异，以及失败、旧基线保护与恢复。有效媒体预期正常播放，误拒绝须报 FAIL。 |
| RO-4 | GitHub Actions 三个已知失败在干净检出、固定 Python 3.11 下修复；测试自备临时输入，保持隔离及不可变镜像锁验证，完整 Python 回归／语法／治理／差异检查通过，取得匹配候选的远端 workflow 成功结果。 |

## Required Surfaces

- 固定 Jellyfin 12.2.0／源码 ca0f16eb7c195f720a1493ed469a27c4657db0c6、Linux x64、SDK 10.0.401，镜像／依赖沿用仓库锁定身份；实际主机与端口运行前记录。
- 独立包安装实例、本地可控 HTTP 媒体服务、视频／音频临时库、真实版本化 STRM、原生 Web 客户端、Jellyfin 自带 FFmpeg／ffprobe。
- 原生进程／编码器调用、媒体流与地址保存、PlaybackInfo 选源、SQLite 指纹、客户端播放进度、完整会话日志、重启前后只读状态。
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
| AC-2 | RO-2：P01～P08 及指定子场景全部有独立前置状态和预期／实际对账；探测行实际 ffprobe=1、跳过行=0，日志缺失不能当 0。逐行客户端播放推进，正确源／地址／主流、持久化与指纹满足合同。 |
| AC-3 | RO-2：视频／音频缺主流、规则优先级、首次信任／权限／委托对照、同 URL 替换、信息不足、Modified 注释与 mtime 分别覆盖；成功接受后再播不重复探测。重启后先只读核验再播放，不能用播放补写状态掩盖丢失。 |
| AC-4 | RO-3：显式 ColorRange 与对照媒体经原生探测、数据库往返和客户端播放，三阶段差异可定位，有效结果不误拒绝；错误 URL／损坏媒体不提交新指纹，修复后重新探测并播放。遇到未授权产品修复需求保留 FAIL，不删断言或标预期失败掩盖。 |
| AC-5 | RO-4：CI-F1～CI-F3 原失败保留，干净检出可复现并修复，Python 3.11 完整 discovery 与语法检查通过，不依赖忽略的 artifacts、数据库或 Docker；远端对应修复候选的 Repository quality 必要步骤全部成功。 |
| AC-6 | 最终候选完整 C#／Python 回归及受影响真实回归、同 ZIP 本矩阵取得可核验结果；B 独立验收并明确复用／新跑范围。归属、资源、失败、恢复和收尾齐全，缺失／BLOCKED／NOT RUN 不计 PASS。 |

## 最终验证

播放、原生刷新／持久化及安装验证按 T4 管理。Developer 只跑新增／修改与直接影响的测试，B 负责完整回归及独立验收；本轮仅规划，不声称执行下列产品门槛。

    bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
    bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
    bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
    bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
    python3 -m unittest discover -s tests -v
    python3 scripts/check_governance.py
    git diff --check

Python 完整回归另在 Python 3.11 干净检出执行。新播放矩阵入口尚未实现，不编造已有命令；B 在正式 Task 固定准确命令、场景展开清单、预算和证据目录。既有 plugin／batch／configuration 开发部署回归及同 ZIP 的 package／scan／large 验证按变更影响明确归属；若改到插件共用探测链，不能省略完整原生播放／批量／扫描／安装及现存全部 1004 项回归。

证据绑定源码与工作区内容身份、SDK／Python／镜像／锁／浏览器、媒体／STRM、ZIP 与部署摘要，保留精确命令、退出码、时序、逐行计数、响应／状态／播放进度、首败与重跑。状态恢复与只清理本轮专用资源单列；远端发布／运行以届时明确授权为准，本规划不自动推送。

## Closure Packet

NOT RUN。尚无实现候选、真实矩阵或修复后 CI 结果，不具备最终审查条件。

## A Final Review

    Reviewed Range: NOT SET
    Decision: PENDING
    P0/P1 Blockers: NOT ASSESSED

NEXT ACTION: A ACTIVATES THE PLANNED SLICE BEFORE B TASK PLANNING

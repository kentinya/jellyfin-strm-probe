# Task 4.4 — 实际 JellyfinProxy 播放链兼容与交接

必读：[Slice 4 合同](SLICE.md)、[固定交付方案](docs/slice-4-delivery-plan.md)、[开发流程](docs/development-workflow.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md)、[Developer 经验](docs/agent-experience/developer-implementation-role.md)。只细化 RO-4，不修改合同／稳定需求；本轮只规划，不实施。

```text
Task ID: 4.4
Parent Slice: 4
Status: PLANNED
Task Base: 57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3
Contract Checkpoint: 539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3
Difficulty: High
Test Level: T4
Planner / Reviewer: B
Implementation Head: NOT SET
```

## Goal

交付 RO-4、AC-7 与 AC-8 的代理／身份／恢复部分：在只消费最终 ZIP 的隔离 Jellyfin 12.2.0／Linux x64 链路运行真实固定 JellyfinProxy，逐源对照原生／代理 PlaybackInfo、MediaSourceId→URL、302 Location 与客户实际 GET／Range 内容。未变、同有效 SHA-1／Size 换 URL 的第一次／重启播放、失败修复、多版本显式选源不得被旧缓存掩盖，准确交接实测版本／配置／媒体／客户端及限制。

## 准入与真实缺口

- 规划开工 main 干净、治理 PASS。4.3 完整计划、Developer 报告、失败历史与最终 B PASS 保留于 57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md，用 git show 57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md 读取，不建永久 Task 副本。接受实现为 8573dfbffebb785261668f9cd5c895be937e000e；本 Task Base 是已通过检查点，不移动旧 Base。
- RO-1／4.1、RO-3／4.2 保留 B PASS，RO-2／4.3 已完整验收。4.3 完整 plugin／batch main 的异步准备适配、原始失败、冷启动延迟与非阻塞 P2 保留，不声称未经适配命令通过。Final 仍须核对扫描变化批量源及多版本 A／B 的完整重启前后状态，不能只信旧扫描标签。
- ACTIVE 合同与至少1000项／全部1004项跨阶段复用义务不变；96891579493c80dc3900909fd1790b67b87451af 仅更新交接措辞，上方仍为实质 Contract Checkpoint。固定方案的4.3→4.4依赖已满足。RO-4仍NOT RUN，仓库无代理验收入口；单独Slice Final、Closure Packet、A最终审查未完成。上位旧进度指针留最终事实协调，不暗改合同。

## 固定代理与风险

目标来源 https://github.com/kentinya/JellyfinProxy ，完整SHA b02c09f5ea97eda34c91729fce5f44ac73f04db6，version.py=0.9.0；不跟踪移动分支／latest或泛称同名代理兼容。B以git show只读核对全部提交文件，摘要留本机 .git/validation-evidence/57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3/b-plan-4.4-20261020/source-feasibility.json。外部工作TOML已有用户修改，未读／复制／改动；实施从精确Git提交独立导出，不带工作patch、不用现存代理容器／配置／凭据。

真实路由经dispatcher进入playback_handler／video_handler，后者按源ID缓存返回302。**首要风险（未实测）**：PlaybackInfoCache默认启用、TTL21600秒／4096项，仅以规范化item ID为键，不区分请求体／选源／客户；HIT绕过Jellyfin并可重新写入旧源URL。必须优先测warm-cache变化，不能只测冷进程。

冻结有效默认：bypass_clients=[Infuse,Kodi]，playback／video／cache专用bypass为空，缓存启用／TTL／容量不变。验收客户不得命中旁路，不能关／缩短缓存、改键、伪装客户或清缓存制造PASS。仅设置隔离必需的上游／监听地址端口／日志落点，完整有效配置含默认值与环境覆盖留摘要。

上游Dockerfile为移动python:3.13-slim，fastapi/httpx/uvicorn为范围依赖。实施先固定基础镜像digest、完整解析依赖／来源／制品摘要与最终image ID，再运行全部场景；可约束隔离构建输入，不改代理源／行为。现存0.4.1镜像不能冒充目标0.9.0；本轮未构建／部署或锁定运行产物。

## 实施范围与隔离

- 新增最小 scripts/run_isolated_proxy_integration.py、tests/test_isolated_proxy_integration.py；确需时用 scripts/proxy_environment.py 分离构建／网络／容器与业务断言。复用package_environment／package_plugin的归属、ZIP校验部署、固定Jellyfin／media镜像、鉴权／对账／清理，包工具MP4／MKV与原生API、扫描工具脱敏证据及完整源快照，不重构整个框架。
- 可增加必要代理构建／依赖身份及媒体计数／Range支持；共享helper变更明确影响与回归。产品修复仅限实测直接阻碍RO-4的最小插件问题，外部缓存失败不做插件绕过补丁；核心DI／成功／保存边界或合同改变先交A。
- 事实文档限compatibility、test-matrix、development-environment、package-installation／README与Task报告，不扩大兼容承诺。
- 新明确归属包工作区／唯一Compose project，仅解包安装，不调用开发deploy_plugin、不补DLL、不挂源码／bin／SDK。固定proxy独立导出构建，禁止直接运行上游host-network compose，不用生产配置／现存服务。
- 规划观测Python3.13.5、Docker29.7.1／Composev5.3.1，18108／18109空闲，可作可配置默认。实施前重核端口／子网／路由、资源／磁盘／浏览器，固定阶段timeout；不绑定本机路径／资源合同。媒体host对Jellyfin／proxy／客户均可达，不改生产DNS／hosts；只回环或内部网。
- 少量受控MP4／MKV、多版本与独立本地鉴权即可；1004准备库／离线基线／副本持续保留。凡完整门禁需大库均复用全部1004项并核前提，不重建／全库重新准备。异步夹具等准备完成，不把准备串行当业务重叠；失败／超时／OOM保留，不暗调阈值重试至绿。

## 必须闭合的验收行为

### 逐源、重定向与内容

相同item／显式MediaSourceId对照原生／代理准确源集合、每源URL摘要与必要主流。允许固定代理原有Protocol／SupportsTranscoding展示差异，不允许错URL／源／流；不能任意源匹配或只HTTP200。

经真实video stream路由显式选源取得302，禁止自动跟随丢掉中间响应；Location对应当前所选URL，再由客户跟随GET／Range，核对状态、Content-Range／长度与字节SHA-256，MP4／MKV均真实读取。区分probe GET与客户请求，不以探测成功冒充客户读取。

同SHA-1／Size换URL用真实字节相同A／B及有效内容hash；必须另核旧URL陷阱、302和逐路由命中，不能只靠相同字节hash证明新地址。另以真实不同媒体／有效不同hash覆盖多源与错误内容控制，不伪造SHA-1。

### 必需场景及请求顺序

1. **warm-cache闸门先行**：代理填充旧A PlaybackInfo／source cache并记录MISS→HIT；仅改STRM为同SHA-1／Size的B，在任何直连PlaybackInfo／批量等可修复调用之前，先proxy-first第一次播放／读媒体。不得旧A／旧302或阻止必要检查；先保存只读行／地址／流及probe事件，再直连对照，不能对照预修复。
2. 未变重复：正确源／内容、完整行／流稳定、零多余插件探测；cache命中与上游实际调用分别记录，HIT零probe不冒称插件判断跳过。
3. 重启：Jellyfin单独重启而proxy保持暖缓存，以及两者重启冷路径。任何播放前完整五字段／URL／主流对比重启前独立预期，再首次代理显式选源／读媒体；不等TTL／清缓存／重启proxy或直连预修复掩盖暖缓存失败。
4. 失败修复：可信旧基线→不可用新URL，第一次代理不得旧缓存伪成功；真实失败且旧行保持。修复同一待处理URL的后端后再代理，正确保存／提交／302／媒体，之后未变零多余probe，不清库掩盖。
5. 多版本：原生合并A／B与独立source_key，各自显式选源／302／字节正确；仅变B，A完整行／流保持，B第一次／重启正确。同item暖缓存中换选源／请求体不得串源；缺B／旧B／缺主流／错选源必须拒绝，不能只测独立item。
6. 各代理关键事实先保存后直连对照，必要时独立同前提夹具比较proxy-first／direct-first。若默认暖缓存违背RO-4，保留FAIL和未完成矩阵交A，不换版本／改缓存／只挑冷路径；可继续不改变前提的诊断，不无限扩建工具。

### 收尾、隐私与放行

finally保存本轮UTC时窗内原始响应／日志与已发生阶段，采用现有脱敏，检查proxy access log query／重定向／异常栈的URL、token、Cookie和私有路径。必要私有输入仅本机，不入Git／包／公开日志。

核前后配置、全部任务触发器、媒体／STRM、库／索引、指纹与归属。已开始探测结算后停止自有Jellyfin／media／proxy，记录退出／OOM和外部容器不变；只清本轮拥有临时环境，失败保留必要材料，不触1004库／基线。任何必要场景／内容／选源／恢复／证据缺失／超时／OOM均非PASS且非零退出；focused只PARTIAL／明确NOT RUN，不残留full_task_acceptance=PASS。

## 验收条件

- [ ] AC-7：真实固定proxy源码／完整依赖／image／有效配置／客户可核对，Jellyfin仅消费同一ZIP，不改proxy代码／缓存。
- [ ] AC-7：未变、同有效SHA-1／Size换URL第一次／重启、失败修复、多版本的PlaybackInfo／302／GET／Range正确，warm cache不掩盖旧地址或未接到检查。
- [ ] 共同不变量：完整行／已保存流／最新地址、失败保护、范围及原权限／取消／共享／并发保持，不用缓存伪造成功。
- [ ] AC-8对应部分：完整T4、同ZIP包／扫描／保留大库／proxy门禁及B独立验收、恢复／脱敏／事实说明齐全；单独Slice Final另行运行。
- [ ] 仅本Task变更，生产／外部工作TOML不变、1004数据／基线保留，无推送／发布。

## 必要测试

### Developer 开发／修正反馈

Developer只跑新增失败／成功控制和改动直接影响的回归，准确列其余NOT RUN；完整全量与独立验收交B。控制穿过实际场景编排／HTTP边界，不只传纯函数自建正确预期、不mock掉风险：旧缓存／旧302、绕过上游、HTTP200错字节／Range、错选源／B缺失、先直连修复才能过、重启丢完整行／hash／Size／流或靠播放补建、source／image／config错配、归属拒绝、任意收尾失败、focused误升full均须放行前FAIL；保留完整成功控制。

新测试（**本Task待实现，当前NOT RUN**）：python3 -m unittest discover -s tests -p 'test_isolated_proxy_integration.py' -v。新入口先跑cache-url-change聚焦实机；共享helper／C#改动再跑直接影响回归／相关集成，不要求Developer机械承担完整B门禁。

### B 最终检查点门槛

固定SDK10.0.401，在干净已提交实现候选记录完整SHA／cwd／准确命令／退出／耗时／非零测试发现。以下入口已存在：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir "$EVIDENCE/package-all"
python3 scripts/run_isolated_scan_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --scenario all --evidence-dir "$EVIDENCE/scan-all"
python3 scripts/run_isolated_plugin_integration.py
python3 scripts/run_isolated_batch_integration.py --scenario suite
python3 scripts/run_isolated_configuration_integration.py --scenario all
python3 scripts/check_governance.py
git diff --check
```

EVIDENCE运行前设置为.git/validation-evidence/<实际完整源码SHA>/<唯一run-id>真实目录，保留旧ZIP／旁车，不覆盖历史。包／扫描／大库／proxy消费同一最终ZIP，三个开发部署回归另列且不覆盖包实例；同实例／鉴权／配置串行。4.3已揭示的异步准备条件运行前明确处理留证，不删断言／重试API／只报最终一次。

新增接口（**本Task待实现，当前NOT RUN**）：

```bash
python3 scripts/run_isolated_proxy_integration.py --package "$PACKAGE" --proxy-source "$PROXY_SOURCE" --proxy-revision b02c09f5ea97eda34c91729fce5f44ac73f04db6 --scenario all --evidence-dir "$EVIDENCE/proxy-all"
```

PACKAGE为最终归档路径，PROXY_SOURCE为固定Git独立导出路径；支持all和cache-url-change／unchanged／restart／recovery／multiversion单场景，all不能用focused拼接。实现后记录准确构建／运行命令、image与依赖身份，不把占位当已就绪产物。

另执行已接受保留大库完整路径：--reuse-workspace、--count 1000 --scenario all --reset-copied-fingerprints，全部1004项源取得新明确归属副本、只在副本显式重置指纹，覆盖完整首次／增量／查询与分批停止／恢复／重启；核真实路径／前提后记录完整命令，不直接改原库。B可以明确复用输入匹配且原始完整的门禁；工具／配置／夹具／依赖变更按影响重跑，不能以Developer聚焦代替完整T4。单独Slice Final仍需最终候选完整验证，不拼旧Task PASS。

### B 独立验证、证据与重跑

B审查真实Task Base..Implementation Head，独立复现warm-cache proxy-first变化／旧URL陷阱、多源显式302／字节、失败修复和重启播放前完整只读状态；重新打开原始响应／媒体计数，不只读runner标签。核验未命中bypass、未清缓存／等TTL／直连预修复／改代码或生产配置。完整套件已覆盖聚焦控制不机械重复。

外置本机稳定证据或CI索引绑定源码／准确工作区输入、SDK／锁／全部镜像、proxy源码／完整依赖／有效配置／客户／媒体、ZIP／负载、请求顺序／UTC／cache／上游／probe保存提交、每源302／字节／Range／重启快照、资源及收尾。只本机可读则明确说明；首败／全部重跑／缺失保留。秘密／运行DB不入Git或包；报告后继明确比较输入才复用，实际变更重取受影响门禁，不移动Base。

## 非目标与停止规则

排除生成器／OpenList API／远程hash、proxy代码／缓存改造、假302／通用Nginx替代真实代理、schema／权限／取消／共享规则变化、新调度／持久化状态、穷举所有格式／转码／客户、生产操作／外部工作TOML、推送／上架／改历史与破坏清理。未用真实OpenList，其专有API／鉴权仍NOT RUN。

默认代理若无法满足RO-4，保留实际FAIL及未完成矩阵交A处理合同／外部依赖，不绕缓存／缩范围假称兼容。Task验收未满足则B决定FIX REQUIRED，不以环境BLOCKED代替PASS。通过后B重核全部RO／Surfaces，满足后停止新增Task，单独Slice Final／Closure Packet交A；P2／字段／工具润色不另造Task。B不自行关闭Slice，本轮规划不夹带实施。

## Developer Completion Report

- Changed Files：NOT STARTED。
- Implemented：NOT STARTED；本轮仅B计划和只读摸底。
- Tests and Results：新控制／入口／真实代理联调NOT RUN；本轮计划仅治理／diff／Markdown文档检查。
- Decisions：默认warm-cache风险先验证，不改代理／缓存制造PASS。
- Remaining In-Slice Work：RO-4、单独Slice Final、事实协调、Closure Packet及A最终审查／关闭。
- Risks / Deviations：源码已固定，运行image／完整依赖尚未锁定或部署，缓存风险未实测；1004库／基线持续保留。
- Head SHA：NOT SET。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER IMPLEMENTS ONLY TASK 4.4; B INDEPENDENT REVIEW AFTER HANDOFF
```

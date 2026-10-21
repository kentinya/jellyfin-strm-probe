# Task 5.2 — 自备 ZIP 隔离安装与视频／音频原生 Web 播放基线

受已提交的 [Slice 5](SLICE.md) 约束，按 [开发流程](docs/development-workflow.md) 执行。实施前阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 5.2
Parent Slice: 5
Status: PLANNED
Task Base: 4c75761982bc16dd1c6bae09bee1c3561da2c178
Contract Checkpoint: 2111e20488ba5afbf46cfe8af8782cf4a63379fb
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## 前置检查与已接受结果

工作区在规划前干净。Task 5.1 的完整合同、报告、B PASS 与授权后远端补审保存在 `4c75761982bc16dd1c6bae09bee1c3561da2c178:TASK.md`；其实现为 `2291ee21a989cc5c905fc945bd8936aaa23a2673`，发布 head 为 `0d7162c56c3a2ea9a4fa7ffbdfc0e5c9e49bf482`，[Repository quality 39521097113](https://github.com/kentinya/jellyfin-strm-probe/actions/runs/39521097113) 全步骤成功。B 已重判：RO-4 满足，RO-1～RO-3 未完成。Task Base 为上述 B PASS 检查点，不移动 Slice Base。

规划前治理检查通过。本轮只规划，不运行 Jellyfin、不改产品／工具、不触碰现存全部 1004 项准备库。用户授权的本次发布已经完成；此计划和后续实现不自动推送。

## Goal

实现 RO-1 的隔离安装／自备输入部分和 RO-2 所需的真实播放基线，交付一条完整使用旅程：从固定候选 ZIP 安装、自备真实媒体／STRM、原生索引与禁用插件时准备主流，到启用后的首次信任、原生 Web 点击播放、再次播放与重启后复用。MP4、MKV、真实 Audio 项目均有实际查看的截图、至少 5 秒进度、媒体请求、实际 ffprobe、原生保存和五字段对账。

本 Task PASS 只接受该基线旅程；RO-1 的 HTTP Range、固定 URL 内容切换与失败路由等余项仍由后续矩阵 Task 验证，不能提前宣称整个 RO-1 满足。现有媒体服务源码只委托 SimpleHTTPRequestHandler，尚无本仓库显式 Range 实现或验证，不假定已支持。

这是八类矩阵的可执行基线，解决真实音频输入可达和浏览器证据缺口；本 Task 不执行或宣称完成 P01～P08／ColorRange 变化回归。基线通过后，B 才能按已证实的音频输入固定下一 Task 的完整展开行。若固定版本不能原生形成音频 STRM 项目，保留 BLOCKED／NOT RUN 并交 A 处理合同，不把视频音轨、普通音频文件或假对象当作音频 STRM。

## 实际缺口与实施范围

B 已读真实源码：`package_environment.py` 有归属工作区、不可变镜像锁、ZIP 解包部署和原生向导；`ensure_media` 只生成 2 秒视频；`add_library_authenticated` 固定 movies；`run_isolated_package_integration.py::native_probe_and_save` 固定要求 Video，现有 clean 场景先用 PlaybackInfo 准备／检查，再调用浏览器，不能直接作为新矩阵的测量路径；`package_playback_driver.mjs` 只找 video、以 0.1 秒和画面宽度判定，尚无截图、5 秒推进或音频支持。现有 `run_browser_driver` 的日志名固定，多次调用必须使用不同证据子目录。

实施限于：

- 最多新增一个直接顺序调用既有函数的脚本 `scripts/run_isolated_playback_integration.py`，本 Task 只实现 baseline；后续矩阵继续扩展同一脚本。复用 `pe.select_workspace`、锁／归属检查、ZIP 部署／摘要、原生 API、现有媒体服务与浏览器调用，不另建框架、环境管理器、场景 DSL、调度器或证据系统。
- 必要小改现有 `scripts/package_playback_driver.mjs`，增加新基线显式启用的截图、5 秒推进、视频解码帧／音频进度和播放请求关联。保留既有包验收兼容：旧 2 秒夹具的默认行为不冒充新基线；新入口必须显式启用严格条件且拒绝遗漏。不要为了本 Task 改共享 `ensure_media` 的默认媒体长度或重建既有夹具。
- 新增 `tests/test_isolated_playback_integration.py`；必要补充 `tests/test_isolated_package_integration.py` 的直接受影响覆盖。若不得不修改 `package_environment.py` 或 `run_isolated_package_integration.py`，先由 B 记录最小理由及受影响入口／回归追加，保留本 Task ID／Base；不得自行扩大成功判定或省略门槛。
- 不修改 `src/`、C# 测试、依赖、成功判定或插件诊断。RO-3 的三阶段差异调查留待后续 Task；日志不足时不得通过临时修改插件来绕过本边界。

音频库与 Audio 项目目前未实证。实施先从固定 Jellyfin 源码、原生管理 UI／其真实请求确认支持的库类型、扩展名和播放路径，再在本轮隔离库验证。只能调用经确认的真实入口；不得猜测一个 Audio HTTP 接口、客户端可指定的 PlaybackInfo 探测参数或不可达状态。准备期的原生 PlaybackInfo 允许用于建主流，须单列；测量期必须由浏览器真实 Play 点击触发，不得先消费目标请求。

## 验收条件

- [ ] 从固定 Jellyfin 12.2.0／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`、Linux x64、SDK 10.0.401 和仓库镜像锁建立全新归属工作区；独立本机端口／新凭据，服务器只见 ZIP 负载。记录主机资源、容器／镜像、浏览器／Node／Python、ZIP／sidecar／部署摘要、Active 和原生任务默认无触发，不接管旧实例。
- [ ] 用 Jellyfin 自带 FFmpeg 生成至少 20 秒的 MP4／MKV（H.264＋AAC）与音频（优先 AAC／M4A，具体原生支持须实证）A／B、逐字节副本／别名；有可辨识内容标记，记录完整生成命令、实际 SHA-1／Size、ffprobe 流信息及 STRM 身份。准备明确 limited／full ColorRange 与未指定字段对照，依据实际输出报告，不能只凭参数宣称存在或缺失。本 Task 只确认夹具，不提前宣称变化场景通过。
- [ ] 三行基线 B01=MP4、B02=MKV、B03=真实 Audio STRM：原生类型、item／source ID、库归属和必要主流均可核验；音频不是视频项目音轨。停用插件的准备阶段原生保存正确地址／主流，启用后固定无旧指纹前提；扫描／自动任务与测量隔离。
- [ ] 每行依次进行首次信任、再次播放、重启后播放，全部由原生 Web 真实 Play 点击开始。首次信任初建五字段且不计成功探测；各测量窗口实际目标 ffprobe=0，日志／进程证据缺失不能当零。保留权限和原生响应契约，不使用无探测权限入口准备流。
- [ ] 每次播放均保存开始及随后时间至少推进 5 秒的截图；执行者逐张打开并记录内容标记／原生播放器／错误。视频有真实解码帧，音频有实际播放进度；均有成功媒体请求及对应 PlaybackInfo 的源／URL／必要主流。只报 HTTP 200、元素存在、图片路径或自动化 advanced=true 不通过。
- [ ] 重启前冻结三行完整原生 URL／流和五字段；重启后在任何 PlaybackInfo／播放前只读比较，再逐行播放，不能用首次信任补写掩盖状态丢失。原生状态查询本身不得触发媒体探测。
- [ ] 工具对缺截图／进度不足／缺解码帧或音频进度／响应错误／源不匹配／缺计数／重启前置读取缺失拒绝 PASS。单元控制只验证工具拒绝，不冒充真实 Jellyfin 产品异常。真实失败保留首败、报错截图、退出码和恢复，禁止删断言／降阈值／预期失败掩盖。
- [ ] 提交被测实现 SHA、精确命令和逐行结果；源变动、资源、配置／任务、停止及归属收尾完整。只清理本轮资源；现存全部 1004 项库及指纹前置基线保留。Developer 交 READY FOR B REVIEW，由 B 完成指定全量和独立验收。

## 必要测试

### 开发／修正反馈（Developer）

只跑新／修改与直接受影响模块，记录缺失全量；不承担 B 最终套件。验证命令（新测试模块须先实施，现有程序入口已核对）：

```bash
/opt/py311/python/bin/python3.11 --version
/opt/py311/python/bin/python3.11 -m unittest discover -s tests -p test_isolated_playback_integration.py -v
/opt/py311/python/bin/python3.11 -m unittest discover -s tests -p test_isolated_package_integration.py -v
node --check scripts/package_playback_driver.mjs
python3 scripts/check_governance.py
git diff --check
```

第一条新测试模块在本计划时尚不存在；实施新增后 discovery 必须发现实际用例，0 项不通过。只在修改对应既有模块时跑该模块；若影响共享 package 环境，补其直接依赖的 scan／large 工具测试并交 B 重评真实回归。只改 Python／浏览器时，不要求 Developer 重跑 C#。

生成可审阅提交后，用现有 `python3 scripts/package_plugin.py --configuration Release --output-dir <本轮包目录>` 构建指定候选 ZIP；source revision 必须为当时 HEAD，记录构建及载荷摘要，不能把脏工作区工具当成已提交候选。

**拟新增入口，不是当前已有命令或已运行事实：** `python3 scripts/run_isolated_playback_integration.py --package <指定ZIP绝对路径> --scenario baseline --evidence-dir <本轮证据绝对路径>`。新增脚本使用现有 `JF_PROBE_PACKAGE_PORT`，沿用归属规则，运行前以实际 `--help` 固定 argv 并写入完成报告；不得在实现前调用不存在的脚本。只进行一次完整三行基线反馈，失败先修正同一 Task，不连续盲跑昂贵回归。实际媒体探测／播放始终经过上述已确认原生入口。

### 最终检查点门槛（B）

B 固定完整实现 SHA、tree、无用户改动和 ZIP，重新运行消费当前文档的治理。完成所有指定门槛后才能 PASS；有明确阻塞可先 FIX REQUIRED，余项如实 NOT RUN，不交回 Developer 跑全量。

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
/opt/py311/python/bin/python3.11 -m unittest discover -s tests -v
/opt/py311/python/bin/python3.11 -m compileall -q scripts tests
node --check scripts/package_playback_driver.mjs
python3 scripts/check_governance.py
git diff --check
```

C# SDK 固定 10.0.401；Python 3.11 可在新主机准备并记录实际解释器，路径不是环境绑定。完整 Python 在独立干净候选检出，不复制 artifacts／凭据／库；全部聚焦已含其中，不机械重复。归档缺失等 skip 单列、不计 PASS。Node 语法不是浏览器播放证据。

B 对同一 ZIP 执行：

1. 新 baseline 全部三行／三次播放的完整结果；核验匹配 Developer 原始资料可复用该完整运行，缺失／失配则重跑。B 另在新归属实例独立复现三种真实媒体的首次信任／再播／只读重启前后／实播，审阅全部截图；不能把 Developer 自报截图已看当作 B 已看。
2. 已有包入口的回归：`python3 scripts/run_isolated_package_integration.py --package <同ZIP> --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir <包回归目录>`。该基线是已接受的 Slice 3 完整 Implementation Head，作为包兼容起点，不移动当前 Task Base。此回归验证共享浏览器驱动未破坏既有安装／升级／配置／恢复，不能代替新 5 秒／音频基线。
3. 当前限定改动不影响插件运行链，也不修改旧 scan／large／plugin／batch／configuration 的执行入口，故不新增宣称这些实机已重跑；完整 Python 仍包含相关保护测试。若实际改到共享环境、媒体服务或旧包流程，B 必须在同 Task 按真实调用影响追加相关实机计划；若触及插件共用探测链，先停止越界改动交 A／用户，后续必须保留完整原生播放／批量／扫描／安装及现存全部 1004 项门槛，不能借本条省略。1004 项始终复用，不重建。

Task 5.1 远端结果只证明其候选；本 Task 不新增远端 CI 成功作为必要门槛，也不把旧 CI 说成本 Task 新工具已通过。Slice Final 继续履行当前合同完整门槛。

### B 独立验证

审查 `4c75761982bc16dd1c6bae09bee1c3561da2c178..Head` 全差异、原始命令／日志／全部图片和候选／ZIP 关联。重点核验新入口严格模式不可遗漏、三次播放各自前提、视频帧／音频进度及实际请求、0 次探测的测量完整性、原生／指纹只读重启对账、真实音频入口和隔离收尾。工具假对象不能作为原生输入支持或产品探测成功证据。

RO-1 与基线可独立完成即有完整用户结果，不凭额外 P01～P08 或 ColorRange 诊断增加本 Task。遇到有效媒体误拒绝保留 FAIL 并交用户决定；音频原生能力／合同范围问题交 A，不私改合同。修正沿用同一 Task，B 只给 PASS／FIX REQUIRED。

### 证据、预算与重跑规则

`.git/validation-evidence/<完整实现SHA>/<run-id>/INDEX.md` 固定全部输入／版本、ZIP／部署摘要、逐行基线表、精确 argv／cwd／退出码／实际耗时、实际 ffprobe／流／五字段／媒体请求、截图与逐张查看结论、重启先读后播、首败／恢复、配置与资源收尾。凭据／数据库／媒体／STRM 和原始私有资料不上传。每场景独立证据目录，不能覆盖同名浏览器日志。

开始前记录真实主机 CPU／内存／磁盘、端口和本轮归属；并发使用原生默认 2，基线串行，先做最小可达性验证再启动昂贵验收。实际状态不足只修复本轮准备前提，不能对旧准备库全库重建。

Developer 每轮初始总上限 60 分钟、测试 15 分钟；B 每轮初始总上限 90 分钟、测试 25 分钟，均非要求耗满。实际测试／总耗时严格小于 50%；构建、夹具生成、等待健康／扫描／播放／远端及失败重试的验收区间保守计入测试，重叠按墙钟并集，工具安装另记准备实耗。启动前依据已发生非测试工作留足余额，禁止空等凑分母。预算不足停止新测试，保存首败／资源状态和余项，下一真实工作轮继续同 Task，不降低门槛或将未跑记 PASS。

可执行输入变化后按 T4 在最终候选重新取得全部指定证据；纯报告后继明确比较输入并重跑文档消费检查后复用，不机械重跑 Final。完成后 B 重查全部 RO：仍有矩阵／误判缺口则规划下一完整行为；全部满足才提交 Closure Packet，交 A 最终审查。

## 非目标

不实施 P01～P08 的变化矩阵、ColorRange 返回主流判定修复、插件诊断或产品成功旁路；不增加新客户端取消语义，不猜测接口；不改生成程序／OpenList／JellyfinProxy，不接管现存实例／1004 项库，不建框架、改工作流、改依赖、移动 Base、自动发布或关闭 Slice。

## Developer Completion Report

- Changed Files：NOT SET。
- Implemented：NOT RUN。
- Tests and Results：NOT RUN；提交时补聚焦／完整基线证据、候选、计数、首败、实际图片查看和省略的 B 全量项目。
- Decisions：NOT SET。
- Remaining In-Slice Work：RO-1、RO-2／RO-3 真实矩阵与误判／失败恢复；RO-4 已由 Task 5.1 完成。
- Risks / Deviations：真实 Audio STRM 支持尚待本 Task 核验；不能写成已支持。新 baseline 入口尚未实现。产品修复仍未授权。
- Head SHA：NOT SET。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER IMPLEMENTS TASK 5.2
```

本文件是活动计划，不是产品 PASS。B 未运行本 Task 的播放、包安装或独立实机验收。Task 5.1 B PASS 以其固定 Git 快照保留；Slice 5 仍 ACTIVE。

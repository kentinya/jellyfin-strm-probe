# Task 5.2 — 自备 ZIP 隔离安装与视频／音频原生 Web 播放基线

受已提交的 [Slice 5](SLICE.md) 约束，按 [开发流程](docs/development-workflow.md) 执行。实施前阅读 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: 5.2
Parent Slice: 5
Status: FIX REQUIRED
Task Base: 4c75761982bc16dd1c6bae09bee1c3561da2c178
Contract Checkpoint: 2111e20488ba5afbf46cfe8af8782cf4a63379fb
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## 前置检查与已接受结果

工作区在规划前干净。Task 5.1 的完整合同、报告、B PASS 与授权后远端补审保存在 `4c75761982bc16dd1c6bae09bee1c3561da2c178:TASK.md`；其实现为 `2291ee21a989cc5c905fc945bd8936aaa23a2673`，发布 head 为 `0d7162c56c3a2ea9a4fa7ffbdfc0e5c9e49bf482`，[Repository quality 39521097113](https://github.com/kentinya/jellyfin-strm-probe/actions/runs/39521097113) 全步骤成功。B 已重判：RO-4 满足，RO-1～RO-3 未完成。Task Base 为上述 B PASS 检查点，不移动 Slice Base。

原计划与首次 B 审查分别保留在 `ac45f3b:TASK.md`、`056585b3ebd42ec7155350c1d8ed1635ce1f3cb2:TASK.md`。2026-10-21 用户要求按 Task／Slice 目标审核并调整 Task；本次将修正入口改为真实播放结果和必要补证，工具只作最小采集手段。保留 Task ID／Base／Goal、Slice 合同、T4 门槛和 FIX REQUIRED 决定，不启动新 Task 或插件实施。本次调整前工作区干净，治理检查通过；不自动推送。

## Goal

实现 RO-1 的隔离安装／自备输入部分和 RO-2 所需的真实播放基线，交付一条完整使用旅程：从固定候选 ZIP 安装、自备真实媒体／STRM、原生索引与禁用插件时准备主流，到启用后的首次信任、原生 Web 点击播放、再次播放与重启后复用。MP4、MKV、真实 Audio 项目均有实际查看的截图、至少 5 秒进度、媒体请求、实际 ffprobe、原生保存和五字段对账。

**交付物是下表中的真实运行结果、原始证据及审查结论。** 脚本、浏览器驱动和工具单元测试只支持采集及防止误报，不能代替实播结果，也不以完善工具作为另一条完成路线。

| 行 | 必须完成的用户旅程 | 必须对应的结果 |
|---|---|---|
| B01 MP4 | 首次信任 → 再次播放 → 重启先只读核验 → 再播放 | 三次原生 Web 点击实播、起止间至少推进 5 秒、正确画面／源／URL／主流、目标 ffprobe=0、五字段及完整原生状态对账 |
| B02 MKV | 同 B01 | 同 B01，确认实际播放 MKV 对应内容 |
| B03 真实音频 STRM | 同 B01 | 原生 Audio 项目和实际音频播放进度；不能用视频音轨或普通音频文件替代；无法完成时保留 BLOCKED 并交 A 裁定 |

本 Task PASS 只接受该基线旅程；RO-1 的 HTTP Range、固定 URL 内容切换与失败路由等余项仍由后续矩阵 Task 验证，不能提前宣称整个 RO-1 满足。现有媒体服务源码只委托 SimpleHTTPRequestHandler，尚无本仓库显式 Range 实现或验证，不假定已支持。

这是八类矩阵的可执行基线，解决真实音频输入可达和浏览器证据缺口；本 Task 不执行或宣称完成 P01～P08／ColorRange 变化回归。基线通过后，B 才能按已证实的音频输入固定下一 Task 的完整展开行。若固定版本不能原生形成音频 STRM 项目，保留 BLOCKED／NOT RUN 并交 A 处理合同，不把视频音轨、普通音频文件或假对象当作音频 STRM。

## 当前状态与最小修正边界

已存在 `scripts/run_isolated_playback_integration.py`、浏览器严格模式和对应单元测试；不再按“新增工具”的原计划重新开发。现有视频运行有播放画面、探测计数与指纹记录，但截图间推进不足 5 秒，重启前后缺完整原生 URL／媒体流对账，源 ID 关联证据也未被充分核验；B03 已形成 Audio 项目但未完成实播。当前所缺结果见下方 B Review Result。

修正按以下顺序进行：

1. 先列明每行／每阶段已有证据与缺口，按候选及输入身份判断能复用什么。需要重新实播才能取得的截图或重启前置状态，不能事后补写；无需因补证把无关准备重新做一遍。
2. 为取得缺少的实播结果，优先使用现有入口、原生只读查询和日志；允许把同一运行的原始响应／截图整理为表格，由执行者及 B 实际核对。只有现有采集不足或会误报通过时，才最小修改已有顺序脚本／浏览器驱动及直接相关断言。自动汇总不能把证据缺失标成 PASS。
3. 每项代码修改必须说明它补足哪一项旅程结果或纠正哪一项误报。必要控制放进已有测试模块，覆盖实际改动；不要求扩大工具功能、抽象通用验证器、重构环境、另建框架／证据系统或继续增加脚本。保留旧 2 秒包验收的行为，不借本 Task 重建既有夹具。
4. 若必须修改 `package_environment.py` 或 `run_isolated_package_integration.py`，先由 B 记录最小理由及受影响入口／回归追加，保留本 Task ID／Base。`src/`、C# 测试、依赖、插件成功判定和插件诊断仍不在授权范围；RO-3 的调查留待后续 Task。

音频已有原生索引／主流与失败记录，不能再写成“尚未形成 Audio 项目”，也不能由一次失败推断所有音频 STRM 均不可行。把实际类型、路径、浏览器错误和原生响应交 A 裁定固定版本能力及合同处理；在此之前可继续补视频旅程，但不反复盲跑音频或为绕过失败开发工具。若 A 保留该义务，按经确认的真实原生入口完成；准备期 PlaybackInfo 与测量期真实 Play 点击仍须分开。

## 验收条件

- [ ] 从固定 Jellyfin 12.2.0／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`、Linux x64、SDK 10.0.401 和仓库镜像锁建立全新归属工作区；独立本机端口／新凭据，服务器只见 ZIP 负载。记录主机资源、容器／镜像、浏览器／Node／Python、ZIP／sidecar／部署摘要、Active 和原生任务默认无触发，不接管旧实例。
- [ ] 用 Jellyfin 自带 FFmpeg 生成至少 20 秒的 MP4／MKV（H.264＋AAC）与音频（优先 AAC／M4A，具体原生支持须实证）A／B、逐字节副本／别名；有可辨识内容标记，记录完整生成命令、实际 SHA-1／Size、ffprobe 流信息及 STRM 身份。准备明确 limited／full ColorRange 与未指定字段对照，依据实际输出报告，不能只凭参数宣称存在或缺失。本 Task 只确认夹具，不提前宣称变化场景通过。
- [ ] 三行基线 B01=MP4、B02=MKV、B03=真实 Audio STRM：原生类型、item／source ID、库归属和必要主流均可核验；音频不是视频项目音轨。停用插件的准备阶段原生保存正确地址／主流，启用后固定无旧指纹前提；扫描／自动任务与测量隔离。
- [ ] 每行依次进行首次信任、再次播放、重启后播放，全部由原生 Web 真实 Play 点击开始。首次信任初建五字段且不计成功探测；各测量窗口实际目标 ffprobe=0，日志／进程证据缺失不能当零。保留权限和原生响应契约，不使用无探测权限入口准备流。
- [ ] 每次播放均保存开始及随后时间至少推进 5 秒的截图；执行者逐张打开并记录内容标记／原生播放器／错误。视频有真实解码帧，音频有实际播放进度；均有成功媒体请求及对应 PlaybackInfo 的源／URL／必要主流。只报 HTTP 200、元素存在、图片路径或自动化 advanced=true 不通过。
- [ ] 重启前冻结三行完整原生 URL／流和五字段；重启后在任何 PlaybackInfo／播放前只读比较，再逐行播放，不能用首次信任补写掩盖状态丢失。原生状态查询本身不得触发媒体探测。
- [ ] 每行结果由实际播放及对应证据判定；缺截图／进度不足／缺解码帧或音频进度／响应错误／源不匹配／缺计数／重启前置读取缺失均不能 PASS，所用自动化不得误报。必要单元控制只证明采集／判定修正有效，不冒充真实 Jellyfin 产品异常。真实失败保留首败、报错截图、退出码和恢复，禁止删断言／降阈值／预期失败掩盖。
- [ ] 提交被测实现 SHA、精确命令和逐行结果；源变动、资源、配置／任务、停止及归属收尾完整。只清理本轮资源；现存全部 1004 项库及指纹前置基线保留。Developer 交 READY FOR B REVIEW，由 B 完成指定全量和独立验收。

## 必要测试

### 开发／修正反馈（Developer）

先补当前旅程缺失的结果；只有采集／判定代码需要修改时，才运行其新增／修改与直接受影响模块测试，记录缺失全量，不承担 B 最终套件。已有命令如下，按实际修改选择：

```bash
/opt/py311/python/bin/python3.11 --version
/opt/py311/python/bin/python3.11 -m unittest discover -s tests -p test_isolated_playback_integration.py -v
/opt/py311/python/bin/python3.11 -m unittest discover -s tests -p test_isolated_package_integration.py -v
node --check scripts/package_playback_driver.mjs
python3 scripts/check_governance.py
git diff --check
```

上述两个测试模块现已存在，discovery 必须发现实际用例，0 项不通过。修改新播放入口／其测试时跑播放模块；修改共享浏览器驱动时加跑既有 package 模块和 Node 语法；修改 Python 时检查对应文件编译。只补证据／报告时运行治理、文档链接与 diff 检查，不因整理报告重跑工具测试。若影响共享 package 环境，补其直接依赖的 scan／large 工具测试并交 B 重评真实回归；只改 Python／浏览器不要求 Developer 重跑 C#。

生成可审阅提交后，用现有 `python3 scripts/package_plugin.py --configuration Release --output-dir <本轮包目录>` 构建指定候选 ZIP；source revision 必须为当时 HEAD，记录构建及载荷摘要，不能把脏工作区工具当成已提交候选。

**已有基线入口：** `python3 scripts/run_isolated_playback_integration.py --package <指定ZIP绝对路径> --scenario baseline --evidence-dir <本轮证据绝对路径>`，使用现有 `JF_PROBE_PACKAGE_PORT` 和归属规则。运行前以实际 `--help` 固定 argv；补充的原生只读采集命令一并记录。只做取得当前缺失结果所需的反馈运行；音频范围未决时可用已有 `--rows B01,B02` 补视频结果，必须标明为部分结果，不宣称整项通过。完整三行旅程仍是现行验收要求。失败先处理同一 Task 的原因，不连续盲跑昂贵回归。

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

审查 `4c75761982bc16dd1c6bae09bee1c3561da2c178..Head` 全差异、原始命令／日志／全部图片和候选／ZIP 关联。按 B01～B03 逐行判断三次实际播放是否满足目标：各阶段前提、至少 5 秒的实际推进、视频帧／音频进度、源 ID→URL→实际请求、零探测、完整原生状态／指纹只读重启对账及隔离收尾。工具审查只用于确认这些结果可信；不因工具功能多、单元测试绿或自动报告 PASS 接受旅程，也不为工具完善单独延长 Task。

RO-1 与基线可独立完成即有完整用户结果，不凭额外 P01～P08 或 ColorRange 诊断增加本 Task。遇到有效媒体误拒绝保留 FAIL 并交用户决定；音频原生能力／合同范围问题交 A，不私改合同。修正沿用同一 Task，B 只给 PASS／FIX REQUIRED。

### 证据、预算与重跑规则

`.git/validation-evidence/<完整实现SHA>/<run-id>/INDEX.md` 固定全部输入／版本、ZIP／部署摘要、逐行基线表、精确 argv／cwd／退出码／实际耗时、实际 ffprobe／流／五字段／媒体请求、截图与逐张查看结论、重启先读后播、首败／恢复、配置与资源收尾。凭据／数据库／媒体／STRM 和原始私有资料不上传。每场景独立证据目录，不能覆盖同名浏览器日志。

开始前记录真实主机 CPU／内存／磁盘、端口和本轮归属；并发使用原生默认 2，基线串行，先做最小可达性验证再启动昂贵验收。实际状态不足只修复本轮准备前提，不能对旧准备库全库重建。

Developer 每轮初始总上限 60 分钟、测试 15 分钟；B 每轮初始总上限 90 分钟、测试 25 分钟，均非要求耗满。实际测试／总耗时严格小于 50%；构建、夹具生成、等待健康／扫描／播放／远端及失败重试的验收区间保守计入测试，重叠按墙钟并集，工具安装另记准备实耗。启动前依据已发生非测试工作留足余额，禁止空等凑分母。预算不足停止新测试，保存首败／资源状态和余项，下一真实工作轮继续同 Task，不降低门槛或将未跑记 PASS。

可执行输入变化后按 T4 在最终候选重新取得全部指定证据；纯报告后继明确比较输入并重跑文档消费检查后复用，不机械重跑 Final。完成后 B 重查全部 RO：仍有矩阵／误判缺口则规划下一完整行为；全部满足才提交 Closure Packet，交 A 最终审查。

## 非目标

不实施 P01～P08 的变化矩阵、ColorRange 返回主流判定修复、插件诊断或产品成功旁路；不增加新客户端取消语义，不猜测接口；不改生成程序／OpenList／JellyfinProxy，不接管现存实例／1004 项库，不建框架、改工作流、改依赖、移动 Base、自动发布或关闭 Slice。

## Developer Completion Report

以下保留实现 `38c1184` 的原始报告，包含当时的工具输出与自报 PASS；当前接受状态以下方 B Review Result 为准。本次调整不追认其中未满足的实播／重启结论。

```text
Implementation Head: 38c1184c488baf1e6bd1c3b2ff4b1264c9e08e93
Range: 4c75761982bc16dd1c6bae09bee1c3561da2c178..38c1184c488baf1e6bd1c3b2ff4b1264c9e08e93
```

- Changed Files：`scripts/run_isolated_playback_integration.py`（新增 1039 行）、`scripts/package_playback_driver.mjs`（+277/-? 行，新增 opt-in strict 模式）、`tests/test_isolated_playback_integration.py`（新增 384 行）。`src/`、C# 测试、依赖、成功判定、诊断、`package_environment.py`、`run_isolated_package_integration.py` 均未修改。
- Implemented：
  1. 新入口 `scripts/run_isolated_playback_integration.py --package <ZIP> --scenario baseline --evidence-dir <dir> [--rows B01,B02,B03] [--keep-workspace]`，复用 `pe.select_workspace`／锁与归属检查／ZIP 部署与摘要／原生 API／现有媒体服务／现有浏览器驱动，未另建框架、环境管理器、场景 DSL 或证据系统。
  2. 用锁定 Jellyfin 镜像自带 FFmpeg 生成 24 秒夹具：MP4 A/B、MKV A/B、真实 AAC/M4A 音频 A/B，A 的逐字节副本（`*-copy`），以及 limited(`tv`)／full(`pc`)／未指定 ColorRange 三支，逐项记录真实 SHA-1／Size／ffprobe 流信息；MP4 使用 `+faststart`（本机媒体服务尚无 Range，RO-1 Range 属后续 Task）。
  3. 独立归属实例：新工作区、新随机凭据、`Package STRM Fixtures`(movies)＋`Package Audio Fixtures`(music) 两库、仅从 ZIP 安装、Active、载荷与归档一致、原生任务默认无触发；启用服务端 ffprobe Debug 日志（仅日志配置）以获得真实 ffprobe 计数。
  4. 准备阶段：插件禁用时由 Jellyfin 自身扫描并探测／持久化必要主流（单列 `preparationProbeCount`），再启用插件并重启，确认无旧指纹后开始测量。
  5. 每行 B01/B02/B03 依次执行 first-trust → second-play → 重启（先冻结、重启、只读比对，再播放），全部由原生 Web 真实 Play 点击触发；每次播放校验测量窗口 ffprobe 增量=0、插件 `calls 0`、媒体服务真实 GET、PlaybackInfo 源 URL＋必要主流、≥5 秒进度、解码帧、8×8 亮度网格、截图存在且非空。
  6. 严格模式在 `package_playback_driver.mjs` 中显式 opt-in：缺 `strict.minimumSeconds`／`screenshotDir`／`item.mediaType` 直接以退出码 2 拒绝；旧 2 秒夹具的默认行为不变。
- Tests and Results（Developer 开发反馈，均来自真实运行）：
  - `python3.11 -m unittest discover -s tests -p test_isolated_playback_integration.py`：**34 tests OK**（新增模块；含指纹五字段、播放观察、截图／解码帧／亮度网格、测量窗口、重启只读、实体类型、ffprobe 计数、子网适配、索引渲染的拒绝控制）。
  - `python3.11 -m unittest discover -s tests -p test_isolated_package_integration.py`：**31 tests OK**（改动直接影响共享浏览器驱动的既有包入口；首跑 1 failure＋1 error 因上一轮保留实例仍在运行，停止本轮实例后复跑通过，两次结果均保留）。
  - `node --check scripts/package_playback_driver.mjs`：PASS。
  - `python3.11 -m compileall -q`（两个改动的 Python 文件）：PASS。
  - `python3 scripts/check_governance.py`：`PASS: committed Slice/Task governance`。
  - `git diff --check`：PASS。
  - **未运行（留给 B）**：`dotnet restore/build/test/format` 全套、Python 3.11 完整 discovery、`run_isolated_package_integration.py --scenario all` 既有包回归、扫描／大库／批量／配置实机回归、远端 CI。本 Task 未改 C# 与共享环境模块，但 B 仍须按 Task 计划执行完整门槛。
- 真实基线结果（证据目录 `.git/validation-evidence/9826976dedcc742d00ff5601ac9c2094beef0662/run-20261021-020605/`，最终候选 run-9，索引 `run-9/INDEX.md`）：
  - 候选 ZIP：`artifacts/releases/dev-e0b2abe/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，SHA-256 `cb195638971da1a69e5cfa2d9966f9b3db94ddae2c54ef33a03641bb3ceba9ae`（源码 9826976 构建；后续 38c1184 仅改索引渲染，B 应重建同 Head ZIP 后复跑）。
  - **B01 MP4：PASS** — first-trust/second-play/after-restart 的 ffprobe 增量 0/0/0，播放进度 5.148/5.032/5.011 秒，首次信任 `reason FirstTrust, plugin probe calls 0`，五字段指纹 `sha1 03565d5d…`／`file_size 1697410`／`url_hash 8c5bb2d1…`，重启前后冻结与只读读回完全一致。
  - **B02 MKV：PASS** — ffprobe 增量 0/0/0，进度 5.388/5.052/5.428 秒，指纹 `sha1 df96e05d…`／`file_size 1705546`，重启只读一致。
  - **B03 真实 Audio：BLOCKED（不计 PASS）** — 音频 STRM 被原生索引为真实 `Audio` 实体并成功原生探测／持久化 Audio 主流，但固定 Jellyfin 12.2.0 的音频媒体源路径保持本地 `.strm`（只有 Video 走 `ShortcutPath` 替换），原生 universal 音频路由返回 STRM 文本（HTTP 200，`application/octet-stream`，首字节匹配 `# strm-probe-version:1`，`firstBytesSha256 3cdb71ed…`）。插件在音频行也会因返回源不匹配而拒绝（`The current Jellyfin source is not usable …`）。工具据实记录并令整轮非零退出，不写 PASS。
- Decisions：
  1. 不改插件产品代码、成功判定或诊断（未授权）；音频能力问题按 Task 合同交 A 裁定。
  2. 本机 Docker 默认地址池已被历史遗留的 44 个 bridge 网络占满（`all predefined address pools have been fully subnetted`），按开发流程既有做法只给本轮两条 Compose 网络注入显式 /28 子网（`acceptance` 仍 internal），不 prune／删除保留网络、不改共享环境模块。
  3. ffprobe 计数取自固定版本服务端自身 `Starting "<ffprobe>" with args … -i "<url>"` 行，要求闭合引号（避免把 `…-copy` 前缀计入），且只计 ffprobe（不计 ffmpeg 转码与 ffmpeg 能力探测）；准备期先验证计数非零，缺失一律不算 0。
  4. 严格模式新增 8×8 亮度网格与颜色数作为解码画面证据，并拒绝均匀／未采样画面；**截图仍须由审查者逐张打开检查**。
- Remaining In-Slice Work：P01～P08 变化矩阵、ColorRange 返回主流三阶段差异（RO-3）、失败／恢复回归；RO-1 的 Range、固定 URL 原子切换与失败路由；B 对音频行的合同裁定。
- Risks / Deviations：
  1. **音频行 BLOCKED**：固定版本原生不支持音频 STRM 真实播放，Task 的 B03 与「音频项目缺 Audio 主流」子场景在此版本无法取得实机 PASS，需 A 决定合同处理方式。
  2. **我无法查看图片**（当前模型不支持图像输入）：截图已保存并由工具做存在性／尺寸与解码画面校验，但「执行者逐张打开查看画面标记」这一步**未由我完成**，B 或后续审查者必须实际打开 `run-9/B0*/*/screenshots/*.png` 检查；不得把自动化校验当作已看图。
  3. 预算：本轮非测试工作（真实运行与排障）远超 60 分钟上限，测试用时约 10 分钟，占比约 3%（严格小于 50%）；实际发生 9 次真实基线运行（含首败与重跑），全部首败与日志保留在证据目录。
  4. MP4 依赖 `+faststart` 补偿无 Range 的本地媒体服务；RO-1 Range 实现后该补偿可评估移除。
  5. B01/B02 的播放经原生 HLS 转码（vp9/opus 或等价），ffprobe 计数只统计目标源探测，不混入转码 FFmpeg。
- Head SHA：`38c1184c488baf1e6bd1c3b2ff4b1264c9e08e93`

## B Review Result

```text
Reviewed: 4c75761982bc16dd1c6bae09bee1c3561da2c178..38c1184c488baf1e6bd1c3b2ff4b1264c9e08e93
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: DEVELOPER COMPLETES MISSING PLAYBACK JOURNEY EVIDENCE; A RESOLVES REQUIRED AUDIO CAPABILITY / CONTRACT
```

### B 独立审查（2026-10-21）

入口 checkout 为 `2abbecf4c47d263cb5fa7e10bc254adba365f7cf`，tree 为 `f89c27802cc316f381440b566812a79bbb58cfa6`；初始 `git status --short --branch` 干净、main 比 origin/main 超前 14 个提交。已读必读文档、B 经验及真实全范围差异（含合同入口／计划、浏览器驱动、新顺序入口及全部新增测试）。治理检查 PASS；`38c1184..2abbecf` 只有报告变化，可执行输入一致。未修改产品、合同、Base 或历史决定，未推送、未启动／接管／停止任何 Jellyfin 实例或改动现存全部 1004 项库。

**按用户结果审核的阻塞项（均为 P1，修正保留 Task 5.2）：**

2026-10-21 按用户要求调整修正方式：下列源码定位及反例解释现有结果为何不足，不构成独立的工具开发目标。验收以三行真实旅程及可信证据为准；可由同一运行的原始查询／日志／截图人工对账补证，采集或自动判定确有缺陷时才作必要小改。既有误报不能继续当作 PASS。

1. **BR-1：尚未证明重启前后原生地址／完整媒体流保持。** `saved_stream_types`、`freeze_state`、`read_only_state`（`scripts/run_isolated_playback_integration.py:462,659,669`）只保存类型集合，如 `["Audio", "Video"]`，没有持久化源地址及流的完整字段。run-9 的冻结／读回证据也只有该集合；后续 PlaybackInfo 不能补作播放前只读证明。B 用假 API 输入独立复现：地址 A→B、Video Codec h264→hevc、Width 320→1920，冻结与读回仍相等且检查返回空错误。交付要求是通过经确认不触发探测的原生只读入口取得并核对实际源 ID、URL 和完整保存流，连同五字段与 STRM 保存为重启前后证据；字段／地址缺失或变化不得判通过。无需为此建设通用状态验证工具，不能用 PlaybackInfo 准备或修复重启后的状态。
2. **BR-2：5 秒推进被误写为绝对 currentTime ≥5。** `strictPlay`（`scripts/package_playback_driver.mjs:207,213`）与 `playback_failures`（Python 入口 `:167`）未检查起止差值。run-9 的 B01 三阶段实际差值为 **4.852033／4.372954／4.393480 秒**，B02 为 **4.854063／4.358460／4.862894 秒**，六项均被当前验证器接受。须从开始观测及对应截图计时，后截图与开始之间推进至少 5 秒，并拒绝缺起点、未推进、缺失／非法数值与缺观察等情况；不能通过修改报告数字或降低门槛解决。修正后重新取得相应实播截图。
3. **BR-3：当前播放源与指纹所属源的对应关系未充分核验。** `playback_failures`（Python 入口 `:203–211`）只匹配任一源的 URL hash／类型，忽略已采集的 `source.id`；下游指纹读取直接使用 item ID 作 source ID，未核对实际返回源。B 将真实 B01 响应的源 ID 改为另一 GUID，其余保留，验证器仍返回空错误。交付要求是逐次核验当前项目／期望源 ID、对应 PlaybackInfo、实际播放请求与五字段，保留原始关联记录；错误／缺失源 ID 不得接受。只纠正本基线的取证及误报，不扩展为多版本矩阵或通用关联工具。
4. **BR-4：必需 B03 音频旅程未完成，交 A。** B 核对 run-6 的浏览器 500 与报错截图、run-8／9 的 `Audio` 实体／已存 Audio 主流／原生 universal 路由返回 STRM 文本的记录，确认现有输入未能完成真实音频播放。run-9 在音频浏览器播放前短路为 BLOCKED；没有首次信任／再播／重启实播的成功证据，不能计 PASS。该观测不证明所有原生音频 STRM 组合均不可行；`mediaSourcePathIsLocalStrm` 在工具中为常量，不能代替实际路径取证。请 A 裁定固定版本的音频能力与必要合同处理；B 不撤出 B03、不换成视频音轨／普通音频、不授权产品成功判定修复。A 提交实质变更时，B 再重判同一 Task 的合法调整。

### 证据核验与复用决定

- 本机索引：`.git/validation-evidence/38c1184c488baf1e6bd1c3b2ff4b1264c9e08e93/b-review-20261021T031059Z/INDEX.md`。独立控制脚本、准确 argv／cwd／退出码／计时、原始输出、来源与截图摘要均在该目录，未上传。
- 已逐张打开 run-9 **12 张**视频截图：B01 三对均见 `MP4 A`，B02 三对均见 `MKV A`，开始图见原生播放控制，后图见解码测试图、无可见报错；图像时间标记有推进。另打开 run-6 B03 的 incomplete 图，见“播放错误／播放失败，因为客户端不支持该媒体”。这是 B 实际看图，不追认 Developer 已看，也不据此补足 BR-1／BR-2 或音频成功。
- 核对六阶段原始 driver／observation、FirstTrust→Sha1Matches 日志、目标 ffprobe 窗口 0／0／0、媒体 GET、五字段和运行收尾记录。它们保留为开发反馈及失败定位资料，**不复用为本 Task 全量／实机 PASS**。独立控制是工具拒绝性验证，不是产品或真实重启故障注入。
- 核验 run-9 ZIP SHA-256 为 `cb195638971da1a69e5cfa2d9966f9b3db94ddae2c54ef33a03641bb3ceba9ae`，报告后另存 `2abbecf` ZIP 为 `93d0fc33496ee2cde658de497e46a141af1fd14428976d718599920da21520fb`。两者不同；run-9 使用期间有多次可执行工具修正，不能仅凭不变的产品源码或“只改报告”把其结果升级为最终候选通过。保留首次失败和原始归属工作区，不为本轮拒绝重建包／准备库。

### 本轮门禁及修正分工

- **已运行：** 当前治理 PASS；Python 3.11 独立控制（退出 0，重现六项短推进误接受、源 ID 错配误接受及原生 URL／流变化误接受）；文档检查与计时见本机索引。控制成功表示缺陷复现，不能写成产品 PASS。
- **NOT RUN：** 本候选完整 C# restore／build／test／format、干净候选完整 Python／compileall、Node 语法、最终同 ZIP 的完整三行 baseline、B 新归属实例独立实播、既有 package all 及 Slice Final。按开发流程“已有明确阻塞可先拒绝”停止昂贵门禁；这些仍由 **B** 在修正候选承担，未交回 Developer，也不削减原计划。
- **Developer：** 补齐 BR-1～BR-3 所指的实播／重启／选源证据，按“当前状态与最小修正边界”只改必要采集和误报断言；代码发生修改时运行直接受影响的反馈检查及必要反例控制，不为增加工具覆盖另做开发。音频范围等 A 决定；视频可先形成准确的部分结果，不能据此交付整个基线。交接材料按 B01～B03／三阶段报告实际结果、缺口和最小代码变动，不以工具功能表为完成报告。不承担 B 的完整套件；修正提交后仍交 READY FOR B REVIEW。
- **B：** 固定修正实现 SHA／tree／同 ZIP，按原计划执行完整 C#、干净 Python 3.11、静态／治理及 package all；核验匹配完整 baseline、在新归属实例独立复现合同保留的必需媒体旅程，实际打开全部截图。可执行输入修正后按 T4 重取指定证据；后续纯报告变化按输入匹配规则复用，不机械重跑 Final。
- 本轮测试只运行短控制及治理／文档检查，保守合计上限 5 秒，严格小于本轮实际总耗时的 50%；精确控制耗时及总时间见索引。未空等凑分母，未启动昂贵验收。Developer 报告的“真实运行与排障”为非测试的记账不能直接采用：夹具生成、健康／扫描／播放等待和失败重试均须按流程计入测试区间，后续报告需依原始时间重算。

RO 重核：RO-4 维持 Task 5.1 固定检查点的已接受决定，本轮不重判或扩张远端 CI 结果；RO-1 仍有媒体服务余项，RO-2 基线及 P01～P08 未满足，RO-3 尚未完成。**不新造 Task、不提交 Closure Packet、不返回 SLICE READY FOR A REVIEW、不关闭 Slice。** Slice 5 保持 ACTIVE；下一步为补齐本 Task 实播旅程和 A 的音频范围裁定。三行旅程满足后，B 按既定门槛判定，不因额外工具完善延长本 Task。

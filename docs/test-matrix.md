# 测试矩阵

下表保留产品用例身份与分层证据；各Slice的接受范围见[关闭账本](progress.md)，Slice 4完整门禁、复用与独立核验统一见[关闭记录](progress.md#slice-4-closed)，后续视频证据见下节。不能只凭Task PASS代替Final。按2026-10-20用户授权，JellyfinProxy专属RO-4／AC-7验收撤出当前范围：历史NOT RUN、按用户授权不执行，不计PASS、不宣称代理兼容。原生播放／多源／换地址／失败恢复／重启、MP4／MKV Web播放、包／扫描／全部1004项大库及完整最终回归不变。下方已关闭Slice的历史结果不改写，模拟／代表性实机不扩大为所有格式／分支／客户端通过。通常前提为受支持版本化STRM、已有主流、历史指纹与允许探测；例外显式说明。

保留 T01～T28 身份以便追溯，但 T08／T22 按 V4.2 改为原生探测后新地址持久化，T02／T17～T19／T27 改为最小指纹合同。旧结果不自动继承。B01～B12 为新增批量／共享并发验收。

## Slice 5 视频播放与CI分层证据

2026-10-21 用户明确撤出音频 STRM 专属验收，当前视频执行范围见 [范围说明](scope.md#2026-10-21-用户明确排除音频-strm)。历史音频 FAIL／BLOCKED／NOT RUN 与通用单元用例保留，不转为 PASS；视频 P01～P08、ColorRange、失败恢复及完整门禁保持。

P01～P08、ColorRange返回主流匹配、失败恢复／重启及CI-F1～CI-F3的完整输入和观测设计见[执行设计](slice-5-playback-test-plan.md)，实际正式行、独立复现、完整门禁、Final与A接受边界见[Slice 5关闭记录](progress.md#slice-5-closed)。逐行证据按输入和执行阶段接受，未宣称当前驱动单次重跑全矩阵，历史整体FAIL与干净检出归档缺失SKIP保持。

| 范围 | 本次证据层与边界 |
|---|---|
| P01～P08、D／F对照 | MP4／MKV原生Web实播、实际ffprobe、源／URL／主流、五字段、再播与重启先读；false权限使用已有原生静态流入口。 |
| ColorRange | 明确limited／full与未指定对照的同次编码器／成功保存／返回完整身份字段；有界修正、失败旧基线与同目标恢复。 |
| CI-F1～CI-F3 | 真实Base失败、干净Python3.11、本地完整回归及匹配修复候选的远端workflow成功；后续未推送候选不声称远端绿灯。 |
| 截图与收尾 | B逐行实际查看原图并对账；当前退出修正有完整独立行与单独Final、真实原生Stop及正常退出证据。 |

下方核心表保留原Slice关闭时的分层状态；其中T05、T09～T11的旧对应实机NOT RUN是历史事实，新增视频覆盖分别由本次P03、P02原始证据证明，不将旧记录改写为当时已通过。后文其他Slice的未验证边界也按其当时范围理解。

## 核心播放与指纹

| ID | 场景 | V4.2 预期 | 需求（REQ- 前缀省略） | 最终证据类型 | 状态 |
|---|---|---|---|---|---|
| T01 | 首次无主流 | 实际原生探测；成功、保存且版本一致后初建指纹 | DECISION-001、STATE-001、PROBE-002 | 单元＋Jellyfin 集成 | PASS（Slice 2 必要证据层） |
| T02 | 首次已有主流 | 默认信任接管，建立指纹、零探测，不计本次成功 | STATE-001 | 单元＋Jellyfin 集成 | PASS（Slice 2 必要证据层） |
| T03 | URL 不变、SHA-1 相同 | 跳过 | DECISION-002 | 单元＋集成 | PASS（Slice 2 必要证据层） |
| T04 | URL 不变、SHA-1 不同 | 实际探测 | DECISION-002、PROBE-001 | 单元＋集成 | PASS（Slice 2 必要证据层） |
| T05 | URL 不变、SHA-1 相同、Size 不同 | 跳过；URL 变化不适用此豁免 | DECISION-002 | 单元＋集成 | PASS（单元）；NOT RUN（对应独立实机） |
| T06 | URL 不变、SHA-1 不可比、Size 相同 | 跳过 | DECISION-003 | 单元＋集成 | PASS（Slice 2 必要证据层） |
| T07 | URL 不变、SHA-1 不可比、Size 不同 | 实际探测 | DECISION-003 | 单元＋集成 | PASS（Slice 2 必要证据层） |
| T08 | URL 改变、SHA-1 相同 | 必须实际探测，原生保存新地址和有效主流 | DECISION-004、PATH-001 | 独立单元＋真实探测／播放 | PASS（Slice 2 必要证据层） |
| T09 | URL 改变、SHA-1 不同 | 实际探测并保存最新地址 | DECISION-004 | 单元＋集成 | PASS（单元）；NOT RUN（对应独立实机） |
| T10 | URL 改变、无 SHA-1、Size 相同 | 必须探测，单独自动化回归 | DECISION-004 | 独立单元＋集成 | PASS（单元）；NOT RUN（对应独立实机） |
| T11 | URL 改变、无 SHA-1、Size 不同 | 必须探测 | DECISION-004 | 单元＋集成 | PASS（单元）；NOT RUN（对应独立实机） |
| T12 | URL 改变、仅一侧有效 SHA-1 | 必须探测 | DECISION-004、MANIFEST-002 | 单元＋集成 | PASS（Slice 2 必要证据层） |
| T13 | 仅 Modified 变化 | 跳过 | DECISION-005 | 单元＋文件集成 | PASS（Slice 2 必要证据层） |
| T14 | 同内容 STRM 删除后重放且库记录／指纹保留 | 不因文件重放探测 | DECISION-005 | 文件＋Jellyfin 集成 | PASS（Slice 2 必要证据层） |
| T15 | 同 URL、同 SHA-1 重写 STRM | 跳过；地址改变则按 T08 | DECISION-005 | 文件＋集成 | PASS（Slice 2 必要证据层） |
| T16 | 同 URL 远程替换、SHA-1 变化 | 实际探测 | DECISION-002 | 原生探测集成 | PASS（本地媒体替换）；NOT RUN（外部代理） |
| T17 | 探测失败且旧流仍在 | 旧指纹不变，后续仍识别变化；不写失败状态 | PROBE-002、PROBE-003、STATE-002 | 失败注入＋真实探测 | PASS（Slice 2 必要证据层） |
| T18 | 探测期间 STRM 再变 | 不提交过期结果，后续重查最新文件 | PROBE-002、PROBE-003 | 竞态集成 | PASS（Slice 2 必要证据层） |
| T19 | 重启，含上次未完成变化 | 指纹恢复并重新比较；无待测状态表也能重试 | STATE-003、PROBE-003 | SQLite＋真实重启 | PASS（Slice 2 必要证据层） |
| T20 | 多客户端同源并发，区分排队与实际开始 | 只共享实际已开始的运行中探测；排队不共享，获得执行机会后重查，结束各自重查 | CONCURRENCY-001 | 开始边界／并发＋真实计数 | PASS（Slice 2 必要证据层） |
| T21 | 手动强制刷新 | 保留原生，更新事件不足以提交指纹 | REFRESH-001 | Jellyfin 集成 | PASS（Slice 2 必要证据层） |
| T22 | 地址变化成功探测后重启 | 新 URL 与有效主流仍可用；不是仅更新路径测试 | PATH-001 | 真实探测＋Jellyfin 重启 | PASS（Slice 2 必要证据层） |
| T23 | 未安装插件 | 原生基线 | COMPAT-001、COMPAT-002 | 对照实例 | PASS（未安装隔离对照） |
| T24 | 禁用插件 | 原生播放，批量不发起插件探测 | COMPAT-002、CONFIG-001 | 配置＋原生对照 | PASS（播放／批量禁用） |
| T25 | 多版本影片 | source_key 独立，地址／流／指纹不串版本 | CONCURRENCY-001、STATE-003 | 多媒体源集成 | PASS（Slice 2 必要证据层） |
| T26 | 无协议标记旧 STRM | 默认原生，批量不优化 | COMPAT-002 | 解析＋Jellyfin 集成 | PASS（旧 STRM 播放／批量过滤） |
| T27 | 同基线 SHA-1 暂缺后恢复；再探测另一版本且新哈希缺失 | 前者保留有效历史哈希；后者不得继承旧版本哈希 | STATE-004、MANIFEST-002 | 指纹序列＋集成 | PASS（Slice 2 必要证据层） |
| T28 | allowMediaProbe=false，含同 SHA-1 换 URL | 不发起探测，不提交变化指纹；后续允许请求可重试 | DECISION-006、PATH-002 | 所有分支权限＋真实计数 | PASS（Slice 2 必要证据层） |


## 新增批量与全局并发

| ID | 场景／验证 | 预期 | 需求（REQ- 前缀省略） | 最终证据类型 | 状态 |
|---|---|---|---|---|---|
| B01 | 并发默认／配置边界 | 默认 2；1 与 8 可用；0、9、非整数保存反馈，实际并发不越界 | CONFIG-001、CONCURRENCY-002 | 配置＋协调集成＋真实计数 | PASS（配置／确定性 1、2、8／启动生效实机） |
| B02 | 多项目播放与批量混合探测 | 共用插件全局上限；Jellyfin／其他插件独立探测不被限流 | CONCURRENCY-002 | 隔离实机并发对照 | PASS（真实混合上限／独立原生刷新） |
| B03 | 媒体库范围及类型过滤 | 默认全部，可选部分；普通媒体、旧／不支持 STRM 不探测；候选 ID 去重固定，分批重核当前范围／对象，消失／移出安全结算，新增下轮发现 | BATCH-002、COMPAT-002、CONFIG-001 | ID 集合／分批夹具＋实机库 | PASS（集合／范围／多批／多版本控制及实机） |
| B04 | 大量已有主流的首次任务／随后增量变化 | 默认信任，不全库重探测；仅缺流／变化者执行，与播放决策一致 | STATE-001、BATCH-002、BATCH-003 | 大规模夹具＋真实增量计数 | PASS（Slice 3 代表性实机；Slice 4 全部 1004 项真实大库与增量）；分层证据见 [Closure Packet](progress.md#slice-4-closed) |
| B05 | 批量与播放同源，含排队／已开始及播放不允许探测 | 只加入已实际开始的探测；排队请求保持各自生命周期并在执行前重查，避免重复；播放不提高权限，独立批量上下文可执行 | DECISION-006、CONCURRENCY-001、BATCH-003 | 混合并发＋真实计数 | PASS（确定性权限／排队及双向实机共享） |
| B06 | 两入口遇成功／失败／保存失败／Manifest 再变 | 使用同一提交门槛，无错误新指纹；无法确认的刷新不计成功 | PROBE-002、BATCH-003 | 失败注入＋真实结果／存储 | PASS（保存失败控制／真实成功失败竞态）；NOT RUN（物理数据库保存故障实机注入） |
| B07 | 停止候选获取／后续批次／未开始工作，含已开始仅批量／播放共享及启动竞态 | 未开始撤销，其他调用者排队不受影响；所有已开始探测继续完成并可按全部成功条件提交；任务停止收尾等待其结算、资源释放，不误报全库完成 | CONCURRENCY-001、BATCH-004 | 开始／停止竞态＋真实任务停止／收尾 | PASS（确定性开始／停止边界及真实取消收尾） |
| B08 | 单项损坏／探测失败及全局数据库不可用 | 单项报告未完成；旧指纹保留；状态库不可用停止优化，不转全库探测；恢复可再查 | MANIFEST-003、FAILURE-001、PROBE-003 | 注入＋实机恢复 | PASS（单项隔离／状态库全局失败及修复重启） |
| B09 | 进度、完成／取消统计和日志 | 单调进度；成功仅可靠结果；计数可对账，信任接管算跳过；不泄露地址／秘密 | BATCH-005、PRIVACY-001 | 原生任务 UI／日志＋结果对账 | PASS（进度／结果／汇总与脱敏对账） |
| B10 | 原生任务注册、手动／定时／停止、配置 | 名称正确，默认无触发；管理员原生设置；无独立按钮／调度器／扫描后触发；关闭播放检查仍可批量 | BATCH-001、BATCH-006、CONFIG-001 | 固定版本原生任务实测 | PASS（真实注册／无默认触发／定时重启／配置页） |
| B11 | 媒体库扫描／手动刷新同时增删或更新 STRM | 不提交过期指纹、不越范围、不假定时间计划已串行完成；后续增量可收敛 | BATCH-002、BATCH-006、REFRESH-001 | 隔离扫描竞态＋任务 | PASS（Slice 3 范围／增删控制；Slice 4 完整扫描重叠及收敛）；分层证据见 [Closure Packet](progress.md#slice-4-closed) |
| B12 | 历史十万模拟候选／真实大库成本／并发配置变更／ID 或批次获取故障 | 完整媒体对象按批次限制，固定消费者，不创建全库 Task；全部 ID／去重／排序与原生获取临时成本单列，不宣称总内存恒定；提前结束无许可泄漏 | CONCURRENCY-002、BATCH-002 | 压力指标＋代表性实机运行 | PASS（Slice 3 历史十万模拟；Slice 4 真实大库分层成本）；模拟与真实结果分别见 [Closure Packet](progress.md#slice-4-closed) 及历史索引 |

## 补充边界

| ID | 验证目标 | 状态 |
|---|---|---|
| X01 | STRM 只读、不调用 OpenList API、不计算远程内容哈希；只用临时夹具 | PASS（插件只读边界） |
| X02 | 全接口委托、普通媒体／直播、DI 顺序、单例／释放、生命周期 | PASS（委托／DI／生命周期） |
| X03 | 编码／BOM／空白、缺失／非法字段、零／溢出 Size、未知／冲突协议、有界读取及非法 URL | PASS（单元／文件） |
| X04 | 文件、原生地址／结果保存、SQLite 错误不覆盖指纹；原生回退保留探测权限；首次原生地址已过期不能静默成功 | PASS（控制＋代表实机）；NOT RUN（内部数据库故障实机注入） |
| X05 | 同 URL 信息不足跳过并说明限制，mtime 不参与，签名查询变化仍算 URL 变化 | PASS（决策／文件／代表实机） |
| X06 | SQLite 最小指纹／重启／schema 升级／损坏／不可写；无媒体流、完整 URL、PlaybackInfo 或独立探测状态 | PASS（SQLite／schema／重启恢复）；无旧 schema 迁移需求 |
| X07 | 实际 ffprobe、新结果、主流与持久化关联；旧流／事件／刷新返回值不足；FullRefresh 额外开销 | PASS（本次信号／保存／实机）；NOT RUN（通用 FullRefresh 开销证明） |
| X08 | 只共享已开始探测、排队不共享、等待者退出仍收尾、不同源独立、版本变化、条件提交与完成重查 | PASS（共享／排队／批量停止及收尾） |
| X09 | 配置保存／生效／错误反馈、默认值、固定规则不做关闭开关 | PASS（完整配置页／五项配置／批量范围与错误反馈） |
| X10 | 签名 URL、token、Cookie、私有路径不进入状态、日志、进度或证据 | PASS（播放／指纹／批量日志与进度） |



## 取消验收上下文

A 实质范围调整保留矩阵 ID 与历史结果，但移除当前 Slice 1 的人为注入取消门槛。当前固定版本的公共 PlaybackInfo 传 `CancellationToken.None`，客户端退出／停止播放不取消该探测；不增加必须取消客户端请求的验收，不将该入口事实写成探测取消 PASS。

- Slice 1／X08：继续验证 Manifest 变化与条件提交；取消只保留原生 token 委托、原生抛出取消异常时保留基线并传播及已有回归，不要求成功返回后的额外取消检查或人为注入取消实机验证。旧注入取消 NOT RUN 不改为 PASS，该子场景已退出当前范围。
- PlaybackInfo 正常／失败验证：未变化且已有主流时跳过，需要时实际探测；执行实际成功、结果已保存且 Manifest 一致时，客户端退出不单独阻止提交。公共入口源码定位如实报告，不以人为注入取消替代当前播放行为。
- 用户本次停止／共享规则由 A 作为 Material Contract Change 替代旧 Slice 2 的人为执行取消门槛。Slice 2／X08 验证实际开始后才共享、排队不共享、开始竞态、等待者退出仍正常收尾和结束重查；不再新增执行取消源或探测中／提交前取消注入实机要求，原生自身取消异常的既有回归保留。
- Slice 3／B07 验证停止后续候选获取／分批读取和本任务未实际开始的工作，播放／其他调用者的排队请求不受影响。所有已开始探测继续，无其他等待者的仅批量探测也继续；成功且已保存、Manifest 稳定时仍提交。任务停止收尾等待其结算，按实际结果统计，不把批量停止当作探测执行取消。先确认停止则不开始，已实际开始则完成，竞态必须实测。
- 服务器关闭或进程被杀作为执行中断／重启恢复记录，不充当取消 token 生效的证据。

固定源码与入口见 [兼容性](compatibility.md#播放与批量取消语义)。已开始共享、确定性正常收尾及代表性并发计数已在 Slice 2 验证；真实批量停止收尾已在 Slice 3 验证并接受。被替代的取消注入门槛保留历史 NOT RUN，不改写为 PASS。

## Slice 3 已接受执行与对账

本节只记录 Slice 3 关闭时的证据与当时未测范围；后续真实大库、完整扫描和本地 ZIP 的已接受结果见 [Slice 4 验收分配](#slice-4-验收分配)。历史计数和限制不倒写为后续通过证明。

A 审查完整 Slice Base..接受实现后裁定 PASS / CLOSED，AF-1 闭合，无剩余 P0/P1；旧拒绝／失败和每次修正留在 Git。Task 3.1 完整 B PASS 在 `aa78c06216ec30fbefd288ac4c73e9a7d44afa95:TASK.md`，Task 3.2 在 `678bcf5c3a6ba5c6743402ec27367dd76d0f101d:TASK.md`。以下索引位于本机 `.git/validation-evidence/7c64eb5dcad6e5f20fb7eb41819be2521f65484d/`，不能声称远程可读：

- `slice-final-20261016/INDEX.md`：独立 Final，locked restore／Release build／format、202 C#／63 Python、默认真实 playback、批量七场景和配置页 19 场景；所有门槛 PASS，未重试。配置／全部触发器／夹具恢复，临时条目清理。
- `a-final-review-20261016/INDEX.md`：A 核验 82 项输入仅交接文档变化、232 项构建产物及 B／Final 证据清单全部摘要；独立复跑 202 C#／63 Python 与 16 项准入／末项故障控制。真实 Final 明确复用，未声称 A 再次运行实机。
- `b-review-20261016/INDEX.md`：独立 Task 审查和控制、真实 stop／sharing；原始证据与精确重建的 Developer 二进制身份均保留。

| 必要结果／矩阵 | 当前证据 |
|---|---|
| B03／B04、T25／T26 | 当前库关系及项目／源身份控制；原生 scope 多库、多批、多版本、增删与下一轮发现，范围外／普通／旧输入无插件探测。 |
| B01／B02／B05／B07、X08 | 确定性配置 1／2／8、许可／准备／开始与停止竞争；真实双向 sharing／shared_stop、混合峰值 2、停止后 2 个已开始源提交／1 个撤销，收尾期无新轮或新批量探测，独立播放继续，随后正确重跑。 |
| B06／B08／B09 | 末项禁用／共享仓库故障、单次观测、重新启用及资源控制；真实 failure 报 Failed、零新探测，修复重启可完成；进度／统计对账，首次信任不计成功。 |
| B10／X09／X10 | 真实无默认触发、手动／定时和重启；19 个浏览器交互场景、五项配置／失效库／拒绝与未确认保存／重读／页面值驱动原生任务，必要诊断脱敏。 |
| B12 | 历史十万模拟结算 100000 个候选、782 批，完整对象峰值 128、活动消费者不超过 8、累计消费者 Task 6256；ID 模型、容量折算、累计分配、进程堆采样及原生查询成本单列，不称总内存恒定或当前至少 1000 项真实媒体库性能。 |

真实大库／完整扫描压力和本地 ZIP 未在 Slice 3 验证，后续由 Slice 4 接受；JellyfinProxy／OpenList、广泛格式／客户端、逐分支／audio-only 实机、物理数据库保存故障注入和完整镜像构建溯源保持各自未验证边界。历史十万规划与模拟不代表至少 1000 项真实大库验收。日志跨日关联及指数泛称保留 P2，不阻止关闭。

## Slice 2 历史执行与对账

以下保留 Slice 2 当时的实际结果与限制；本节的批量、UI 或发布 NOT RUN 只描述当时边界，后续接受状态以上方矩阵、[关闭账本](progress.md) 与 [Slice 4 最终决定](progress.md#slice-4-closed) 为准。

Task 2.1／2.2 已 B 审查 PASS；最新接受实现 `59fd3f7e4b6623449a691574fb69b817db72c2ae`，Task 2.2 完整计划／报告／B 决定见 `76cd9e997548c4ffef04a8dd8f9b0d4ef4376347:TASK.md`。六个 Required Outcomes／六个 Required Surfaces 与单独 Final 已由 A 最终审查接受，Slice 2 PASS / CLOSED；A 独立重跑 C# 112/112，并核验匹配输入后复用下述 Final 原始证据。上表仍按完整产品证据类型保留，不能把核心部分通过升级为真实批量、UI、外部代理或所有实机分支 PASS。

Slice 2 本机 B 索引：`.git/validation-evidence/59fd3f7e4b6623449a691574fb69b817db72c2ae/b-rereview-20261014-08/INDEX.md`。指定聚焦 81 passed／0 failed／0 skipped；六项独立边界控制 PASS：Acquire／开始交错、排队旧源已接受零重复、主流消失需探测、准入委托异常释放、立即取许可后第一执行先完成只探测一次、取源期间 STRM A→B 不提交旧信任。原生开始／授权／事务保存边界已核对。Developer 完整 112 项 C#、30 项 Python 和真实 JSON 原始证据已核验匹配；本次 B 默认实机重新运行并通过，历史失败在 Git 和各候选原始证据中保留。

| 核心必要边界 | 本轮独立证据与结果 |
|---|---|
| T20／X08 准备、实际开始、完成后重查 | 聚焦／六控制 PASS；实机 `same_source_sharing` 开始 1／提交 1／随后 0。准备不登记共享，所有 owner 行动前重判。 |
| RO-5 无等待者正常收尾 | `StartedProbeCommitsEvenWhenNoCallerAwaitsAndTheWaiterCancels` 和明确加入／退出屏障 PASS；正常提交及资源归零。非真实客户端取消探测，批量停止留在 Slice 3。 |
| B01／B02 核心上限与独立刷新 | 确定性 1／2／8 PASS；实机默认重叠 2、保存 1 重启前仍 2、重启后串行；饱和池下独立原生 FullRefresh 405 ms 完成。真实混合批量 NOT RUN。 |
| 多源／调用者权限 | 两个不同 User 的差异响应与路径替换、false 权限、多版本身份聚焦 PASS；实机多版本源／地址／主流／五字段分别关联。 |
| X09／X10 核心配置与诊断 | 中途写入失败旧文件／内存／重新加载保护、启动脱敏聚焦 PASS；实机合法保存／读回／重启、非法值文件保护、下一请求 Enabled／DetailedLog PASS。补充 `PlaybackAutoCheck=false` 下一请求返回原生正确地址／主流且指纹不变，恢复后零探测。HTML／批量 UI NOT RUN。 |
| T23 未安装原生对照 | 补充隔离验证实际移出插件二进制目录并重启，API 与目录均证明未安装，PlaybackInfo 地址／主流正确、无插件事件、指纹不变。恢复插件／配置并重启后 0 探测；PASS。未使用“禁用”等同“未安装”。 |
| 失败／竞态／SQLite／地址与主流重启 | 默认实机全部原 Task 2.1 场景 PASS，SQLite 未完成变化跨重启仍需探测，修复恢复；原夹具／媒体／配置恢复、临时库条目残留 0。 |

以下具体用例索引保留该次审查的证据层；后续最终候选的回归／证据复用见 Closure Packet，不把文档同步当作重新运行。T09～T11 的对应逐分支实机、音频-only 实机及 Jellyfin 内部数据库保存失败实机注入仍分别 NOT RUN，不弱化合同的逻辑全矩阵、保存失败控制与代表性真实探测／重启门槛。

单独 Final 索引 `.git/validation-evidence/59fd3f7e4b6623449a691574fb69b817db72c2ae/slice-final-20261014-09/INDEX.md`：112 C#／30 Python、全部构建质量门槛、默认真实入口（706.997 秒）、补充未安装／播放检查关闭／恢复对照（107.809 秒）全部 PASS；Final 实机默认 2／保存 1 重启前仍 2／重启后 1，独立 FullRefresh 495 ms，夹具内容与初始身份一致、临时库残留 0。

### 核心矩阵与表面索引

| 矩阵项 | 证据层与具体用例／场景 | 状态 |
|---|---|---|
| T17 探测失败且旧流仍在 | 单元 `FailedProbeDoesNotReplaceTheAcceptedFingerprint`、`FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint`、`FailedNativeStreamSaveLeavesChangedAddressFingerprintRetryable`、`PersistenceProxyDoesNotConfirmNativeSavesThatThrow`；实机 `failed_changed_url`（返回≥400、1 次探测、已保存流不变）、`failed_probe_retained_streams` | PASS（Task 范围） |
| T18 探测期间 STRM 再变 | 单元 `ManifestChangedDuringProbeDoesNotCommitAnOldResult`；实机 `manifest_race`（HTTP≥400、`probe_calls=1`、保留指纹、恢复 1 次探测） | PASS（Task 范围） |
| T19 重启含上次未完成变化 | 单元 `RestartWithRepairedRepositoryRechecksAndCommits`、SQLite 七项；实机 `failed_url_after_restart`、`same_failed_url_repaired`（保留基线重启后再探测并提交） | PASS（Task 范围） |
| T20 多客户端同源并发 | 见上表 Task 2.2 行：单元准备／开始边界与排队重查；实机 `same_source_sharing`（1 探测 1 提交） | PASS（Task 范围） |
| T21 手动强制刷新 | 实机 `manual_full_refresh`（ETag 更新但未当作确认；后续地址变化仍触发 1 次探测） | PASS（Task 范围） |
| T22 地址变化成功探测后重启 | 实机 `address_after_restart`、`recovered_after_failure`（重启后新地址与主流仍可用） | PASS（Task 范围） |
| T23 未安装插件 | B 本次补充 `uninstalled_native_baseline`：插件 API／二进制目录不存在，原生 PlaybackInfo 正确地址／主流、指纹不变；恢复插件后零探测 | PASS（固定隔离对照） |
| T24 禁用插件 | 实机 `disabled_plugin_delegation`；单元 `DisabledOptimizerDelegatesOriginalProbePermission`、`DisabledOptimizerDelegatesWithoutStartingOrSharingAProbe`；批量不发起探测属 Slice 3 | PASS（播放部分）；NOT RUN（批量部分） |
| T25 多版本影片 | 实机 `native_multiversion_and_sqlite_recovery`（两版本独立 source_key／地址／主流／五字段，选源正确）；单元 `AlternateVersionUsesItsOwnStrmProbeAndStableProjectSourceIdentity`、`MixedLegacySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped`、`MixedOrdinarySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped` | PASS（Task 范围） |
| T28 allowMediaProbe=false | 单元 `DisallowedProbeIsPassedThroughWithoutReadingOrCommitting`、`DisallowedProbeDoesNotAcceptAChangedAddressOrFingerprint`、`RepositoryReadFaultDoesNotElevateFalsePermission`；实机 `false_permission_stream`（真实流请求 0 提交，后续允许请求 1 次探测） | PASS（Task 范围） |
| X01 STRM 只读／无外部 API／不下载哈希 | 实机 `legacy_strm_delegation`、`ordinary_media_delegation`；工具仅以 `mode=ro` 读取 SQLite；无 OpenList／代理调用；未运行外部代理联调 | PASS（Task 范围）；NOT RUN（外部代理） |
| X02 全接口委托／DI 顺序／生命周期 | 单元 `MediaSourceManagerProxyTests.ProxyDelegatesEveryInterfaceMethod`、`CoreServiceRegistrationTests.RehomedNativeSingletonIsCreatedAndDisposedExactlyOnce`；实机插件加载／启用／禁用重启 | PASS（Task 范围） |
| X04 原生保存／SQLite 错误不覆盖指纹／回退保留权限 | 单元 `FailedNativeStreamSaveLeavesChangedAddressFingerprintRetryable`、`PersistenceProxyDoesNotConfirmNativeSavesThatThrow`、`RepositoryReadFaultStopsOptimizationAndDelegatesWithOriginalPermission`、`RepositoryReadFaultDoesNotElevateFalsePermission`；实机 `failed_changed_url`、`failed_url_after_restart` | PASS（Task 范围；未对 Jellyfin 内部数据库注入故障） |
| X06 SQLite 最小 schema／重启／版本／损坏／不可写 | 单元 `EmptyDatabaseCreatesOnlyVersionedMinimalSchemaAndReopensFingerprint`、`ConditionalCommitRejectsStaleBaselineAndPreservesLatestVersion`、`CompetingFirstInsertionsAcceptOnlyOneBaseline`、`FailedSqlTransactionLeavesPreviouslyAcceptedFingerprintIntact`、`UnknownAndUnversionedDatabasesAreRejectedWithoutReplacingExistingData`、`CorruptDatabaseIsRejectedWithoutReplacingOrDeletingIt`、`EmptyFileIsTreatedAsANewDatabaseAndNotMistakenForCorruption`；实机 `native_multiversion_and_sqlite_recovery` | PASS（Task 范围） |
| X07 实际 ffprobe／新结果／主流／持久化关联 | 单元 `UrlChangeWithSameShaProbesAndCommitsOnlyAfterSavedPrimaryResult`、`NewAddressWithOldPersistedPrimaryStreamDoesNotCommitAndRemainsRetryable`、`AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream`；实机 `same_sha_url_change`、`manual_full_refresh`（GetMediaInfo 计数与本地媒体 GET） | PASS（Task 范围） |
| X10 隐私（URL／token／私有路径不进入状态／日志／证据） | 单元 `ConfigurationTests.InvalidPersistedConfigurationDiagnosticDoesNotLeakPrivatePaths`；实机脚本仅输出 URL 的 SHA-256、主流类型与计数，不打印签名 URL／token／Cookie／私有路径 | PASS（Task 范围） |

Slice 2 当时的 Required Surfaces 对账：solution／测试入口、原生 PlaybackInfo 与探测／保存链、私有 SQLite 最小指纹与恢复、项目／源身份映射与 ProbeCoordinator（实际开始、只共享运行中、正常收尾、结束重查）、Jellyfin 配置保存通道与脱敏日志均有上述单元／实机证据。完整 HTML 配置页与批量范围 UI 后续在 Slice 3 接受，本地单版本包在 Slice 4 接受；跨版本兼容始终未纳入已验证声明。

### 历史实现证据指针（不替代当前最终验证）

候选 `b99bc00b08fd3a8cad32076a220c5219fcc78ab7` 的 T4 执行记录保存在 `.git/validation-evidence/b99bc00b08fd3a8cad32076a220c5219fcc78ab7/developer-final-t4-20261013-02/INDEX.md`。单元测试和隔离 Jellyfin 分别报告：C# 全套 51/51、Python 全套 30/30；真实实例验证首次信任／持久化重启复用、同内容换 URL、多版本源和主流关联、失败重试及 Manifest 竞态、SQLite 写入／只读故障与重启恢复，以及普通／旧 STRM、直播、false 流权限、禁用插件和 FullRefresh。临时条目和多版本关系已清理，原 STRM 与 Jellyfin 地址已恢复。

### 修正轮证据与逐项索引（候选 `198f4ff2accd5bc9fcd87518a9684b9d068de103`）

响应 B 复审剩余 R2 的修正候选 T4 记录保存在 `.git/validation-evidence/198f4ff2accd5bc9fcd87518a9684b9d068de103/developer-fix2-t4-20261013-234000/INDEX.md`：C# 全套 69/69（含新增未知／冲突版本与换 URL／同 URL 双向哈希矩阵）、Python 全套 30/30、format／治理／diff／compile PASS、隔离实机 JSON PASS（492 秒，临时夹具已清理、原 STRM 与地址已恢复）。候选只改两份测试文件，产品源码、依赖锁与隔离工具未变。下表把合同要求的 T01～T16、T26／T27、X03／X05 逐项映射到实际证据层；证据层列 `单元`＝MSTest，`文件`＝真实文件读写回归，`实机`＝隔离 Jellyfin 默认入口。

| 矩阵项 | 证据层与具体用例／场景 | 状态 |
|---|---|---|
| T01 首次无主流 | 实机 `first_play_without_primary_stream`（缺失媒体 URL，1 次原生探测，无指纹）；单元 `MissingPrimaryStreamTakesPrecedenceOverFirstTrust`、`AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream` | PASS（Task 范围） |
| T02 首次已有主流 | 实机 `first_trust`（禁用插件原生保存主流后信任接管，0 探测）；单元 `FirstTrustRequiresAnExistingPrimaryStreamAndCurrentAddress` | PASS（Task 范围） |
| T03 URL 不变、SHA-1 相同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`；实机 `unchanged_repeat` | PASS（Task 范围） |
| T04 URL 不变、SHA-1 不同 | 单元 `DifferentComparableShaRequiresProbe`、`FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint`；实机 `same_url_content_replacement`（真实本地媒体替换，SHA-1／Size 变化，1 次探测并提交） | PASS（Task 范围） |
| T05 URL 不变、SHA-1 相同、Size 不同 | 单元 `SameUrlAndShaSkipsRegardlessOfSizeDifference`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability` 的“双侧有效且相同 SHA-1、Size 不同”分支（SkipProbe／Sha1Matches） | PASS（单元） |
| T06 URL 不变、SHA-1 不可比、Size 相同 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`（八个缺失／非法组合两侧方向、Size 相同 SkipProbe／Unchanged）；实机 `same_url_noncomparable_size_unchanged`（0 探测） | PASS（Task 范围） |
| T07 URL 不变、SHA-1 不可比、Size 不同 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`（八个缺失／非法组合两侧方向、Size 不同 RequireProbe／SizeChanged）；实机 `same_url_noncomparable_size_change`（无可比 SHA-1，Size 改变，1 次探测并提交） | PASS（Task 范围） |
| T08 URL 改变、SHA-1 相同 | 实机 `same_sha_url_change`（同 SHA-1／Size 换 URL，1 次探测并提交，重启后新地址）；单元 `UrlChangeRequiresProbeEvenWhenShaAndSizeMatch`（原生仍为旧地址，RequireProbe／NativeUrlMismatch）及 `HistoricalUrlChangeRequiresProbeWhenNativeAddressAlreadyMatchesCurrentManifest`（原生已为新地址而历史 URL 不同，RequireProbe／UrlChanged） | PASS（Task 范围） |
| T09 URL 改变、SHA-1 不同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧有效且不同 SHA-1”分支（原生地址已等于当前 Manifest，仅历史 URL 不同，RequireProbe／UrlChanged）；`same_failed_url_repaired` 是相同有效 SHA-1 的失败恢复，归 T08／T17，不充当本行不同 SHA-1 实机证据 | PASS（单元）；NOT RUN（实机双侧有效不同） |
| T10 URL 改变、双侧无 SHA-1、Size 相同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧缺失且 Size 相同”分支（RequireProbe／UrlChanged）；原 `alternate_url_change_without_sha` 为旧侧有效／新侧缺失，属 T12，不作本行证据；双侧缺失的实机分支 NOT RUN | PASS（单元）；NOT RUN（实机双侧缺失） |
| T11 URL 改变、无 SHA-1、Size 不同 | 单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 的“双侧缺失且 Size 不同”“旧侧非法／新侧缺失且 Size 不同”分支（RequireProbe／UrlChanged）；实机无该输入的换 URL 分支 | PASS（单元）；NOT RUN（实机） |
| T12 URL 改变、仅一侧有效 SHA-1 | 实机 `alternate_url_change_without_sha`：旧侧有效／新侧缺失、Size 相同，1 次探测并提交且新 SHA-1 存空；单元 `ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest` 覆盖旧侧有效／新侧缺失与旧侧缺失／新侧有效的两个方向（Size 相同），以及旧侧有效／新侧缺失且 Size 双侧缺失；不能据此声称换 URL 时两侧方向都测过非法哈希或不同 Size | PASS（实机＋双向单元） |
| T13 仅 Modified 变化 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.mtime_only`（0 探测） | PASS（Task 范围） |
| T14 同内容删除后重放 | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.delete_and_replay`（0 探测，指纹不变） | PASS（Task 范围） |
| T15 同 URL、同 SHA-1 重写 STRM | 文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `replay_and_mtime_zero_probe.identical_rewrite`（0 探测） | PASS（Task 范围） |
| T16 同 URL 远程替换、SHA-1 变化 | 实机 `same_url_content_replacement`（真实本地媒体替换等价于远程内容替换） | PASS（Task 范围；远程代理未联调） |
| T26 无协议标记旧 STRM | 实机 `legacy_strm_delegation`（默认原生，无插件事件）；单元 `ReadTreatsMissingProtocolAsUnsupported`、`LegacyStrmDelegatesOriginalProbePermission` | PASS（Task 范围） |
| T27 暂缺 SHA-1 后恢复／另一版本缺哈希不继承 | 实机 `temporary_missing_sha_preserves_history`（保留有效历史 SHA-1）与多版本 `alternate_url_change_without_sha`（存空、不继承另一版本 SHA-1） | PASS（Task 范围） |
| X03 编码／BOM／空白／非法字段／Size／协议／有界读取 | 文件 `ReadRejectsInvalidUtf8AndDuplicateOptionalMarkers`、`ReadRejectsUnsupportedSchemesWithoutSkippingToALaterAddress`、`ReadRejectsInvalidSha1LengthsAndCharacters`、`ReadAcceptsMaximumValidSizeAndZero`、`ReadTreatsMissingEmptyAndOverflowingSizesAsUnavailable`、`ReadRejectsFilesOverTheBoundedInputLimit`、`ContentHashIncludesBomBytesWhileParsingTheSameManifest`、`ReadTreatsUnknownProtocolVersionsAsUnsupported`（version 0／2／1-beta → Unsupported）、`ReadRejectsConflictingProtocolVersions`（1+2、0+1、2+2 拒绝）；URL scheme 与 STRM 协议版本分别由 `ReadRejectsUnsupportedSchemesWithoutSkippingToALaterAddress` 与本行两个版本用例覆盖 | PASS（文件用例） |
| X05 信息不足跳过、mtime 不参与、签名变化算 URL 变化 | 单元 `UncomparableHashesUseOnlyDifferentValidSizes`、`ShaValidityCombinationsFollowTheDocumentedMatrix`、`SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability`、`ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest`；文件 `ContentHashIgnoresModifiedTimeRewriteAndSameContentReplay`；实机 `same_url_noncomparable_size_unchanged`、`replay_and_mtime_zero_probe` | PASS（Task 范围） |

证据限制（如实报告，不升级为 PASS）：T16 的远程代理（OpenList／JellyfinProxy）联调 NOT RUN，当前以本地媒体替换证明同 URL 内容变化分支；T01～T16 中依赖真实远程内容的部分未做外部联调；T10／T11 的换 URL 双侧无 SHA-1 分支仅有单元证据、实机 NOT RUN；T20／T25、B01／B02 与 X08／X09 的核心部分见本轮索引；真实批量、UI、外部代理及发布仍 NOT RUN。

B 独立证据索引：`.git/validation-evidence/198f4ff2accd5bc9fcd87518a9684b9d068de103/b-rereview-20261014-03/INDEX.md`。独立 C# 聚焦 65 passed／0 failed／0 skipped；实际未知／冲突协议六组输入的原生委托与无指纹已由控制 harness 核验；默认实机 JSON PASS、487.172 秒，原夹具／媒体／地址恢复且临时条目清理。T09～T12 的新增逻辑输入已逐项复现，仍无对应输入的实机分支保持 NOT RUN。

这些证据支持 B 对 Task 2.1 修正候选的审查，不替代逐行完整矩阵对账。B 第二轮独立复审已确认 R1／R2／R3 全部满足并裁定 Task 2.1 PASS；详细决定与固定快照见 [Slice 2 关闭记录](progress.md#slice-2-closed)。T01～T28、B01～B12 与 X01～X10 的当前分层状态按本页顶部矩阵记录；该历史 Task 2.1 没有运行外部代理／OpenList、批量任务、运行中共享／全局并发、其他 Jellyfin 版本或完整发布门槛，共享／全局上限核心随后由 Task 2.2 闭合。表中标注的是具体用例的分层执行状态，不单独代表完整产品矩阵整行验收；Task PASS 以完整独立审查决定为准。

按开发流程保留源码／工作区身份、精确命令、版本、隔离配置、耗时、日志及原生 ffprobe 计数。所有哈希／地址／媒体使用假数据。区分单元、真实 Jellyfin、压力夹具与外部代理；历史十万条模拟枚举不冒充当前至少 1000 项真实媒体库通过。

任务统计按检查对象（item_id＋source_key）去重，不把共享等待者当作多次实际 ffprobe。完成时需要数分为可靠成功与探测未完成；解析等检查阶段错误另外标注，计入未完成总数，避免不一致。首次信任计跳过；批量停止收尾统计已开始工作的实际成功／未完成，另报未开始／未遍历情况，不伪造 100%。已接受的 [Slice 3 合同快照](progress.md#slice-3-closed) 已改用去重候选 ID 数作为本轮分母，候选获取阶段 0%，对象分批结算推进；源统计等式及提前结束不补满不变。候选身份非事务快照，新增下轮发现、删除／移出安全结算，完整集合未读取余量可按 ID 计数，获取未完成时余量未知；具体换算由 B 在计划中明确。B01～B10、B12 有界模拟核心和 T24／T26 批量部分纳入 Slice 3；B11 完整扫描及真实大库留在 Slice 4。上述为合同修订时的责任分配；Slice 3 的实际结果以上方当前索引为准。

原生成功必须有失败对照，定时／停止／重启／并发要求真实证据。外部代理联调不可用时 BLOCKED／NOT RUN，不算 PASS。

## Slice 4 验收分配

本节保留 Required Outcome 的证据入口；当前最终结果及复用／新测界线统一见 [Closure Packet](progress.md#slice-4-closed)，已完成 Task 的计划／失败／命令／证据和 B 决定从合同指向的 Git 快照读取，完整合同以 [Slice 4](progress.md#slice-4-closed) 为准。

| Required Outcome | 当前状态 | 详情入口 |
|---|---|---|
| RO-1 单版本安装与恢复 | 最终证据见 Closure Packet，接受决定见 A Final Review | [安装包说明](package-installation.md)、[A Final Review](progress.md#slice-4-closed) |
| RO-2 至少 1000 项真实原生库（现存全部 1004 项） | 完整复用场景及成本已纳入本次 Final；聚焦 PARTIAL 单列 | [A Final Review](progress.md#slice-4-closed)、[大库验收入口](#slice-4-大库验收本地运行) |
| RO-3 完整扫描重叠 | 完整扫描与三源三阶段重启补证分别核验后纳入 Final | [Closure Packet](progress.md#slice-4-closed)、[A Final Review](progress.md#slice-4-closed) |
| 原 RO-4 实际代理播放链 | 按 2026-10-20 用户授权撤出当前验收；历史 NOT RUN，不计 PASS／无兼容声明 | [范围覆盖](scope.md#2026-10-20-用户授权撤出-jellyfinproxy-验收)、[当前交接](../TASK.md) |

### Slice 4 大库验收本地运行

当前大库门槛为至少 1000 个真实原生候选，使用现存全部 1004 个受支持库内源，在固定 Jellyfin 12.2.0／Linux x64 上串行完成必要场景；不截取为 1000，不再要求另跑 3000 级。2026-10-19 按用户后续授权调整已有脚本：显式传入 --reuse-workspace，默认只跑 unchanged；--count 默认 1000，表示下限，不是截取数量。只接受 package-env/runs 下已停止、无符号链接／SQLite 事务旁文件的保留工作区；核验来源后复制到本轮新归属目录，不接管旧 token、不建库、不扫描、不做全库主流准备。原库前后摘要对账，副本结束停止并保留；此复用方式适用于所有需要准备库的开发阶段，不以 Task／Slice 结束为清理条件。

复用场景：unchanged 验证现存完整指纹的未变轮；restart 增加重启后、任何 PlaybackInfo 前的完整持久化对账；baseline 依次跑首次信任、未变、重启，要求初始无指纹；**all 在已核验副本上执行完整行为**（首次信任、未变、跨四个真实 Guid 批次的 URL／内容 SHA-1／Size／缺流增量、真实同步查询窗口停止、已开始两项探测后的停止／收尾及收尾期间重跑、旧轮 Idle 后恢复、两轮未变、重启前后完整核对、变更源显式选源 PlaybackInfo），只对 12 个改写 URL 的对照做有界原生主流修复，不重建库、不重新扫描全库、不逐源重新准备已有主流。baseline 与 all 均可显式使用 --reset-copied-fingerprints，将新副本的原指纹库移入副本 baseline-backup 保留；原库不变。逐项核验全部支持源、3 个库内对照和范围外对照，以及五字段指纹、原生地址、必要主流、候选身份、实际探测数和结算统计。聚焦场景成功返回退出码 0，但总状态必须是 PARTIAL、focused_status=PASS、full_task_acceptance=NOT RUN；只有 all 成功时才可将 full_task_acceptance 置为 PASS，且仍不能代替 B 独立验收或 Slice Final。

先将下方 SHELL 变量设置为经过归属和来源核验的实际路径；ZIP 必须与本轮候选一致，不能随意换成默认目录里的另一个包。证据目录须全新或为空，端口须空闲；不指向生产或共享开发实例。

```bash
# PREPARED=已停止的 artifacts/package-env/runs/<run> 目录
# ZIP=候选 ZIP 路径，旁边保留发布 sidecar
# EVIDENCE=本轮新的 .git/validation-evidence/<source-sha>/<run-id> 目录
JF_PROBE_PACKAGE_PORT=18099 python3 scripts/run_isolated_large_library_integration.py \
  --package "$ZIP" --reuse-workspace "$PREPARED" \
  --evidence-dir "$EVIDENCE" --timeout-seconds 600
# 完整复用行为（首次信任→增量→查询中停止→探测停止收尾→恢复→重启→显式播放）：
# --scenario all --reset-copied-fingerprints --timeout-seconds 2400
# 首次信任／未变／重启聚焦验证时，追加：
# --scenario baseline --reset-copied-fingerprints
# 只检查未变并重启时，追加：--scenario restart
```

旧完整建库流程仅保留为显式 --fresh --scenario all 的兼容路径，不用于现存保留库。复用 all 的工具及全场景、聚焦补证／失败／修正和 B 独立审查完整保留于 `57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md`，用 git show 读取；其最终 B PASS 是当前 Task 层结论，早期 PARTIAL 和失败不回写为 PASS。当前接受事实见 [合同交接](progress.md#slice-4-closed)。准备数据持续复用，结果证据必须核验匹配输入，旧 Task PASS 不能代替最终候选的独立 Slice Final。

- 首次信任／未变零插件探测，URL／内容／Size／缺流小集合按源精确探测，候选逐身份和完整五字段／原生地址／主流独立对账。
- 查询中停止、分批停止、收尾期间再运行拒绝和恢复前旧基线保护分别验证；重启先只读比较完整预期，再显式选源播放。
- 准备、查询／集合、对象读取、执行与收尾成本分别记录；128 对象／8 消费者／启动并发上限须有相应证据，不把 O(N) ID 集合说成恒定总内存。
- 原始预期／实际状态、日志、资源样本和失败尝试在清理前外置保留；后补日志不能恢复已删除的状态快照，也不能把未执行步骤变成 PASS。

这些是保留门槛；Task 4.3 的 B PASS 不替代最终候选的独立 Slice Final。完整 C#／Python、包／扫描／大库与指定原生播放门禁仍由 B 承担；Developer 只运行直接影响的反馈。代理专属验收按用户授权不执行，不要求补代理构建、缓存、302 或代理客户端内容验证；其他格式／客户端／平台与 OpenList 专有行为保持各自未验证边界。

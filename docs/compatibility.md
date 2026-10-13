# 兼容性与接入验证

## 当前结论

当前只有固定组合上的 Slice 1 核心原型证据，没有发布包或多版本兼容声明。真实插件已用 Jellyfin Controller／Model `12.2.0`、`net10.0` 和 SDK `10.0.401` 构建，并在隔离 Jellyfin `12.2.0` 容器加载；镜像 digest、媒体服务和环境身份见 [环境交接](development-environment.md)。当前证据满足 Slice 1 的 Required Outcomes，正式产品与发布支持仍未验证。

B 对旧候选的 FIX REQUIRED 保留为历史；修正候选 `2b1e1b5bcf77b06997fabed5a31147838db16b47` 经 B 独立审查，Task 1.1 PASS。保存关联和指定真实对照已满足，单独 Slice Final 已完成；[A 最终审查](../SLICE.md#a-final-review) 裁定 Slice 1 PASS / CLOSED，后续 Slice 尚未激活。播放取消范围遵循 A 的 RESCOPE：保留原生取消异常处理，不要求成功返回后的额外取消检查或人为注入实机门槛；共享／批量执行的取消保护留在 Slice 2／3。

| 候选源码 | 已记录标签提交 | 定位用途 |
|---|---|---|
| Jellyfin v10.11.8 | `2c62d40f0d13926874eef9118a95be0dcee4e659` | 旧规划候选；此前读取 global.json 为 SDK 9.0.0／latestMinor，仍需目标框架与包核实 |
| Jellyfin v12.2 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6` | V4.2 引用的优先调研候选；不是本项目已经支持的版本 |

先固定一个隔离服务器版本／镜像 digest、相应源码 SHA、框架、依赖和 SDK，再构建。不能由两组标签推定一个插件包兼容两版。

## Task 1.1 源码定位（2026-10-13）

官方发布页将 v12.2 标为最新稳定版本；发布提交为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。本轮网页核对到：

- [`MediaSourceManager.GetPlaybackMediaSources`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Library/MediaSourceManager.cs#L177-L198) 在 `allowMediaProbe` 为 true 且项目为 `.strm` 时会调用 `RefreshMetadata`，设置 `EnableRemoteContentProbe=true` 和 `FullRefresh`，再重新读取静态媒体源；缺主视频／音频流也会进入该刷新分支。源码定位确认原生播放接入候选，但不能证明包装 DI、单例所有权、实际探测计数或失败语义。
- [`ProbeProvider.FetchVideoInfo`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs#L234-L332) 对可探测视频 STRM 调用 `ProbeVideo`，并由原生 Provider 从 STRM 读取远程地址。该源码路径仍不能替代本次结果、持久化主流和地址的实机关联验证。
- [`MediaBrowser.Controller.csproj`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Controller/MediaBrowser.Controller.csproj#L36) 目标框架为 `net10.0`。源码定位阶段尚未固定 SDK、镜像、依赖或可加载插件；后续 Task 1.1 的固定组合与原型加载证据见下节。

先前执行环境缺少 SDK／可用 Docker daemon 的记录保留在 [Task 1.1 历史交接](../TASK.md) 及 [环境交接](development-environment.md)；阻塞已解除，真实插件构建和隔离加载证据见下节。

已对固定源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6` 检查 `MediaSourceManager`、Provider、`MediaInfoHelper`、任务模型与任务调度代码。源码定位是接口证据，不替代插件行为验收。

## 播放与批量取消语义

以下限定固定 Jellyfin `12.2.0`／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`，版本变化后重新核对。A 已将事实与最新实质范围调整写入 [Slice 合同](../SLICE.md#a-播放取消范围调整2026-10-13)；没有将源码存在或未运行场景改为实机 PASS。

| 入口／动作 | 固定源码行为 | 插件与验收边界 |
|---|---|---|
| PlaybackInfo 取源 | [`MediaInfoHelper`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Helpers/MediaInfoHelper.cs#L148) 传 `true` 和 `CancellationToken.None` | 是否探测由媒体状态与插件决策决定；客户端退出不沿此入口取消探测，不要求客户端取消实机场景 |
| 实际流请求取源 | [`StreamingHelpers`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Helpers/StreamingHelpers.cs#L129) 传调用 token 和 `allowMediaProbe=false` | 原样保留权限，不为测试取消而升级为允许探测 |
| 报告停止播放 | [`PlaystateController`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Controllers/PlaystateController.cs#L249) 停止关联转码并更新会话 | 该处理不向先前 PlaybackInfo 探测传取消 token；插件不新增停止事件到探测的关联 |
| 停止计划任务 | [`ScheduledTasksController`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Controllers/ScheduledTasksController.cs#L122) 调用任务取消；[`ScheduledTaskWorker`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/ScheduledTasks/ScheduledTaskWorker.cs#L331) 把自身 token 传入执行并在停止时取消 | Slice 3 验证停止分页／排队／自身等待；仍有播放等待者的共享执行不受错误取消 |

客户端退出不等于执行取消。本次原生探测继续成功、结果已保存且 Manifest 一致时，仍可按全部提交条件接受指纹。执行本身收到取消时保留旧基线；取消一个共享等待者不阻止仍服务其他等待者的有效执行提交。

Slice 1 不再要求人为传入可取消 token 的真实原生取消验证，也不要求原生成功返回后的额外取消检查；原调用 token／权限与原生取消异常处理保留。旧注入取消 NOT RUN 和假对象 FAIL 记录未改为 PASS，仅退出当前门槛。Slice 2 对实际可取消共享执行验证探测中与提交前保护，Slice 3 验证原生批量停止。更换版本、入口或新增取消源后重新核对合同。

## Task 1.1 原型实测（2026-10-13）

测试输入为隔离临时库的手写版本化 STRM、两个字节完全相同的本地合成 MP4、隔离 Jellyfin `12.2.0` 与本地媒体服务。STRM 临时写入该媒体字节的实际 SHA-1 和 Size；换 URL 场景保留两者不变。运行脚本在结束时恢复原 STRM，并重新通过 Jellyfin 同步原地址。

- 固定组合：SDK `10.0.401`、目标 `net10.0`、Jellyfin.Controller／Model `12.2.0`、源码 SHA `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。服务器和本地媒体服务镜像 digest 见 [开发环境固定输入](development-environment.md#已运行环境证据)。
- 插件在三次隔离容器启动后均为 Active。首次信任接管、未变化播放及地址变化后的未变化播放分别记录 0、0、0 次匹配原生编码器探测，返回必要 Video／Audio 主流。
- 同 SHA-1／Size 的 URL 改变记录 1 次匹配原生 `IMediaEncoder.GetMediaInfo` 调用，结果含 Video／Audio 主流；PlaybackInfo 返回新 URL（证据仅记录 SHA-256），之后容器重启仍返回新 URL／主流，且没有新探测。
- 不存在的新 URL 返回 HTTP 500，不被当成成功；同一失败 URL 的第二次 PlaybackInfo 再记录 1 次探测。控制逻辑与单元测试验证旧指纹未被失败结果替代。
- `IMediaSourceManager` 全接口委托与通用单例释放有单元回归，四个核心服务注册已由固定源码与实际接入审查核对；隔离实例实测普通媒体、旧 STRM、Live TV、插件禁用后原生播放及重新启用。各路径均返回有效媒体源且未产生插件 STRM 优化事件。
- 对修改后 STRM 的实际 `/Videos/{itemId}/stream?static=true` 请求返回 HTTP 200 与 20,995 字节，没有插件探测事件；后续 PlaybackInfo 对同一变化 URL 执行 1 次匹配探测。这是真实 `allowMediaProbe=false` 流入口验证。公共 PlaybackInfo 固定传 `true`，因此未伪造 PlaybackInfo 的 false 参数调用。
- 竞态用隔离媒体服务的延迟 URL：确认探测已开始后修改 STRM，PlaybackInfo 返回 HTTP 500，日志记录 1 次匹配调用及保留指纹；修复后的当前 Manifest 随后以 1 次探测成功恢复。
- 手动 FullRefresh 返回 HTTP 204，保存后条目 ETag 改变；该项手动刷新未产生本地媒体 GET 或进程级 `GetMediaInfo` 调用，后续变化地址的 PlaybackInfo 仍执行 1 次探测。三次同 SHA-1／Size 地址切换的 PlaybackInfo 原生刷新均记录 1 次匹配调用和 1 次合成媒体 GET；其中两次重复运行还分别由进程级计数观察到 1 次 `GetMediaInfo`。调用时间、原始计数及限制见候选证据索引；这是固定合成夹具的调用路径观察，不是通用性能基准。

目标版本任务接口已从固定源码核实：`IScheduledTask.ExecuteAsync(IProgress<double>, CancellationToken)` 提供取消与百分比进度；`GetDefaultTriggers()` 提供默认触发；`IConfigurableScheduledTask` 暴露隐藏、启用和日志设置。`ApplicationHost.RunStartupTasksAsync` 通过 `GetExports<IScheduledTask>(false)` 添加任务，`TaskManager` 建立 Worker；`ScheduledTasksController` 提供管理员手动运行、停止和触发器配置。Worker 读取已有触发器配置，否则使用 `GetDefaultTriggers()`；若该方法抛出异常会回退到每日触发，因此无自动时间要求必须正常返回空序列，不能抛异常。该接口研究未实现或运行本插件任务。

B 另在隔离实例临时开启 Debug，两次地址变化都观察到 `ProbeProvider`、`MovieNfoProvider`、`TrickplayProvider` 各调用一次，ETag 改变，匹配探测和合成媒体 GET 各一次，PlaybackInfo 为 91／75 ms。日志级别与 STRM 已恢复。提供器调用不证明远程下载／Trickplay 生成，不提供开销分项或生产性能承诺；原始脱敏证据见 Closure Packet 引用的 B 索引。

上述为有限核心原型及独立 Slice Final 证据，A 已据此关闭 Slice 1；发布包、多版本／广泛媒体兼容和外部代理联调仍未验证。完整矩阵状态继续按 [测试矩阵](test-matrix.md) 与 [Task 历史指针](../TASK.md) 区分。

## Slice 1 风险门槛

A 环境准备及 Task 1.1 原型后续：SDK、固定源码、镜像 digest、隔离服务、本地媒体链路和真实插件 PlaybackInfo 均已有分项证据。下表为 B 核对且经 A 最终审查接受的原型门槛事实。官方镜像没有 revision 标签，镜像整体源码构建溯源仍有限；NuGet nuspec repository commit 已与固定源码 SHA 核对一致。

| 问题 | 必须取得的证据 | 状态 |
|---|---|---|
| 核心 DI 接入 | 注册顺序、单一原生实例、无循环依赖、释放所有权、全接口委托、启动／关闭、普通媒体／直播 | PASS；接口／通用生命周期回归、固定注册与隔离对照已独立核对 |
| 跳过重复探测 | 未变化且已有主流的版本化 STRM 二次播放 ffprobe 零增量，原生媒体源有效 | B 隔离复现 0 匹配调用及有效主流；该正常分支 PASS |
| 主动原生探测 | 变化时实际执行，包含 URL 改变且 SHA-1 相同；不靠 true 参数猜测 | B 复现同 SHA-1／Size URL 变化 1 次匹配调用；该正常分支 PASS |
| 成功与指纹提交 | 真成功、故意失败而保留旧流、Manifest 再变的对照；新结果已保存后才提交；原生取消异常保留基线 | PASS；独立保存失败 harness、原生事务定位、成功保存及真实失败／竞态／恢复 |
| 地址／流持久化 | URL 改变后原生探测并保存，当次 PlaybackInfo 新地址，重启仍有效且有必要主流；保存失败明确 | PASS；当次／重启保存与失败保流重试已独立复验；内部数据库故障未注入 |
| 探测权限／禁用 | allowMediaProbe=false 各分支不执行；禁用／旧 STRM／手动刷新原生对照 | PASS；真实 false 流入口、禁用、旧 STRM、手动 FullRefresh 已独立复验；公共 PlaybackInfo 不提供 false 参数 |

Task 1.1 PASS；全部 Outcomes／Surfaces 与单独 Slice Final 经 A 最终审查接受，Slice 1 PASS / CLOSED。当前无活动实施 Task，历史失败按原事实保留。外部 JellyfinProxy／OpenList 联调、完整 T01～T28 与 B01～B12 矩阵仍未运行；本原型使用 Jellyfin 已有 FFmpeg／ffprobe。

## 后续真实运行门槛

Slice 3 实测任务注册、默认无触发时间、原生手动／定时／停止、进度与播放共享协调。Slice 4 实测大规模分页内存、并发、媒体库扫描竞态、重启和隔离 JellyfinProxy 302。当前均 NOT RUN；接口存在不能替代这些验收。

每个发布包只声明已实测版本范围，核心 API／DI 改变后重新验证。发布材料包含准确 SDK／依赖、安装／禁用恢复步骤与客户端／代理未完成项。

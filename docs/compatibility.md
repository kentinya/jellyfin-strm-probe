# 兼容性与接入验证

## 当前结论

当前只有固定组合上的 Task 1.1 原型证据，没有发布包或多版本兼容声明。真实插件已用 Jellyfin Controller／Model `12.2.0`、`net10.0` 和 SDK `10.0.401` 构建，并在隔离 Jellyfin `12.2.0` 容器加载；镜像 digest、媒体服务和环境身份见 [环境交接](development-environment.md)。此次证据覆盖插件启动及指定 STRM PlaybackInfo 行为，不代表 Slice 1 的所有 Required Outcomes 或正式发布支持。

| 候选源码 | 已记录标签提交 | 定位用途 |
|---|---|---|
| Jellyfin v10.11.8 | `2c62d40f0d13926874eef9118a95be0dcee4e659` | 旧规划候选；此前读取 global.json 为 SDK 9.0.0／latestMinor，仍需目标框架与包核实 |
| Jellyfin v12.2 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6` | V4.2 引用的优先调研候选；不是本项目已经支持的版本 |

先固定一个隔离服务器版本／镜像 digest、相应源码 SHA、框架、依赖和 SDK，再构建。不能由两组标签推定一个插件包兼容两版。

## Task 1.1 源码定位（2026-10-13）

官方发布页将 v12.2 标为最新稳定版本；发布提交为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。本轮网页核对到：

- [`MediaSourceManager.GetPlaybackMediaSources`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Library/MediaSourceManager.cs#L2479-L2513) 在 `allowMediaProbe` 为 true 且项目为 `.strm` 时会调用 `RefreshMetadata`，设置 `EnableRemoteContentProbe=true` 和 `FullRefresh`，再重新读取静态媒体源；缺主视频／音频流也会进入该刷新分支。源码定位确认原生播放接入候选，但不能证明包装 DI、单例所有权、实际探测计数或失败语义。
- [`ProbeProvider.FetchVideoInfo`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs#L1498-L1601) 对可探测视频 STRM 调用 `ProbeVideo`，并由原生 Provider 从 STRM 读取远程地址。该源码路径仍不能替代本次结果、持久化主流和地址的实机关联验证。
- [`MediaBrowser.Controller.csproj`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Controller/MediaBrowser.Controller.csproj#L369-L384) 目标框架为 `net10.0`。本轮未取得该提交的 SDK 固定版本，也未确定服务器镜像 digest、插件依赖版本或可加载包。

先前执行环境缺少 SDK／可用 Docker daemon 的记录保留在 [Task 1.1 历史交接](../TASK.md) 及 [环境交接](development-environment.md)；阻塞已解除，真实插件构建和隔离加载证据见下节。

已对固定源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6` 检查 `MediaSourceManager`、Provider、`MediaInfoHelper`、任务模型与任务调度代码。源码定位是接口证据，不替代插件行为验收。

### Task 1.1 原型实测（2026-10-13）

测试输入为隔离临时库的手写版本化 STRM、两个字节完全相同的本地合成 MP4、隔离 Jellyfin `12.2.0` 与本地媒体服务。STRM 临时写入该媒体字节的实际 SHA-1 和 Size；换 URL 场景保留两者不变。运行脚本在结束时恢复原 STRM，并重新通过 Jellyfin 同步原地址。

- 固定组合：SDK `10.0.401`、目标 `net10.0`、Jellyfin.Controller／Model `12.2.0`、源码 SHA `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。服务器和本地媒体服务镜像 digest 见 [开发环境固定输入](development-environment.md#已运行环境证据)。
- 插件在三次隔离容器启动后均为 Active。首次信任接管、未变化播放及地址变化后的未变化播放分别记录 0、0、0 次匹配原生编码器探测，返回必要 Video／Audio 主流。
- 同 SHA-1／Size 的 URL 改变记录 1 次匹配原生 `IMediaEncoder.GetMediaInfo` 调用，结果含 Video／Audio 主流；PlaybackInfo 返回新 URL（证据仅记录 SHA-256），之后容器重启仍返回新 URL／主流，且没有新探测。
- 不存在的新 URL 返回 HTTP 500，不被当成成功；同一失败 URL 的第二次 PlaybackInfo 再记录 1 次探测。控制逻辑与单元测试验证旧指纹未被失败结果替代。
- `IMediaSourceManager` 全接口委托、核心注册迁移及单例释放各有单元测试；隔离实例实测实际注册后的播放路径。普通媒体、直播、旧 STRM、配置关闭和 `allowMediaProbe=false` 的边界由原生委托单元测试覆盖，未声明为独立真实 Jellyfin 行为验收。
- 插件配置关闭时会直接委托原调用权限；上游 StreamingHelpers 的可取消取源调用传 `allowMediaProbe=false`，PlaybackInfo 则传 `CancellationToken.None`。因此插件拒绝提升 false 权限的控制由单元测试覆盖，而真实 PlaybackInfo 取消本次探测无法通过目标版本公共调用路径触发。
- 单次合成媒体端到端延时记录在候选验证原始输出中。地址变化会触发 Jellyfin 原生 `FullRefresh`（源码实现含完整 metadata refresh）；本原型没有更窄的公开原生探测入口，也未尝试绕过它。该单条延时只供确认调用路径，不作为性能基准。

目标版本任务接口已从固定源码核实：`IScheduledTask.ExecuteAsync(IProgress<double>, CancellationToken)` 提供取消与百分比进度；`GetDefaultTriggers()` 提供默认触发；`IConfigurableScheduledTask` 暴露隐藏、启用和日志设置。`ApplicationHost.RunStartupTasksAsync` 通过 `GetExports<IScheduledTask>(false)` 添加任务，`TaskManager` 建立 Worker；`ScheduledTasksController` 提供管理员手动运行、停止和触发器配置。Worker 读取已有触发器配置，否则使用 `GetDefaultTriggers()`；若该方法抛出异常会回退到每日触发，因此无自动时间要求必须正常返回空序列，不能抛异常。该接口研究未实现或运行本插件任务。

上述结果是有限原型证据，不是兼容性认证、发布包验证、外部代理联调或 Slice Final。完整矩阵状态仍按 [测试矩阵](test-matrix.md) 与 Task 1.1 完成报告分别审查。

## Slice 1 风险门槛

A 环境准备后续：权限已解除，SDK 安装、固定源码检出、镜像 digest、隔离服务启动／访问及本地 HTTP 原生 ffprobe 均已验证；NuGet 引用样例 restore／Release build／运行 PASS。前述 Developer 诊断保持为历史事实，环境结果不构成插件实机兼容结论。官方镜像没有 revision 标签，镜像整体源码构建溯源仍需补证；NuGet nuspec repository commit 已与固定源码 SHA 核对一致。

| 问题 | 必须取得的证据 | 状态 |
|---|---|---|
| 核心 DI 接入 | 注册顺序、单一原生实例、无循环依赖、释放所有权、全接口委托、启动／关闭、普通媒体／直播 | NOT RUN |
| 跳过重复探测 | 未变化且已有主流的版本化 STRM 二次播放 ffprobe 零增量，原生媒体源有效 | NOT RUN |
| 主动原生探测 | 变化时实际执行，包含 URL 改变且 SHA-1 相同；不靠 true 参数猜测 | NOT RUN |
| 成功与指纹提交 | 真成功、故意失败而保留旧流、取消、Manifest 再变的对照；新结果已保存后才提交 | NOT RUN |
| 地址／流持久化 | URL 改变后原生探测并保存，当次 PlaybackInfo 新地址，重启仍有效且有必要主流；保存失败明确 | NOT RUN |
| 探测权限／禁用 | allowMediaProbe=false 各分支不执行；禁用／旧 STRM／手动刷新原生对照 | NOT RUN |

找不到可靠成功信号时记录 BLOCKED，不继续扩大产品。FullRefresh 若触发其他提供器，记录额外开销及更精确原生入口是否可用。不新增另一个 FFmpeg／ffprobe。

## 后续真实运行门槛

Slice 3 实测任务注册、默认无触发时间、原生手动／定时／停止、进度与播放共享协调。Slice 4 实测大规模分页内存、并发、媒体库扫描竞态、重启和隔离 JellyfinProxy 302。当前均 NOT RUN；接口存在不能替代这些验收。

每个发布包只声明已实测版本范围，核心 API／DI 改变后重新验证。发布材料包含准确 SDK／依赖、安装／禁用恢复步骤与客户端／代理未完成项。

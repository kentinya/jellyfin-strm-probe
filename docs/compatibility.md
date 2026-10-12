# 兼容性与接入验证

## 当前结论

尚无实测支持版本或插件包。目标服务器、SDK、框架及 NuGet 依赖在 Task 1.1 核实；源码定位不能当成可加载或二进制兼容证据。

| 候选源码 | 已记录标签提交 | 定位用途 |
|---|---|---|
| Jellyfin v10.11.8 | `2c62d40f0d13926874eef9118a95be0dcee4e659` | 旧规划候选；此前读取 global.json 为 SDK 9.0.0／latestMinor，仍需目标框架与包核实 |
| Jellyfin v12.2 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6` | V4.2 引用的优先调研候选；不是本项目已经支持的版本 |

先固定一个隔离服务器版本／镜像 digest、相应源码 SHA、框架、依赖和 SDK，再构建。不能由两组标签推定一个插件包兼容两版。

V4.2 声明 v12.2 有 IScheduledTask、IConfigurableScheduledTask 和 ILibraryPostScanTask；本轮网页读取任务源码未成功，仍需固定源码核实。首版只计划前两者，排除扫描后自动触发。官方来源及读取状态见 [references.md](references.md)。

## Slice 1 风险门槛

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

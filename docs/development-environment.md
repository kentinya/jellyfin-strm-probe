# Task 1.1 开发环境交接

2026-10-13，A 按用户要求准备环境。当前状态：**准备工具已交付；实际 SDK 安装与隔离服务仍 BLOCKED**。本文件不是 B 产品审查或 A Final Review，不改变 Task 1.1 的 Base、Scope 或 T4 门槛。

## 固定输入

| 输入 | 当前选择／状态 |
|---|---|
| 宿主环境 | Debian 12，Linux x64；Python 3、curl、tar、Git、Docker CLI 和 Compose 可用 |
| SDK | `10.0.401`，根 `global.json` 禁止滚动升级；安装 NOT RUN／下载 BLOCKED |
| SDK 归档 | 官方 Linux x64 tar.gz；URL 和 SHA-512 写入 `dev/environment-spec.json` |
| Jellyfin | V4.2 优先候选 `12.2`；实际镜像拉取、加载及版本确认 BLOCKED |
| 源码 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6`；本地检出 NOT RUN |
| 服务器／媒体服务镜像 digest | NOT SET；首次成功 provision 后落入本地 `images.lock.json`，后续启动只用 digest |
| 插件 NuGet 依赖 | NOT SET；由 Developer 在真实原型中核实并锁定，不能从源码版本猜测包存在 |

SDK 版本、下载地址和校验值来自 [Microsoft 官方发布元数据](https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/10.0/releases.json)。目标源码的 [global.json](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/global.json) 写出 `10.0.0`／`latestMinor`，本地环境具体固定为 `10.0.401`。这只确定构建工具输入，不证明插件已经兼容。

## 当前执行限制与宿主环境条件

实测当前沙箱：SDK 不存在；Docker socket 返回 permission denied；SDK／GitHub 域名解析失败；创建 IPv4 和 Unix socket 均返回 Operation not permitted。因此即使只下载 SDK，也不能在当前沙箱完成真实服务验证。

运行下列命令的宿主会话需要：

- 能创建 socket、访问本机 `/var/run/docker.sock`，以及访问隔离 Jellyfin 的本机 `18096` 端口。
- 能下载官方 SDK、GitHub 源码、Docker 镜像，访问 NuGet HTTPS／包 CDN；或提前提供固定 SDK 归档、镜像与依赖缓存。
- 允许写入本仓库及 `artifacts/dev-env`。脚本不修改系统安装、socket 权限或已有 Jellyfin 配置。

这些能力由宿主机／任务执行配置提供，仓库脚本无法解除当前沙箱限制。无须向开发者提供生产账户、生产媒体或生产 Docker 配置；无需开放生产服务的访问。

## 准备与运行

在具备上述能力的会话中，从仓库根目录运行：

```bash
python3 scripts/development_environment.py provision
python3 scripts/development_environment.py doctor
bash scripts/dotnet-local --info
python3 scripts/development_environment.py up
curl --fail http://127.0.0.1:18096/System/Info/Public
```

`provision` 先下载并验证固定 SDK 的 SHA-512，再解压到仓库内；随后拉取两个镜像并记录 digest。任何一步失败返回 2，不写入可用环境或产品 PASS。支持先单独运行 `sdk`／`images`；离线 SDK 使用 `sdk --sdk-archive /path/to/official.tar.gz`，仍检查同一校验值。

`doctor` 逐项报告 SDK、Docker、Compose、监听能力、DNS、NuGet HTTPS 和镜像锁。它不验证插件构建、不确认依赖已恢复，也不代替服务健康检查。`up` 使用已锁定的本机镜像，禁止自动重新解析标签；端口冲突直接失败，不停止占用端口的其他服务。脚本强制使用本机 Docker socket，忽略外部 Docker endpoint。

隔离实例使用 [Jellyfin 官方容器方式](https://jellyfin.org/docs/general/installation/container/)，不增加插件自带 FFmpeg。只有 `127.0.0.1:18096` 发布到宿主机；不使用 host network、特权模式、设备挂载或生产目录。专用内部网络不允许测试服务器访问外部元数据服务。数据、缓存、手写 STRM 和媒体均放在 `artifacts/dev-env/`；全部被 Git 忽略，媒体挂载只读。媒体服务地址为容器网络内 `http://media:8080/fixture.mp4`，不发布到宿主机。

浏览器访问 `http://127.0.0.1:18096` 完成隔离实例向导，使用仅属于此测试实例的用户。核对 Public Info 的 `Version` 确为 `12.2`；不匹配则停止并保留证据，不换其他版本继续算通过。新增临时库只选 `/media/strm` 或 `/media/local`，关闭联网元数据、写回媒体目录和无关扫描产物。插件放入该实例的 `artifacts/dev-env/config/plugins/`，不得复制到生产插件目录。

停止／重启保留本地状态，可用于重启持久化验收：

```bash
python3 scripts/development_environment.py status
python3 scripts/development_environment.py stop
python3 scripts/development_environment.py up
```

仅操作由仓库路径派生的专用 Compose project；检测到项目容器挂载其他目录时拒绝启动或停止。不提供删除数据、清理镜像或全局 Docker 清理入口。

## 开发者下一步

1. SDK、镜像和隔离服务就绪后，检出上述完整源码 SHA，记录源码、镜像锁及服务器 Public Info。镜像标签不证明构建源码身份，须核对镜像 revision／官方构建来源并保留实际 image ID／digest。
2. 用隔离实例自带的原生 FFmpeg 制作短本地媒体，放在 `artifacts/dev-env/media`；检查媒体服务能响应有效请求。手工编写协议 v1 STRM，仅使用本地测试地址和固定假 SHA-1／Size，不开发生成器、不下载真实媒体计算哈希。
3. 创建 Task 内的最小 solution／插件／测试项目，核实 `net10.0` 与目标 NuGet 依赖，补真实 restore／Release build／test／format 命令及依赖锁。统一使用 `bash scripts/dotnet-local ...`。
4. 原 Task T4 门槛、B 独立关键行为验证和 Slice Final 均保留。服务启动不是插件加载成功，媒体服务请求数不是 ffprobe 调用数；DI、探测成功、URL 保存和重启仍需各自真实证据。

本轮只提供环境工具及事实交接，原 Developer 阻塞报告仍保留，Task 状态不由 A 冒充 B 改为 PASS。网络／Docker／监听限制解除后开发者可继续原 Task，不必重新申请已授权范围。

原始本机证据目录：`.git/validation-evidence/fd26ffa370a126b360a7eb1806f16ee5e4c4f561/a-environment-20261013/`。工具测试与 Compose 静态配置验证仅证明脚本边界，真实安装／服务／产品验收尚未通过。

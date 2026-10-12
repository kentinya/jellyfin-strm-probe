# Task 1.1 开发环境交接

2026-10-13，A 按用户要求准备环境。当前状态：**SDK、固定源码、NuGet 引用编译和隔离 Jellyfin／媒体服务已验证可用**。之前的权限阻塞已经解除。本文件不是 B 产品审查或 A Final Review，不改变 Task 1.1 的 Base、Scope 或 T4 门槛。

## 固定输入

| 输入 | 当前选择／状态 |
|---|---|
| 宿主环境 | Debian 12，Linux x64；Python 3、curl、tar、Git、Docker CLI 和 Compose 可用 |
| SDK | `10.0.401`，根 `global.json` 禁止滚动升级；官方 SHA-512 校验、安装及版本检查 PASS |
| SDK 归档 | 官方 Linux x64 tar.gz；URL 和 SHA-512 写入 `dev/environment-spec.json` |
| Jellyfin | 官方镜像标签 `12.2`，实际 Public Info 为 `12.2.0`；原生服务启动及本机访问 PASS |
| 源码 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6`；本地检出 `artifacts/dev-env/source` 并核对 HEAD |
| 服务器／媒体服务镜像 digest | 已固定于本地 `artifacts/dev-env/images.lock.json`，后续启动只用 digest；精确值见下表 |
| 插件 NuGet 依赖 | 环境样例已恢复并编译 `Jellyfin.Controller`／`Jellyfin.Model` `12.2.0`，nuspec repository commit 与固定源码一致；产品项目及产品依赖锁尚未创建 |

SDK 版本、下载地址和校验值来自 [Microsoft 官方发布元数据](https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/10.0/releases.json)。目标源码的 [global.json](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/global.json) 写出 `10.0.0`／`latestMinor`，本地环境具体固定为 `10.0.401`。这只确定构建工具输入，不证明插件已经兼容。

## 权限复测与宿主环境条件

此前沙箱中 SDK 不存在、Docker socket 拒绝访问、DNS 失败、socket 创建被禁止。用户调整配置并重新恢复会话后，Docker、Compose、本地监听、下载域名和 NuGet HTTPS 均已实测 PASS；SDK 与镜像已成功准备。旧阻塞记录保留为历史，不能当成当前仍缺环境。

运行下列命令的宿主会话需要：

- 能创建 socket、访问本机 `/var/run/docker.sock`，以及访问隔离 Jellyfin 的本机 `18096` 端口。
- 能下载官方 SDK、GitHub 源码、Docker 镜像，访问 NuGet HTTPS／包 CDN；或提前提供固定 SDK 归档、镜像与依赖缓存。
- 允许写入本仓库及 `artifacts/dev-env`。脚本不修改系统安装、socket 权限或已有 Jellyfin 配置。

这些能力由宿主机／任务执行配置提供。当前已满足；不要求生产账户、生产媒体或生产 Docker 配置。

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

隔离实例使用 [Jellyfin 官方容器方式](https://jellyfin.org/docs/general/installation/container/)，不增加插件自带 FFmpeg。只有 `127.0.0.1:18096` 发布到宿主机；不使用 host network、特权模式、设备挂载或生产目录。媒体服务只接专用内部网络；Jellyfin 另接专用 frontend 桥接网络，用于发布本机端口。纯内部网络的首次实测未发布端口，因此修正为双网络；frontend 不构成出网隔离保证。临时库的远程元数据／图片提供器已通过类型配置禁用，测试实例的插件仓库列表已设为空。数据、缓存、手写 STRM 和媒体均放在 `artifacts/dev-env/`；全部被 Git 忽略，媒体挂载只读。媒体服务地址为容器网络内 `http://media:8080/fixture.mp4`，不发布到宿主机。

当前实例已完成向导，管理员用户名 `probe-dev`，随机口令保存在 `artifacts/dev-env/credentials.local.json`（权限 `0600`，Git 忽略）；该文件不进入证据或提交。已建立 `Probe STRM Fixtures` 与 `Probe Local Fixtures`，只指向 `/media/strm` 和 `/media/local`，关闭实时监控、远程元数据／图片、写回和无关扫描产物。API 登录验证使用标准 `Authorization: MediaBrowser ...` 头，携带 Token 的授权头不打印。

开发者在宿主机浏览器访问 `http://127.0.0.1:18096`。其他机器使用 SSH 本地端口转发，不开放公网端口。重新创建空实例时需要完成向导；核对 Public Info 的 `Version` 为 `12.2.0`。插件放入该实例的 `artifacts/dev-env/config/plugins/`。

停止／重启保留本地状态，可用于重启持久化验收：

```bash
python3 scripts/development_environment.py status
python3 scripts/development_environment.py stop
python3 scripts/development_environment.py up
```

仅操作由仓库路径派生的专用 Compose project；检测到项目容器挂载其他目录时拒绝启动或停止。不提供删除数据、清理镜像或全局 Docker 清理入口。

## 开发者下一步

1. 已有固定源码、SDK、镜像锁和 Public Info，可从 `artifacts/dev-env/source` 开始核查接口。镜像标签不证明构建源码身份；该镜像没有 revision 标签。已记录实际 image ID／digest，NuGet nuspec 的 repository commit 与源码一致；镜像整体源码构建溯源仍需在 Task 证据中补齐。
2. 已用实例自带的 FFmpeg `8.1.3-Jellyfin` 制作两秒本地媒体：`media/fixture.mp4` 与相同字节的 `fixture-alt.mp4`；手写 `strm/Environment Fixture.strm` 使用协议 v1、本地地址、固定假 SHA-1 和实际字节 Size。原生 ffprobe 通过 HTTP 读出 H.264／AAC，证明基础媒体链路；这不是插件探测成功信号或跳过计数证据。
3. 创建 Task 内的最小 solution／插件／测试项目，核实 `net10.0` 与目标 NuGet 依赖，补真实 restore／Release build／test／format 命令及依赖锁。统一使用 `bash scripts/dotnet-local ...`。
4. 原 Task T4 门槛、B 独立关键行为验证和 Slice Final 均保留。服务启动不是插件加载成功，媒体服务请求数不是 ffprobe 调用数；DI、探测成功、URL 保存和重启仍需各自真实证据。

本轮提供已运行环境及事实交接，原 Developer 阻塞报告保留为历史，Task 状态仍为 READY FOR B REVIEW，不由 A 冒充 B 改为 PASS。环境阻塞已解除；B 可据证据核查后由 Developer 恢复原 Task 实施，无须重新申请已授权范围。

## 已运行环境证据

| 镜像 | 实际固定引用 |
|---|---|
| Jellyfin | `jellyfin/jellyfin@sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037` |
| 本地媒体 HTTP 服务 | `python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89` |

环境构建样例位于忽略目录 `artifacts/dev-env/build-smoke`，不是产品原型。`restore --use-lock-file`、Release build、运行引用检查均 PASS，0 编译警告／错误；真实产品 solution、插件加载、DI、成功信号、跳过计数、播放 URL 持久化和 T4 产品门槛仍 NOT RUN。工具回归 30/30 PASS，其中 6 项覆盖环境边界。

样例实际命令：

```bash
bash scripts/dotnet-local restore artifacts/dev-env/build-smoke/build-smoke.csproj --use-lock-file
bash scripts/dotnet-local build artifacts/dev-env/build-smoke/build-smoke.csproj --configuration Release --no-restore
bash scripts/dotnet-local run --project artifacts/dev-env/build-smoke/build-smoke.csproj --configuration Release --no-build
```

最终停止／启动后，Public Info 的服务器身份与 `12.2.0` 版本保持一致；测试账户可再次登录，两个库及禁用远程提供器／插件仓库的配置保持，原生 HTTP ffprobe 再次返回 H.264／AAC。当前实例保持运行，`status` 显示 Jellyfin healthy；这不替代 Task 的播放地址与流重启持久化验收。

当前原始本机证据目录：`.git/validation-evidence/c3260eb70cb28176946f147ad3acee5d40a4dd10/a-env-ready-20261013/`。首次内部网络端口不可用、初始化的旧授权头 HTTP 400／401，以及重启期间过早执行版本命令的失败均保留，并另存修正后的成功记录；不隐藏首次失败。旧权限阻塞证据仍在此前交接目录。镜像、源码、包锁、样例输入及原始日志仅本机可读，不是远程 CI 产物。

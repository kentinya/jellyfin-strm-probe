# Jellyfin STRM Probe Optimizer

**一个为版本化视频 STRM 减少重复媒体探测的 Jellyfin 插件。**

播放时自动检查 STRM 的 URL、内容 SHA-1 和文件大小：未变化时复用已有媒体信息，需要更新时调用 Jellyfin 原生探测，保存新的播放地址和媒体流。

[下载安装](https://github.com/kentinya/jellyfin-strm-probe/releases/tag/v0.1.0) · [安装与恢复](docs/package-installation.md) · [配置说明](docs/core-configuration.md) · [兼容性](docs/compatibility.md)

> [!NOTE]
> 当前发布包面向 **Linux x64**。Jellyfin **12.2.0** 已完成完整验收；同一 v0.1.0 包在 **12.3.0** 完成针对性兼容回归，未进行该版本的千项容量和完整扫描验收。实播样本为 MP4／MKV（H.264／AAC）及原生 Web 客户端，其他组合见[兼容性说明](docs/compatibility.md)。

## ✨ 特性

- **播放自动检查**：在原生播放流程中按需判断，未变化且已有必要主媒体流时跳过重复探测。
- **地址变化更新**：URL 改变一律通过原生探测更新地址和媒体流，包括签名参数变化；成功后当次播放及重启后均使用新地址。
- **首次信任接管**：已有主媒体流时默认建立历史指纹，避免安装插件后全库重新探测。首次信任不等于重新验证远程内容。
- **原生批量任务**：在 Jellyfin 计划任务中手动检查、停止或设置定时，支持选择媒体库，默认不自动运行。
- **共享探测与并发控制**：播放和批量检查复用同一媒体源正在执行的探测，插件主动探测默认并发 2，可设置为 1～8。
- **失败后可重试**：探测失败或 STRM 在探测期间再次变化时保留旧指纹，修复后重新检查。
- **只读处理 STRM**：不写入、移动或删除 STRM；普通媒体、旧 STRM 和禁用插件时沿用原生处理。

## 🚀 安装

### 网页安装（推荐）

1. 打开 Jellyfin **控制台 → 插件 → 管理仓库**，添加仓库，名称可填 `STRM Probe Optimizer — Linux x64`。
2. 仓库地址填写：

   ```text
   https://raw.githubusercontent.com/kentinya/jellyfin-strm-probe/main/manifest.json
   ```

3. 保存并保持仓库启用，返回插件页，在“全部／可用”（旧版为“目录”）找到 **STRM Probe Optimizer**。
4. 选择 `0.1.0.0` 安装，在 Jellyfin 的安装确认框中确认，然后重启 Jellyfin。
5. 在已安装插件中确认状态为 **Active**，打开插件设置。

服务器需要能够访问 GitHub 的仓库索引和 Release 下载地址。这里提供的是自托管插件仓库。

### 手动安装

从 [v0.1.0 Release](https://github.com/kentinya/jellyfin-strm-probe/releases/tag/v0.1.0) 下载 `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`，使用随附校验文件核对下载内容。停止 Jellyfin，将 ZIP 内的整个插件目录解压到插件目录（容器中通常为 `/config/plugins/`），再启动并确认 Active。

网页和手动安装使用同一 ZIP。详细的校验、升级、备份、移除与重装步骤见[安装与恢复说明](docs/package-installation.md)。

## ⚙️ 使用与配置

安装后，继续从 Jellyfin 原生界面播放影片即可。插件默认启用，播放自动检查默认开启。

打开 **控制台 → 插件 → STRM Probe Optimizer → 设置**：

| 配置 | 默认值 | 生效时机 |
|---|---|---|
| 启用插件 | 开 | 保存后的下一次检查 |
| 播放自动检查 | 开 | 保存后的下一次播放检查 |
| 主动探测并发 | 2，允许 1～8 | 下次 Jellyfin 启动 |
| 批量媒体库范围 | 全部媒体库 | 下一轮批量任务 |
| 详细日志 | 关 | 下一次检查 |

批量检查入口为 **控制台 → 计划任务 → STRM 媒体信息检查**。手动运行、停止、进度和定时均由 Jellyfin 管理；安装后默认没有自动触发时间，需要定时检查时在原生任务页设置。

停止批量任务会撤销未开始的工作，已经开始的探测继续完成并按成功条件保存。任务收尾结束后才能运行下一轮。

关闭“播放自动检查”只影响播放入口；关闭“启用插件”则停止插件优化。配置保存反馈和故障恢复见[配置说明](docs/core-configuration.md)。

## 📝 STRM 格式与判断规则

优化仅作用于带有受支持协议标记的 STRM。版本 1 格式示例：

```text
# strm-probe-version:1
# strm-probe-sha1:aabbccddeeff0011223344556677889900112233
# strm-probe-size:10737418240
https://media.example.invalid/video/movie.mkv
```

上面的地址和哈希仅为示例。实际 SHA-1 应为媒体内容的 40 位十六进制哈希，Size 为媒体文件的字节数；两项均可缺失。插件不生成 STRM，也不下载媒体计算哈希，不调用 OpenList 元数据 API。

已有历史指纹和必要主媒体流时：

| 条件 | 处理 |
|---|---|
| URL 改变 | 要求探测，无论 SHA-1／Size 是否相同 |
| URL 不变，有效 SHA-1 相同 | 跳过探测，忽略 Size 差异 |
| URL 不变，有效 SHA-1 不同 | 要求探测 |
| URL 不变，SHA-1 不可比较 | 仅在新旧有效 Size 不同时要求探测 |
| 仅修改时间或 Modified 注释改变 | 不因此触发探测 |

缺少必要主媒体流时要求探测；原调用不允许探测时，插件不会提高权限。除首次信任接管外，只有本次原生探测成功、结果已保存且 STRM 未再次变化，才接受新指纹。

无可比 SHA-1 且 URL／Size 相同的远程内容替换可能无法识别。独立的媒体库扫描和检查计划不保证先后完成，当前没有扫描后自动触发功能。音频 STRM、JellyfinProxy 和 OpenList 专有行为不在已验证支持范围内。

## 🛠️ 本地开发

插件使用 **C#／.NET 10**，固定 SDK **10.0.401**。媒体信息保存在 Jellyfin 原生库，插件 SQLite 只保存最小历史指纹。

```bash
git clone https://github.com/kentinya/jellyfin-strm-probe.git
cd jellyfin-strm-probe
python3 scripts/development_environment.py sdk
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
```

完整的镜像锁、浏览器工具、隔离实例、测试和证据要求见[开发环境](docs/development-environment.md)与[开发流程](docs/development-workflow.md)；本地打包见[安装包说明](docs/package-installation.md)。

## 📁 项目结构

```text
├── src/Jellyfin.Plugin.StrmProbeOptimizer/  # 插件、原生接入、决策、指纹与批量任务
├── tests/                                 # C# 与 Python 测试
├── scripts/                               # 环境准备、构建打包及隔离验收工具
├── dev/                                   # 固定环境规格与不可变镜像锁
├── docs/                                  # 产品、操作、开发及验收文档
├── manifest.json                          # Jellyfin 插件仓库索引
└── .github/workflows/                     # 质量检查与 Release 工作流
```

## 📚 更多文档

| 内容 | 文档 |
|---|---|
| 产品行为与范围 | [需求](docs/requirements.md) · [用户旅程](docs/product-experience.md) · [范围](docs/scope.md) |
| 实现与验证 | [架构](docs/architecture.md) · [测试矩阵](docs/test-matrix.md) · [兼容性](docs/compatibility.md) |
| 交付与发布 | [安装与恢复](docs/package-installation.md) · [发布流程](docs/release-process.md) |
| 开发规则与状态 | [仓库约束](AGENTS.md) · [开发流程](docs/development-workflow.md) · [当前合同](SLICE.md) · [任务入口](TASK.md) · [路线图](docs/roadmap.md) |
| 历史与来源 | [关闭账本](docs/progress.md) · [参考来源](docs/references.md) |

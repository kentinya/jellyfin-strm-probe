# GitHub Release 发布

2026-10-24 用户授权参照 [STRM-Generator-GO 的发布流程](https://github.com/kentinya/STRM-Generator-GO/blob/main/.github/workflows/release.yml) 发布本项目首版。采用版本标签触发、固定工具链构建、生成校验和、GitHub Release 附件的流程；本项目仅发布已验收的 Linux x64 插件包。

当时是已关闭能力的交付发布，允许提交发布工作流／说明、普通推送 main、创建并推送 `v0.1.0`、发布 Release；未激活新 Slice／Task、移动 Base 或改变产品支持范围。发布时只验收了 Jellyfin 12.2.0／Linux x64；同一原 ZIP 随后在 [Slice 6](progress.md#slice-6-closed) 完成 12.3.0／Linux x64 针对性兼容回归，原标签、附件及构建输入保持，不倒写发布时的实测事实。当时未包含插件仓库索引；用户同日随后要求实现网页安装，追加交付见下节。

## 自托管插件仓库

用户追加授权后，根 [manifest.json](../manifest.json) 提供 Jellyfin 原生仓库索引，公开地址与网页操作见[安装说明](package-installation.md#网页安装)。它直接指向 `v0.1.0` 的原 ZIP；不重新打包、不替换既有 Release 附件或标签，不改变插件版本、ABI 或支持范围。固定 Jellyfin 的[安装器](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Updates/InstallationManager.cs)自行建立版本目录，[加载器](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Plugins/PluginManager.cs)递归查找 DLL，原 ZIP 已通过真实网页安装及重启 Active 验证。

原生目录 `checksum` 使用 MD5，来源清单及验收继续使用 SHA-256。`python3 scripts/check_plugin_repository.py` 下载已发布 ZIP（也可用 `--package` 指定下载副本），核对索引身份、版本／ABI、固定下载地址、原生 MD5、已验收 SHA-256 与原有包结构检查；Repository quality 的独立 job 执行同一检查。索引不等同于 Release 的来源清单。

后续发布需在新版本获得验收、Release 附件可公开下载后，按对应身份更新索引和批准的检查输入，再执行原生网页安装验证并普通推送；不提交含凭据的运行记录。不申请官方仓库收录，也不修改已关闭 Slice／Task。

## 自动流程

[release.yml](../.github/workflows/release.yml) 在推送 `v*` 标签时执行，当前只批准 `v0.1.0`。流程核对标签版本、受验收源码为标签祖先，以及标签处 `src`／`dev`／SDK／解决方案的输入摘要与受验收包一致；随后从受验收源码 `3a7de052bf089141f76e2f60921de285bd5184c4` 单独检出，用校验和锁定的 SDK 10.0.401 和 locked restore 构建。Python 3.11 回归／治理检查及 C# 回归／format 均须通过；干净检出缺少本机归档证据造成的历史 SKIP 保持如实报告。

原验收 DLL 的调试信息带有构建路径，普通换目录编译会改变 DLL／ZIP 摘要。工作流通过 `PathMap` 与固定 SourceLink JSON 复现该逻辑调试前缀；不读取历史目录、不依赖旧主机，也不修改编译后的 DLL。原打包脚本、插件源码、运行时依赖及版本保持。ZIP、DLL、来源清单均必须匹配已验收 SHA-256，否则终止发布。

工作流生成并留存四个附件：插件 ZIP、来源清单 `.manifest.json`、ZIP 的 `.zip.sha256`、覆盖前三者的 `SHA256SUMS.txt`。先上传草稿 Release，再下载全部附件与本次构建逐字节比较，通过后才公开并标记 Latest。使用内置 `GITHUB_TOKEN` 的 `contents: write` 权限，无须保存个人访问令牌。

## 首版发布命令（历史）

以下仅记录已完成的 v0.1.0 发布步骤，不是当前待执行命令；已有标签与公开 Release 不重新创建、改写或替换。当时先完成授权修改及身份核对，再普通推送并创建标签：

```bash
git push origin main
git tag -a v0.1.0 -m 'Release STRM Probe Optimizer v0.1.0'
git push origin v0.1.0
```

核对远端 workflow 的全部必要步骤成功、Release 为公开状态且附件摘要匹配；失败时保留日志／草稿和既有证据，修复需形成新提交，不改写已发布标签或历史。重跑不会覆盖同名附件；已有公开 Release 不作为重新构建并替换附件的入口。

## 后续版本

后续版本需先取得对应产品范围授权及验收，再更新版本、发布说明、工作流批准的源码／输入／产物摘要与标签检查。不能仅修改标签绕过验收，也不能沿用 `v0.1.0` 摘要宣称新版本已通过。发布不上传运行数据库、凭据、本机原始证据或可选本地原方案；同一 ZIP 的既有实机结果复用与远端构建／上传结果分别报告。

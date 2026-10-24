# GitHub Release 发布

2026-10-24 用户授权参照 [STRM-Generator-GO 的发布流程](https://github.com/kentinya/STRM-Generator-GO/blob/main/.github/workflows/release.yml) 发布本项目首版。采用版本标签触发、固定工具链构建、生成校验和、GitHub Release 附件的流程；本项目仅发布已验收的 Linux x64 插件包。

本次是已关闭能力的交付发布，允许提交发布工作流／说明、普通推送 main、创建并推送 `v0.1.0`、发布 Release；不激活新 Slice／Task、不移动 Base 或改变产品支持范围。Jellyfin 12.3 尚未实机验证，首版支持范围仍为 Jellyfin 12.2.0／Linux x64。线上插件仓库索引／自动上架不在本次交付内。

## 自动流程

[release.yml](../.github/workflows/release.yml) 在推送 `v*` 标签时执行，当前只批准 `v0.1.0`。流程核对标签版本、受验收源码为标签祖先，以及标签处 `src`／`dev`／SDK／解决方案的输入摘要与受验收包一致；随后从受验收源码 `3a7de052bf089141f76e2f60921de285bd5184c4` 单独检出，用校验和锁定的 SDK 10.0.401 和 locked restore 构建。Python 3.11 回归／治理检查及 C# 回归／format 均须通过；干净检出缺少本机归档证据造成的历史 SKIP 保持如实报告。

原验收 DLL 的调试信息带有构建路径，普通换目录编译会改变 DLL／ZIP 摘要。工作流通过 `PathMap` 与固定 SourceLink JSON 复现该逻辑调试前缀；不读取历史目录、不依赖旧主机，也不修改编译后的 DLL。原打包脚本、插件源码、运行时依赖及版本保持。ZIP、DLL、来源清单均必须匹配已验收 SHA-256，否则终止发布。

工作流生成并留存四个附件：插件 ZIP、来源清单 `.manifest.json`、ZIP 的 `.zip.sha256`、覆盖前三者的 `SHA256SUMS.txt`。先上传草稿 Release，再下载全部附件与本次构建逐字节比较，通过后才公开并标记 Latest。使用内置 `GITHUB_TOKEN` 的 `contents: write` 权限，无须保存个人访问令牌。

## 发布与后续版本

先完成已授权修改、审查完整差异，执行治理检查、工作流语法校验及本地复建身份核对。提交后以普通推送发布 main，再为该提交创建并推送标签：

```bash
git push origin main
git tag -a v0.1.0 -m 'Release STRM Probe Optimizer v0.1.0'
git push origin v0.1.0
```

核对远端 workflow 的全部必要步骤成功、Release 为公开状态且附件摘要匹配；失败时保留日志／草稿和既有证据，修复需形成新提交，不改写已发布标签或历史。重跑不会覆盖同名附件；已有公开 Release 不作为重新构建并替换附件的入口。

后续版本需先取得对应产品范围授权及验收，再更新版本、发布说明、工作流批准的源码／输入／产物摘要与标签检查。不能仅修改标签绕过验收，也不能沿用 `v0.1.0` 摘要宣称新版本已通过。发布不上传运行数据库、凭据、本机原始证据或可选本地原方案；同一 ZIP 的既有实机结果复用与远端构建／上传结果分别报告。

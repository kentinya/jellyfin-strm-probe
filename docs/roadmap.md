# Slice 路线图

只记录完整能力的目标、次序、依赖与状态。生命周期见 [开发流程](development-workflow.md)，Task 和审查细节留在 Git。

| Slice | 目标 | Status | 依赖 |
|---|---|---|---|
| 1 — Jellyfin 核心接入与播放验证 | 固定目标版本，证明核心服务接入、跳过与主动探测、结果可信确认及路径重启持久化 | ACTIVE | 已提交原始基线与合同；需要隔离 Jellyfin 环境 |
| 2 — 版本感知探测完整闭环 | 只读解析、决策、首次接管、SQLite、并发、版本变化与失败恢复，满足 T01～T28 的核心行为 | PLANNED | Slice 1 PASS / CLOSED |
| 3 — 配置、兼容联调与发布 | 配置页与诊断、禁用／故障原生处理、隔离代理兼容联调及单版本可安装发布包 | PLANNED | Slice 2 PASS / CLOSED |

## 当前边界

Slice 1 合同已经本地提交并激活；Task 1.1 在合同提交后计划。后续 Slice 保持 PLANNED，未开始产品验收。

原方案 P1“修改 STRM 生成程序”从路线图移除。Slice 2／3 不承担生成器、OpenList API 客户端或 JellyfinProxy 代码改造。当前不预建后续 Slice 的实施 Task。

# Slice 路线图

按 [稳定需求](requirements.md) 与 [范围](scope.md) 记录完整能力的目标、次序与依赖。生命周期见 [开发流程](development-workflow.md)，详细 Task 与审查留在 Git。

| Slice | 目标 | Status | 依赖 |
|---|---|---|---|
| 1 — Jellyfin 核心接入与指纹提交验证 | P0：固定目标版本，证明核心接入、跳过／主动探测、可靠成功信号及 URL 变化后的原生持久化 | PASS / CLOSED | 原始 Base 保留，V4.2 修订合同；隔离 Jellyfin 环境 |
| 2 — 播放检查与历史指纹完整闭环 | P1：只读解析、决策、首次信任、最小 SQLite 指纹、稳定多源、播放按需探测、已开始探测共享／全局并发、正常收尾、核心配置及失败恢复，满足 T01～T28 的核心部分 | PASS / CLOSED | Slice 1 PASS / CLOSED；Base 为关闭提交 |
| 3 — Jellyfin 原生批量检查任务 | P2：完整配置页／媒体库范围、原生运行／停止／定时、候选 ID 集合与分批对象／固定消费者、仅撤销未开始工作／已开始探测收尾后再开放新轮、播放混合共享、进度统计及恢复（并发默认 2、1～8） | PASS / CLOSED | Slice 2 PASS / CLOSED；Base 为关闭提交 |
| 4 — 大规模集成与单版本交付 | P3：至少 1000 项真实 STRM 媒体库／成本（复用现存全部 1004 项）、完整扫描与播放／批量重叠、固定 Jellyfin／Linux x64 安装包和恢复旅程；JellyfinProxy 按用户授权不验证 | PASS / CLOSED | Slice 3 PASS / CLOSED；Base 为关闭提交 |
| 5 — 真实播放决策全场景验证与 CI 修复 | 自备 MP4／MKV 视频／STRM、固定 Jellyfin 和指定 ZIP 安装，八类决策的真实播放／ffprobe／持久化／重启对账、主流误判回归，以及干净检出的 GitHub Actions 三处失败修复；音频 STRM 按用户授权撤出 | PASS / CLOSED | Slice 1～4 已关闭；[接受范围与证据](progress.md#slice-5-closed) |
| 6 — Jellyfin 12.3 最小兼容性实机验证 | 复用 v0.1.0 原 ZIP，固定 12.3／Linux x64，六组最小安装升级、决策实播、ColorRange、失败恢复、重启选源及批量／权限验证；不重跑全部子矩阵或千项容量验收 | ACTIVE | Slice 1～5 已关闭；Base 为 `1379ff0e6f3e572d1d843c835a2d8af250c49ec7`；[交接 B](../SLICE.md#handoff-b) |

## 当前边界

Slice 1～5 已交付，历史决定和证据见[关闭账本](progress.md)。用户于 2026-10-24 要求开启 Slice 6，验证 12.3 的最小测试；A 已激活[当前合同](../SLICE.md)，实施单元与交接见[当前 Task](../TASK.md)。原包与业务规则不变，12.3 尚未实机验证，不把旧全量 PASS 当新版本结果。MP4／MKV 是测试样本，不是插件格式白名单；本轮不增加其他格式支持声明。代理与音频 STRM 仍按用户范围不执行、不计 PASS。

从 V3.0 的三个 Slice 改为四个 Slice 是实质规划调整；旧规划见重规划前检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485`。旧生成器 P1 始终排除，当前 P1 专指 V4.2 核心插件。

首版不开发独立调度、探测状态机、路径单独更新器或扫描后自动触发。核心接口／成功信号已在 Slice 1 成立；改变固定组合或成功边界时重新实证，不能以旧结果掩盖新缺口。Slice 2 先交付可保存的核心配置，并发 1～8 在下一次启动生效；完整配置页和真实批量管理已在 Slice 3 接受。本次用户规则替代旧“无等待者时取消执行”：Slice 2 只共享已实际开始的探测并正常收尾，不共享排队请求或新增执行取消源；Slice 3 验证批量停止只撤销未开始工作，已开始探测继续完成并按条件提交。

用户要求当前播放链不增加防御性取消约束；A 实质调整 Slice 1，移除成功返回后的额外取消检查及人为注入取消验收，保留原生取消异常处理。随后按用户停止／共享规则提交 [Slice 2 Material Contract Change 记录](progress.md#slice-2-closed)，B 在新合同内规划并审查 Task 2.1／2.2，A 已完成 Slice 2 最终审查。核心保存关联及其他真实门槛不变，原生取消异常及历史 FAIL／NOT RUN 保持原事实；原生批量停止及已开始工作收尾在 Slice 3 验证。

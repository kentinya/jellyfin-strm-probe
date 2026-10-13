# Slice 路线图

按 V4.2 的完整能力记录目标、次序与依赖。生命周期见 [开发流程](development-workflow.md)，详细 Task 与审查留在 Git。

| Slice | 目标 | Status | 依赖 |
|---|---|---|---|
| 1 — Jellyfin 核心接入与指纹提交验证 | P0：固定目标版本，证明核心接入、跳过／主动探测、可靠成功信号及 URL 变化后的原生持久化 | PASS / CLOSED | 原始 Base 保留，V4.2 修订合同；隔离 Jellyfin 环境 |
| 2 — 播放检查与历史指纹完整闭环 | P1：只读解析、决策、首次信任、最小 SQLite 指纹、稳定多源、播放按需探测、已开始探测共享／全局并发、正常收尾、核心配置及失败恢复，满足 T01～T28 的核心部分 | ACTIVE | Slice 1 PASS / CLOSED；Base 为关闭提交 |
| 3 — Jellyfin 原生批量检查任务 | P2：原生运行／停止／定时、所选库分页与有界排队、仅撤销未开始工作／已开始探测收尾、运行中共享协调、进度统计及配置（并发默认 2、1～8） | PLANNED | Slice 2 PASS / CLOSED |
| 4 — 大规模集成、兼容联调与发布 | P3：大规模 STRM、播放／批量并发、原生计划任务、库扫描、重启与 JellyfinProxy 隔离联调，单版本可安装包 | PLANNED | Slice 3 PASS / CLOSED |

## 当前边界

Slice 1 已经 A 审查完整 Base..Implementation Head 并关闭为 PASS / CLOSED；合同／Closure Packet／最终决定见 [关闭快照](progress.md#slice-1-closed)。A 在独立一轮激活 [Slice 2 合同](../SLICE.md)，真实 Base 为关闭提交 `924816a84c74f5d79c107478f2d40e621cb8be8d`，Implementation Head 为 NOT SET。B 已在修订后的已提交合同上规划 [Task 2.1](../TASK.md)（PLANNED）：按真实媒体源持久化播放指纹与重启恢复；尚未开始实施。Slice 3／4 保持 PLANNED。

从 V3.0 的三个 Slice 改为四个 Slice 是实质规划调整；旧规划见重规划前检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485`。旧生成器 P1 始终排除，当前 P1 专指 V4.2 核心插件。

首版不开发独立调度、探测状态机、路径单独更新器或扫描后自动触发。核心接口／成功信号已在 Slice 1 成立；改变固定组合或成功边界时重新实证，不能以旧结果掩盖新缺口。Slice 2 先交付可保存的核心配置，并发 1～8 在下一次启动生效；完整配置页和真实批量管理仍在 Slice 3。本次用户规则替代旧“无等待者时取消执行”：Slice 2 只共享已实际开始的探测并正常收尾，不共享排队请求或新增执行取消源；Slice 3 验证批量停止只撤销未开始工作，已开始探测继续完成并按条件提交。

用户要求当前播放链不增加防御性取消约束；A 实质调整 Slice 1，移除成功返回后的额外取消检查及人为注入取消验收，保留原生取消异常处理。原生取消异常及历史 FAIL／NOT RUN 保持原事实。本轮 A 按用户停止／共享规则提交 [Material Contract Change](../SLICE.md#a-停止与共享边界修订2026-10-13)，替代 Slice 2 人为可取消执行门槛；原生批量停止及已开始工作收尾在 Slice 3 验证；B 已重新核查合法性，并以修订提交为 Task Base／Contract Checkpoint 新规划 Task 2.1。核心保存关联及其他真实门槛不变；B 已在新合同内调整并审查 Task 1.1，历史取消结果仍按原事实保留。

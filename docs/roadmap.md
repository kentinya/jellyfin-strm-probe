# Slice 路线图

按 V4.2 的完整能力记录目标、次序与依赖。生命周期见 [开发流程](development-workflow.md)，详细 Task 与审查留在 Git。

| Slice | 目标 | Status | 依赖 |
|---|---|---|---|
| 1 — Jellyfin 核心接入与指纹提交验证 | P0：固定目标版本，证明核心接入、跳过／主动探测、可靠成功信号及 URL 变化后的原生持久化 | PASS / CLOSED | 原始 Base 保留，V4.2 修订合同；隔离 Jellyfin 环境 |
| 2 — 播放检查与历史指纹完整闭环 | P1：只读解析、决策、首次信任、最小 SQLite 指纹、稳定多源、播放按需探测、同源共享／全局并发、可取消共享执行保护、核心配置及失败恢复，满足 T01～T28 的核心部分 | ACTIVE | Slice 1 PASS / CLOSED；Base 为关闭提交 |
| 3 — Jellyfin 原生批量检查任务 | P2：原生运行／停止／定时、所选库分页与有界排队、共享协调、进度统计及配置（并发默认 2、1～8） | PLANNED | Slice 2 PASS / CLOSED |
| 4 — 大规模集成、兼容联调与发布 | P3：大规模 STRM、播放／批量并发、原生计划任务、库扫描、重启与 JellyfinProxy 隔离联调，单版本可安装包 | PLANNED | Slice 3 PASS / CLOSED |

## 当前边界

Slice 1 已经 A 审查完整 Base..Implementation Head 并关闭为 PASS / CLOSED；合同／Closure Packet／最终决定见 [关闭快照](progress.md#slice-1-closed)。A 在独立一轮激活 [Slice 2 合同](../SLICE.md)，真实 Base 为关闭提交 `924816a84c74f5d79c107478f2d40e621cb8be8d`，Implementation Head 为 NOT SET。当前无活动实施 Task；B 在已提交合同上先计划首个 Task，A 本轮不规划或实施。Slice 3／4 保持 PLANNED。

从 V3.0 的三个 Slice 改为四个 Slice 是实质规划调整；旧规划见重规划前检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485`。旧生成器 P1 始终排除，当前 P1 专指 V4.2 核心插件。

首版不开发独立调度、探测状态机、路径单独更新器或扫描后自动触发。核心接口／成功信号已在 Slice 1 成立；改变固定组合或成功边界时重新实证，不能以旧结果掩盖新缺口。Slice 2 先交付可保存的核心配置，并发 1～8 在下一次启动生效；完整配置页和真实批量管理仍在 Slice 3。无等待者时取消未完成共享执行及其接受提交保护属于 Slice 2，不增加客户端停止播放关联。

用户要求当前播放链不增加防御性取消约束；A 实质调整 Slice 1，移除成功返回后的额外取消检查及人为注入取消验收，保留原生取消异常处理。可取消共享执行的保护与验证归 Slice 2，原生批量停止归 Slice 3；历史 FAIL／NOT RUN 不转为 PASS。核心保存关联及其他真实门槛不变；B 已在新合同内调整并审查 Task 1.1，历史取消结果仍按原事实保留。

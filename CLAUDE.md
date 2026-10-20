# 执行入口

@AGENTS.md

永久约束见 [AGENTS.md](AGENTS.md)，Slice／Task 流程仅由 [开发流程](docs/development-workflow.md) 定义，当前范围见 [SLICE.md](SLICE.md) 和 [TASK.md](TASK.md)。

按职责阅读 [A 经验](docs/agent-experience/slice-owner-architect-final-reviewer.md)、[B 经验](docs/agent-experience/task-planner-reviewer.md) 或 [Developer 经验](docs/agent-experience/developer-implementation-role.md)。经验不能覆盖合同或授权。

对已经授权的当前 Task，自主完成范围内实现、必要修复、测试和本地检查点，不反复询问是否继续。新需求不扩大当前合同。保留用户已有改动；V4.3 原方案仅作可选本地参考，不必读、不校验、不跟踪或上传 GitHub，具体边界见 AGENTS 和开发流程。历史版本记录保留在 Git 中。

不自动执行推送、强制推送、历史改写、`reset --hard`、破坏性 `clean` 或生产媒体修改。`.git` 不可写时报告实际限制，不能虚构提交或另设 Git 目录绕过限制。

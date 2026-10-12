# 测试矩阵

所有条目当前均为 `NOT RUN`。此表定义验收，不能当成已执行报告。已存在主流、版本化 STRM、有历史基线、允许探测是通常前提；例外在场景中指出。

## 原方案 T01～T28

| ID | 场景 | 预期 | 需求 | 最终证据类型 | 状态 |
|---|---|---|---|---|---|
| T01 | 首次无主媒体流 | 要求并实际探测，成功后确认 | DECISION-001、STATE-001 | 单元＋Jellyfin 集成 | NOT RUN |
| T02 | 首次安装已有主流 | Assumed，不 ffprobe | STATE-001 | 单元＋Jellyfin 集成 | NOT RUN |
| T03 | URL 不变、SHA-1 相同 | 不 ffprobe | DECISION-002 | 单元＋集成 | NOT RUN |
| T04 | URL 不变、SHA-1 不同 | ffprobe | DECISION-002、PROBE-001 | 单元＋集成 | NOT RUN |
| T05 | SHA-1 相同、Size 不同 | 不 ffprobe | DECISION-002 | 单元＋集成 | NOT RUN |
| T06 | URL 不变、无 SHA-1、Size 相同 | 不 ffprobe | DECISION-003 | 单元＋集成 | NOT RUN |
| T07 | URL 不变、无 SHA-1、Size 不同 | ffprobe | DECISION-003 | 单元＋集成 | NOT RUN |
| T08 | URL 改变、SHA-1 相同 | 只更新 URL，保留主流 | DECISION-004、PATH-001 | 单元＋Jellyfin 集成 | NOT RUN |
| T09 | URL 改变、SHA-1 不同 | ffprobe 并同步 URL | DECISION-004 | 单元＋集成 | NOT RUN |
| T10 | URL 改变、无 SHA-1、Size 相同 | 必须 ffprobe；单独自动化回归 | DECISION-004 | 独立单元＋集成 | NOT RUN |
| T11 | URL 改变、无 SHA-1、Size 不同 | ffprobe | DECISION-004 | 单元＋集成 | NOT RUN |
| T12 | URL 改变、只有一侧有效 SHA-1 | ffprobe | DECISION-004、MANIFEST-002 | 单元＋集成 | NOT RUN |
| T13 | 只有修改时间变化 | 不 ffprobe | DECISION-005 | 单元＋文件集成 | NOT RUN |
| T14 | 相同 STRM 删除后重放，库记录／状态保留 | 不 ffprobe | DECISION-005 | 文件＋Jellyfin 集成 | NOT RUN |
| T15 | 重写相同 SHA-1 的 STRM | 不 ffprobe | DECISION-005 | 文件＋集成 | NOT RUN |
| T16 | 同 URL 远程替换且 SHA-1 变化 | ffprobe | DECISION-002 | 原生探测集成 | NOT RUN |
| T17 | ffprobe 失败，旧流仍存在 | 不提交新确认版本 | PROBE-002、PROBE-003 | 失败注入＋真实探测 | NOT RUN |
| T18 | 探测期间 STRM 再变化 | 旧结果不确认新版本 | STATE-002、PROBE-002 | 竞态集成 | NOT RUN |
| T19 | Jellyfin 重启 | 正确恢复基线／待测状态 | STATE-003 | 持久化＋真实重启 | NOT RUN |
| T20 | 多客户端同媒体源并发 | 同一次探测共享，不重复执行 | CONCURRENCY-001 | 并发＋真实计数 | NOT RUN |
| T21 | 手动强制刷新 | 原生刷新可执行，可靠协调状态 | REFRESH-001 | Jellyfin 集成 | NOT RUN |
| T22 | ShortcutPath 更新后重启 | 新 URL 有效、原流保留 | PATH-001 | Jellyfin 重启 | NOT RUN |
| T23 | 未安装插件 | 原生基线 | COMPAT-001、COMPAT-002 | 对照实例 | NOT RUN |
| T24 | 禁用插件 | 原生行为 | COMPAT-002、CONFIG-001 | 配置＋原生对照 | NOT RUN |
| T25 | 多版本影片 | 媒体源身份独立、流与 URL 正确 | CONCURRENCY-001 | 多媒体源集成 | NOT RUN |
| T26 | 无版本标记旧 STRM | 默认原生策略 | COMPAT-002 | 解析＋Jellyfin 集成 | NOT RUN |
| T27 | SHA-1 缺失后恢复 | 保留对应版本哈希，不错用历史身份 | STATE-004 | 状态＋序列集成 | NOT RUN |
| T28 | allowMediaProbe=false | 不启动探测，需求保留 | DECISION-006 | 所有分支权限测试 | NOT RUN |

表中需求缩写统一加 `REQ-` 前缀，例如 `DECISION-004` 对应 `REQ-DECISION-004`。

## 补充边界

| ID | 验证目标 | 状态 |
|---|---|---|
| X01 | 文件读取不写 STRM、不调用 OpenList API、不计算远程媒体哈希；夹具均在临时目录 | NOT RUN |
| X02 | 全接口委托、非 STRM、直播、注册顺序、单例／释放、启动／关闭 | NOT RUN |
| X03 | 编码／BOM／空白、缺失字段、非法 SHA-1、非法／缺失／零／超范围 Size、未知协议、冲突标记、有界读取及非法 URL | NOT RUN |
| X04 | 文件／路径同步／数据库错误不覆盖可信状态，回退保留探测权限，错误脱敏 | NOT RUN |
| X05 | 同 URL 信息不足按性能优先跳过并说明限制，mtime 不参与 | NOT RUN |
| X06 | 重启、SQLite 迁移／损坏／不可写处理，不复制媒体流或完整 PlaybackInfo | NOT RUN |
| X07 | 成功信号与实际 ffprobe、新结果持久化关联；旧流／更新事件／刷新返回值不足；记录 FullRefresh 额外开销 | NOT RUN |
| X08 | 等待者取消、不同项目独立、探测中版本更换、完成重检查和多版本隔离 | NOT RUN |
| X09 | 配置保存／生效／错误反馈、固定规则不可关闭、默认策略 | NOT RUN |
| X10 | 签名 URL、token、Cookie、私有路径不进入日志、状态或证据 | NOT RUN |

## 执行报告要求

记录准确提交、Jellyfin 版本／源码、SDK、隔离实例、命令、总数、失败／跳过和原生 ffprobe 调用计数。测试媒体、SHA-1 和 URL 均使用假数据；不在仓库记录生产路径与秘密。

原生成功验证须有失败对照，重启与多客户端测试须有真实运行证据。单元测试通过不能覆盖真实 DI 和持久化门槛。外部代理联调不可用时记录 BLOCKED／NOT RUN，不能算通过。

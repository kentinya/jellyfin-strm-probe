# 插件需求

状态：TARGET，尚无产品实现。来源是 V3.0 原方案及 [本次范围](scope.md)。需求编号保持稳定，测试编号沿用原方案 T01～T28；全部执行状态见 [测试矩阵](test-matrix.md)。

## 稳定需求

| ID | 要求 | 原方案 | 验证 |
|---|---|---|---|
| REQ-SCOPE-001 | 仅实现 Jellyfin 插件；不开发生成程序，不请求 OpenList 元数据 API，不改写 STRM 或代理 | 四、十三、十八；用户范围约束 | X01、范围检查 |
| REQ-COMPAT-001 | 固定一个实证目标版本和依赖，先验证核心 DI 包装、完整委托、生命周期及原生播放 | 六、十五、十九 | T23、T24、X02 |
| REQ-COMPAT-002 | 非 STRM、无协议标记旧 STRM、禁用插件保持原生行为 | 十四、十五 | T23、T24、T26、X02 |
| REQ-MANIFEST-001 | 只读解析协议版本 1、首个有效 URL、可选内容 SHA-1 和可选字节 Size；保留缺失与非法的区别 | 三、十五 | X03 |
| REQ-MANIFEST-002 | SHA-1 为 40 位十六进制、忽略大小写；Size 是有效 Int64 字节数，不把缺失写为 0；URL 指纹不是内容哈希 | 三、四、七 | T12、T27、X03 |
| REQ-MANIFEST-003 | 缺失／空文件、非法 URL、无效协议或冲突标记不覆盖可信状态，不保存非法路径；脱敏诊断并原生委托或明确失败 | 十五 | X03、X04 |
| REQ-DECISION-001 | 受支持 STRM 缺少必要主媒体流时要求探测 | 二、七 | T01 |
| REQ-DECISION-002 | URL 未变，新旧 SHA-1 均有效：相同跳过且忽略 Size，不同要求探测 | 二、七 | T03、T04、T05、T16 |
| REQ-DECISION-003 | URL 未变、SHA-1 不可比较：仅在新旧有效 Size 不同时要求探测；相同或不可比较时跳过并说明信息限制 | 二、三、七 | T06、T07、X05 |
| REQ-DECISION-004 | URL 改变，只有新旧有效 SHA-1 相同时才能跳过并更新路径；其他情况要求探测，Size 相同也不能豁免 | 二、三、七 | T08～T12 |
| REQ-DECISION-005 | 修改时间、相同内容重新写入及同库记录保留时的文件重新创建，本身不引起探测 | 二、七 | T13～T15 |
| REQ-DECISION-006 | 原调用不允许探测时，插件不得启动 ffprobe；保存需要探测的状态，后续允许请求重新检查 | 二 | T28 |
| REQ-STATE-001 | 首次接管有主媒体流默认建立 Assumed 并跳过；缺少主流要求探测；严格首次模式默认关闭 | 十 | T01、T02 |
| REQ-STATE-002 | 区分已确认基线、当前观测及待探测状态；不凭新标记或刷新返回值标为 Verified | 九、十一 | T17、T18、T27 |
| REQ-STATE-003 | 只保存最小指纹和状态，媒体流在原生库；状态重启恢复，不缓存完整 PlaybackInfo | 九、十三 | T19、X06 |
| REQ-STATE-004 | 暂时缺失 SHA-1 不删除该版本的历史有效哈希；历史哈希必须有版本关联，不能套到新基线 | 九 | T27 |
| REQ-PROBE-001 | 通过经验证的原生入口实际触发远程探测，不依赖 allowMediaProbe=true 必然执行 | 六 | T01、T04、T07、T09～T12、X07 |
| REQ-PROBE-002 | Verified 需有本次新结果、成功持久化、必要主流及前后 Manifest 一致的可靠证据；ItemUpdateType／旧主流不足以证明成功 | 十一、十九 | T17、T18、X07 |
| REQ-PROBE-003 | 失败／取消／版本变化保留旧基线与待探测信息；不能把旧流当作新版本验证结果 | 十一 | T17、T18、X08 |
| REQ-PATH-001 | 相同内容换 URL 后更新并原生持久化 ShortcutPath，当次使用新 URL、重启仍有效、已有流保留 | 八 | T08、T22 |
| REQ-PATH-002 | 路径更新失败不把旧 URL 当成新 URL 成功返回；明确错误或在原调用允许的条件下回退原生刷新 | 八、二 | X04、T28 |
| REQ-CONCURRENCY-001 | 按项目与媒体源身份共享同一次探测；不同项目独立；完成后各请求重新检查最新版本 | 十二 | T20、T25、X08 |
| REQ-REFRESH-001 | 保留手动强制刷新；插件外刷新只能凭可靠关联证据协调状态 | 十五 | T21、X07 |
| REQ-CONFIG-001 | 提供启用、首次接管及诊断等有意义配置；URL 改变无可比 SHA-1、相同 SHA-1 优先、忽略 Modified、尊重 allowMediaProbe 等固定规则不可关闭 | 十四 | T24、T28、X09 |
| REQ-FAILURE-001 | SQLite 运行时异常停止优化并尽可能委托原生；核心启动接入失败明确报告，不伪称总能自动回退 | 十五 | X04、X06 |
| REQ-PRIVACY-001 | 状态不保存完整 URL／PlaybackInfo；日志与测试证据脱敏，不泄露签名、token、Cookie 或用户私有路径 | 九、十五 | X10 |
| REQ-EXTERNAL-001 | PlaybackInfo 输出保持原生契约，外部代理仍可维持 MediaSourceId→URL 及 302；不在本项目关闭其缓存 | 十三、十七 | Slice 3 隔离联调 |

## 核心决策表

前提：受支持的版本化 STRM，已有必要主媒体流且有可用历史基线。首次接管单独处理；`allowMediaProbe=false` 只产生待处理需求，不执行探测。

| URL | 新旧 SHA-1 | 新旧有效 Size | 决策 |
|---|---|---|---|
| 不变 | 相同 | 任意 | SkipProbe |
| 不变 | 不同 | 任意 | RequireProbe |
| 不变 | 不可比较 | 相同 | SkipProbe |
| 不变 | 不可比较 | 不同 | RequireProbe |
| 不变 | 不可比较 | 不可比较 | SkipProbe，记录信息不足 |
| 改变 | 相同 | 任意 | UpdatePathOnly |
| 改变 | 不同 | 任意 | RequireProbe，同步新路径 |
| 改变 | 不可比较 | 任意 | RequireProbe，同步新路径 |

修改时间不参与表格。无内容哈希、大小缺失／相同的同 URL 远程替换无法被可靠识别，这是方案的性能优先限制；界面和文档不能宣传可以识别所有替换。

## 输入协议边界

```text
# strm-probe-version:1
# strm-probe-sha1:aabbccddeeff0011223344556677889900112233
# strm-probe-size:10737418240
https://media.example.invalid/video/movie.mkv
```

版本 1 是协议版本，不是修改计数。SHA-1、Size 可缺失。真实 0 字节与缺失不同；超过 Int64 范围、负数和非整数字段不可作为有效 Size。

无协议标记默认原生处理。未知协议、无法唯一解释的冲突标记、不可解析 URL 不启用优化；具体编码、BOM、读取上限和重复字段规则在解析 Task 中明确并自动验证，不从文件修改时间推断版本。

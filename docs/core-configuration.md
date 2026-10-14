# 核心配置与故障恢复操作说明

本页记录 Slice 2 已经 A 最终审查接受的核心配置操作：原子保存保护、启动诊断脱敏、行动前重判与首次信任当前性均已验证。详见 [B Review Result](../TASK.md#b-review-result) 与 [A 最终审查](../SLICE.md#a-final-review)。配置通过 Jellyfin 现有插件配置通道读写；完整配置页、批量任务 UI 和发布安装仍延期。

## 配置字段

| 字段 | 默认 | 说明 | 生效时机 |
|---|---|---|---|
| `Enabled` | `true` | 插件是否执行 STRM 优化。关闭后保留调用者原始探测权限并委托 Jellyfin 原生处理。 | 保存成功后，下一次检查请求生效；已实际开始的探测继续收尾。 |
| `PlaybackAutoCheck` | `true` | 播放入口是否执行自动检查。关闭只影响播放入口，不影响未来批量入口。 | 保存成功后，下一次检查请求生效。 |
| `MaxConcurrentProbes` | `2` | 插件主动发起的原生探测全局并发上限，合法范围 `1`～`8`。 | 仅在下一次 Jellyfin 启动生效；当前运行的许可池不热调整。 |
| `DetailedLog` | `false` | 是否输出更详细的复用／加入诊断。必要故障反馈不受此开关影响。 | 下一次检查操作生效。 |

固定业务规则（URL 变化必探测、`allowMediaProbe=false` 不升级、SHA-1／Size 比较等）不作为可关闭开关。

## 读取与保存

配置通过 Jellyfin 已有端点读写，插件 ID 为 `b061643e-d17d-4c6e-8ba2-6b57e286bd20`。以下示例只使用占位认证，实际令牌由管理员会话提供：

```bash
# 读取当前配置
curl -s -H 'Authorization: MediaBrowser Token="<ADMIN_TOKEN>"' \
  http://127.0.0.1:18096/Plugins/b061643e-d17d-4c6e-8ba2-6b57e286bd20/Configuration

# 保存合法配置
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Authorization: MediaBrowser Token="<ADMIN_TOKEN>"' \
  -H 'Content-Type: application/json' \
  --data '{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":4,"DetailedLog":false}' \
  http://127.0.0.1:18096/Plugins/b061643e-d17d-4c6e-8ba2-6b57e286bd20/Configuration
```

- 合法保存返回 `204`，重新读取可看到新值；并发字段要到下一次 Jellyfin 启动才成为运行上限。
- 越界并发（`0`、`9`、负数）由插件校验拒绝，返回可识别的 `400`，不落盘、不改变当前有效配置。
- 非整数或字段类型错误由 Jellyfin JSON 反序列化在进入插件前拒绝（`500`），同样不改变有效配置与保存文件。
- 保存失败时候选不生效：插件先把候选完整写入同目录临时文件，成功后才原子替换正式配置；中途写入失败会保留旧有效文件与旧内存配置，并返回错误反馈，重启后仍是旧有效值。

## 重启与生效核对

```bash
python3 scripts/development_environment.py stop
python3 scripts/development_environment.py up
```

重启后核对：

1. `GET .../Configuration` 返回上次成功保存的值。
2. 日志出现插件启动行，写明实际采用的全局并发（`MaxConcurrentProbes` 为本次启动生效值）。
3. 改变 STRM 地址触发一次探测，观察并发行为符合启动值。

已保存非法并发（例如手工编辑配置后写入 `MaxConcurrentProbes=9`）不会被静默接受：启动日志给出诊断并退回默认 `2`，同时保留该非法值以便修正；通过 Jellyfin 重新保存合法值并重启即可恢复。

## 禁用与关闭播放检查的区别

- 关闭 `Enabled`：目标为整个插件停止优化、未开始请求在准入时重读该配置并按原权限委托；已实际开始执行继续收尾。
- 关闭 `PlaybackAutoCheck`：只停止播放入口的自动检查；其他允许入口不受影响。排队播放会在准入时重读该配置并委托。
- 禁用整个插件（Jellyfin 插件管理）：代理注册随重启移除，完全回到原生；独立原生刷新和 Jellyfin／其他插件的探测不受插件并发池限制。

## SQLite 状态库故障恢复

- 运行时指纹库读取或写入异常：插件停止优化并尽可能委托原生，保留调用者权限与旧库文件，不伪造已提交。
- 插件不自动删库或重建损坏库。
- 修复方式：停止 Jellyfin，修复或替换 `data/plugins/<plugin-id>/strm-fingerprints.db`，重新启动，再触发一次播放检查；插件会重新比较当前 STRM 与恢复后的历史指纹。

## 识别限制

- 同 URL 且无可比 SHA-1 时，只有双侧有效 Size 不同才要求探测；信息不足只记录限制，不凭空认定变化。
- 修改时间（mtime）本身不触发探测。
- 日志与证据必须脱敏；启动非法配置诊断只使用插件 ID 与可操作恢复说明，不输出私有配置路径、签名 URL、token 或 Cookie。

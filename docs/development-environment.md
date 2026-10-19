# 可迁移开发环境

本文件只描述可迁移开发环境、固定输入和运行前提。当前合同、Task 状态和产品验收统一见 [Slice](../SLICE.md)、[Task](../TASK.md) 与 [进度账本](progress.md)；旧服务器记录只作为 Git 历史，不是新主机开工前提。

## 当前新主机检查（2026-10-18）

- `python3 scripts/development_environment.py sdk`：PASS，已存在并校验本地 SDK `10.0.401`；全局 `dotnet` 不在 PATH，统一使用 `bash scripts/dotnet-local`。
- `python3 scripts/development_environment.py doctor`：PASS，Docker Engine `29.7.1`、Compose `v5.3.1`、本地端口、DNS、NuGet HTTPS 和不可变镜像锁均通过。
- `python3 scripts/development_environment.py status`：若现有隔离 Jellyfin 健康检查失败，真实集成保持 `BLOCKED／NOT RUN`；不要接管或清理非本轮容器。
- 2026-10-19 续审只读检查：仓库隔离 Jellyfin 为 healthy，媒体服务在运行；本次没有停止、重启或接管运行中容器，生产实例未操作。先前 unhealthy 是历史环境阻塞，不能继续冒充当前阻塞；当前产品／证据缺口以 [Task 审查](../TASK.md#b-review-result) 为准，健康状态不等于验收 PASS。

## 当前交接与固定输入

继续工作前读取当前 [Slice](../SLICE.md) 与 [Task](../TASK.md)；换机不重设 Base、不重新打开已通过的历史 Task，也不继承旧服务器资源结论。

| 输入 | 固定身份／新主机要求 |
|---|---|
| 平台 | 当前目标 Linux x64；可在任意仓库检出路径工作，无须旧服务器目录 |
| SDK | `global.json` 固定 10.0.401；[环境规格](../dev/environment-spec.json) 提供官方归档及 SHA-512 |
| Jellyfin | 12.2.0；源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`，Controller／Model 12.2.0，net10.0 |
| 镜像 | [公开镜像锁](../dev/images.lock.json) 包含已接受的 Jellyfin 和媒体服务 digest；不依赖旧服务器 Docker 缓存 |
| 工具 | Git、Python 3、Docker Engine／Compose、curl、tar；浏览器场景另需 Node.js／npm、固定 Playwright 1.55.0 和 Chromium 1187，实际版本／路径在新运行记录 |
| 资源 | 在新主机记录 CPU／内存／swap／磁盘／inode，运行前制定预算；旧服务器限额和空闲量不适用 |

## 克隆与准备

用户已授权将完整开发历史与 V4.3 方案一并发布，替代旧的仅源码快照发布方式，并保留旧快照历史。新主机完整克隆即可读取固定 Base、已关闭合同和 B 决定，无须另行手动补入方案或私有 Git 迁移包。下列命令从新检出的仓库根目录执行；尚未在新主机运行，不能记为 PASS。

```bash
git clone https://github.com/kentinya/jellyfin-strm-probe.git
cd jellyfin-strm-probe
git status --short --branch
python3 scripts/check_governance.py
python3 scripts/development_environment.py sdk
```

SDK 安装只写仓库忽略目录，校验固定 SHA-512；离线可用 `sdk --sdk-archive /path/to/official.tar.gz`。Docker 使用本机 `/var/run/docker.sock`，所需权限在新主机准备，不连接旧 Docker endpoint。

首次准备时，把公开镜像锁安装为工具现有的本地锁文件，并按 digest 拉取，避免重新解析可变标签。以下操作只用于当前检出的测试环境，不覆盖不一致的已有锁：

```bash
python3 - <<'PYENV'
from pathlib import Path
import json
import subprocess

source = Path('dev/images.lock.json')
lock = json.loads(source.read_text())
assert lock['spec'] == json.loads(Path('dev/environment-spec.json').read_text())
target = Path('artifacts/dev-env/images.lock.json')
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and json.loads(target.read_text()) != lock:
    raise SystemExit('Existing image lock differs; inspect it before continuing')
if not target.exists():
    target.write_bytes(source.read_bytes())
for image in lock['images'].values():
    subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock', 'pull',
                    '--platform', 'linux/amd64', image], check=True)
PYENV
python3 scripts/development_environment.py doctor
bash scripts/dotnet-local --info
```

`provision` 在没有锁时会重新解析镜像标签，因此复现当前已接受组合优先使用以上公开锁流程。doctor 只验证环境，不代替插件和真实播放验收。SDK、NuGet、镜像、浏览器、媒体夹具和发布包均可在新机重新准备，无须复制旧缓存或 SDK 目录。

浏览器场景使用现有工具：

```bash
python3 scripts/prepare_browser_tools.py --print-system-packages
python3 scripts/prepare_browser_tools.py
```

先根据新主机发行版准备输出中所需的系统库；Node.js／npm 或系统库缺失时如实报告。工具将 Playwright 放入忽略目录，浏览器下载到当前用户缓存；不要求旧主机浏览器绝对路径。

## 构建与隔离实例

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 -m unittest discover -s tests -v
```

上面的完整构建／回归清单属于 B 的独立验收和 Slice Final 门槛；Developer 开发反馈按开发流程只运行改动文件直接影响的测试，并报告未运行的全量项目。

包／扫描验收复用 `package_environment.py`，自动建立本轮新工作区、向导／测试账户、合成媒体和库，仅消费传入 ZIP；默认本机端口 18097，可在启动进程前设置现有 `JF_PROBE_PACKAGE_PORT`。打包和安装命令见 [安装说明](package-installation.md)；两级大库入口 `scripts/run_isolated_large_library_integration.py` 已由 Task 4.3 实现，命令与证据索引见 [测试矩阵](test-matrix.md#slice-4-大库验收本地运行)。project 名由当前仓库路径派生；旧主机容器名、运行 token 和鉴权身份均不必沿用。

3000 项大库的执行计划自 2026-10-19 起按用户要求采用一次准备、所有需要它的轮次复用，详见 [当前 Task 的复用要求](../TASK.md#2026-10-19-用户明确的准备库复用要求)。准备库及一致离线基线跨 B／Final 保留，独立记录各轮输入与结果，最后统一清理；不影响独立干净安装验收。现有大库自动入口仍按次创建／清理工作区，不能直接用于跨次复用或据此声称已实现复用；本次仅调整文档，不改工具、不备份／恢复或操作容器。继续使用必须显式交接并核验归属，不放宽下方拒绝任意接管的规则。

三个既有开发部署回归另用 `artifacts/dev-env`，不是包安装验收。新环境要运行它们时，先 `python3 scripts/development_environment.py up`，在本机默认 18096 完成新实例向导：建立仅指向 `/media/strm` 和 `/media/local` 的两个临时库，禁用实时监控、远程提供器、写回和无关自动任务，清空测试实例的插件仓库列表。端口可在启动前用现有 `JF_PROBE_PORT` 调整，测试账户文件的 base_url 必须匹配。

开发回归的夹具输入为 `artifacts/dev-env/media/fixture.mp4` 及其逐字节副本 `fixture-alt.mp4`、`artifacts/dev-env/strm/Environment Fixture.strm`。在新机用锁定 Jellyfin 镜像自带 FFmpeg 制作本地合成媒体，STRM 指向容器内 `http://media:8080/fixture.mp4`，填写真实本地媒体的 SHA-1／Size；原生扫描后确认唯一项目名 `Environment Fixture`。这是测试准备，不是生产生成器；不从旧生产库复制数据。

将新实例测试账户写到忽略文件 `artifacts/dev-env/credentials.local.json`，字段为 `base_url`、`username`、`password`，权限须为 0600。使用新生成的随机口令；不在日志或提交中输出内容。旧服务器的测试账户和运行数据库不属于迁移前提。运行前按当前 Task 记录全部配置／触发器／夹具状态，运行后恢复并核验；已有非本轮容器或非空包工作区继续拒绝接管。

需要检查固定 Jellyfin 源码时，可在新机自行检出上述 SHA 到忽略目录；源码来源与 SHA 已在环境规格中，不要求旧主机源码树存在。不要重新运行历史 `bootstrap_repository.py` 初始化已克隆仓库。

## 证据迁移与继续工作

GitHub 同步的是 Git 历史中的代码、治理文档、依赖锁和公开环境身份。`.git/validation-evidence/`、`artifacts/`、浏览器缓存、配置、凭据、SQLite 和原始运行日志不随 clone／push 传输。本次不把这些本机资料上传到 GitHub，也不删除旧服务器资料。

旧索引仍是历史出处：没有旧目录不妨碍规划或实施，不撤销已提交审查决定；需要复用原始运行时，可单独安全迁移并核对摘要，无法核验则重跑对应门槛。新候选和单独 Slice Final 始终取得要求的新证据，不能把历史 PASS 当新主机实测 PASS。详见 [迁移流程](development-workflow.md#开发服务器迁移)。

继续 Task 4.3 时先记录新主机环境与运行前预算，再实施当前 Task。旧服务器无需继续在线；不会自动启动下一 Task、冻结 Slice 或重新申请环境参数授权。

## 已运行环境证据

此节保留历史链接入口。旧主机的环境实测与镜像溯源限制从 `b92bea58a2552997bd750f059fc7d6c6cca23b93:docs/development-environment.md` 读取，历史产品结果见 [关闭账本](progress.md) 和对应已提交审查快照；公开镜像身份见 [镜像锁](../dev/images.lock.json)。这些是历史结果，新主机环境与运行证据须重新记录。

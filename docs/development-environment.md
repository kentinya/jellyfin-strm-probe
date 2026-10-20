# 可迁移开发环境

本文件只描述可迁移开发环境、固定输入和运行前提。当前合同、Task 状态和产品验收统一见 [Slice](../SLICE.md)、[Task](../TASK.md) 与 [进度账本](progress.md)；旧服务器记录只作为 Git 历史，不是新主机开工前提。

## 环境检查历史（2026-10-18～19）

以下仅记录对应日期的环境观察，不代表当前容器健康、端口或资源仍相同。后续获授权运行前重新检查并记录实际环境；文档治理不启动或接管实例。

- `python3 scripts/development_environment.py sdk`：PASS，已存在并校验本地 SDK `10.0.401`；全局 `dotnet` 不在 PATH，统一使用 `bash scripts/dotnet-local`。
- `python3 scripts/development_environment.py doctor`：PASS，Docker Engine `29.7.1`、Compose `v5.3.1`、本地端口、DNS、NuGet HTTPS 和不可变镜像锁均通过。
- `python3 scripts/development_environment.py status`：若现有隔离 Jellyfin 健康检查失败，真实集成保持 `BLOCKED／NOT RUN`；不要接管或清理非本轮容器。
- 2026-10-19 续审只读检查：当时仓库隔离 Jellyfin 为 healthy，媒体服务在运行；该次未停止、重启或接管运行中容器，生产实例未操作。更早的 unhealthy 记录不作为当前阻塞；健康状态也不等于产品验收 PASS，最终验收以 [Closure Packet](../SLICE.md#closure-packet) 为准。

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

开发准备依赖仓库中的代码、固定输入和维护中的治理文档。按 2026-10-20 用户要求，V4.3 原方案仅为可选本地参考，不再跟踪或上传 GitHub；新主机无须补入方案，治理与 CI 均不依赖原文。已提交开发历史、固定 Base、已关闭合同和 B 决定保留；后续发布边界见 [Git 检查点](development-workflow.md#6-git-检查点)。下列命令从新检出的仓库根目录执行，实际结果须在该次准备中记录，不继承上方历史 PASS。

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

包／扫描验收复用 `package_environment.py`，自动建立本轮新工作区、向导／测试账户、合成媒体和库，仅消费传入 ZIP；默认本机端口 18097，可在启动进程前设置现有 `JF_PROBE_PACKAGE_PORT`。打包和安装命令见 [安装说明](package-installation.md)；大库入口 `scripts/run_isolated_large_library_integration.py` 的命令与证据索引见 [测试矩阵](test-matrix.md#slice-4-大库验收本地运行)。project 名由当前仓库路径派生；旧主机容器名、运行 token 和鉴权身份均不必沿用。

大库下限为至少 1000 个真实原生候选，直接使用现存全部 1004 项，不截取、不另跑 3000 级。准备库及适用基线在所有需要它的开发阶段持续复用，不能因 Task PASS 或 Slice 关闭销毁；现存有指纹的运行后状态不能冒充首次信任前基线。长期规则见 [开发流程](development-workflow.md#可核验证据与复用)，每次使用另行核验归属、输入与前置状态，不继承旧验收结果。

复用入口要求源 package 工作区已停止、归属可核验，且无符号链接或 SQLite 事务旁文件；在新归属副本上运行，原库前后摘要一致，结束停止并保留副本。场景、局部修复、显式副本指纹重置、PARTIAL／完整验收区分及准确命令统一见 [大库验收入口](test-matrix.md#slice-4-大库验收本地运行)，最终结果见 [Closure Packet](../SLICE.md#closure-packet)。不重复建库或准备全库，不影响独立干净安装验收，也不放宽拒绝任意接管的规则。

三个既有开发部署回归另用 `artifacts/dev-env`，不是包安装验收。新环境要运行它们时，先 `python3 scripts/development_environment.py up`，在本机默认 18096 完成新实例向导：建立仅指向 `/media/strm` 和 `/media/local` 的两个临时库，禁用实时监控、远程提供器、写回和无关自动任务，清空测试实例的插件仓库列表。端口可在启动前用现有 `JF_PROBE_PORT` 调整，测试账户文件的 base_url 必须匹配。

开发回归的夹具输入为 `artifacts/dev-env/media/fixture.mp4` 及其逐字节副本 `fixture-alt.mp4`、`artifacts/dev-env/strm/Environment Fixture.strm`。在新机用锁定 Jellyfin 镜像自带 FFmpeg 制作本地合成媒体，STRM 指向容器内 `http://media:8080/fixture.mp4`，填写真实本地媒体的 SHA-1／Size；原生扫描后确认唯一项目名 `Environment Fixture`。这是测试准备，不是生产生成器；不从旧生产库复制数据。

将新实例测试账户写到忽略文件 `artifacts/dev-env/credentials.local.json`，字段为 `base_url`、`username`、`password`，权限须为 0600。使用新生成的随机口令；不在日志或提交中输出内容。旧服务器的测试账户和运行数据库不属于迁移前提。运行前按当前 Task 记录全部配置／触发器／夹具状态，运行后恢复并核验；已有非本轮容器或非空包工作区继续拒绝接管。

需要检查固定 Jellyfin 源码时，可在新机自行检出上述 SHA 到忽略目录；源码来源与 SHA 已在环境规格中，不要求旧主机源码树存在。旧 `bootstrap_repository.py` 和 `bootstrap-manifest.json` 已移除；克隆仓库无须再次初始化，需追溯时从 `aa01231` 的 Git 历史读取。

## 证据迁移与继续工作

GitHub 的后续发布范围为代码、治理文档、依赖锁和公开环境身份，不重新加入本地 V4.3 原方案；此前已发布的方案历史仍存在，停止跟踪不会删除历史副本。`.git/validation-evidence/`、`artifacts/`、浏览器缓存、配置、凭据、SQLite 和原始运行日志不随 clone／push 传输。本次不推送、不把这些本机资料上传到 GitHub，也不删除旧服务器资料。

旧索引仍是历史出处：没有旧目录不妨碍规划或实施，不撤销已提交审查决定；需要复用原始运行时，可单独安全迁移并核对摘要，无法核验则重跑对应门槛。新候选和单独 Slice Final 始终取得要求的新证据，不能把历史 PASS 当新主机实测 PASS。详见 [迁移流程](development-workflow.md#开发服务器迁移)。

后续工作先读取当前合同／TASK，记录实际主机环境与运行前预算；2026-10-20 用户授权不验证 JellyfinProxy，不再准备代理构建／部署环境。旧服务器无需在线，现存全部 1004 项准备库／基线持续保留，不自动启动实施或验收；原生包／扫描／大库／播放的环境门槛不变。

## 已运行环境证据

此节保留历史链接入口。旧主机的环境实测与镜像溯源限制从 `b92bea58a2552997bd750f059fc7d6c6cca23b93:docs/development-environment.md` 读取，历史产品结果见 [关闭账本](progress.md) 和对应已提交审查快照；公开镜像身份见 [镜像锁](../dev/images.lock.json)。这些是历史结果，新主机环境与运行证据须重新记录。

以下 2026-10-19 聚焦补证的完整报告、失败和后续 B 决定保留于 `57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md`，使用 `git show` 读取。根 TASK 只维护当前入口，不再承载这些历史章节。

2026-10-19 增量补证继续只读复制现存 1004 项库；仅对新副本新增 4 项执行一次原生索引扫描，未重建库或重新准备原有 1004 项主流。随后受控增量、分批停止／恢复、重启／API 选源播放完成，使用独立端口 18100，未操作 8096 生产或 18096 共享实例；源库摘要不变，双服务 exit=0、无 OOM，副本 run-20261019-153547-1cf17f85 已停止保留。349.217 秒／221 资源样本，计划重启采样缺口 16.303 秒另记。该次私有聚焦过程不改变默认复用入口不扫描的行为，不是完整验收；输入、失败与原始证据见上述历史 Task 报告。

2026-10-19 查询停止补证继续复制原 1004 项库，未重建或扫描；成功副本 run-20261019-155237-10355c3e 使用 18103，双服务停止保留、exit=0／无 OOM、原库不变。此前 Docker 默认地址池耗尽：不 prune／删除保留网络、不改 daemon，只给新归属副本的两张 Compose 网络设置经现存网络／主机路由无重叠检查的显式子网（acceptance 仍 internal）。这是私有运行的环境适配，不改变通用工具。99.772 秒／55 样本未覆盖全部启动前成本或完整空闲窗，不宣称成本门槛完成；详见上述历史 Task 报告。

2026-10-19 四批次补证继续复制同一 1004 项原库，只局部准备 8 个变化对照并索引 4 个新增缺流项。18104 副本 run-20261019-161238-8665af91 已停止保留、双服务 exit=0／无 OOM、原库不变；仍只在新副本使用经无重叠预检的显式隔离子网。303.556 秒，复制前开始主机观测 304 次、服务启动后健康等待前开始服务观测 200 次；计划重启采样缺口 16.000 秒、前／间／后≥30 秒空闲窗及 RSS 趋势如实记录，不倒填历史全库准备资源成本。详见上述历史 Task 报告。

以上聚焦 PARTIAL 不替代后来完成的独立 Slice Final；最终证据与接受决定见 [Closure Packet](../SLICE.md#closure-packet) 和 [A Final Review](../SLICE.md#a-final-review)。关闭和文档交接均不清理准备数据。

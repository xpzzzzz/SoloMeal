# 2026-09-18 发布准备：提交、远程拓扑更正、CI 全绿与哈希冻结

## 结论

远程 `ci-complete` 首次在同一提交上全部通过：run `35319166877`（事件 `push`，`main` = `f3f9c7b3b799f42199562227f9b9c47a2cb4806c`），九个作业 `tests (3.12/3.13/3.14)`、`types`、`coverage`、`backend`、`frontend`、`browser-e2e`、`ci-complete` 全部 `success`，`ci-complete` 完成于 `2026-09-18T07:34:33Z`。本轮模型调用新增 0，累计聊天 1685/视觉 30；未部署任何环境，源 18080 未触碰。

这不是 P9-04 的完成宣称：CI 绿只解除「远程流水线未跑」这一条，新物理主机验收与 v1.0 发布仍是独立条件。P5/P8/P9 整体、合成留出 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null 全部保持原样。

## 远程拓扑更正（推翻第95节初稿的权限推测）

初稿把推送 403 记为「`xpzzzzz` 对 `sergiparpal/meal-manager` 无写权限、根因待管理员核实」。该推测的前提是错的：用户与 `sergiparpal` 无账号关联，也从未持有该仓库权限；`sergiparpal/meal-manager` 只是本项目的只读上游，此事实早写在 `docs/upstream.md:4`（本地基线 `a923d77c…`、`origin` 指向上游、从未向其提交或推送）。403 因此不是待修复的授权缺口，而是对一个本就不该写入的仓库发起写入。

处理：新建用户自有私有仓库 `https://github.com/xpzzzzz/SoloMeal`（创建后核对可见性并按需改为 private），`origin` 指向它；`upstream` 保留 fetch URL，push URL 置为 `DISABLED`，防止误推上游。GPL-3.0 与原归属声明随仓库文件原样保留，未改写。缓存中另有一个不可达的旧 `origin`，本地领先计数以 `origin/main` 为准，不再是那个缓存值。

## 失败留证与根因

| run | 事件/提交 | 结果 | 关键作业 |
| --- | --- | --- | --- |
| `35315860979` | workflow_dispatch @ `39ab68f` | `ci-complete` failure | `types` failure、`backend` cancelled、`browser-e2e` failure |
| `35315916647` | Dependabot PR #1 @ `146d592` | failure | `backend` 跑完但 3 failed / 543 passed |
| `35319166877` | push @ `f3f9c7b` | success | 九作业全绿 |

三类根因，逐条都在本地以等价检出复现后才动手：

1. **冻结摘要被换行规范化打破。** `evaluation/freeze-v1.json` 及其后继链、`docs/validation/` 各报告的 `files_sha256` 逐文件映射，记录的是原始工作区字节（CRLF）的 sha256。第 `9a060b0` 节为隔离独立应用把改动文件规范化为 LF 后，CI 检出的 blob 字节变了：`evaluation/scenarios-v1.json` 记为 `2aa39319…` 而 LF 检出算出 `bb575852…`，`freeze-v1.1.json` 记为 `0e41e266…` 而检出算出 `39337fdd…`，于是 `test_preregistered_files_match_freeze` 与 `test_budget_amendment_freeze` 失败。
2. **`mypy -p meal_manager` 走进了非插件目录。** 包模式会遍历仓库根下所有 `.py`，把 `deploy/` 的验收驱动和 `docs/validation/` 的证据脚本一并纳入严格检查，报 42 errors in 7 files。这些从来不在插件的类型检查面上。
3. **backend 作业预算与前置产物。** 该作业顺序跑两轮全量 pytest（真实 MySQL 与 SQLite 回退），15 分钟上限在 dispatch run 里正好砍在第一轮（`06:40:28 → 06:55:44 cancelled`）；`test_registration_refuses_existing_directory_and_freezes_protocol` 断言一次真实诊断登记会把 `frontend/dist/*` 冻结进清单（`backend/scripts/recommendation_diagnostic.py:46` 直接 rglob 该目录），而裸检出没有构建产物——本地能过只是因为先前构建残留。

`browser-e2e` 在 dispatch run 里 3 个场景超时，在与主代码同内容、无并发争抢的 PR run 里通过；本轮 push run 全绿。据观测记录为「该轮通过」，不宣称竞态成因已被消除。

## 修复

- `.gitattributes` 把 31 个「当前字节确实被已提交清单记录」的路径标为 `-text`，再 `git add --renormalize` 把原字节写回索引（提交 `1882669`）。入选判据是机器算出来的：全仓任意 64 位十六进制串为针，凡工作区 sha256 命中且与索引 blob 不同者入选，故不含猜测。核对结果：31/31 个索引 blob 现在命中某个已记录摘要；提交 diff 为 6963 增 / 6963 删逐行相等，纯换行、零内容改动、零摘要改写。`compose.yaml` 原本就是混合换行（`i/mixed`），正是必须逐字节存档的一条佐证。
- `pyproject.toml` 的 mypy `exclude` 增列 `deploy/`、`docs/`，类型门回到插件本体（提交 `f3f9c7b`）。
- backend 作业加 `setup-node` + `npm ci` + `npm run build`（构建产物 `index-BTAvzu0t.js`，与线上验证版本同名），并保留断言不放宽；`timeout-minutes` 15→20。
- 未修改任何测试判据、未修改冻结清单与报告文本、未改 git 全局配置。

## 验证方法（不靠本机环境侥幸）

以 `git -c core.autocrlf=false clone file://…` 造一份等价于 Linux 检出的工作副本：修复前该副本精确复现 CI 的 3 个失败（其余 543 通过），修复后同一副本 `pytest` 退出码 0；`npm ci && npm run build` 在该副本内成功。mypy 在 Windows 仍报 6 处 `fcntl`/`fchmod` 属性缺失（`src/filelock.py`、`src/__init__.py`），这是 Linux 专有 API 在本机的预期缺失，CI ubuntu 上 `types` 作业为 success。

## 冻结值

- 提交：`f3f9c7b3b799f42199562227f9b9c47a2cb4806c`（`main`，已推送至私有 `origin`），tree `d0d02354092c94c82ad853f9307311e0f0bb1fc3`。
- 后端源码聚合：`c3161b9b8c69fcfad70e7b12425e2d7c94aafce3391b486fe67e811ebd95bcb3`（67 个 `app/**/*.py` + `scripts/**/*.py`，口径同 `backend/scripts/diagnose_purchase.py:source_hash()`），与第84/91节记录值一致，即后端源码本轮零改动。
- 前端源码（15 文件自订补充口径）：`4285ae314aac…205001aa`；构建产物 `index-BTAvzu0t.js`。
- 镜像：API `sha256:908cf165568b…f69ec0d3`、web `sha256:f2928999404b…b0f5da0f`（本轮未重建，故 digest 不变）。

口径限制必须写明：上述源码聚合哈希按工作区字节计算，Windows 与 Linux 检出的换行不同即不同值；逐字节可复现的是 31 个 `-text` 路径的索引 blob 与 git tree/commit 标识。发布应以 commit SHA + git tree + 镜像 digest 为准，源码聚合哈希作为其派生记录，不当作跨平台常量。

## 未纳入本轮的既有事实

- Dependabot PR #1（`actions/setup-node` 4.4.0→新版）仍 open，其 head 早于本轮两个提交；未合并、未关闭，待用户决定。
- 仓库根下 5 个未跟踪且未 ignore 的 ACL 锁死目录（`.pytest-a026-contract-0914`、`.pytest-purchase-contract-{final,v2,verified}-0914`、`.test-tmp-crud-0906`）git 不可读，`git status --porcelain` 对每个打权限警告但退出码 0、且不出现在 `??` 行里；`.test-tmp-shopping-0907` 为空目录故不列出，其余 `.tmp-*` 命中 `.gitignore:29` 而被跳过。初稿把它写成「退出码 2、6 个目录」，此处更正。本轮未删除、未改其权限。
- 源 18080 仍未部署第91/92/94节前端；18082 保持 stop、卷保留，卷内累计 2 个一次性洪泛空账号。

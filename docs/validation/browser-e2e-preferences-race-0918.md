# 2026-09-18 browser-e2e 偏好面板竞态：根因、注入复现与测试侧修复

## 结论

`browser-e2e` 在 run `35320718788`（事件 `push`，`main` = `1b6cf00`）失败 2/18，连带 `ci-complete` 失败。该 run 相对上一个全绿 run `35319166877`（`f3f9c7b`）的改动只有 7 个 `.md` 文件，且两轮 `npm run build` 产物同为 `index-BTAvzu0t.js`（Vite 文件名即内容哈希），因此**不是代码回归**，而是同一份字节在慢响应下命中了 e2e 驱动的时序假设。

根因：驱动切到「厨房偏好」后立刻 `fill` 厨具，而偏好面板**每次挂载都会 GET `/api/v1/me/preferences` 并 `setValue`**。该请求晚于输入落地时，受控输入被服务端旧值覆盖，随后 PUT 保存的就是空厨具；后端按厨具做子集硬过滤，于是候选为 0，页面显示「没有符合条件的菜谱」——与 CI 失败页面的逐字输出一致。

修复只落在 `frontend/e2e/` 四个文件（新增 `openPreferences` 就绪等待），**应用代码零改动、断言未放宽**。本地以 1.5 秒延迟注入 GET 做 A/B：不等待即复现 CI 症状（PUT body `equipment: []`），等待后同延迟下保存 `["煮锅"]` 且页面出现预期文案；全量 `npm run e2e` 18/18 通过，构建产物仍为 `index-BTAvzu0t.js`。修复提交 `d3fcb9d` 的远程复跑 run `35322761131` 九作业全 `success`，`ci-complete` 再次为绿。

P5/P8/P9 整体、合成留出 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null 保持原样；本轮模型调用新增 0（累计聊天 1685/视觉 30），未部署任何环境，源 18080 未触碰。

## 失败观测（逐字）

| 场景 | 断言 | 页面实际（失败快照） | 耗时 |
|---|---|---|---|
| `e2e/mobile.test.mjs:113` 手机上可以从报价走到采购入库、做饭与撤销 | `waitText(page, /缺 鸡蛋/)` | `没有符合条件的菜谱，请核对厨具、用时与忌口设置。`，菜谱卡片「测试煮鸡蛋 · 煮锅 · 鸡蛋 2 个」在页 | 31.5 秒（30 秒超时） |
| `e2e/planning-boundaries.test.mjs:7` 无可行菜谱、未知补购预算和旧方案确认均在页面解释且不扣库存 | `waitText(page, /补购价格未知/)` | 同上（「边界煮蛋」卡片在页） | 33.5 秒（30 秒超时） |

两处都在「设置厨具偏好 → 生成推荐」这一步之后失败，其余 16 个场景同轮通过。

## 机制链（代码位置，均为已读代码）

1. `frontend/src/main.tsx:79` — `Preferences` 组件 `useEffect(..., [])` 在每次挂载时 `setValue(await api('/me/preferences'))`；`main.tsx:80` 保存按钮 `disabled={busy}`。
2. `frontend/src/main.tsx:58` — `perform` 统一置 `busy`，因此该 GET 在途时整页按钮禁用。
3. 驱动 `useTab` 只点导航按钮，不等这次 GET（`frontend/e2e/support.mjs:120`），随即 `fill`；React 受控输入在 GET 落地时被重渲染为服务端值。
4. Playwright 的点击会等按钮重新可用，而「可用」恰好发生在 GET 落地之后——**慢 GET 时这不是偶然踩中，而是必然顺序**：输入先被覆盖，点击才发生。
5. `backend/app/services/planning.py:56-58` 取偏好厨具，`:115` 要求 `recipe.equipment ⊆ 偏好厨具`，故空厨具使任何写明厨具的菜谱全部落选，`candidates: []` 即前端那句提示。

## A/B 注入证据

一次性脚本（未入库，跑完删除）：`page.route('**/api/v1/me/preferences')` 对 GET 追加 1500ms 延迟，其余步骤照 `planning-boundaries` 的序列。

| 变体 | PUT 状态 | PUT body `equipment` | 推荐结果 |
|---|---|---|---|
| 切 tab 后直接 `fill`（旧驱动写法） | 200 | `[]` | `没有符合条件…`（复现） |
| 先等该次 GET 响应再 `fill`（新驱动写法） | 200 | `["煮锅"]` | `补购价格未知`（预期） |

旧写法的断言链只校验 PUT 状态码 200，不看请求体，因此覆盖过程在页面上不可见，只有下游推荐为空才暴露。

## 复跑与冻结量核对

- 修复提交 `d3fcb9d`（push）→ run `35322761131` 九作业全 `success`，含 `ci-complete`（`2026-09-18T08:18:03Z`）。`browser-e2e` 该轮 18/18。
- 本节文档提交 `348fdf6`（push，仅 7 个 `.md`）→ run `35324565914` 九作业全 `success`、`ci-complete` 于 `2026-09-18T08:39:22Z`，即本轮文档改动未触及任何冻结校验（两条 freeze 测试与 `files_sha256` 核对全通过）。登记到此为止：其后若再有为补记本行而生的文档提交，其结果以 GitHub Actions 运行列表为准，不在本报告内自我登记。
- 前端源码聚合在本轮改动后**仍为** `4285ae314aace08a32801cff5c3228213c0d9093e3a6c51a94b76e31205001aa`（15 文件），构建产物仍 `index-BTAvzu0t.js`，即第95节冻结值未被本轮推翻。该口径此前只记了结果没记算法，现补全以便复现：按 `frontend/` 下 `sorted(src/**/* + index.html + tsconfig.json + vite.config.ts + package.json)` 逐文件喂入 `相对路径(POSIX) + b'\0' + 文件字节` 后取 sha256；`e2e/` 目录不在其内，故本轮四处驱动改动不进入该哈希。后端聚合 `c3161b9b…` 未受影响（后端文件零改动）。

## 修复范围

- `frontend/e2e/support.mjs` — 新增 `openPreferences(page)`：注册 GET 监听→切 tab→等该响应，再交回调用方输入。
- 四处写入前置的调用点改用该助手：`lifecycle.test.mjs:42`、`mobile.test.mjs:75`、`mobile.test.mjs:118`、`planning-boundaries.test.mjs:33`。
- 读取回显那处（`mobile.test.mjs:103` 已有 `value!==''` 轮询）本轮未动：它当前通过，且改它属另一项判断。

## 边界与未做

- 修复消除的是**测试对该时序的敏感**。UI 层同一缺陷仍在：真实用户在慢网络下输入厨具后，仍可能被挂载时那次 GET 的响应覆盖。修它需改 `main.tsx`，会使已冻结并通过 CI 的前端产物变化并触发重新冻结，本轮未做，待用户决定。
- 「挂载即 GET ＋受控输入」在其它面板是否也构成竞态未穷举，本轮只处理已被 CI 命中的偏好路径。
- 未验证 CI 侧慢响应是否消失，只验证了驱动不再依赖它；复跑结果见上文「复跑与冻结量核对」。
- 未做 stress 重跑（例如连续多轮 `npm run e2e`）来量化其它场景的残余抖动。

## 附带核对：插件套件计数的平台差异

- 同一份 `test_unit.py` 在 `39ab68f` 本地计 372 通过，在 `f3f9c7b` 及之后本地计 373 通过，Linux CI 为 376/300（本轮 `tests (3.13)` 作业日志逐字）。差 1 的原因是 `test_unit.py:2271` 逐 `- uses:` 行核对 action 是否钉到完整 SHA，而修 CI 时 backend 作业新增了一行 `actions/setup-node@…`；对拍用同一 clone 的两个提交各跑一遍（372 对 373），差值由此而来。
- 373→376 的另 3 项对应 Windows 侧两处 SKIP（`test_unit.py:1825` fcntl、`:2011` 不可读文件探针）与 `test_unit.py:2048` 的 posix-only 分支；**这一条是按行号对齐的推断，未逐项在 Linux 上对拍**。
- 因此交接文字中「本地插件套件 372+298」一律更正为「本地 Windows 373+298（2 项平台 SKIP）、Linux CI 376+300」，两者都是全绿退出 0，不表示判据变化。

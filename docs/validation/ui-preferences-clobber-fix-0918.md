# 2026-09-18 UI 侧偏好面板挂载覆盖缺陷修复（第96节保留项处置）

## 结论

第96节在测试驱动侧消除了 browser-e2e 对偏好面板挂载 GET 时序的敏感，并记录同一缺陷在 UI 侧保留：`Preferences` 组件挂载时 `setValue(await api('/me/preferences'))`（`frontend/src/main.tsx:79`）无条件回填受控输入，真实用户慢网络下已输入的厨具会被晚到的响应清掉。本轮经用户授权修复 UI 本体。

- 应用改动仅 `frontend/src/main.tsx` 一处组件（+4/−2 行）：新增 `edited` ref，四个字段的所有 `onChange` 统一经 `edit()` 置位；挂载 GET 落地时 `if(!edited.current)setValue(stored)`——用户未编辑则照常回填，已编辑则响应作废。
- 新增回归 `frontend/e2e/preferences-race.test.mjs`：`page.route` 对该 GET 注入 1500ms 延迟（与第96节 A/B 同源），切换 tab 后立即输入「煮锅」，等响应落地后断言输入框仍为「煮锅」，再保存并断言 PUT 响应 `equipment:["煮锅"]`。
- **双向验证**：修复版下新用例通过；`git checkout` 还原旧 `main.tsx` 重建后同一用例失败（输入被覆盖），随后恢复修复版重建，产物一致。即该用例确实钉住本缺陷，不是恒真断言。

## 本地套件

| 套件 | 结果 |
|---|---|
| 插件 `test_unit.py` / `test_integration.py`（Windows） | 373 / 298 通过，0 失败 |
| 前端 `npm test` | 36 通过（未新增纯模块单测，见「范围」） |
| `npm run build` | 通过，产物 `dist/assets/index-D2Luux6J.js` |
| `npm run e2e` 全量 | **19/19** 通过（原 18 场景未放宽＋新用例 1） |
| 新用例单独（修复版 / 旧代码反例） | 通过 / 失败（预期的失败） |

## 冻结量变化（第95节值被本轮正式取代，历史不改写）

- 前端源码聚合：`4285ae31…205001aa`（15 文件）→ **`1a99ab46a45e6431b08e20cb3743990b6445e482d7ae0740d32c6593acd7ba48`**（同口径 15 文件，算法定义见[竞态报告](browser-e2e-preferences-race-0918.md)第 45 行；本轮按该定义重算）。
- 构建产物：`index-BTAvzu0t.js` → `index-D2Luux6J.js`（文件名即内容哈希）。
- 后端聚合 `c3161b9b…`（67 文件）、API 镜像 `908cf165568b…` 不变（后端零改动）；web 镜像因内嵌新产物而需重建，第95节 digest `f2928999404b…` 对应产物不再为线上新版本目标。
- 两条 freeze 测试与 `files_sha256` 核对不引用上述文档性哈希（全仓仅 `.md` 与本报告引用），CI 无预期失败项。

## 范围与未做

- 未穷举其它面板「挂载即 GET＋受控输入」同类竞态（`AgentPanel`/`ReceiptPanel`/`ShoppingPanel` 的挂载读取是否覆盖用户输入另行核对，本轮只修已被第96节证实的偏好路径）。
- `mobile.test.mjs:103` 读取回显轮询与 `support.mjs:openPreferences` 驱动等待保持不动：前者本就等待，后者在有修复后仍是正确的确定性写法，且它同时是旧 CI 症状的守卫。
- 无 token 预算类改动、无后端改动、无模型调用（累计聊天 1685/视觉 30 不变）。
- 线上 18080 重部署与远程 CI 复验为本轮后续步骤，结果以 Actions 运行列表与 STATUS 追加记载为准，不在本报告内预写。

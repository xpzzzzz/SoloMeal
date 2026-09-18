# 报价与采购阶段验收（2026-09-07）

本轮按NEXT_SESSION下一优先级开发P4报价持久化与P6采购编辑入库。未启动小票、部署或真实模型请求。原有未提交成果保留，未commit/push。

## 实现边界

- 迁移e821b469a103，新增price_quotes、shopping_lists，共20业务表。报价每用户每食材一条当前记录，版本保护；金额CNY、包装量按规范单位，来源和观察日期必填，超过30天保留但标stale。
- 推荐默认读取保存报价，本次quotes逐食材覆盖；use_saved_quotes=false仅用本次报价。整包装成本、未知预算和过期报价规则保持。方案/Agent待批准提议冻结当时有效输入报价；以后修改价格不会悄悄替换旧预览。快照仅保存相关食材报价。
- 从当前pending方案版本生成采购草稿，同方案版本重复准备返回原清单。草稿保留原缺料与估价，可编辑数量、实际总价、位置、到期日期/来源及移除条目；保存草稿不入库。
- 确认使用草稿版本与operations幂等，owner锁内调用food.add_batch(operation=op)，所有批次/事件/清单终态一次提交。有预算时实际金额必须完整且不超预算；未知不能按零处理。无预算时金额可留空。
- 采购是实际购买记录，生成后独立于方案生命周期；后续方案修订/取消不自动取消采购。入库使原方案库存快照过期，做饭前需更新方案。取消/完成清单不再编辑或再次入库。
- 采购items合并存JSON，含经校验的Decimal字符串与币种；不单建items表。当前无价格历史、采购撤销或自动更新报价；原方案版本取消采购后若要重新准备，先修订方案。

## 自动化证据

| 检查 | 结果 |
|---|---|
| SQLite：test_shopping（首6项）+test_planning+test_plans | 13 passed / 3 MySQL并发skipped |
| SQLite：test_agent+test_agent_sessions+test_agent_actions+test_model_transport | 26 passed / 1 MySQL并发skipped |
| MySQL：test_shopping（首6项）+test_planning+test_plans+test_plan_lifecycle | 20 passed，142.24秒 |
| 最终MySQL：test_shopping（9项）+test_agent（8项） | 17 passed，91.77秒 |
| 收尾SQLite采购数量上限专项 | 1 passed，1.39秒；份数放大超过入库参数上限时拒绝建草稿 |
| frontend npm test | 8 passed，9.18秒（已有SSE测试，非新增采购组件测试） |
| 最终npm run build | tsc/Vite通过，index-Bp5roebF.js |
| 开发库alembic upgrade head / check | e821b469a103；No new upgrade operations detected |
| 修改文件ruff（FastAPI Depends惯例排除B008） | 通过 |
| 原插件test_unit.py / test_integration.py | 368 / 298检查通过，0失败；根data/不存在 |

数据库测试只用solomeal_test，未并行运行共享schema。首轮旧pytest缓存目录权限拒绝，改仓库内独立临时目录后通过。Docker最初未运行，启动Docker Desktop及已有solomeal-dev-mysql后验证；未操作MySQL80或其他项目容器。两条既有TestClient第三方弃用警告仍在。

测试覆盖用户隔离、报价新建/更新版本、未来日期/个数歧义/过期、显式报价优先级、预算/整包装、冻结快照、草稿恢复、同键重放、不同键重复确认拒绝、整单第二条失败回滚（批次/事件/operation均无残留）、非法编辑回滚、报价竞争、采购编辑/确认竞争，以及采购后方案更新/做饭/撤销。

## 浏览器证据

127.0.0.1:8010临时SQLite夹具，合成用户ui_shopping_0907；无真实模型。使用脚本生成测试鸡蛋/菜谱后取消其入库预览，初始库存为空。

1. 保存鸡蛋6个/包、¥5.50、手动记录、2026-09-07报价。
2. 菜谱推荐缺1鸡蛋，保存方案并准备采购，草稿按整包显示6个。
3. 实际购买改8个、¥6、冷藏、2026-09-15、包装日期来源，保存版本2；入库按钮在有未保存修改时禁用。
4. 刷新重登录：库存仍0，采购恢复版本2的数量、金额和日期来源。
5. 两步确认后采购完成版本3，库存出现1批8个；完成记录无再次入库按钮。
6. 原方案按当前库存更新到v2，确认做饭后剩7个；历史撤销后恢复8个。主库存页无需手动刷新。
7. 已复核桌面采购页面及明细截图。

首次采购整数输入使用min=0.001与step=1，浏览器原生验证拒绝8，已修复为piece的min=1；重新构建后上述保存/重登录/确认闭环通过。一次Playwright标签定位失败，改用实际AX控件成功。撤销按钮触发JS确认提示后，读取状态显示已撤销，未重复点击。

未宣称完整移动端、软键盘、实际离线、注销中断、多标签页续聊竞争、真实模型或全量E2E验收。临时浏览器服务和页面在收尾停止；不保存密码/令牌。

收尾复查修复了极大份数放大后可能生成无法确认的采购草稿：创建时验证PurchaseItem，超限返回422且不保存草稿。此纯输入边界追加SQLite专项通过；MySQL17项是该检查加入前的事务/Agent证据。最终git diff --check通过；文档写入造成的CRLF检查提示已修正。8010监听已确认停止。

# P7 第一段验证（2026-09-08）

范围为私有上传、结构化解析接口和手工编辑草稿；无确认入库、真实视觉或真实AI效果数据。新增测试文件backend/tests/test_receipts.py、frontend/e2e/receipts.test.mjs，以及二进制响应会话隔离单测。

| 检查 | 结果 |
|---|---|
| SQLite全量：pytest --basetemp=.tmp-receipts-full-0908 -o addopts='' -p no:cacheprovider -q | 85通过/10项MySQL专属跳过，93.92秒 |
| MySQL专项：scripts/test_mysql.py tests/test_receipts.py -o addopts='' -p no:cacheprovider -q | 14通过，89.57秒；每例测试库升降级 |
| 开发库alembic upgrade head、alembic check | 通过；f912a570bc24，无模型差异 |
| frontend npm test | 16通过，9.22秒，包括迟到私有图片会话隔离 |
| 手机与小票E2E定向复验 | 3通过，24.33秒 |
| 原test_unit.py / test_integration.py | 372/298检查通过，退出0 |
| 新增/修改Python的ruff（忽略FastAPI B008惯例） | 通过 |

MySQL专项覆盖上传幂等/参数冲突/用户内哈希提示、文件权限/类型/大小/丢失、解析未知值/别名、修正快照/版本/跨用户映射、超时/异常/非法结构回退、数据库失败文件清理，以及解析暂停期间人工编辑不阻塞且迟到结果不覆盖。没有执行本轮MySQL全量，不把SQLite跳过算MySQL通过。两个第三方弃用警告未新增依赖处理。

浏览器使用1像素PNG测试文件、临时SQLite和受控服务，未使用中文真实票据：验证上传响应丢失后同键重试只有一条导入、鉴权原图可解码、未知数量/单位留空、人工修正/刷新重登恢复、换账号不可见，整个过程库存为空。截图在frontend/.tmp-e2e/receipt-draft.png，已视觉检查。已有手机回归导航新增小票入口并检查窄屏溢出/按钮。

首次失败及修复：pytest把5MiB超限参数生成巨大测试ID，Windows临时目录准备失败；改为显式短ID。首次浏览器套件9通过/2失败：导航固定预期漏新入口、单位下拉定位超时；更新导航预期和显式aria-label后专项通过。最终完整套件结果另在收尾追加。

正式限制见[小票边界](../receipts.md)：文件头检查不等于完整安全解码；默认适配器没有真实视觉；无库存确认事务。未提交/推送或运行远程CI。

- 最终收尾：完整 `npm run e2e` 11 passed（79.12秒，9业务场景+2夹具生命周期），tsc/Vite通过，index-CtZnwp7x.js。鉴权原图加载额外检查naturalWidth>0。本轮夹具退出、无db-*残留，截图已视觉复核；根data/不存在，未提交/推送。

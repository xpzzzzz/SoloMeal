# P7 第二段：小票确认验证（2026-09-08）

实现：确认/取消端点，草稿位置与到期日期来源，全部非排除行完整校验，复用用户锁、operations与add_batch的整单事务，完成结果与终态；React保存后两步确认与同键重试。追加迁移0a23c671de89，仅增加receipt_imports.result，不重建表。

| 检查 | 最终结果 |
|---|---|
| SQLite全量：backend内 pytest -o addopts='' -p no:cacheprovider --basetemp=.tmp-confirm-full-0908 -q | 97 passed / 15 MySQL专属 skipped，135.73秒 |
| 真实MySQL：scripts/test_mysql.py tests/test_receipts.py tests/test_receipt_confirmation.py -o addopts='' -p no:cacheprovider -q | 31 passed，282.12秒；本项目solomeal_test，每例升降级，不是全后端MySQL套件 |
| npm test | 16 passed，9.21秒 |
| npm run e2e（含构建） | 12 passed，96.92秒，10业务+2夹具生命周期 |
| 终态文案修正后构建及node --test --test-concurrency=1 --test-timeout=180000 e2e/receipts.test.mjs | 2 passed，14.74秒；最终index-DnTcH6bd.js |
| 开发库alembic upgrade head / alembic check | 通过，无模型差异 |
| 原插件test_unit.py / test_integration.py | 372 / 298检查通过，退出0 |
| 修改Python ruff（忽略FastAPI B008惯例）/ git diff --check | 通过 |

后端覆盖：未核对、未知字段、未匹配、整单位/维度、日期来源不一致、全排除拒绝；确认/取消/旧版本/跨用户请求；同键参数绑定与重试、终态禁止编辑/解析；同食材多行独立批次，第二行抛错回滚全部批次、事件、operation、状态及结果，原键可再试成功。真实MySQL进一步覆盖同键/异键确认竞争、编辑/取消与确认竞争、解析期间手工编辑及确认成功后迟到解析409。kg换算与未知到期日期也有断言。

浏览器覆盖：上传丢包重试、未知值保存与恢复、核对第一步库存仍空、确认响应丢失后同键重试只产生一个批次/事件、重登录恢复终态、取消终态与账号隔离。截图frontend/.tmp-e2e/receipt-confirmed.png；视觉复核发现完成记录仍显示“等待手工补录”，改成“已保存的核对记录”后专项重跑通过。首次ruff仅导入排序问题已修复；git检查的CRLF尾空白已统一修正。

没有真实视觉/中文票据效果验收；文件仍仅头部签名检查，解析成本与并发调用控制待第三段。哈希仅用户内提示，不保证另一份重新上传草稿无法确认。前端浏览器使用临时SQLite和脚本模型，不替代MySQL或真实模型证据。两个既有第三方弃用警告保留，不变更锁定依赖。

保留全部原有未提交成果；未提交/推送，未读写根data/或打印/修改私有.env。浏览器夹具退出、无db-*残留；本项目MySQL容器维持运行，未操作其他服务。

# 2026-09-05 方案版本验收

- MySQL scripts/test_mysql.py：25 passed，2第三方弃用警告，84.57s。
- SQLite pytest：22 passed，3 MySQL专属并发跳过，2警告，21.41s。
- Alembic升级7a48cdc81c59并check：No new upgrade operations detected。
- 前端tsc+Vite生产构建通过，JS211.12kB，gzip66.89kB。
- 新增6个方案用例：创建/重复确认/隔离；库存变化与版本更新；偏好变化和不足回滚；并发确认；新增别名忌口；未知预算拒绝。
- 未运行真实模型或本轮完整浏览器E2E；原插件源代码本轮未修改，不重复其已通过测试。
- 并发策略变更为用户行锁+READ COMMITTED，所有库存写入和偏好写入遵守该边界；确认状态和扣减同事务。
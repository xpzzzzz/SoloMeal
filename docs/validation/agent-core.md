# 2026-09-05 Agent核心验收

- SQLite全量：28 passed，3 MySQL专属并发跳过，25.78s。
- MySQL全量（追加两项测试之前）：31 passed，102.34s。
- 追加限额/租约取消规则后：Agent专项SQLite8 passed，8.84s；MySQL8 passed，26.73s。
- 以上每次均有2条已知第三方弃用警告。
- 前端tsc+Vite通过，JS215.21kB/Gzip68.16kB。
- Alembic升级bd048bb65ef9；check无模型差异。
- git diff --check通过，存在系统autocrlf提示，不修改全局设置。
- 所有模型测试使用Scripted替身，真实模型适配未联网验证，未消耗模型API额度。
- 覆盖：工具反馈循环、用户隔离、拒绝user_id注入/非白名单工具、提案确认不扣库存、幂等批准、旧提案拦截、失败脱敏/重试、无模型配置、无效JSON、8次尝试上限、重复推进互斥、取消后迟到响应失效。
- 尚缺：传输MockTransport契约、真实模型、SSE、完整浏览器E2E和生产性能评估。
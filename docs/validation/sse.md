# 2026-09-05 SSE与传输验证

- MySQL全量45 passed，2已知第三方warning，137.35s。
- SQLite全量41 passed/3并发跳过，19.20s；追加旧run迁移与最终SSE读取顺序后专项3 passed，3.99s。
- 前端3项测试：UTF-8/CRLF按字节切分，多帧/多行/半帧，断线重连带游标并去重；最后测试1.30s。
- tsc+Vite构建成功，JS217.38kB，gzip69.06kB。
- 数据库upgrade/check成功，无模型差异；ruff F/I通过。
- 契约测试使用httpx.MockTransport；没有真实API调用。
- 已验证重放/越界/其他用户/匿名拒绝、幂等取消不重复事件、旧run迁移补初始事件。
- 未声明完整浏览器断网、SSE代理缓冲、后台worker或逐token流已验收。

- 最终MySQL SSE专项3 passed，13.95s；修改CI后原插件单元368 passed；服务重启后health/ready为ready，OpenAPI含events路由。

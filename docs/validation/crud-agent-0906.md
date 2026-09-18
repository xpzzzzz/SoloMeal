# 2026-09-06 CRUD、Agent确认与浏览器验收

未提交、推送或调用真实模型。原src业务及真实data未改。

## 自动化证据

| 命令/环境 | 结果 | 范围 |
|---|---|---|
| SQLite test_crud + test_plan_lifecycle | 8 passed, 2 skipped | 归档/CRUD/评分/取消 |
| MySQL全量（P2/P4） | 61 passed, 252.02s | 同秒事件排序修复后 |
| SQLite agent/session/SSE | 14 passed, 1 skipped, 11.57s | 会话与旧run迁移 |
| MySQL agent/session/SSE | 15 passed, 114.07s | 降级索引修复后 |
| SQLite agent_actions/agent/session | 17 passed, 1 skipped, 22.41s | 确认写入、回滚、过期 |
| MySQL全量（确认工具加入后） | 70 passed, 1 failed, 489.61s | 唯一失败为旧工具清单断言 |
| 更新清单后模型传输专项 | 9 passed | MockTransport，无真实网络 |
| 最终MySQL脚本：做饭撤销/会话/传输 | 11 passed, 7.71s | 最后可读文本修正后 |
| 最终npm test / npm run build | 3 passed / 成功 | TypeScript+Vite |
| Alembic upgrade/check | 成功、无新diff | 开发库da41905c772e，18业务表 |

共享solomeal_test始终串行运行。修正传输断言后未重跑全量，不能写成一次71全绿。

## 失败与修复

1. 旧pytest缓存ACL拒绝，改仓库内专用临时目录，未修改系统ACL。
2. MySQL容器停止导致拒绝连接，核实后启动solomeal-dev-mysql，不使用MySQL80。
3. 同批次同秒事件乱序：新事件保存batch_version，旧事件null不捏造历史。
4. 会话降级先删FK索引导致失败：改为直接drop会话表，核实后仅修复solomeal_test半降级。
5. 工具扩展后传输测试仍预期旧4工具，保留严格清单并加入4新工具，专项9通过。
6. 脚本夹具替换路由未生效，误走MODEL_NOT_CONFIGURED；改正式注入点app.state.agent_model，生产服务未启用Mock。
7. 浏览器自动审批超时，读状态后按允许规则重试一次成功。

## 浏览器实际完成

开发MySQL账号ui_crud_0906：导入示例不加库存、编辑菜谱保存；2鸡蛋入库/归档/恢复；新建单食材煮鸡蛋，设置煮锅、推荐、保存、修订v2、查看v1/v2、确认做饭2→1、撤销1→2；另一个方案取消。模型未配置失败run刷新重登录后恢复。库存表单截图已复核。

隔离脚本环境：运行backend/scripts/browser_fixture.py，访问127.0.0.1:8010。单临时账号在UI创建，设置煮锅，发送“测试入库”。待确认刷新重登录后恢复原run；批准得2鸡蛋；同session“测试做饭”预览1个并批准得库存1；“测试撤销”预览恢复1个并批准得库存2。主页面自动刷新。页面标注脚本模型与临时数据。

此验证证明UI/工具/事务接线，不证明真实自然语言效果，也不等于完整网络故障SSE测试。移动端、多标签页、真实模型、小票、部署仍待验。测试密码、令牌及数据库凭据未写入报告。

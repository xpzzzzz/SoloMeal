# P9 请求限流、列表分页、容器配置与交付材料

日期：2026-09-17。对应NEXT_SESSION第83节指定下一步，参照PLAN P9-01/03。实现与独立验证完成，不代表P9整体完成或源服务已部署。

## 改动

- Compose Nginx按连接IP限制普通请求20r/s（burst80）、认证5r/m（burst10）、模型执行30r/m（burst16）。登录/注册共享额度，Agent advance/小票parse共享额度。429返回JSON、Retry-After:60和no-store；不信任客户端X-Forwarded-For，健康检查豁免。
- 12类REST列表以SQL LIMIT/OFFSET分页，默认100、最大200，offset最大100000；保留数组响应和原排序方向，为菜谱同名/做饭同时间添加ID排序。所有者/归档过滤在分页前执行。领域层库存与版本历史调用不默认截断。
- 前端统一读取每页200条，保留include_archived等过滤，跨页出错不发布部分结果；跨会话停止读取，最多10000条，超限明确报错。429给出中文等待提示，不自动重放写请求。
- Compose透传聊天/视觉thinking、聊天输出预算、视觉每日额度和超时。omit明确表示不发送thinking字段，true/false独立；显式空值和无效/越界值拒绝。默认模型开关仍关闭。
- 新增[交付手册](../delivery.md)：三分钟演示脚本、十项技术问答、新主机清单、简历描述草案；更新README/架构图/部署指南。材料准备不等于完成录制或新主机验收。

## 验证与原始失败

| 检查 | 本轮结果 | 范围 |
| --- | --- | --- |
| 首轮后端子集 | 100通过、1失败、4跳过 | 空字符串被改为None与原契约冲突，保留[首次JUnit](p9-boundaries-0917-backend.xml) |
| 修正后完整后端 | 530通过、16跳过、0失败/错误 | 546用例，234.957秒；[最终JUnit](p9-boundaries-0917-final.xml)，跳过均为MySQL专属 |
| Linux容器 | 58通过 | test_p9_boundaries + test_model_transport；禁网、只读源码、临时SQLite，与Windows覆盖重叠，不重复计数 |
| 前端单测/构建 | 29通过，构建成功 | 5项新增分页测试；错误、会话切换和超大列表边界 |
| 浏览器 | 9通过 | accounts/lifecycle/planning-boundaries/receipts/shopping共8项，新增pagination 1项；临时SQLite/脚本模型 |
| Docker镜像 | 构建成功 | 独立solomeal-api:p9-boundaries-0917，不替换运行服务 |
| Nginx与配置 | 通过 | 两次独立合成目录，最终额外验证空值/越界启动失败 |
| Ruff F/B/I | 通过 | 修改Python文件；显式将FastAPI Depends/Query声明为immutable calls，未批量修改既有API声明 |
| git diff --check | 通过 | Git现有LF/CRLF提示保留，不是空白错误 |

首轮空值失败后保留原有拒绝测试，改为显式omit，没有删除旧反例或放宽true/false判据。首次Ruff直接扫描API出现FastAPI默认依赖声明的B008提示及验证脚本三条提示；脚本提示已修复，FastAPI声明用检查配置说明。两个既有Starlette/httpx与AnyIO弃用警告保留，未更换依赖。

容器最终[结果JSON](p9-boundaries-0917-container-final/results.json)：默认/显式配置与api/migrate一致，空thinking、空输出预算和3001预算均被拒；nginx -t通过。24认证请求拒绝13、40模型路径请求拒绝23、240普通请求拒绝182。请求携带变化的伪造X-Forwarded-For，仍受同IP额度限制；健康检查持续200，普通请求等待4.5秒后恢复200。仅合成上游，不读取数据库、图片或真实模型。

前一轮[容器结果](p9-boundaries-0917-container/results.json)保留（普通请求拒绝180），扩展后使用新目录，没有覆盖证据。拒绝数量受执行时序影响，不作为固定性能门槛。Windows/Linux运行结果不能合计为不同测试。

浏览器新增场景实际创建205个合成批次，确认默认REST只返回100、页面请求offset=200并展示205行；拦截成429后出现60秒提示，取消拦截可手动刷新恢复。截图在frontend/.tmp-e2e/pagination-205.png，stdout结果由本会话工具记录。其他页面回归验证库存归档恢复、菜谱编辑、旧方案拒绝、跨账号、小票确认和采购幂等。

## 状态与限制

后端源码指纹（app/scripts，共67文件）：`c3161b9b8c69fcfad70e7b12425e2d7c94aafce3391b486fe67e811ebd95bcb3`。独立API镜像ID：`sha256:908cf165568b66eff3295df8d13bc5cf4aa0102646cb0f961326b336f69ec0d3`。文件哈希见[摘要](p9-boundaries-0917.json)。

- 当前分页是单次SQL读取边界。前端仍汇总完整列表，会话runs等嵌套集合、推荐候选集合仍可能增长；offset跨请求不保证并发修改时的快照一致性。尚未实现滚动加载、游标快照或总存储配额。
- 限流只覆盖Compose Nginx入口，同NAT共享额度；未提供多节点按用户费用预算、并发连接数限制或公网TLS。连接真实代理前需重新验证信任链。
- 本轮没有迁移、业务写入算法、生产提示/工具schema或冻结评分改动；没有新MySQL实测、远程CI、真实模型或受控弱网。累计聊天1663/视觉30不变，旧留出48/60与holdout_gate=failed保留。
- 源solomeal-acceptance-0916a三个容器最终均健康，18080 readiness为ready；未重新部署。临时限流容器已清理，原恢复/故障/开发项目没有启动或删除卷。本轮无提交推送。
- P5/P8/P9整体未完成；三分钟材料尚未实际录制，新物理主机、主机断电/MySQL数据盘写满、真实Agent断线仍未验收。

下一步先在新独立Compose项目整体验证新web/api组合（本轮API禁网配置与Nginx合成测试是分别验证），再按交付手册预演/录制，并推进受控弱网/真实Agent断线；新物理主机条件不满足时保留明确缺口。旧模型批次不重跑或追加。

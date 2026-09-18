# P7 离线诊断与数量规则（2026-09-09）

本轮按 NEXT_SESSION 继续 P7 收尾，新增外部调用 0 次。此前授权的 6 次已用完；不读取或修改私有配置、原始 manifest、票据及隔离业务库，不回填旧报告。P7 仍为 IN_PROGRESS。

## 实现

- receipt_parser.failure_diagnostic 只输出固定 category 和提供方 HTTP 状态码；区分 provider_auth（401/403）、provider_rate_limit（429）、provider_http、timeout、provider_transport、invalid_response、unavailable、unknown。
- 字段验收脚本失败时增加 diagnostic，保留原 error_code。外层总超时与 HTTP 客户端超时均分类为 timeout，不自动重试。未知异常不猜原因。
- 页面解析服务在失败时记录小票 UUID 和同一脱敏诊断，不记录异常文本、堆栈、URL、响应原文或凭据。API 仍返回已保存的 failed 状态；HTTP 200 不代表识别成功。诊断不新增数据库列，不改变原幂等/事务/人工回退。
- 提示版本变为 receipt-v2：明确固定包装含量与购买包数才能相乘得到整行总量；约重、不定重、范围或包装数歧义返回未知数量/单位，名称保留相关标记供人工核对；外部 note 不属于图片证据。用户仍可手工接受估计总量。此提示尚无真实模型效果证据。

## 下一轮数量标注规则

识别 expected 仅记录图片可支持的字段；人工接受的入库数值单独记录。以下为规则示例，不是新增真实样本，也不是模型实测结果。

| 票面情况 | 自动识别 quantity/unit | 人工确认 |
|---|---|---|
| 明确称重 0.750kg | 0.750 / kg | 核对后确认 |
| 固定每包450g，明确购3包 | 1350 / g | 核对总量，不只填单包量 |
| 每包约450g，购3包 | null / null，名称保留约重 | 用户可接受1350g估计总量，不能称实称 |
| 不定重黄瓜，缺少明确称重总量 | null / null，名称保留不定重 | 用户可依据补充信息填写1kg |
| 2盒豆腐，无每盒含量 | null / null | 补齐含量；不能将2盒当2g或2个食材 |
| 只有价格/单价或重量范围 | null / null | 不按金额反算或取范围中点 |
| 图片无完整日期，note有日期 | purchased_on=null | 人工填写日期并单独记录依据 |

下次真实运行前另建版本化 manifest，冻结图片摘要、prompt版本和人工标签；保留旧 manifest 与 receipt-v1 得分。不同单位表示的等值数量仍按既有评分规则处理，不在本轮放宽比较门槛。当前 schema/库存没有独立数量来源字段，估计依据仍保留在人工验收记录与原图中，不能声称库存已结构化追踪估计来源。

## 验证

在 backend 执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_receipt_acceptance.py tests/test_receipt_vision.py tests/test_receipts.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p7-diagnostics-final-0909 -q
```

最终 37 passed / 2 skipped（MySQL 专属），12.26s；保留2条第三方弃用警告。新增8种提供方/超时失败场景通过 MockTransport 验证诊断、每票一次调用及报告脱敏；原有4种 API 失败回退场景补日志断言。首轮35 passed / 2 failed / 2 skipped：诊断递归解包到了 asyncio CancelledError，丢失外层 TimeoutError 分类；改为只解包 AppError 后重跑通过。初次 lint 有2处导入排序，已修正。

本轮未改数据库事务、schema、前端或原插件；未重跑 MySQL、后端全量、浏览器、原插件和远程 CI。不以本轮专项覆盖此前全部业务验收。真实401根因与新提示效果仍待新授权的外部验证；不得无授权重跑真实脚本。P8/P9未开始。

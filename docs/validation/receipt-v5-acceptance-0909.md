# P7 收尾验收：receipt-v5（2026-09-09）

结论：在qwen3.8-flash、receipt-v5、enable_thinking=false、30秒时限配置下，三张授权真实小票字段脚本及真实React页面均全字段匹配；三份人工修正/确认/同键丢包重试/刷新通过。结合第25/26节既有权限、事务、MySQL并发及文件边界证据，P7既定小票验收完成。不是通用OCR准确率、生产部署或P8完整评测通过。

## 本轮实现与依据

- v3改中文结构化提取提示，明确固定规格乘购买份数、约重逐行判断、名称/规格分离及顶层对象示例。
- v4补已知量名称清理示例与最后检查；v5补约重名称去包装后缀。未放宽schema、未自动修补顶层数组，也未回填旧标签。
- 可选SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING（bool或未配置）；默认不发送扩展字段，false/true才发送enable_thinking。只影响小票适配器，不改变聊天模型。
- [阿里云官方说明](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)列明qwen3.8-flash默认开启混合思考、可设enable_thinking=false。结合此前返回的reasoning token和时延，本轮验证关闭后的表现；不以少量样本断言时延波动完全由思考导致。
- .env与模型名未修改。正式使用当前验收配置，可在启动后端的环境设置SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING=false；不要给不支持该扩展的提供方照搬。空缺默认仍沿用提供方行为，不能称现有.env已经启用关闭思考。

## 调用与失败记录

本轮共17次真实模型请求，持续授权内执行；v3四次、v4五次、v5字段/合成五次、v5页面三次。发送前记录尝试，不自动重试。此前两轮6+7次单独保留，累计记录30次。所有本轮调用时限30秒，没有延长时限凑通过。

| 版本/模式 | 真实01 | 真实02 | 真实03 | 合成指令 | 合成多包装 |
|---|---|---|---|---|---|
| v3 默认思考 | 38/38，8.836s | 24/26，8.681s | 33/34，20.354s | 6/6，17.476s | 未跑 |
| v4 默认思考 | 38/38，11.144s | 26/26，15.395s | 超时30.015s | 6/6，9.044s | 17/18，7.106s |
| v5 关闭思考 | 38/38，5.953s | 26/26，2.764s | 34/34，4.404s | 6/6，1.827s | 17/18，2.621s |

v3差异为三个商品名仍带重量规格。v4/v5多包装量、单位、金额、日期全部正确，仍保留一项约重名称后缀：v4多了“/袋 ×2”，v5多了“/袋”。该报告保持mismatch，不改答案或放宽比较；名称可人工编辑，不影响库存数值，列入P8非阻断缺陷。新合成多包装样本在调用前冻结：150ml×3=450ml、2kg×2=4kg、约300g×2留未知、相邻330ml保持明确量。合成样本不计真实小票数量。

真实字段标签沿用v2冻结清单（SHA256 7686151fa997b21483952cb48346de190406c153ba6716d6b13a24e66494686a），v3/v4/v5之间未改标签或评分。三张已被用作调试集，不能充当P8独立留出集。

## 真实页面与数据库

新隔离SQLite目录D:/SoloMeal-Acceptance/ui-v5-0909/live-isolated-run1，临时服务8030；三个独立账号，真实VisionReceiptParser，显式enable_thinking=false。前端tsc/Vite构建通过，index-D9nhtyk5.js。页面脚本直接操作上传/发送前确认/原图/编辑/整单确认，不用脚本模型替代真实请求。

三张parse_status均parsed且field_mismatches为空，所有行要求核对；编辑和二次确认前库存为0。人工采用用户此前已接受的估计量，生菜1350g、第三张黄瓜1kg；估计不称实称。最终9+8+6=23批次、23事件，数量与用户修正一致，到期日期未知。提交后模拟响应丢失，同键重试返回相同批次；刷新重登录恢复终态。三张截图已视觉复核。

识别标签与人工入库清单分别读取，不用人工接受值覆盖识别评分。UI指标为receipt-v5-ui-0909.json。浏览器及本轮8030服务已关闭，隔离数据保留。开发MySQL、旧验收库、根data均未修改。

## 工程验证与边界

```powershell
# backend目录
.venv/Scripts/python.exe -m pytest tests/test_receipt_vision.py tests/test_receipt_acceptance.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p7-v5-0909 -q
.venv/Scripts/python.exe -m ruff check app/core/config.py app/services/receipt_parser.py tests/test_receipt_vision.py --select F,B,I
```

最终27 passed/1 MySQL专属skipped，3.05s；2条原有第三方弃用警告。新增顶层数组拒绝、enable_thinking未配置/false/true传参覆盖。前序v3专项25/1为本轮中间结果，不与最终相加。ruff通过。未改事务或schema，因此未重跑MySQL、后端全量或原插件；之前结果不冒充本轮重跑。未重跑完整常规E2E，本轮为三份真实页面专项。

原始模型响应、图片、冻结manifest、attempt及截图保存在上述私有验收目录；仓库仅保存v3/v4/v5字段、合成和页面指标。未汇总完整token/实际账单费用。真实恶意指令样本通过仅证明这张合成样本，不能保证所有提示注入无效。

下一步P8：冻结独立评测集与门槛、覆盖Agent真实闭环/异常/对照，跟进约重名称后缀与时延稳定性。P4/P5/P6未完成验收项及远程CI仍保留；P9部署、私有文件联合备份仍未开始。未提交/推送。

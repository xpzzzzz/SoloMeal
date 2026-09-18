# P7 真实视觉验收入口

最新验收（2026-09-09）：receipt-v5关闭Qwen思考模式后，三份真实字段和页面闭环通过，P7完成，见[报告](receipt-v5-acceptance-0909.md)。本地配置新增可选SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING=false，只在提供方支持时使用；默认省略。P8须用独立留出集检查稳定性，历史失败不删除。

> 2026-09-09授权更新：用户已持续授权本项目后续视觉模型调用，无需逐批确认。下文限次/需新授权表述为此前历史；调用仍须记录实际结果，避免无意义重试。

2026-09-09：当前提示为 receipt-v2；下一轮前按[数量规则](receipt-diagnostics-0909.md)另建版本化标签，区分图片提取与用户接受的估计总量，不改旧manifest及得分。失败报告新增脱敏 diagnostic；仍不自动重试。本轮仅离线验证，之前6次授权已用完。

代码支持显式启用的 Chat Completions 图片请求，沿用项目模型配置。实现格式参考 [OpenAI 图片输入文档](https://developers.openai.com/api/docs/guides/images-vision)；完整图片读取和校验参考 [Pillow Image 文档](https://pillow.readthedocs.io/en/stable/reference/Image.html)。未指定或替换模型名，所选服务必须支持 image_url 和 JSON object 输出。

## 本地配置

在被忽略的 backend/.env 本地配置 SOLOMEAL_MODEL_NAME、SOLOMEAL_MODEL_API_KEY、必要时的 SOLOMEAL_MODEL_BASE_URL，并设置 SOLOMEAL_RECEIPT_VISION_ENABLED=true。无需开启聊天Agent。不要在聊天、代码或报告中写密钥。重启服务后小票页显示自动识别入口；用户点击“发送图片并识别”后才发送图片。

## 样本与门槛（首次真实运行前冻结）

至少3份获得使用授权的中文超市真实小票：清晰计重/计数、包装数量歧义/缺失字段、模糊或倾斜票据。样本由用户明确选择，不扫描private_uploads。可另加人工制作的恶意指令票据，但须标synthetic，不能计为真实票据。真实收据和人工核对的期望清单未提供时不能标P7完成。

- 所有输出必须通过schema；已识别行必须uncertain=true；确认前库存写入数为0。
- 清晰真实样本的名称/数量/单位/金额/日期与人工标签匹配；歧义量或单位必须null，不编造值。脚本报告逐字段正确数；失败或不匹配不算通过。
- 对模糊样本允许识别失败或保留未知，但用户可依据原件手工修改后完成确认。
- 每份真实样本在隔离测试账号走完上传→识别→修正→确认，库存数量与用户修正一致，同键重试不增加批次。
- 恶意文本、越权、重复/并发、失败回滚和文件限制以自动测试补充；不能据此声称真实模型从不受提示注入影响。

## 脚本用法

在一个用户指定目录中放图片和manifest.json（相对图片路径不能越出此目录），例如：

```json
{"dataset_kind":"real","cases":[{"id":"receipt-01","file":"receipt-01.png","expected":{"purchased_on":"2026-09-08","items":[{"name":"鸡蛋","quantity":"6","unit":"piece","amount":"6.50"}]}}]}
```

在backend目录运行：

```powershell
.venv/Scripts/python.exe scripts/validate_receipt_vision.py --manifest <指定目录>/manifest.json --report <报告路径>.json --send-images
```

脚本每次最多10份，不自动重试；每份最多4000输出token，完整请求受超时控制。直接脚本不访问业务数据库，因而不使用API中的用户配额；不要反复运行作为无限制生产入口。未配置或未传--send-images时不调用模型并报告blocked。无有效样本时失败；仅状态passed退出0。报告记录模型名、prompt版本、图片/清单摘要、延迟和字段匹配，不保存密钥、原图或模型原文。脚本核验识别字段，人工确认库存闭环另按上方门槛验收。

脚本独立校验适配器输出schema，并将每行显式uncertain=true纳入通过条件；字段匹配但未要求人工核对仍不通过。报告scope=recognition_fields_only、inventory_workflow_verified=false，即使字段检查passed，也不表示达到三份真实样本要求或完成P7库存闭环。

2026-09-08预检报告为receipt-vision-live-0908.json：模型名/密钥未配置，0次调用；该报告不是识别效果证据。当前仓库仅有1像素合成图片和脚本解析器测试，没有中文真实票据样本。

后续同日已收到用户授权样本并完成6次真实调用，见[真实验收报告](receipt-vision-real-0908.md)。图片留在用户指定的仓库外目录；上述blocked报告仅为历史预检。真实三票修正入库闭环通过，但识别整体仍有失败，授权次数已用完，不得直接重复上方命令。

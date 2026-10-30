# M4.5 OCR 验证入口（已完成，M5收口中）

M4可靠性验收后才创建本目录。当前采用PaddlePaddle3.3.1 CPU、PaddleOCR3.7.0、PaddleX3.7.2的ocr-core依赖，未安装all/LLM/GPU扩展。候选版本依据官方PyPI元数据及 [OCR API文档](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html)。API原依赖环境没有安装OCR；依赖实验在独立Linux镜像内。

[Windows解析结果](windows-compatibility.json)证明本机CPython3.13 AMD64存在CPU wheel且与原锁定包可解析。这里只做wheel/依赖检查，原生Windows DLL和完整OCR推理未验证；开发链路使用已验证的Linux Docker Worker。Linux实际CPU导入、数学检查、推理及完整版本冻结已完成，见[M4.5报告](m45-hybrid-1015.md)。

`compat.Dockerfile`只是M4.5隔离实验。M5再收口正式Worker Docker依赖、CI和README。大型框架wheel（Linux185.8MiB/Windows99.9MiB）及OpenCV系统库下载不计入识别请求耗时。

`create_dataset.py`先生成并冻结6份合成图片及真值，覆盖清晰、模糊、多包装、约重、金额缺失及包装购买数量未知。图片、完整OCR文本/坐标和Mock响应只放仓库外私有目录，仓库只存汇总与生成器。字体由开发机提供，仅记录摘要，不复制字体文件。

`compare_modes.py`在实际CPU OCR上比较三模式，VLM为明确标注的真值Oracle Mock。对照会报告字段匹配、真值修正字段数、耗时、Mock/真实调用数、冲突与失败；没有真实付费VLM调用、Token未知。该Mock的100%字段匹配不能当视觉模型准确率；合成排版及6份样本不足以证明真实准确率提升或成本下降。

当前候选默认模式保持原 `vlm_only`，最终选择在实际报告中决定；取得可信对照后才变更；用户可选择本地或混合方式。混合路径OCR优先、缺失/低置信度/歧义按需辅助，约重/包装数量未定不因高置信度或VLM数字变为确定量，冲突保持需核对。所有识别均复用同一Celery任务、原字段/单位/版本/幂等及人工入库保护。

完整结果见[M4.5报告](m45-hybrid-1015.md)：18次三模式CPU实测、8个真实MQ场景、2个真实页面流程通过，规则/任务22项通过。Linux推理已验证，Windows原生推理仍未测。

M5将正式安装固定到`backend/requirements-ocr.lock`，模型的6个文件摘要位于`backend/app/services/ocr_models_manifest.json`。正式Worker要求先准备本地模型目录，避免请求内下载；重新运行直接对照时需设置`receipt_ocr_model_dir`指向已验证的模型目录。正式Compose流程见[部署指南](../../../deploy/README.md)。

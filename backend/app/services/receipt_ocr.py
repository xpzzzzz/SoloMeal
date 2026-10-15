"""Lazy CPU-only PaddleOCR adapter. Text, scores and geometry never enter logs."""
from io import BytesIO
import math

from ..core.errors import AppError
from .receipt_ocr_models import verify_models


class PaddleReceiptOCR:
    def __init__(self, settings):
        self.settings = settings
        self.engine = None

    def extract(self, content):
        if not self.settings.receipt_ocr_enabled:
            raise AppError(503, "RECEIPT_OCR_UNAVAILABLE", "Use manual receipt entry")
        try:
            if not self.settings.receipt_ocr_model_dir:
                raise ValueError("Prepare local OCR models before enabling OCR")
            if self.engine is None:
                verify_models(self.settings.receipt_ocr_model_dir)
            import numpy as np
            from PIL import Image
            from paddleocr import PaddleOCR
            if self.engine is None:
                kwargs = dict(device="cpu", cpu_threads=2, enable_mkldnn=False,
                              use_doc_orientation_classify=False, use_doc_unwarping=False,
                              use_textline_orientation=False,
                              text_detection_model_name="PP-OCRv5_mobile_det",
                              text_recognition_model_name="PP-OCRv5_mobile_rec")
                if self.settings.receipt_ocr_model_dir:
                    base = self.settings.receipt_ocr_model_dir
                    kwargs.update(text_detection_model_dir=str(base / "PP-OCRv5_mobile_det"),
                                  text_recognition_model_dir=str(base / "PP-OCRv5_mobile_rec"))
                self.engine = PaddleOCR(**kwargs)
            with Image.open(BytesIO(content)) as picture:
                pixels = np.asarray(picture.convert("RGB"))[:, :, ::-1].copy()
            lines = []
            for result in self.engine.predict(pixels):
                for index, (value, score, box) in enumerate(zip(
                        result["rec_texts"], result["rec_scores"], result["rec_polys"], strict=True)):
                    score = float(score)
                    if not math.isfinite(score) or not 0 <= score <= 1:
                        raise ValueError("Invalid OCR score")
                    if len(str(value)) > 2000 or not all(math.isfinite(float(n)) for point in box for n in point):
                        raise ValueError("Invalid OCR evidence")
                    lines.append({"text": str(value), "confidence": score,
                                  "box": [[float(x), float(y)] for x, y in box],
                                  "recognizer_index": index})
            lines.sort(key=lambda row: (min(y for _, y in row["box"]), min(x for x, _ in row["box"])))
            for order, line in enumerate(lines):
                line["order"] = order
            if not lines:
                raise ValueError("No OCR text")
            if len(lines) > 500:
                raise ValueError("OCR line limit exceeded")
            return lines
        except Exception as exc:
            # Only the category crosses this boundary, never paths, receipt text or provider output.
            raise AppError(503, "RECEIPT_OCR_UNAVAILABLE", "Use manual receipt entry") from exc

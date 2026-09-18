"""Bound decoding before storing or forwarding receipt images."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from ..core.errors import AppError

MAX_PIXELS = 20_000_000
MAX_SIDE = 12_000


def validate_image(content: bytes, media_type: str):
    try:
        with Image.open(BytesIO(content), formats=["PNG", "JPEG"]) as image:
            if Image.MIME[image.format] != media_type:
                raise ValueError("Mismatched format")
            width, height = image.size
            if width * height > MAX_PIXELS or max(width, height) > MAX_SIDE:
                raise AppError(413, "RECEIPT_PIXELS", "Image exceeds 20 megapixels or 12000 pixels per side")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Animated images are unsupported")
            image.verify()
        with Image.open(BytesIO(content), formats=["PNG", "JPEG"]) as image:
            image.load()
    except AppError:
        raise
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise AppError(415, "RECEIPT_IMAGE_INVALID", "Image is damaged or unsupported; upload a valid PNG or JPEG") from exc

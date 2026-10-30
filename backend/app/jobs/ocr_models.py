"""Explicit setup/check; Worker only reads weights and never downloads them on a job."""
import argparse
import json
import sys

from app.core.config import Settings
from app.services.receipt_ocr_models import prepare_models, verify_models


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    if not settings.receipt_ocr_model_dir:
        parser.error('Set SOLOMEAL_RECEIPT_OCR_MODEL_DIR')
    try:
        (verify_models if args.check else prepare_models)(settings.receipt_ocr_model_dir)
    except Exception:
        print(json.dumps({'ocr_models': 'unavailable', 'action': 'verify' if args.check else 'prepare'}))
        return 1
    print(json.dumps({'ocr_models': 'verified', 'model_count': 2}))
    return 0


if __name__ == '__main__':
    sys.exit(main())

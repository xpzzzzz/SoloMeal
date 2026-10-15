"""Test-only selection of the real CPU OCR and a closed, synthetic VLM oracle."""
from app.jobs.supervise import main

if __name__ == '__main__':
    raise SystemExit(main('validation_recognizer:app'))

"""Pinned, public OCR weights; no receipt input is involved in preparation."""
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MANIFEST = json.loads(Path(__file__).with_name('ocr_models_manifest.json').read_text())
BASE_URL = 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0'


def verify_models(directory):
    for model, expected in MANIFEST.items():
        for name, digest in expected.items():
            file = directory / model / name
            if not file.is_file() or file.is_symlink():
                raise ValueError('OCR model files are missing')
            with file.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                    raise ValueError('OCR model checksum mismatch')


def prepare_models(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for model, expected in MANIFEST.items():
        target = directory / model
        if target.exists():
            # Never replace unknown/corrupt weights silently.
            for name, digest in expected.items():
                file = target / name
                if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                    raise ValueError('Existing OCR model failed verification')
            continue
        with tempfile.TemporaryDirectory(prefix='.prepare-', dir=directory) as temp:
            staging = Path(temp)
            package = staging / 'model.tar'
            with urllib.request.urlopen(f'{BASE_URL}/{model}_infer.tar', timeout=60) as response, package.open('xb') as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 64 * 1024 * 1024:
                        raise ValueError('OCR model download exceeds limit')
                    output.write(chunk)
            extracted = staging / model
            extracted.mkdir()
            found = set()
            with tarfile.open(package) as archive:
                for member in archive:
                    name = Path(member.name).name
                    if name not in expected:
                        continue
                    if name in found or not member.isfile() or member.size > 32 * 1024 * 1024:
                        raise ValueError('Invalid OCR model archive')
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError('Missing OCR model content')
                    with source, (extracted / name).open('xb') as output:
                        shutil.copyfileobj(source, output)
                    if hashlib.sha256((extracted / name).read_bytes()).hexdigest() != expected[name]:
                        raise ValueError('OCR model checksum mismatch')
                    found.add(name)
            if found != set(expected):
                raise ValueError('Incomplete OCR model archive')
            extracted.rename(target)
    verify_models(directory)

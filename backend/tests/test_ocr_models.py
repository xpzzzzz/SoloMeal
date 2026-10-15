import hashlib
import io
import tarfile

import pytest

from app.services import receipt_ocr_models as models


def package(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, content in entries:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    output.seek(0)
    return output


def test_model_setup_verifies_content_and_reuses_only_verified_existing_weights(tmp_path, monkeypatch):
    data = {'inference.json': b'configuration', 'inference.pdiparams': b'weights'}
    manifest = {'synthetic-model': {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}}
    monkeypatch.setattr(models, 'MANIFEST', manifest)
    downloads = []

    def download(url, **kwargs):
        downloads.append(url)
        return package([('nested/' + name, value) for name, value in data.items()])

    monkeypatch.setattr(models.urllib.request, 'urlopen', download)
    with pytest.raises(ValueError):
        models.verify_models(tmp_path)
    models.prepare_models(tmp_path)
    models.verify_models(tmp_path)
    models.prepare_models(tmp_path)
    assert len(downloads) == 1
    (tmp_path / 'synthetic-model/inference.pdiparams').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='verification'):
        models.prepare_models(tmp_path)
    assert len(downloads) == 1


@pytest.mark.parametrize('entries', [
    [('inference.json', b'wrong')],
    [('inference.json', b'expected'), ('other/inference.json', b'expected')],
    [('unrelated', b'expected')],
])
def test_invalid_model_package_is_never_published(tmp_path, monkeypatch, entries):
    monkeypatch.setattr(models, 'MANIFEST', {'synthetic-model': {
        'inference.json': hashlib.sha256(b'expected').hexdigest()}})
    monkeypatch.setattr(models.urllib.request, 'urlopen', lambda *a, **kw: package(entries))
    with pytest.raises(ValueError):
        models.prepare_models(tmp_path)
    assert not (tmp_path / 'synthetic-model').exists()

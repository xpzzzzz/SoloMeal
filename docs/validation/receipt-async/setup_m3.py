"""Fresh isolated Compose for the real-broker Mock-parser normal workflow."""
import argparse
import json
import secrets
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KIT = Path(__file__).resolve().parent


def command(args, private, *, fail=True):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    with (private / 'commands.log').open('a', encoding='utf-8') as output:
        output.write(result.stdout + result.stderr)
    if fail and result.returncode:
        raise RuntimeError(f'Command failed with exit {result.returncode}; inspect private log')
    return result


def context(private):
    state = json.loads((private / 'state.json').read_text(encoding='utf-8'))
    if state['project'] != 'solomeal-backend-m3-1015-01':
        raise RuntimeError('Only this named validation project is allowed')
    return state, ['docker', 'compose', '--project-directory', str(ROOT),
                   '--env-file', str(private / 'validation.env'), '-f', str(ROOT / 'compose.yaml'),
                   '-f', str(KIT / 'compose.test.yaml'), '-p', state['project']]


def setup(private):
    project = 'solomeal-backend-m3-1015-01'
    result_dir = KIT / 'results-m3-1015-01'
    if private.exists() or result_dir.exists():
        raise RuntimeError('Validation directories already exist')
    for kind in ('container', 'volume'):
        result = subprocess.run(['docker', kind, 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project],
                                capture_output=True, text=True, check=True)
        if result.stdout.strip():
            raise RuntimeError('Validation project already exists')
    for port in (18110, 18111):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    private.mkdir(parents=True)
    result_dir.mkdir()
    values = {'DB_PASSWORD': secrets.token_hex(24), 'DB_ROOT_PASSWORD': secrets.token_hex(32),
              'RABBITMQ_PASSWORD': secrets.token_hex(24), 'IMAGE_TAG': 'backend-m3-1015-01',
              'HTTP_PORT': '18110', 'VALIDATION_API_PORT': '18111', 'BIND_ADDRESS': '127.0.0.1',
              'VALIDATION_KIT_DIR': KIT.as_posix(), 'VALIDATION_PRIVATE_DIR': private.resolve().as_posix(),
              'SOLOMEAL_AGENT_ENABLED': 'false', 'SOLOMEAL_RECEIPT_VISION_ENABLED': 'false',
              'SOLOMEAL_RECIPE_DISCOVERY_ENABLED': 'false', 'SOLOMEAL_MODEL_API_KEY': '', 'SOLOMEAL_MODEL_NAME': ''}
    (private / 'validation.env').write_text(''.join(f'{k}={v}\n' for k, v in values.items()), encoding='utf-8')
    (private / 'state.json').write_text(json.dumps({'project': project, 'private_dir': str(private.resolve()),
                                                 'result_dir': str(result_dir), 'tag': values['IMAGE_TAG']}), encoding='utf-8')
    _, compose = context(private)
    print('Building new API and web images for the isolated M3 project', flush=True)
    command(compose + ['build', 'api', 'web'], private)
    print('Starting MySQL, RabbitMQ and the real Celery test Worker', flush=True)
    command(compose + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '240'], private)
    print(json.dumps({'project': project, 'web_port': 18110, 'api_port': 18111, 'real_model_calls': 0}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-dir', type=Path, required=True)
    setup(parser.parse_args().private_dir)

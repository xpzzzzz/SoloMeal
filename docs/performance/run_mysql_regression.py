"""Run related regressions in a new test schema on this sandbox's retained MySQL."""
import argparse
import json
import time
from pathlib import Path

from run_m1 import ROOT, command, context


def run(state_file):
    state, compose, log = context(state_file)
    private = Path(state['private_dir'])
    command(compose + ['start', 'db'], log=log)
    mysql = compose + ['exec', '-T', 'db', 'sh', '-c',
                       'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B -e "$1"', 'sh']
    for _ in range(30):
        ready = command(mysql + ['SELECT 1'], log=log, fail=False)
        if ready.returncode == 0:
            break
        time.sleep(1)
    present = command(mysql + ["SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='solomeal_test'"], log=log)
    if present.stdout.strip() != '0':
        raise RuntimeError('Test schema already exists; refusing destructive reuse')
    command(mysql + ["CREATE DATABASE solomeal_test CHARACTER SET utf8mb4; GRANT ALL ON solomeal_test.* TO 'solomeal'@'%';"], log=log)
    values = dict(line.split('=', 1) for line in (private / 'sandbox.env').read_text().splitlines() if '=' in line)
    url = 'mysql+pymysql://solomeal:' + values['DB_PASSWORD'] + '@db:3306/solomeal_test?charset=utf8mb4'
    files = ['test_planning_performance', 'test_planning', 'test_personalization',
             'test_home', 'test_personal_time', 'test_food', 'test_recipe_feedback']
    print('Running related regressions on a new isolated solomeal_test schema', flush=True)
    result = command(compose + ['run', '--rm', '--no-deps', '-T',
                     '-v', str(ROOT / 'backend/tests') + ':/app/tests:ro',
                     '-v', state['run_dir'] + ':/perf-output',
                     '-e', 'SOLOMEAL_TEST_DATABASE_URL=' + url, 'api',
                     'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                     '--junitxml', '/perf-output/mysql-regression.xml']
                     + ['tests/' + name + '.py' for name in files], log=log, fail=False)
    with (Path(state['run_dir']) / 'mysql-regression-outcome.json').open('x') as output:
        json.dump({'exit_code': result.returncode, 'dedicated_schema': 'solomeal_test',
                   'fixture_volume': state['project'], 'models_disabled': True}, output, indent=2)
    print('MySQL regression exit code:', result.returncode, flush=True)
    command(compose + ['stop'], log=log)
    if result.returncode:
        raise RuntimeError('Regression failed; inspect private log and JUnit')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    run(parser.parse_args().state)

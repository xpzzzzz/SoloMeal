"""Compare matching saved load cells; do not compare different endpoint mixes as capacity."""
import argparse
import json
from pathlib import Path

from summarize import summarize


def compare(before, after):
    summarize(after)
    baseline = json.loads((before / 'summary.json').read_text(encoding='utf-8'))
    optimized = json.loads((after / 'summary.json').read_text(encoding='utf-8'))
    old = {r['run']: r for r in baseline['runs']}
    pairs = []
    for new in optimized['runs']:
        prior = old.get(new['run'])
        if prior is None:
            continue
        names = {r['name']: r for r in prior['endpoints']}
        pairs.append({'run': new['run'], 'scale': new['scale'], 'users': new['users'],
                      'before_rps': prior['rps'], 'after_rps': new['rps'],
                      'before_failures': prior['failures'], 'after_failures': new['failures'],
                      'before_samples': prior['requests'], 'after_samples': new['requests'],
                      'endpoints': [{'name': row['name'], 'before': names.get(row['name']), 'after': row}
                                    for row in new['endpoints']]})
    output = {'paired_cells': len(pairs), 'pairs': pairs,
              'limitations': ['mixed endpoint proportions change with latency',
                              'short windows and small baseline samples',
                              'RPS includes drain; think time retained',
                              'no hardware or production capacity extrapolation']}
    (after / 'comparison.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    for pair in pairs:
        for endpoint in pair['endpoints']:
            if endpoint['name'].endswith('/recommendations') and endpoint['before']:
                print(pair['run'], 'RPS', round(pair['before_rps'], 3), round(pair['after_rps'], 3),
                      'recommendation P95', round(endpoint['before']['p95_ms'], 1),
                      round(endpoint['after']['p95_ms'], 1), 'errors', pair['before_failures'], pair['after_failures'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    compare(args.before, args.after)

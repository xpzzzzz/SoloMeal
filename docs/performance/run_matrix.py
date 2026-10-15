"""One bounded baseline matrix plus two repeated cells and Nginx comparison."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from run_m1 import load, context


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=45)
    args = parser.parse_args()
    state, _, _ = context(args.state)
    for scale in (10, 100, 500):
        for users in (1, 5, 20):
            if scale == 500 and users == 20:
                skipped = {"scale": scale, "users": users, "reason": "Serial diagnostic ~7.3s per recommendation; cap the largest fixture at 5 users to bound CPU/60s request deadlines", "status": "not executed"}
                with (Path(state["run_dir"]) / "skipped-r500-u20.json").open("x") as out:
                    json.dump(skipped, out, indent=2)
                print(json.dumps(skipped), flush=True)
                continue
            name = f"api-r{scale}-u{users}-a"
            load(args.state, scale, users, args.seconds, "api", name, "mixed")
    for scale in (100, 500):
        load(args.state, scale, 5, args.seconds, "api", f"api-r{scale}-u5-b", "mixed")
    load(args.state, 10, 20, args.seconds, "nginx", "nginx-r10-u20-a", "mixed")

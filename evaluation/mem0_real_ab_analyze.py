"""Recompute the predeclared metrics from sanitized real-AB evidence."""
import argparse
import json
import statistics
from pathlib import Path


def analyze(evidence):
    results = evidence["case_results"]
    memory_specs = {p["key"]: p for p in evidence["protocol"]["memories"]}
    top_hits = {group: {"top1": 0, "top3": 0} for group in ("A", "B")}
    preference_cases = 0
    retrieval_hits = 0
    no_match = 0
    no_match_changed = 0
    candidates = {group: 0 for group in ("A", "B")}
    violations = {group: 0 for group in ("A", "B")}
    latencies: dict[str, list[float]] = {group: [] for group in ("A", "B")}
    deltas = []
    for case in results:
        spec, groups = case["scenario"], case["groups"]
        for group in ("A", "B"):
            candidates[group] += len(groups[group]["candidates"])
            violations[group] += groups[group]["hard_violations"]
            latencies[group].append(groups[group]["elapsed_ms"])
        deltas.append(groups["B"]["elapsed_ms"] - groups["A"]["elapsed_ms"])
        if spec["relevant_memory"]:
            preference_cases += 1
            expected = memory_specs[spec["relevant_memory"]]
            retrieval_hits += any(all(record.get(k) == expected[k] for k in ("category", "target", "polarity"))
                                  for record in groups["B"]["retrieved"])
            for group in ("A", "B"):
                names = [x["name"] for x in groups[group]["candidates"]]
                for field, n in (("top1", 1), ("top3", 3)):
                    present = spec["target_recipe"] in names[:n]
                    top_hits[group][field] += int(present if spec["top3_predicate"] == "target_present" else not present)
        elif spec["type"] in ("unrelated_memory", "no_matching_signal"):
            no_match += 1
            a = [(x["name"], x["score"]) for x in groups["A"]["candidates"]]
            b = [(x["name"], x["score"]) for x in groups["B"]["candidates"]]
            no_match_changed += a != b
    return {"scenarios": len(results), "preference_cases": preference_cases,
            "top_hits": top_hits, "retrieval_hits": retrieval_hits,
            "no_match_cases": no_match, "no_match_changed": no_match_changed,
            "candidate_observations": candidates, "hard_violations": violations,
            "median_a_ms": statistics.median(latencies["A"]) if results else None,
            "median_b_ms": statistics.median(latencies["B"]) if results else None,
            "median_paired_delta_ms": statistics.median(deltas) if results else None,
            "http_requests": len(evidence["http"]), "cleanup": evidence["cleanup"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(json.loads(args.evidence.read_text(encoding="utf-8"))), indent=2))

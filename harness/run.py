#!/usr/bin/env python3
"""Your entrypoint. Usage:
  python3 harness/run.py --phase practice --defense solution/defense.py --out solution/practice_report.json
Decrypts the named phase's schedule in-memory, spawns your defense.py in an
isolated subprocess, streams events through it, scores, and writes a signed
result. See ../README.md and ../RULES.md before you start."""
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))  # this dir only: crypto/scoring/signing/isolation/toolkit
import crypto
import scoring
import signing
from isolation import IsolatedRun

BUDGET = 220.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["practice", "public", "private"])
    ap.add_argument("--defense", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    phases_dir = ROOT / "phases"
    key_path = phases_dir / f"{args.phase}.key"
    if not key_path.exists():
        sys.exit(f"'{args.phase}.key' not released yet — check the phase schedule in README.md.")
    key = key_path.read_bytes()
    ciphertext = (phases_dir / f"{args.phase}_schedule.json.enc").read_bytes()
    schedule = crypto.decrypt_schedule(ciphertext, key)

    baseline_path = ROOT / "data" / "baselines.json"
    baseline = json.loads(baseline_path.read_text())

    events = schedule["events"]
    truths = schedule["ground_truth"]
    labels = schedule["labels"]
    gt_by_key = {(t["type"], t["batch_id_or_ref"]): t["gt"] for t in truths}

    run = IsolatedRun(args.defense, str(baseline_path), gt_by_key, budget=BUDGET)

    verdicts = []
    try:
        for ev in events:
            verdicts.append(run.dispatch(ev))
    finally:
        run.shutdown()

    result = scoring.score_run(verdicts, labels, run.toolkit.cost_ledger, BUDGET)
    result["phase"] = args.phase
    result["defense_file"] = str(args.defense)

    if args.phase == "private":
        public_result = {"phase": "private", "score": result["score"],
                          "tpr": result["tpr"], "fpr": result["fpr"],
                          "cost_overage": result["cost_overage"]}
    else:
        public_result = dict(result)
        public_result["per_pillar_band"] = scoring.banded_diagnostics(result)
        del public_result["per_pillar"]
        del public_result["tp"], public_result["fp"], public_result["tn"], public_result["fn"]
        del public_result["tier_breakdown"]

    signature = signing.sign(public_result, key)
    signed = {"result": public_result, "signature": signature}

    Path(args.out).write_text(json.dumps(signed, indent=2))
    print(json.dumps(signed, indent=2))


if __name__ == "__main__":
    main()

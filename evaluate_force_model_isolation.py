#!/usr/bin/env python3
"""Evaluate whether exact-repeat divergence persists without contact history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(frictional: dict, frictionless: dict) -> dict:
    frictional_status = frictional.get("status")
    frictionless_status = frictionless.get("status")
    if "NO_COMPLETE_REPEAT_SET" in {frictional_status, frictionless_status}:
        status = "INCONCLUSIVE"
        decision = "Complete at least two exact repeats for each force model."
    elif frictionless_status == "DIVERGENT_OUTPUTS":
        status = "DIVERGENCE_PERSISTS_WITHOUT_HISTORY"
        decision = (
            "Contact-history removal did not restore byte-identical output; isolate contact "
            "detection and force-reduction ordering next."
        )
    elif (
        frictional_status == "DIVERGENT_OUTPUTS"
        and frictionless_status == "IDENTICAL_OUTPUTS"
    ):
        status = "CONTACT_HISTORY_PATH_IMPLICATED"
        decision = (
            "The history-free model restored exact-repeat output; focus next on friction-history "
            "migration and contact ordering before resuming wheel ranking."
        )
    elif (
        frictional_status == "IDENTICAL_OUTPUTS"
        and frictionless_status == "IDENTICAL_OUTPUTS"
    ):
        status = "NO_DIVERGENCE_OBSERVED"
        decision = "Repeat the diagnostic at full duration before changing solver physics."
    else:
        status = "INCONCLUSIVE"
        decision = "Review the two divergence ledgers before selecting another isolation variable."
    return {
        "schema_version": 1,
        "status": status,
        "decision": decision,
        "qualification": (
            "Numerical root-cause diagnostic only. Frictionless torque, mobility, and compaction "
            "must not be compared with RIDER or used to rank wheels."
        ),
        "frictional": {
            "status": frictional_status,
            "repeats_compared": frictional.get("repeats_compared", []),
            "first_divergent_frame": frictional.get("first_divergent_frame"),
            "first_divergent_time_s": frictional.get("first_divergent_time_s"),
        },
        "frictionless": {
            "status": frictionless_status,
            "repeats_compared": frictionless.get("repeats_compared", []),
            "first_divergent_frame": frictionless.get("first_divergent_frame"),
            "first_divergent_time_s": frictionless.get("first_divergent_time_s"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("frictional_divergence_json", type=Path)
    parser.add_argument("frictionless_divergence_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.frictional_divergence_json.read_text()),
        json.loads(args.frictionless_divergence_json.read_text()),
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    print(result["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

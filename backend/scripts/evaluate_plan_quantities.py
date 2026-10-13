"""Compare an actual engine export to independent truth; no network calls or writes to platform."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines.eval_harness import score_quantities  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True, help="JSON list or {quantities: [...]} from the engine")
    parser.add_argument("--truth", type=Path, required=True, help="Independent verified reference JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.results.resolve(), args.truth.resolve()):
        parser.error("Output must not replace either input")
    try:
        readings = json.loads(args.results.read_text())
        engine_version = readings.get("engine_version") if isinstance(readings, dict) else None
        truth = json.loads(args.truth.read_text())
        if isinstance(readings, dict):
            readings = readings["quantities"]
        report = score_quantities(readings, truth)
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    report.update(evaluated_at=datetime.now(timezone.utc).isoformat(), evaluation_code_commit=revision,
                  engine_version=engine_version, plan_sha256=truth.get("plan_sha256"),
                  truth_sha256=hashlib.sha256(args.truth.read_bytes()).hexdigest(),
                  results_sha256=hashlib.sha256(args.results.read_bytes()).hexdigest(), verified_by=truth.get("verified_by"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"{report['within_tolerance']}/{report['expected']} quantités dans la tolérance ; couverture {report['coverage']:.1%}. Échantillon uniquement.")


if __name__ == "__main__":
    main()

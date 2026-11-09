"""python -m engines.bet_clt_ua.run input.json --output path (from backend)."""
import argparse
import json
from pathlib import Path
from .engine import run
from .report import save

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run(raw)
    files = save(args.output, result, raw)
    print(json.dumps({"status": result["status"], "files": files}))

if __name__ == "__main__":
    main()

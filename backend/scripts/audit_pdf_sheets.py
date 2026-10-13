"""Run the real PDF import locally. No database, provider, upload or accuracy claim."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines.plan_processor import process_pdf  # noqa: E402
from engines.plan_page_context import initial_pdf_calibrations  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = sorted(args.input_dir.glob('*.pdf'))
    if not inputs:
        parser.error('No PDF files found')
    if args.output.resolve() in [p.resolve() for p in inputs]:
        parser.error('Output must not replace an input')
    files = []
    for source in inputs:
        data = source.read_bytes()
        start = time.monotonic()
        record = {'filename': source.name, 'sha256': hashlib.sha256(data).hexdigest()}
        try:
            result = process_pdf(data)
            pages = []
            for p in result['pages']:
                # Exclude drawings/images and keep diagnostic evidence only.
                pages.append({k:p[k] for k in ('index','view_kind','scale_denominators','detected_scale_denominator',
                    'auto_calibration_blocked','interior_analysis_blocked','level_candidates','level_index','reading_warnings',
                    'pdf_dimensions','pdf_vector_scale','geometry_version','vectors_total','text_blocks_total')})
                pages[-1]['wall_stats'] = p['walls_analysis']['stats']
                pages[-1]['validation'] = p['walls_analysis']['validation']
            record.update(status='read', pages=pages, calibrations=initial_pdf_calibrations(result,'offline-audit'))
        except Exception as exc:
            record.update(status='error', error=f'{type(exc).__name__}: {exc}')
        record['seconds'] = round(time.monotonic()-start, 2)
        files.append(record)
        print(f"{source.name}: {record['status']} ({record['seconds']} s)", flush=True)
    engine_root = Path(__file__).resolve().parents[1]/'engines'
    report = {'scope':'native PDF import only; no quantity truth or provider validation',
              'accuracy_established': False,
              'engine_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [engine_root/n for n in ('plan_processor.py','plan_page_context.py','plan_refresh.py','plan_vector_pdf.py','plan_walls.py')]},
              'files': files}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return 1 if any(f['status']=='error' for f in files) else 0


if __name__ == '__main__':
    raise SystemExit(main())

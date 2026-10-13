"""Generate a project drawing dossier locally using the production renderer.

python backend/tools/structuro_dossier.py --demo --output /tmp/my-new-dossier
python backend/tools/structuro_dossier.py --input model.json --revision 2 --output /tmp/rev2
No database, AI provider, credentials or paid service required.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engines.structuro_calc import Model
from engines.structuro_drawing_example import drawing_example,automation_example
from engines.structuro_automation import run_automation
from engines.structuro_drawings import compile_dossier
from engines.structuro_drawing_exports import build_drawing_pdf,build_schedule_csv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo',action='store_true');source.add_argument('--auto-demo',action='store_true');source.add_argument('--input',type=Path)
    parser.add_argument('--automate',action='store_true',help='Recalculer les choix automatiques avant génération')
    parser.add_argument('--revision',type=int,default=1)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.revision<1:parser.error('La révision doit être positive')
    if args.output.exists() and any(args.output.iterdir()):parser.error('Choisissez un dossier de sortie vide pour conserver les anciennes révisions')
    model=automation_example() if args.auto_demo else drawing_example() if args.demo else Model.model_validate_json(args.input.read_text(encoding='utf-8'))
    report=None
    if args.auto_demo or args.automate or model.automation_settings:
        model,report=run_automation(model)
    data=compile_dossier(model,args.revision)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'modele.json').write_text(model.model_dump_json(indent=2),encoding='utf-8')
    (args.output/'controles.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    if report:
        (args.output/'automatisation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        if report['status']=='blocked':
            print('Automatisation bloquée : consultez automatisation.json');return 2
    if not data['can_export']:
        print('Génération bloquée : consultez controles.json');return 2
    (args.output/'plans_A3.pdf').write_bytes(build_drawing_pdf(model,args.revision,data))
    (args.output/'nomenclature.csv').write_bytes(build_schedule_csv(data))
    if report:
        from engines.structuro_automation_exports import build_automation_pdf
        from engines.structuro_calc_exports import build_pdf
        (args.output/'note_automatisation.pdf').write_bytes(build_automation_pdf(model,report,args.revision))
        (args.output/'note_gravitaire.pdf').write_bytes(build_pdf(model,args.revision))
    print(f"{len(data['sheets'])} planches A3 générées dans {args.output.resolve()} - dossier non exécutoire")
    return 0


if __name__=='__main__':raise SystemExit(main())

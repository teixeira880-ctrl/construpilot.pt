"""Processo isolado que executa o motor BIM sobre UM ficheiro IFC.

Lançado pelo dispatcher com ``python -I worker_main.py <ifc> <out_dir> <limits.json>``:
  * ``-I`` (modo isolado): ignora PYTHONPATH/variáveis de ambiente e o diretório
    corrente, para que nenhum ficheiro carregado possa ser importado como código;
  * limites de memória (RLIMIT_AS), CPU (RLIMIT_CPU) e tamanho de ficheiros
    escritos (RLIMIT_FSIZE) aplicados antes de abrir o IFC;
  * o IFC é apenas lido pelo parser STEP do IfcOpenShell — nunca executado.

Protocolo: uma linha JSON por evento no stdout ({"progress": p, "stage": s} …
e no fim {"done": true, "summary": {...}} ou {"error": "...", "code": "..."}).
"""
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _apply_limits(limits: dict) -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover (não-Linux)
        return
    mem = int(limits.get("memory_mb", 0)) * 1024 * 1024
    if mem > 0:
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    cpu = int(limits.get("cpu_seconds", 0))
    if cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 5))
    fsize = int(limits.get("output_mb", 0)) * 1024 * 1024
    if fsize > 0:
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        _emit({"error": "argumentos inválidos", "code": "usage"})
        return 2
    ifc_path, out_dir, limits_raw = argv[1], argv[2], argv[3]
    limits = json.loads(limits_raw)
    # Bibliotecas (código confiável) carregadas ANTES dos limites; os limites aplicam-se ao processamento.
    from bim_studio import engine
    _apply_limits(limits)
    try:
        result = engine.process(
            ifc_path, out_dir,
            max_elements=int(limits.get("max_elements", 60000)),
            max_triangles=int(limits.get("max_triangles", 4_000_000)),
            threads=int(limits.get("threads", 1)),
            progress=lambda p, s: _emit({"progress": round(p, 3), "stage": s}),
        )
        _emit({"done": True, "summary": result["stats"]})
        return 0
    except MemoryError:
        _emit({"error": "Memória insuficiente para processar o modelo.", "code": "memory"})
        return 3
    except Exception as exc:  # noqa: BLE001 — devolve erro controlado ao dispatcher
        name = type(exc).__name__
        text = str(exc)
        if name in ("LimitExceeded", "EmptyModel"):
            code, msg = ("limit" if name == "LimitExceeded" else "empty"), text[:300]
        elif "bad_alloc" in text or "memory" in text.lower():
            code, msg = "memory", "Memória insuficiente para processar o modelo."
        else:
            code, msg = "invalid_ifc", "Ficheiro IFC inválido ou não suportado."
        _emit({"error": msg, "code": code, "detail": f"{name}: {str(exc)[:200]}"})
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""ERR-0A49: um valor enumerado mal escrito pelo modelo (kind="facto") não pode dar um erro técnico ao utilizador."""
import os

os.environ.setdefault("STUDIES_MODEL_ANALYSIS", "x")
os.environ.setdefault("STUDIES_MODEL_LIGHT", "x")


def test_enum_synonyms_are_normalized():
    from routes.assistant import _normalize_enum_args
    a = {"kind": "facto", "statement": "x"}
    _normalize_enum_args("update_project_state", a)
    assert a["kind"] == "fait"
    b = {"kind": "Hipótese"}
    _normalize_enum_args("update_project_state", b)
    assert b["kind"] == "hypothese"


def test_schema_errors_return_corrective_message_not_err_ref():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "routes/assistant.py").read_text()
    i, j = src.index("except _ArgsError as exc:"), src.index("ref = _error_ref()")
    assert i < j and "chama de novo a ferramenta" in src[i:j]

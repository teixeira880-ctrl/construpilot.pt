"""Local regression runner: providers disabled; real routes and in-memory database fixtures."""
import sys,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT / "tests")]
from unittest.mock import AsyncMock,patch
fallback=types.ModuleType('engines.assistant_fallback')
fallback.use_fallback_now=AsyncMock(return_value=(False,None))
fallback.fallback_available=lambda:False
fallback.should_failover=lambda exc:False
fallback.friendly_error=lambda exc:type(exc).__name__
fallback.mark_openai_degraded=AsyncMock(side_effect=AssertionError('No live provider in unit tests'))
claude=types.ModuleType('engines.assistant_claude')
async def no_provider(*args,**kwargs):
 raise AssertionError('No live provider in unit tests')
 yield
claude.run_chat_claude=no_provider
def main():
    with patch.dict(sys.modules,{'engines.assistant_claude':claude,'engines.assistant_fallback':fallback}):
     suite=unittest.defaultTestLoader.loadTestsFromNames(['test_assistant_background_regressions','test_assistant_collaboration','test_assistant_workspace_regressions','test_assistant_revision_regressions'])
     result=unittest.TextTestRunner(verbosity=1).run(suite)
     sys.exit(not result.wasSuccessful())


if __name__ == "__main__":
    main()

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

runpy.run_path(str(ROOT / "scripts/integrate_diarization_feature.py"), run_name="__main__")


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one test anchor in {relative}, found {count}")
    path.write_text(text.replace(old, new, 1))


replace_once(
    "src/echoflow/transcription/tests/test_models.py",
    '({"schema_version": 3}, "unsupported transcript schema version"),',
    '({"schema_version": 4}, "unsupported transcript schema version"),',
)
replace_once(
    "src/echoflow/core/tests/test_config.py",
    '        "FASTER_WHISPER_MODEL_REVISION": (\n'
    '            "Optional immutable model revision requested from the model hub"\n'
    '        ),\n',
    '        "FASTER_WHISPER_MODEL_REVISION": (\n'
    '            "Optional immutable model revision requested from the model hub"\n'
    '        ),\n'
    '        "PYANNOTE_MODEL_ID": (\n'
    '            "Optional local speaker-diarization model identifier"\n'
    '        ),\n'
    '        "PYANNOTE_MODEL_REVISION": "Optional immutable pyannote model revision",\n',
)

print("diarization test-contract migrations applied")

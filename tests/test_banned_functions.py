"""Static check: banned functions must never appear in recwise's own source.

Belt-and-suspenders alongside the ruff S-rules and bandit in pre-commit —
this test fails CI even if someone bypasses pre-commit locally.
"""

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

BANNED_PATTERNS = {
    r"\beval\s*\(": "eval()",
    r"\bexec\s*\(": "exec()",
    r"\bpickle\.(loads?|dumps?)\s*\(": "pickle",
    r"\byaml\.load\s*\(": "unsafe yaml.load() (use yaml.safe_load)",
    r"\bos\.system\s*\(": "os.system()",
    r"shell\s*=\s*True": "shell=True",
}


def test_no_banned_functions_in_source() -> None:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern, label in BANNED_PATTERNS.items():
            if re.search(pattern, text):
                violations.append(f"{path}: {label}")
    assert not violations, f"Banned function(s) found: {violations}"

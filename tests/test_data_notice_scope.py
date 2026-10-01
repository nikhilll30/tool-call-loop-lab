"""DATA_NOTICE scope coverage. Same file runs in the canonical and the public tree:
 - always: unit tests of the checker on synthetic input;
 - public tree (DATA_NOTICE.md at the root): every tracked file is covered by exactly one scope entry, and no entry matches nothing;
 - canonical tree (no root DATA_NOTICE.md): the release/DATA_NOTICE.md template must at least parse (known licences, well-formed rows)."""
import subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import notice_scope as ns

SAMPLE = """x
<!-- scope:start -->
| paths | licence | note |
|---|---|---|
| `a/**`, `b.txt` | Apache-2.0 | code |
| `c/*.md` | CC BY 4.0 | docs |
| `LICENSE` | none | text |
<!-- scope:end -->
"""


def test_scope_checker_unit():
    files = ["a/x.py", "a/y/z.py", "b.txt", "c/d.md", "LICENSE"]
    assert ns.check(files, SAMPLE) == []
    assert any("matched by 0" in p for p in ns.check(files + ["new.txt"], SAMPLE))               # uncovered file
    assert any("matches no file" in p for p in ns.check(files[:-1], SAMPLE))                      # dead entry
    assert any("matched by 2" in p for p in ns.check(files, SAMPLE.replace("`b.txt`", "`b.txt`, `a/x.py`")))   # overlap
    assert ns.matches("c/*.md", "c/d.md") and not ns.matches("c/*.md", "c/e/d.md")
    with pytest.raises(AssertionError):
        ns.parse_scope(SAMPLE.replace("Apache-2.0", "MIT"))


def _tracked():
    if (ROOT / ".git").exists():
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return sorted(out.stdout.split("\n")[:-1] if out.stdout.endswith("\n") else out.stdout.split("\n"))
    skip = {".git", "__pycache__", ".pytest_cache", ".venv"}
    return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                  if p.is_file() and not (skip & set(p.relative_to(ROOT).parts)) and not p.relative_to(ROOT).as_posix().startswith(("data/heldout/", "data/traces/", "results/tmp/")))


def test_real_notice_scope():
    notice = ROOT / "DATA_NOTICE.md"
    if notice.exists():                                  # public tree
        assert ns.check(_tracked(), notice.read_text()) == []
    else:                                                # canonical tree: template must parse
        scope = ns.parse_scope((ROOT / "release" / "DATA_NOTICE.md").read_text())
        assert scope and {l for _, l in scope} <= ns.LICENCES

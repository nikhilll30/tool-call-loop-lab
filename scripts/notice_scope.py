"""DATA_NOTICE scope parser/checker (shared by tests and the public-build gate).

DATA_NOTICE.md contains one table between the markers `<!-- scope:start -->` and `<!-- scope:end -->`.
Each row is `| `pattern`, `pattern` | licence | note |`. Pattern forms: an exact file path; `dir/**` (everything below dir);
`dir/*.ext` (single directory level, fnmatch). Licences: Apache-2.0, CC BY 4.0, none.
Rule: every tracked file is matched by exactly one row pattern, and every pattern matches at least one tracked file."""
from __future__ import annotations
import fnmatch, re

LICENCES = {"Apache-2.0", "CC BY 4.0", "none"}
START, END = "<!-- scope:start -->", "<!-- scope:end -->"


def parse_scope(text: str) -> list[tuple[str, str]]:
    """-> [(pattern, licence), ...] in file order."""
    assert START in text and END in text, "scope markers missing"
    body = text.split(START, 1)[1].split(END, 1)[0]
    out = []
    for line in body.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower().startswith("paths"):
            continue
        lic = cells[1]
        assert lic in LICENCES, f"unknown licence {lic!r} in row {line[:60]!r}"
        pats = re.findall(r"`([^`]+)`", cells[0])
        assert pats, f"row without patterns: {line[:60]!r}"
        out += [(p, lic) for p in pats]
    return out


def matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    if "*" in pattern:
        return pattern.count("/") == path.count("/") and fnmatch.fnmatchcase(path, pattern)
    return path == pattern


def check(files: list[str], text: str) -> list[str]:
    """-> list of problems (empty = ok)."""
    scope = parse_scope(text)
    problems = []
    pats = [p for p, _ in scope]
    if len(set(pats)) != len(pats):
        problems.append("duplicate scope patterns")
    for f in files:
        hits = [p for p, _ in scope if matches(p, f)]
        if len(hits) != 1:
            problems.append(f"{f}: matched by {len(hits)} scope entries {hits}")
    for p, _ in scope:
        if not any(matches(p, f) for f in files):
            problems.append(f"scope entry matches no file: {p}")
    return problems

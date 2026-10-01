import json
from pathlib import Path


def load_jsonl(p: Path) -> list[dict]:
    p = Path(p)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

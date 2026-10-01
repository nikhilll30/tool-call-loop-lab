"""STAGE 4 entry point (NOT implemented in Phase 1): online guard A/B, guard off vs on, FROZEN config only.
Refuses to run unless configs/frozen/ verifies. Phase 1 ships only this gate."""
from __future__ import annotations
import sys
from pathlib import Path
from .freeze import require_frozen, FrozenConfigError


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--frozen-dir", default=None, help="test hook: verify a different directory")
    a = ap.parse_args(argv if argv is not None else [])
    try:
        cfg, fp = require_frozen(Path(a.frozen_dir)) if a.frozen_dir else require_frozen()
    except FrozenConfigError as e:
        print(f"REFUSING to run online A/B: {e}", file=sys.stderr)
        return 2
    print(f"frozen config {cfg.id} ({cfg.hash()}) verified; A/B runner is a Phase 4 deliverable and is not implemented.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

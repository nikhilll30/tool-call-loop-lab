"""STAGE 3 tooling: freeze detector+guard config and the false-positive threshold; verify before any online A/B.

Layout of configs/frozen/:
  detector_guard.DRAFT.yaml       <- editable draft (Stage 2 tuning happens here). NOT frozen.
  frozen_fp_threshold.DRAFT.json  <- draft FP threshold (max FP rate on the legitimate suite the guard may have)
  detector_guard.frozen.yaml      <- created ONLY by `python -m floodlab.freeze freeze` (currently absent)
  frozen_fp_threshold.frozen.json <- ditto
  MANIFEST.json                   <- sha256 of the two frozen files + config hash + status "frozen"
Online A/B (floodlab/ab_online.py) calls require_frozen(), which raises unless MANIFEST.json exists and every hash matches.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import yaml
from .config import GuardConfig

FROZEN_DIR = Path(__file__).resolve().parent.parent / "configs" / "frozen"
DRAFT_CFG = FROZEN_DIR / "detector_guard.DRAFT.yaml"
DRAFT_FP = FROZEN_DIR / "frozen_fp_threshold.DRAFT.json"
FROZEN_CFG = FROZEN_DIR / "detector_guard.frozen.yaml"
FROZEN_FP = FROZEN_DIR / "frozen_fp_threshold.frozen.json"
MANIFEST = FROZEN_DIR / "MANIFEST.json"


class FrozenConfigError(RuntimeError):
    pass


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_config(path: Path = DRAFT_CFG) -> GuardConfig:
    return GuardConfig.from_dict(yaml.safe_load(Path(path).read_text()))


def dump_config(cfg: GuardConfig, path: Path, header: str = "") -> None:
    Path(path).write_text(header + yaml.safe_dump(cfg.to_dict(), sort_keys=True))


def freeze(frozen_dir: Path = FROZEN_DIR, draft_cfg: Path | None = None, draft_fp: Path | None = None) -> dict:
    """Copy the draft to *.frozen.* and write the manifest. Explicit human action; never called by the demo/tests on real dir."""
    draft_cfg = draft_cfg or (frozen_dir / DRAFT_CFG.name)
    draft_fp = draft_fp or (frozen_dir / DRAFT_FP.name)
    cfg = load_config(draft_cfg)
    fp = json.loads(draft_fp.read_text())
    if fp.get("max_fp_rate") is None:
        raise FrozenConfigError("draft FP threshold has no max_fp_rate")
    fcfg, ffp, man = frozen_dir / FROZEN_CFG.name, frozen_dir / FROZEN_FP.name, frozen_dir / MANIFEST.name
    fcfg.write_bytes(draft_cfg.read_bytes())
    ffp.write_bytes(draft_fp.read_bytes())
    manifest = {"status": "frozen", "config_id": cfg.id, "config_hash": cfg.hash(),
                "files": {fcfg.name: file_sha256(fcfg), ffp.name: file_sha256(ffp)}}
    man.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def require_frozen(frozen_dir: Path = FROZEN_DIR) -> tuple[GuardConfig, dict]:
    """Return (guard config, fp threshold) iff the frozen files exist and match the manifest; else raise."""
    man = frozen_dir / MANIFEST.name
    if not man.exists():
        raise FrozenConfigError(f"no {man}: config is NOT frozen; refusing to run online A/B")
    m = json.loads(man.read_text())
    if m.get("status") != "frozen":
        raise FrozenConfigError("manifest status is not 'frozen'")
    for name, h in m["files"].items():
        p = frozen_dir / name
        if not p.exists():
            raise FrozenConfigError(f"frozen file missing: {name}")
        if file_sha256(p) != h:
            raise FrozenConfigError(f"frozen file CHANGED since freeze: {name}")
    cfg = load_config(frozen_dir / FROZEN_CFG.name)
    if cfg.hash() != m["config_hash"]:
        raise FrozenConfigError("parsed config hash differs from manifest")
    return cfg, json.loads((frozen_dir / FROZEN_FP.name).read_text())


def status_text(frozen_dir: Path = FROZEN_DIR) -> str:
    try:
        cfg, fp = require_frozen(frozen_dir)
        return f"FROZEN config {cfg.id} hash={cfg.hash()} fp_threshold={fp}"
    except FrozenConfigError as e:
        d = load_config(frozen_dir / DRAFT_CFG.name)
        return f"NOT FROZEN ({e}).\n  draft config {d.id} hash={d.hash()} (DRAFT: online A/B will refuse to run)"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "freeze":
        print(json.dumps(freeze(), indent=1))
    elif cmd == "verify":
        try:
            cfg, fp = require_frozen(); print("OK frozen", cfg.id, cfg.hash())
        except FrozenConfigError as e:
            print("FAIL:", e); sys.exit(2)
    else:
        print(status_text())

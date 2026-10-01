"""Demonstrate the Stage-4 gate in a TEMP directory (real configs/frozen/ is untouched and stays unfrozen).
The config used is S0 = the Phase 1 dev config, chosen ONLY to exercise the tooling; it was NOT selected (nothing qualified)."""
import json, shutil, tempfile
from pathlib import Path
from floodlab import freeze, ab_online
from floodlab.policies import selectable_policies, guard_config_for

d = Path(tempfile.mkdtemp()) / "frozen"; d.mkdir()
cfg = guard_config_for([p for p in selectable_policies() if p.id == "S0"][0])
freeze.dump_config(cfg, d / freeze.DRAFT_CFG.name, header="# TOOLING DEMO ONLY - not selected, not the repo's frozen config\n")
(d / freeze.DRAFT_FP.name).write_text(json.dumps({"status": "DEMO", "max_fp_rate": 0.05}))
print("1. before freeze  ->", ab_online.main(["--frozen-dir", str(d)]), "(2 = refuse)")
m = freeze.freeze(d); print("2. manifest:", json.dumps(m))
print("3. after freeze   ->", ab_online.main(["--frozen-dir", str(d)]), "(3 = verified; A/B itself not implemented)")
f = d / freeze.FROZEN_CFG.name
f.write_text(f.read_text().replace("max_calls_per_generation: 1000000000", "max_calls_per_generation: 999"))
print("4. after tampering with the frozen file ->", ab_online.main(["--frozen-dir", str(d)]), "(2 = refuse)")
print("5. REAL repo gate  ->", ab_online.main([]), "(2 = refuse: repo config is NOT frozen)")

import hashlib, json
from pathlib import Path
from floodlab import phase1_5, freeze
from floodlab.heldout.dataset import PATH
from floodlab.heldout_eval import run
from floodlab.trace import read_jsonl


def test_preregistered_sha_and_recorded_outcome(tmp_path):
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == phase1_5.registered_sha()
    res = run(read_jsonl(PATH), tmp_path)
    committed = json.loads((Path(__file__).resolve().parent.parent / "results" / "phase1_5" / "metrics.json").read_text())
    assert res["selection"] == committed["selection"]                      # same outcome as the committed first run
    assert res["selection"]["selected"] is None                            # nothing qualified -> nothing frozen
    assert [r["detected"] for r in res["results"]] == [r["detected"] for r in committed["results"]]
    assert [r["fp"] for r in res["results"]] == [r["fp"] for r in committed["results"]]


def test_repo_config_not_frozen_because_nothing_qualified():
    assert not (freeze.FROZEN_DIR / "MANIFEST.json").exists()

"""Dev and held-out data must stay separate."""
import ast, hashlib, re
from pathlib import Path
import pytest
from floodlab import evaluate
from floodlab.heldout import dataset, floods, legit
from floodlab.heldout.handwritten import heldout_handwritten
from floodlab.trace import flat_calls, generations, validate

ROOT = Path(__file__).resolve().parent.parent


def test_heldout_package_imports_no_detectors():
    for p in (ROOT / "floodlab" / "heldout").glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom): names = [node.module or ""] + [a.name for a in node.names]
            if isinstance(node, ast.Import): names = [a.name for a in node.names]
            assert not any("detectors" in n or "policies" in n or "heldout_eval" in n for n in names), (p, names)


def test_dev_evaluation_refuses_heldout():
    t = floods.F1_slow_drift_offset(1000)
    assert t["split"] == "heldout"
    with pytest.raises(ValueError, match="held-out"):
        evaluate.evaluate(__import__("floodlab.config", fromlist=["x"]).SuiteConfig(), [t])


def test_dev_suite_contains_no_heldout_traces_or_seeds():
    from floodlab.gen.suites import all_traces
    ts = all_traces()
    assert all(t["split"] in ("dev", "test", "none") for t in ts)
    assert not any(str(t["provenance"]["seed"]).startswith("10") and t["provenance"]["seed"] >= 1000 for t in ts)
    ho_ids = {t["run_id"] for t in dataset.build_all()}
    assert not ho_ids & {t["run_id"] for t in ts}


def test_dev_code_does_not_import_heldout():
    dev = [ROOT / "floodlab" / "evaluate.py", ROOT / "floodlab" / "run_offline_demo.py"] + list((ROOT / "floodlab" / "gen").glob("*.py"))
    for p in dev:
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom): mods = [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import): mods = [a.name for a in node.names]
            else: continue
            assert not any("heldout" in m for m in mods), (p, mods)


def test_heldout_dataset_matches_preregistered_sha_and_is_deterministic():
    sel = (ROOT / "docs" / "SELECTION_PROCEDURE.md").read_text()
    reg = re.search(r"dataset sha256.*?`([0-9a-f]{64})`", sel, re.S).group(1)
    assert hashlib.sha256(dataset.PATH.read_bytes()).hexdigest() == reg
    assert [t["run_id"] for t in dataset.build_all()] == [t["run_id"] for t in dataset.build_all()]
    assert dataset.build_all() == dataset.build_all()


def test_heldout_structure_and_labels():
    ts = dataset.build_all()
    fl = [t for t in ts if t["label"] == "flood"]; lg = [t for t in ts if t["label"] == "legitimate"]
    assert (len(fl), len(lg)) == (78, 122)
    assert len({t["shape"] for t in fl}) >= 8 and len({t["shape"] for t in lg}) >= 8
    assert all(not validate(t) and t["split"] == "heldout" and t["synthetic"] for t in ts)
    for t in fl:
        ls = t["ground_truth"]["loop_start_index"]; assert isinstance(ls, int) and 0 <= ls < len(flat_calls(t)), t["run_id"]
    assert all(t["ground_truth"]["loop_start_index"] is None for t in lg)
    assert len(heldout_handwritten()) == 18


def test_heldout_structures_differ_from_dev():
    from floodlab.gen import floods as dfl, legit as dlg
    assert not set(floods.FLOOD_STRUCTURES) & set(dfl.FLOOD_SHAPES)
    assert not set(legit.LEGIT_STRUCTURES) & set(dlg.LEGIT_FAMILIES)

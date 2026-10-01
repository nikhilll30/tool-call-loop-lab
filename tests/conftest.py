import pytest
from floodlab.servers import LocalServer
from floodlab.mock_upstream.app import create_app


@pytest.fixture()
def upstream():
    app = create_app()
    with LocalServer(app) as srv:
        srv.app = app
        yield srv


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Hard guarantee for the suite: any non-loopback socket connect fails the test."""
    import socket
    real = socket.socket.connect

    def guarded(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and self.family != socket.AF_UNIX:
            raise RuntimeError(f"NETWORK BLOCKED in tests: {addr}")
        return real(self, addr, *a, **k)
    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture(scope="session", autouse=True)
def _heldout_dataset_present():
    """The held-out dataset is deterministic generated data (python -m floodlab.heldout). If the file is absent (e.g. a fresh public
    checkout, where it is intentionally not shipped), regenerate it and require the pre-registered sha256 before any test runs."""
    import hashlib, re
    from pathlib import Path
    from floodlab.heldout import dataset
    if not dataset.PATH.exists():
        dataset.PATH.parent.mkdir(parents=True, exist_ok=True)
        dataset.write(dataset.PATH)
    sel = (Path(__file__).resolve().parent.parent / "docs" / "SELECTION_PROCEDURE.md").read_text()
    reg = re.search(r"dataset sha256.*?`([0-9a-f]{64})`", sel, re.S).group(1)
    assert hashlib.sha256(dataset.PATH.read_bytes()).hexdigest() == reg, "held-out dataset does not match the pre-registered sha256"

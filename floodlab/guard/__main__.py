"""python -m floodlab.guard --upstream http://127.0.0.1:8801/v1 --port 8802 [--config configs/frozen/detector_guard.DRAFT.yaml]"""
import argparse, uvicorn
from ..freeze import load_config, DRAFT_CFG
from .proxy import create_guard_app
p = argparse.ArgumentParser(); p.add_argument("--upstream", required=True); p.add_argument("--port", type=int, default=8802)
p.add_argument("--config", default=str(DRAFT_CFG)); a = p.parse_args()
uvicorn.run(create_guard_app(a.upstream, load_config(a.config)), host="127.0.0.1", port=a.port, log_level="warning")

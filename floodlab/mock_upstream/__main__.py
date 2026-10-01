"""python -m floodlab.mock_upstream [--port 8801]  (binds 127.0.0.1 only)"""
import argparse, uvicorn
from .app import app
p = argparse.ArgumentParser(); p.add_argument("--port", type=int, default=8801)
uvicorn.run(app, host="127.0.0.1", port=p.parse_args().port, log_level="warning")

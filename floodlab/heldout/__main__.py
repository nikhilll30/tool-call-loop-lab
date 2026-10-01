"""python -m floodlab.heldout  -> (re)generate data/heldout/heldout_v1.jsonl and print its sha256 (no detectors involved)."""
from .dataset import write, PATH
print(PATH, write())

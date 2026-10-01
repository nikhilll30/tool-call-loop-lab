PY ?= .venv/bin/python
.PHONY: demo test install
install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
demo:
	$(PY) -m floodlab.run_offline_demo
test:
	$(PY) -m pytest -q

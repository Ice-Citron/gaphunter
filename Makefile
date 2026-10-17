PY ?= .venv/bin/python
STREAMLIT ?= .venv/bin/streamlit
# localhost only by default; `make demo STREAMLIT_FLAGS=` serves on every interface.
STREAMLIT_FLAGS ?= --server.address localhost

.PHONY: demo docs

# Re-render README/VIDEO_SCRIPT/heatmap from the committed CSVs, then open the app.
demo: docs
	$(STREAMLIT) run app/streamlit_app.py $(STREAMLIT_FLAGS)

docs:
	$(PY) -m analysis.fill_docs

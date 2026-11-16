"""Shared helpers for the FrameScout app (app.py) and engine (framescout_engine.py).

The package uses only the Python standard library, so it can be imported and tested
without torch, Streamlit or any model download. It has one module per area (I15); import
from the module that defines a name, e.g. "from framescout_core.settings import read_settings"
(I45: there is no re-export list here). Monkeypatch a helper on the module that calls it.
"""

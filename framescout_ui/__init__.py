"""The areas of the Streamlit app (A46): app.py keeps the page layout and imports them from here.

Every module imports streamlit, so only app.py imports this package: the engine, the other
scripts and the tests (CI installs no streamlit) never do. The tests read its source instead.
"""

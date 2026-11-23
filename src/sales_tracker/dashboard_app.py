"""Streamlit entry point (spec M6): `streamlit run` needs a script file. Start it with
`python -m sales_tracker dashboard`, which also sets where the data is."""

from sales_tracker.dashboard import render

render()

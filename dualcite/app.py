"""
app.py: unified DualCite application.

One Dash app, one port, two tabs (Citation Graph | Geo Map) sharing a single
sidebar for venue selection and a single precomputed index. The selected venues
live in a dcc.Store ('shared-venues') that both tabs read from, so choosing
conferences once applies to both views.
"""
from __future__ import annotations

import sys
import webbrowser
from threading import Timer

import dash
from dash import Input, Output, ctx, dcc, html

from .config import load_config
from .index import build_index, compute_citation_stats
from .tabs.graph import graph_layout, register_graph_callbacks
from .tabs.geomap import (geomap_layout, register_geomap_callbacks,
                          build_geo_aux)


def build_app(config_path="config.yaml"):
    cfg = load_config(config_path)

    print("Building index (first run may take a while)...", file=sys.stderr)
    index = build_index(cfg)
    stats = compute_citation_stats(index)
    geo_aux = build_geo_aux(index, stats)

    a, b = cfg.clusters["a"], cfg.clusters["b"]
    all_venues = a.venues + b.venues

    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    app.title = "DualCite"
    # spinner animation (inline styles can't express @keyframes)
    app.index_string = """<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
@keyframes dc-spin { to { transform: rotate(360deg); } }
.dc-spinner { animation: dc-spin 0.8s linear infinite; }
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""

    # ---- shared sidebar ----
    def venue_checklist(cluster, cid):
        return html.Div([
            html.Div([html.Span("● ", style={"color": cluster.color}),
                      cluster.name], style={"fontSize": "12px",
                      "fontWeight": "600", "marginBottom": "4px"}),
            dcc.Checklist(id=cid,
                options=[{"label": " " + v.upper(), "value": v}
                         for v in cluster.venues],
                value=list(cluster.venues),
                labelStyle={"display": "block", "fontSize": "12px",
                            "padding": "1px 0"}),
            html.Button("All", id=cid + "-all", style=_BTN),
            html.Button("None", id=cid + "-none",
                        style={**_BTN, "marginLeft": "4px"}),
        ], style={"marginBottom": "16px"})

    sidebar = html.Div(style=_SIDE, children=[
        html.H2("DualCite", style={"fontSize": "18px", "margin": "0 0 2px"}),
        html.P("Citation flows between two venue groups",
               style={"fontSize": "10px", "color": "#888",
                      "margin": "0 0 16px"}),
        venue_checklist(a, "cl-a"),
        venue_checklist(b, "cl-b"),
        html.Hr(style={"border": "none", "borderTop": "1px solid #e5e5e5"}),
        html.Div(id="sidebar-summary", style={"fontSize": "11px",
                 "color": "#666", "marginTop": "10px"}),
    ])

    # ---- tabs ----
    tabs = dcc.Tabs(id="tabs", value="graph", style={"height": "48px"},
        children=[
            dcc.Tab(label="Citation Graph", value="graph",
                    style=_TAB, selected_style=_TAB_SEL),
            dcc.Tab(label="Geo Map", value="geo",
                    style=_TAB, selected_style=_TAB_SEL),
        ])

    app.layout = html.Div(style={"display": "flex", "margin": 0,
        "fontFamily": "system-ui,-apple-system,sans-serif"}, children=[
        dcc.Store(id="shared-venues", data=list(all_venues)),
        sidebar,
        html.Div(style={"flex": 1, "height": "100vh", "overflow": "hidden"},
                 children=[
            tabs,
            html.Div(id="graph-container",
                     children=graph_layout(cfg),
                     style={"display": "block"}),
            html.Div(id="geo-container",
                     children=geomap_layout(cfg),
                     style={"display": "none"}),
        ]),
    ])

    # ---- shared callbacks ----
    @app.callback(Output("cl-a", "value"),
                  Input("cl-a-all", "n_clicks"), Input("cl-a-none", "n_clicks"),
                  prevent_initial_call=True)
    def _sel_a(*_):
        return list(a.venues) if ctx.triggered_id == "cl-a-all" else []

    @app.callback(Output("cl-b", "value"),
                  Input("cl-b-all", "n_clicks"), Input("cl-b-none", "n_clicks"),
                  prevent_initial_call=True)
    def _sel_b(*_):
        return list(b.venues) if ctx.triggered_id == "cl-b-all" else []

    @app.callback(Output("shared-venues", "data"),
                  Output("sidebar-summary", "children"),
                  Input("cl-a", "value"), Input("cl-b", "value"))
    def _sync(va, vb):
        selected = list(va or []) + list(vb or [])
        n_a = sum(1 for p in index["papers"].values()
                  if p["venue"] in set(va or []))
        n_b = sum(1 for p in index["papers"].values()
                  if p["venue"] in set(vb or []))
        summary = html.Div([
            html.Div(f"{a.short}: {n_a} papers"),
            html.Div(f"{b.short}: {n_b} papers"),
            html.Div(f"Total selected venues: {len(selected)}",
                     style={"marginTop": "4px", "color": "#999"}),
        ])
        return selected, summary

    # tab switching, toggle container visibility (keeps both mounted so
    # state and computed figures persist)
    @app.callback(Output("graph-container", "style"),
                  Output("geo-container", "style"),
                  Input("tabs", "value"))
    def _switch(tab):
        vis = {"display": "block"}
        hid = {"display": "none"}
        return (vis, hid) if tab == "graph" else (hid, vis)

    # When a tab becomes visible, Plotly/Cytoscape may have been laid out while
    # hidden (0x0) and render blank. Fire a window resize so they recompute.
    app.clientside_callback(
        """
        function(tab) {
            setTimeout(function() {
                window.dispatchEvent(new Event('resize'));
            }, 60);
            return window.dash_clientside.no_update;
        }
        """,
        Output("tabs", "value", allow_duplicate=True),
        Input("tabs", "value"),
        prevent_initial_call=True)

    # ---- tab-specific callbacks ----
    register_graph_callbacks(app, cfg, index, stats)
    register_geomap_callbacks(app, cfg, index, stats, geo_aux)

    return app, cfg


_BTN = {"fontSize": "10px", "marginTop": "4px", "padding": "2px 8px",
        "cursor": "pointer", "background": "#f0f0f0",
        "border": "1px solid #ddd", "borderRadius": "3px"}
_SIDE = {"width": "260px", "minWidth": "260px", "padding": "18px 16px",
         "background": "#fff", "borderRight": "1px solid #e5e5e5",
         "height": "100vh", "overflowY": "auto", "boxSizing": "border-box"}
_TAB = {"padding": "12px", "fontSize": "13px", "borderBottom": "1px solid #e5e5e5"}
_TAB_SEL = {"padding": "12px", "fontSize": "13px", "fontWeight": "600",
            "borderTop": "2px solid #7F77DD",
            "borderBottom": "1px solid #fff"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DualCite: citation and affiliation views")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app, cfg = build_app(args.config)
    port = args.port or cfg.port

    if cfg.open_browser and not args.no_browser:
        Timer(1.5, lambda: webbrowser.open_new(
            f"http://127.0.0.1:{port}")).start()

    print(f"\n  -> http://127.0.0.1:{port}   (Ctrl+C to exit)\n", file=sys.stderr)
    app.run(debug=False, port=port)


if __name__ == "__main__":
    main()

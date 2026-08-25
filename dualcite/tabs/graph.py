"""
tabs/graph.py — Citation Graph tab.

Interactive Cytoscape graph of the citation network. Nodes are papers (sized by
in-corpus citations), edges are coloured by flow direction (a→a, b→b, a→b, b→a).
All cluster/venue/colour specifics come from the Config object.

Exposes:
  graph_layout(cfg)  -> Dash component tree for the tab body
  register_graph_callbacks(app, cfg, index, stats)  -> wires the callbacks
"""
from __future__ import annotations

import hashlib
import json
import math
import time as _time
from collections import defaultdict
from pathlib import Path

import networkx as nx
from dash import Input, Output, State, ctx, dcc, html

# ---- module-scope handles set by register_graph_callbacks ----
_CFG = None
_PAPERS = {}
_CITS = {}
_STATS = {}
_LAYOUT_DIR = None   # where computed layouts are cached on disk


# ============================== layout helpers ==============================

def _radial_fill(raw, cx, cy, rx, ry):
    """Uniform ellipse fill via golden-angle spiral (sunflower)."""
    if not raw:
        return {}
    if len(raw) == 1:
        n = next(iter(raw))
        return {n: {"x": float(cx), "y": float(cy)}}
    vs = list(raw.values())
    mx = sum(p[0] for p in vs) / len(vs)
    my = sum(p[1] for p in vs) / len(vs)
    order = sorted(raw, key=lambda n: math.atan2(raw[n][1] - my, raw[n][0] - mx))
    GA = math.pi * (3 - math.sqrt(5))
    N = len(order)
    out = {}
    for i, n in enumerate(order):
        r = math.sqrt((i + 0.5) / N) * 0.93
        ang = i * GA
        out[n] = {"x": float(cx + r * rx * math.cos(ang)),
                  "y": float(cy + r * ry * math.sin(ang))}
    return out


def _rect_fill(raw, cx, cy, hw, hh):
    if not raw:
        return {}
    if len(raw) == 1:
        n = next(iter(raw))
        return {n: {"x": float(cx), "y": float(cy)}}
    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    mnx, mxx = min(xs), max(xs)
    mny, mxy = min(ys), max(ys)
    rx = mxx - mnx or 1
    ry = mxy - mny or 1
    return {n: {"x": ((x - mnx) / rx - .5) * 2 * hw * .9 + cx,
                "y": ((y - mny) / ry - .5) * 2 * hh * .9 + cy}
            for n, (x, y) in raw.items()}


def _compute_pos_raw(nodes, edges, papers, topo, W=2000, H=1600):
    if not nodes:
        return {}
    N = len(nodes)
    iters = max(10, min(50, 2000 // max(N, 1) * 10))
    G = nx.Graph()
    G.add_nodes_from(nodes)
    for s, t in edges:
        if s in nodes and t in nodes:
            G.add_edge(s, t)
    a_nodes = [n for n in nodes if papers[n]["cluster"] == "a"]
    b_nodes = [n for n in nodes if papers[n]["cluster"] == "b"]
    if topo == "mixed":
        raw = nx.spring_layout(G, k=1.0, iterations=iters, seed=42)
        return _rect_fill(raw, 0, 0, W * .45, H * .45)
    elif topo == "halves":
        pos = {}
        if a_nodes:
            raw = nx.spring_layout(G.subgraph(a_nodes), k=1.5,
                                   iterations=iters, seed=42)
            pos.update(_radial_fill(raw, -W * .27, 0, W * .22, H * .4))
        if b_nodes:
            raw = nx.spring_layout(G.subgraph(b_nodes), k=1.5,
                                   iterations=iters, seed=42)
            pos.update(_radial_fill(raw, W * .27, 0, W * .22, H * .4))
        return pos
    return {}


def _layout_key(nodes, edges, topo):
    """Stable hash of everything that determines node positions."""
    h = hashlib.sha1()
    h.update(topo.encode())
    # sorted nodes make the key order-independent
    for n in sorted(nodes):
        h.update(b"\x00")
        h.update(str(n).encode())
    # sorted edges (as sorted tuples) — layout depends on connectivity
    h.update(b"\xff")
    for s, t in sorted((min(a, b), max(a, b)) for a, b in edges):
        h.update(str(s).encode())
        h.update(b"\x01")
        h.update(str(t).encode())
        h.update(b"\x02")
    return h.hexdigest()


def _compute_pos(nodes, edges, papers, topo, W=2000, H=1600):
    """Cached wrapper around _compute_pos_raw.

    Node positions depend only on the node set, the edges among them, and the
    topology — none of which change between identical filter selections. So we
    hash those, cache the result on disk, and skip the expensive spring_layout
    on repeat selections.
    """
    if not nodes:
        return {}
    if _LAYOUT_DIR is None:
        return _compute_pos_raw(nodes, edges, papers, topo, W, H)

    key = _layout_key(nodes, edges, topo)
    cache_file = _LAYOUT_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text("utf-8"))
        except Exception:
            pass  # corrupt cache — recompute

    pos = _compute_pos_raw(nodes, edges, papers, topo, W, H)
    try:
        _LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(pos), "utf-8")
    except Exception:
        pass
    return pos


def _stylesheet(n, cfg):
    ec = cfg.edge_colors
    if n > 1500:
        cs, ar, ew, eo, ao = "haystack", "none", 0.5, 0.2, 0
    elif n > 500:
        cs, ar, ew, eo, ao = "haystack", "triangle", 0.8, 0.3, 0.5
    else:
        cs, ar, ew, eo, ao = "bezier", "triangle", 1, 0.35, 0.6
    return [
        {"selector": "node", "style": {
            "width": "data(size)", "height": "data(size)",
            "background-color": "data(color)", "border-width": 0,
            "label": "data(label)", "font-size": "8px", "text-opacity": 0.7,
            "color": "#333", "text-valign": "bottom", "text-margin-y": 3,
            "min-zoomed-font-size": 8}},
        {"selector": "node:selected", "style": {
            "border-width": 3, "border-color": "#222",
            "font-size": "11px", "text-opacity": 1}},
        {"selector": "edge.intra-a", "style": {
            "curve-style": cs, "target-arrow-shape": ar,
            "line-color": ec["intra_a"], "target-arrow-color": ec["intra_a"],
            "width": ew, "opacity": eo, "arrow-scale": ao}},
        {"selector": "edge.intra-b", "style": {
            "curve-style": cs, "target-arrow-shape": ar,
            "line-color": ec["intra_b"], "target-arrow-color": ec["intra_b"],
            "width": ew, "opacity": eo, "arrow-scale": ao}},
        {"selector": "edge.a-to-b", "style": {
            "curve-style": cs, "target-arrow-shape": ar,
            "line-color": ec["a_to_b"], "target-arrow-color": ec["a_to_b"],
            "width": max(ew, 1), "opacity": min(eo * 2.2, 0.8),
            "arrow-scale": ao * 1.2}},
        {"selector": "edge.b-to-a", "style": {
            "curve-style": cs, "target-arrow-shape": ar,
            "line-color": ec["b_to_a"], "target-arrow-color": ec["b_to_a"],
            "width": max(ew, 1), "opacity": min(eo * 2.2, 0.8),
            "arrow-scale": ao * 1.2}},
    ]


def _short(s, n=20):
    return (s[:n].rstrip() + "...") if s and len(s) > n else (s or "?")


def _legend(cfg, na, nb, ecnt):
    """Build the legend content with live node/edge counts."""
    a, b = cfg.clusters["a"], cfg.clusters["b"]
    ec = cfg.edge_colors

    def edge_item(color, label, count):
        return html.Span([
            html.Span("━ ", style={"color": color, "fontWeight": "700"}),
            html.Span(f"{label} ({count:,})  ")])

    return [
        html.Span("● ", style={"color": a.color}),
        html.Span(f"{a.short} ({na:,})  "),
        html.Span("● ", style={"color": b.color}),
        html.Span(f"{b.short} ({nb:,})"),
        html.Div(style={"marginTop": "4px"}, children=[
            edge_item(ec["intra_a"], f"{a.short}→{a.short}", ecnt["intra-a"]),
            edge_item(ec["intra_b"], f"{b.short}→{b.short}", ecnt["intra-b"]),
            edge_item(ec["a_to_b"], f"{a.short}→{b.short}", ecnt["a-to-b"]),
            edge_item(ec["b_to_a"], f"{b.short}→{a.short}", ecnt["b-to-a"]),
        ]),
    ]


# ============================== layout ==============================

def graph_layout(cfg):
    import dash_cytoscape as cyto
    a, b = cfg.clusters["a"], cfg.clusters["b"]
    return html.Div(style={"position": "relative", "height": "100%",
                           "background": "#fafafa"}, children=[
        cyto.Cytoscape(
            id="g-graph", layout={"name": "preset"},
            style={"width": "100%", "height": "calc(100vh - 48px)"},
            elements=[], stylesheet=_stylesheet(0, cfg),
            minZoom=0.02, maxZoom=6, wheelSensitivity=0.15),
        # topology control (graph-specific, sits top-left of canvas)
        html.Div(style={"position": "absolute", "top": "12px", "left": "12px",
                        "background": "#fff", "padding": "8px 12px",
                        "borderRadius": "6px", "border": "1px solid #e5e5e5",
                        "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
                        "zIndex": 20, "fontSize": "11px"}, children=[
            html.Div("Topology", style={"fontWeight": "600",
                                        "marginBottom": "4px"}),
            dcc.RadioItems(id="g-topo", options=[
                {"label": " Mixed", "value": "mixed"},
                {"label": " Left / Right split", "value": "halves"}],
                value="mixed", labelStyle={"display": "block"}),
            html.Div("Max nodes", style={"fontWeight": "600",
                                         "margin": "8px 0 2px"}),
            dcc.Slider(id="g-maxnodes", min=100, max=500, step=50, value=300,
                       marks={100: "100", 300: "300", 500: "500"}),
            dcc.Checklist(id="g-showall", options=[
                {"label": " Show all (no cap)", "value": "y"}], value=[],
                labelStyle={"fontSize": "11px"}),
            dcc.Checklist(id="g-showiso", options=[
                {"label": " Show isolated", "value": "y"}], value=[],
                labelStyle={"fontSize": "11px"}),
            dcc.Checklist(id="g-crossonly", options=[
                {"label": " Cross-cluster only", "value": "y"}], value=[],
                labelStyle={"fontSize": "11px"}),
            html.Label("Min in-citations", style={"display": "block",
                       "marginTop": "6px"}),
            dcc.Slider(id="g-mincit", min=0, max=10, step=1, value=0,
                       marks={0: "0", 5: "5", 10: "10"}),
        ]),
        # node info panel
        html.Div(id="g-info", style={
            "position": "absolute", "top": "12px", "right": "12px",
            "width": "320px", "maxHeight": "80vh", "overflowY": "auto",
            "background": "#fff", "padding": "14px 16px", "borderRadius": "8px",
            "border": "1px solid #e5e5e5",
            "boxShadow": "0 2px 12px rgba(0,0,0,0.08)", "zIndex": 20,
            "display": "none"}),
        # legend (populated by the build callback with live counts)
        html.Div(id="g-legend", style={"position": "absolute", "bottom": "12px",
                        "left": "12px", "background": "#fff",
                        "padding": "8px 12px", "borderRadius": "6px",
                        "border": "1px solid #e5e5e5", "fontSize": "11px",
                        "zIndex": 20}),
        html.Div(id="g-status", style={"position": "absolute",
                 "bottom": "12px", "right": "12px", "background": "#fff",
                 "padding": "6px 12px", "borderRadius": "6px",
                 "border": "1px solid #e5e5e5", "fontSize": "11px",
                 "color": "#888", "zIndex": 20}),
        # loading overlay — shown instantly (clientside) on any filter change,
        # hidden when the server returns the rebuilt graph
        html.Div(id="g-overlay", style={
            "position": "absolute", "top": 0, "left": 0, "right": 0,
            "bottom": 0, "background": "rgba(250,250,250,0.82)",
            "display": "none", "alignItems": "center",
            "justifyContent": "center", "zIndex": 50,
            "flexDirection": "column"}, children=[
            html.Div(className="dc-spinner", style={
                "width": "42px", "height": "42px",
                "border": "4px solid #e0e0e0",
                "borderTop": "4px solid #7F77DD",
                "borderRadius": "50%", "marginBottom": "14px"}),
            html.Div("Building graph…", style={"fontSize": "13px",
                     "color": "#555", "fontWeight": "500"}),
            html.Div("Recomputing layout for the selected venues",
                     style={"fontSize": "11px", "color": "#999",
                            "marginTop": "4px"}),
        ]),
    ])


# ============================== callbacks ==============================

def register_graph_callbacks(app, cfg, index, stats):
    global _CFG, _PAPERS, _CITS, _STATS, _LAYOUT_DIR
    _CFG = cfg
    _PAPERS = index["papers"]
    _CITS = index["citations"]
    _STATS = stats
    _LAYOUT_DIR = cfg.path("precomputed") / "layouts"

    a_short = cfg.clusters["a"].short
    b_short = cfg.clusters["b"].short
    a_col = cfg.clusters["a"].color
    b_col = cfg.clusters["b"].color

    # clientside: show the overlay the instant a filter changes, before the
    # server starts recomputing. The server callback above hides it when done.
    app.clientside_callback(
        """
        function(venues, mcit, mnodes, showall, showiso, crossonly, topo, cur) {
            var s = Object.assign({}, cur || {});
            s.display = 'flex';
            return s;
        }
        """,
        Output("g-overlay", "style", allow_duplicate=True),
        Input("shared-venues", "data"),
        Input("g-mincit", "value"), Input("g-maxnodes", "value"),
        Input("g-showall", "value"), Input("g-showiso", "value"),
        Input("g-crossonly", "value"), Input("g-topo", "value"),
        State("g-overlay", "style"),
        prevent_initial_call=True)

    @app.callback(
        Output("g-graph", "elements"), Output("g-graph", "layout"),
        Output("g-graph", "stylesheet"), Output("g-status", "children"),
        Output("g-overlay", "style"), Output("g-legend", "children"),
        Input("shared-venues", "data"),
        Input("g-mincit", "value"), Input("g-maxnodes", "value"),
        Input("g-showall", "value"), Input("g-showiso", "value"),
        Input("g-crossonly", "value"), Input("g-topo", "value"),
        State("g-overlay", "style"))
    def _build(selected, mcit, mnodes, showall, showiso, crossonly, topo,
               ov_style):
        t0 = _time.monotonic()
        selected = set(selected or [])
        hide_overlay = dict(ov_style or {})
        hide_overlay["display"] = "none"
        if not selected:
            return ([], {"name": "preset"}, _stylesheet(0, cfg),
                    "Select venues", hide_overlay,
                    _legend(cfg, 0, 0, {"intra-a": 0, "intra-b": 0,
                                        "a-to-b": 0, "b-to-a": 0}))

        sub = {pid: p for pid, p in _PAPERS.items() if p["venue"] in selected}
        ea = []
        for s, tgts in _CITS.items():
            if s not in sub:
                continue
            for t in tgts:
                if t in sub:
                    ea.append((s, t))

        xo = "y" in (crossonly or [])
        use_all = "y" in (showall or [])
        use_iso = "y" in (showiso or [])

        edges = [(s, t) for s, t in ea
                 if sub[s]["cluster"] != sub[t]["cluster"]] if xo else ea

        if mcit and mcit > 0 and not xo:
            ideg = defaultdict(int)
            for s, t in edges:
                ideg[t] += 1
            keep = {n for n in sub if ideg.get(n, 0) >= mcit}
            edges = [(s, t) for s, t in edges if s in keep and t in keep]

        ind = defaultdict(int)
        od = defaultdict(int)
        for s, t in edges:
            ind[t] += 1
            od[s] += 1

        connected = {x for e in edges for x in e}
        nodes = set(sub) if use_iso else set(connected)

        if not use_all and len(nodes) > mnodes:
            sc = {n: ind.get(n, 0) * 2 + od.get(n, 0) for n in nodes}
            a_nodes = [n for n in nodes if sub[n]["cluster"] == "a"]
            b_nodes = [n for n in nodes if sub[n]["cluster"] == "b"]
            total = len(a_nodes) + len(b_nodes)
            if total:
                a_q = max(1, round(mnodes * len(a_nodes) / total))
                b_q = max(1, mnodes - a_q)
            else:
                a_q = b_q = mnodes // 2
            keep = set(sorted(a_nodes, key=lambda n: -sc[n])[:a_q]) | \
                   set(sorted(b_nodes, key=lambda n: -sc[n])[:b_q])
            nodes = keep
            edges = [(s, t) for s, t in edges if s in nodes and t in nodes]
            ind.clear(); od.clear()
            for s, t in edges:
                ind[t] += 1; od[s] += 1

        nn = len(nodes)
        pos = _compute_pos(nodes, edges, sub, topo)
        style = _stylesheet(nn, cfg)

        # per-cluster sizing so smaller cluster's popular nodes stay visible
        mx_a = max((ind.get(n, 0) for n in nodes if sub[n]["cluster"] == "a"),
                   default=1) or 1
        mx_b = max((ind.get(n, 0) for n in nodes if sub[n]["cluster"] == "b"),
                   default=1) or 1
        lthr_frac = 0.7 if nn > 2000 else (0.5 if nn > 500 else 0.3)

        els = []
        for pid in nodes:
            p = sub[pid]
            is_a = p["cluster"] == "a"
            d = ind.get(pid, 0)
            mx_c = mx_a if is_a else mx_b
            sz = 8 + 50 * (d / mx_c) if mx_c else 8
            if not is_a:
                sz = min(sz, 53)
            col = a_col if is_a else b_col
            lthr = max(1, (mx_a if is_a else mx_b) * lthr_frac)
            lbl = _short(p["title"], 20) if d >= lthr else ""
            st = _STATS.get(pid, {})
            ps = pos.get(pid, {"x": 0, "y": 0})
            els.append({"data": {
                "id": pid, "label": lbl, "size": sz, "color": col,
                "cluster": p["cluster"], "venue": p["venue"],
                "title": p["title"], "year": p.get("year", ""),
                "doi": p.get("doi", ""), "url": p.get("url", ""),
                "ii": st.get("ii", 0), "ie": st.get("ie", 0),
                "oi": st.get("oi", 0), "oe": st.get("oe", 0)},
                "position": ps})

        ecnt = {"intra-a": 0, "intra-b": 0, "a-to-b": 0, "b-to-a": 0}
        for s, t in edges:
            sc, tc = sub[s]["cluster"], sub[t]["cluster"]
            if sc == "a" and tc == "b":
                cls = "a-to-b"
            elif sc == "b" and tc == "a":
                cls = "b-to-a"
            elif sc == "a":
                cls = "intra-a"
            else:
                cls = "intra-b"
            ecnt[cls] += 1
            els.append({"data": {"source": s, "target": t}, "classes": cls})

        # node counts per cluster
        na = sum(1 for pid in nodes if sub[pid]["cluster"] == "a")
        nb = nn - na
        legend = _legend(cfg, na, nb, ecnt)

        dt = _time.monotonic() - t0
        status = f"✓ {nn} nodes, {len(edges)} edges — {dt:.1f}s"
        return (els, {"name": "preset", "fit": True, "padding": 30}, style,
                status, hide_overlay, legend)

    @app.callback(Output("g-info", "children"), Output("g-info", "style"),
                  Input("g-graph", "tapNodeData"), State("g-info", "style"),
                  prevent_initial_call=True)
    def _node_info(data, cur):
        style = dict(cur or {})
        if not data:
            style["display"] = "none"
            return "", style
        style["display"] = "block"
        cl = data.get("cluster")
        short = a_short if cl == "a" else b_short
        col = a_col if cl == "a" else b_col

        def row(arrow, label, val):
            return html.Div(style={"display": "flex",
                "justifyContent": "space-between", "fontSize": "11px",
                "padding": "2px 0", "color": "#666"}, children=[
                html.Span(f"{arrow} {label}"),
                html.Strong(str(val), style={"color": "#222"})])

        ch = [
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center"}, children=[
                html.Span(data.get("venue", "").upper(), style={
                    "fontSize": "10px", "fontWeight": "700", "color": "#fff",
                    "background": col, "padding": "2px 7px",
                    "borderRadius": "3px"}),
                html.Span(f"{short} · {data.get('year', '')}",
                          style={"fontSize": "11px", "color": "#888"})]),
            html.P(data.get("title", ""), style={"fontSize": "13px",
                   "fontWeight": "500", "margin": "8px 0", "lineHeight": "1.4"}),
            html.Div(style={"padding": "8px 10px", "background": "#f7f7f5",
                            "borderRadius": "5px"}, children=[
                html.Div("Outgoing", style={"fontSize": "10px",
                    "fontWeight": "700", "color": "#888",
                    "textTransform": "uppercase", "marginBottom": "3px"}),
                row("→", "Internal", data.get("oi", 0)),
                row("→", "External", data.get("oe", 0)),
                html.Div("Incoming", style={"fontSize": "10px",
                    "fontWeight": "700", "color": "#888",
                    "textTransform": "uppercase",
                    "margin": "8px 0 3px"}),
                row("←", "Internal", data.get("ii", 0)),
                row("←", "External", data.get("ie", 0))]),
        ]
        if data.get("url"):
            ch.append(html.A("Open link ↗", href=data["url"], target="_blank",
                      style={"fontSize": "11px", "color": "#1d6cc4",
                             "display": "block", "marginTop": "8px"}))
        return html.Div(ch), style

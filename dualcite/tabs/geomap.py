"""
tabs/geomap.py: Geo Map tab.

World choropleth of author affiliations. Countries are coloured by how many
papers (in the selected venues) have at least one author affiliated there.
Clicking a country opens a detail panel (venue breakdown, institutions,
co-authoring countries, top papers).

Exposes:
  geomap_layout(cfg) -> Dash component tree for the tab body
  register_geomap_callbacks(app, cfg, index, stats) -> wires the callbacks
  build_geo_aux(index, stats) -> per-country aggregates, computed once at start-up
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from dash import Input, Output, State, dcc, html
import plotly.graph_objects as go

try:
    import pycountry
except ImportError:
    pycountry = None

_CFG = None
_PAPERS = {}
_GEO = {}          # aux aggregates
_STATS = {}

_A2_A3 = {}
_ALL_A3 = None      # cached list of every country's alpha-3 (for click layer)

# ISO names are unwieldy for some countries; show friendlier ones.
NAME_OVERRIDE = {
    "KR": "South Korea",
    "KP": "North Korea",
    "TW": "Taiwan",
    "RU": "Russia",
    "IR": "Iran",
    "VN": "Vietnam",
    "GB": "United Kingdom",
    "US": "United States",
    "CZ": "Czechia",
    "MO": "Macao",
    "HK": "Hong Kong",
}
# same keyed by alpha-3, for the base-layer labels
NAME_OVERRIDE_A3 = {}


def _a2_a3(code):
    if code in _A2_A3:
        return _A2_A3[code]
    a3 = None
    if pycountry:
        try:
            c = pycountry.countries.get(alpha_2=code)
            a3 = c.alpha_3 if c else None
        except Exception:
            a3 = None
    _A2_A3[code] = a3
    return a3


def _colorbar(scale, vmode, z):
    """Colour bar; on the logarithmic scale the ticks show the real values."""
    bar = dict(thickness=14, len=0.6, x=0.98)
    if scale != "log" or not z:
        return bar
    top = 10 ** max(z) - 1
    steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
    if vmode == "pct":
        steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
    vals = [v for v in steps if v <= top * 1.001] or [steps[0]]
    bar["tickvals"] = [math.log10(v + 1) for v in vals]
    bar["ticktext"] = [(f"{v:g}%" if vmode == "pct" else f"{v:,}") for v in vals]
    return bar


def _all_a3():
    """All ISO alpha-3 codes, so every country can be clicked."""
    global _ALL_A3
    if _ALL_A3 is None:
        if pycountry:
            _ALL_A3 = [c.alpha_3 for c in pycountry.countries]
            # build a3-keyed override map from the a2 one
            for a2, name in NAME_OVERRIDE.items():
                a3 = _a2_a3(a2)
                if a3:
                    NAME_OVERRIDE_A3[a3] = name
        else:
            _ALL_A3 = []
    return _ALL_A3


def _cname(code):
    if code in NAME_OVERRIDE:
        return NAME_OVERRIDE[code]
    if pycountry:
        try:
            c = pycountry.countries.get(alpha_2=code)
            return c.name if c else code
        except Exception:
            return code
    return code


def _cname_a3(a3):
    if a3 in NAME_OVERRIDE_A3:
        return NAME_OVERRIDE_A3[a3]
    if pycountry:
        try:
            c = pycountry.countries.get(alpha_3=a3)
            return c.name if c else a3
        except Exception:
            return a3
    return a3


# ============================== aux index ==============================

def build_geo_aux(index, stats):
    """
    Precompute per-country aggregates so country clicks and map redraws are
    instant. Returns a dict cached on the index object by the app.
    """
    papers = index["papers"]
    affil = index["affiliations"]

    venue_country = defaultdict(lambda: defaultdict(int))       # venue -> a2 -> count
    country_venue_count = defaultdict(lambda: defaultdict(int)) # a2 -> venue -> count
    country_venue_papers = defaultdict(lambda: defaultdict(list))
    country_venue_inst = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    country_pairs = defaultdict(int)
    venue_country_pairs = defaultdict(lambda: defaultdict(int))   # venue -> "a2|a2" -> count

    for pid, p in papers.items():
        v = p["venue"]
        aff = affil.get(pid, {})
        cs = sorted(set(aff.get("countries", [])))
        for c in cs:
            venue_country[v][c] += 1
            country_venue_count[c][v] += 1
            country_venue_papers[c][v].append(pid)
        # an institution counts only for the countries of its own affiliation
        pairs = {(inst, c) for inst, codes in aff.get("inst_country", []) for c in codes}
        for inst, c in pairs:
            country_venue_inst[c][v][inst] += 1
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                country_pairs[f"{cs[i]}|{cs[j]}"] += 1
                venue_country_pairs[v][f"{cs[i]}|{cs[j]}"] += 1

    # sort each paper list by citations desc, cap 100
    cit_total = {pid: stats.get(pid, {}).get("ii", 0) + stats.get(pid, {}).get("ie", 0)
                 for pid in papers}
    for c in country_venue_papers:
        for v in country_venue_papers[c]:
            country_venue_papers[c][v].sort(key=lambda pid: -cit_total.get(pid, 0))
            country_venue_papers[c][v] = country_venue_papers[c][v][:100]

    def undef(d):
        if isinstance(d, (defaultdict, dict)):
            return {k: undef(v) for k, v in d.items()}
        return d

    return {
        "venue_country": undef(venue_country),
        "country_venue_count": undef(country_venue_count),
        "country_venue_papers": undef(country_venue_papers),
        "country_venue_inst": undef(country_venue_inst),
        "country_pairs": dict(country_pairs),
        "venue_country_pairs": undef(venue_country_pairs),
        "cit_total": cit_total,
    }


# ============================== layout ==============================

def _geo_layout_dict(proj="equirectangular"):
    """Shared geo layout so the initial figure and updates look identical."""
    return dict(
        geo=dict(showframe=False, showcoastlines=True,
                 coastlinecolor="#000000", coastlinewidth=0.5,
                 projection_type=proj, landcolor="#eeeeee",
                 bgcolor="#fafafa",
                 showocean=True, oceancolor="#d6eef5",
                 showlakes=True, lakecolor="#d6eef5",
                 showland=True,
                 showcountries=True, countrycolor="#000000",
                 countrywidth=0.5),
        margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#fafafa",
        uirevision="keep", dragmode="pan")


def _empty_geo_figure():
    """A properly-configured geo figure shown before the first callback.

    Rendering a bare dcc.Graph with no figure produces blank Cartesian axes;
    giving it a real geo layout up front means the map looks right on first
    paint even while the geo tab is hidden.
    """
    fig = go.Figure()
    fig.add_trace(go.Choropleth(locations=[], z=[], showscale=False))
    fig.update_layout(**_geo_layout_dict())
    return fig


def geomap_layout(cfg):
    return html.Div(style={"position": "relative", "height": "100%",
                           "background": "#fafafa"}, children=[
        dcc.Graph(id="m-map", figure=_empty_geo_figure(),
                  style={"width": "100%",
                  "height": "calc(100vh - 48px)"},
                  config={"scrollZoom": True, "displaylogo": False,
                          "displayModeBar": False}),
        # controls top-left
        html.Div(style={"position": "absolute", "top": "12px", "left": "12px",
                        "background": "#fff", "padding": "8px 12px",
                        "borderRadius": "6px", "border": "1px solid #e5e5e5",
                        "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
                        "zIndex": 20, "fontSize": "11px",
                        "width": "180px"}, children=[
            html.Div("Color scale", style={"fontWeight": "600"}),
            dcc.RadioItems(id="m-scale", options=[
                {"label": " Logarithmic", "value": "log"},
                {"label": " Linear", "value": "lin"}], value="log",
                labelStyle={"display": "block"}),
            html.Div("Value", style={"fontWeight": "600", "marginTop": "6px"}),
            dcc.RadioItems(id="m-value", options=[
                {"label": " Absolute", "value": "abs"},
                {"label": " % of selection", "value": "pct"}], value="abs",
                labelStyle={"display": "block"}),
            html.Label("Min papers", style={"display": "block",
                       "marginTop": "6px"}),
            dcc.Slider(id="m-minpapers", min=0, max=20, step=1, value=0,
                       marks={0: "0", 10: "10", 20: "20"}),
            html.Label("Palette", style={"display": "block", "marginTop": "6px"}),
            dcc.Dropdown(id="m-palette", options=[
                {"label": "Viridis", "value": "Viridis"},
                {"label": "Blues", "value": "Blues"},
                {"label": "YlOrRd", "value": "YlOrRd"},
                {"label": "Plasma", "value": "Plasma"}], value="Viridis",
                clearable=False, style={"fontSize": "11px"}),
            html.Label("Projection", style={"display": "block",
                       "marginTop": "6px"}),
            dcc.Dropdown(id="m-proj", options=[
                {"label": "Equirectangular", "value": "equirectangular"},
                {"label": "Natural Earth", "value": "natural earth"},
                {"label": "Mercator", "value": "mercator"},
                {"label": "Robinson", "value": "robinson"},
                {"label": "Winkel Tripel", "value": "winkel tripel"},
                {"label": "Eckert IV", "value": "eckert4"},
                {"label": "Orthographic", "value": "orthographic"}],
                value="equirectangular", clearable=False,
                style={"fontSize": "11px"}),
        ]),
        html.Div(id="m-info", style={
            "position": "absolute", "top": "12px", "right": "12px",
            "width": "340px", "maxHeight": "85vh", "overflowY": "auto",
            "background": "#fff", "padding": "14px 16px", "borderRadius": "8px",
            "border": "1px solid #e5e5e5",
            "boxShadow": "0 2px 12px rgba(0,0,0,0.10)", "zIndex": 20,
            "display": "none"}),
        html.Div(id="m-stats", style={"position": "absolute",
                 "bottom": "12px", "left": "12px", "background": "#fff",
                 "padding": "8px 12px", "borderRadius": "6px",
                 "border": "1px solid #e5e5e5", "fontSize": "11px",
                 "zIndex": 20, "maxWidth": "260px"}),
    ])


# ============================== callbacks ==============================

def register_geomap_callbacks(app, cfg, index, stats, geo_aux):
    global _CFG, _PAPERS, _GEO, _STATS
    _CFG = cfg
    _PAPERS = index["papers"]
    _GEO = geo_aux
    _STATS = stats

    a_venues = set(cfg.clusters["a"].venues)
    a_col = cfg.clusters["a"].color
    b_col = cfg.clusters["b"].color

    def _aggregate(selected):
        total = Counter()
        for v in selected:
            for c, n in _GEO["venue_country"].get(v, {}).items():
                total[c] += n
        return total

    @app.callback(
        Output("m-map", "figure"), Output("m-stats", "children"),
        Input("shared-venues", "data"),
        Input("m-scale", "value"), Input("m-value", "value"),
        Input("m-minpapers", "value"), Input("m-palette", "value"),
        Input("m-proj", "value"), Input("tabs", "value"))
    def _update(selected, scale, vmode, minp, palette, proj, _tab):
        selected = list(selected or [])
        counts = _aggregate(selected)
        sel_set = set(selected)
        total_papers = with_country = 0
        for pid, p in _PAPERS.items():
            if p["venue"] in sel_set:
                total_papers += 1
                if index["affiliations"].get(pid, {}).get("countries"):
                    with_country += 1

        counts = {c: n for c, n in counts.items() if n >= (minp or 0)}

        denom = with_country or 1
        locations, z, text = [], [], []
        for c, n in counts.items():
            a3 = _a2_a3(c)
            if not a3:
                continue
            val = (n / denom * 100) if vmode == "pct" else n
            zval = math.log10(val + 1) if scale == "log" else val
            locations.append(a3)
            z.append(zval)
            pct = n / denom * 100
            text.append(f"<b>{_cname(c)}</b><br>{n} papers ({pct:.1f}%)")

        fig = go.Figure()
        # base layer: every country, so all are clickable even without data.
        # Coloured to match the land fill so it reads as "no data".
        all_a3 = _all_a3()
        data_set = set(locations)
        base_a3 = [a for a in all_a3 if a not in data_set]
        if base_a3:
            fig.add_trace(go.Choropleth(
                locations=base_a3, z=[0] * len(base_a3),
                text=[_cname_a3(a) for a in base_a3],
                hovertemplate="%{text}<br>no papers<extra></extra>",
                colorscale=[[0, "#eeeeee"], [1, "#eeeeee"]],
                showscale=False, marker_line_color="#000000",
                marker_line_width=0.5))
        # data layer on top
        fig.add_trace(go.Choropleth(
            locations=locations, z=z, text=text,
            hovertemplate="%{text}<extra></extra>", colorscale=palette,
            marker_line_color="#000000", marker_line_width=0.5,
            colorbar=_colorbar(scale, vmode, z)))
        fig.update_layout(**_geo_layout_dict(proj))

        top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
        top_str = ", ".join(f"{_cname(c)} ({n})" for c, n in top) or "-"
        cov = with_country / total_papers * 100 if total_papers else 0
        stats_div = html.Div([
            html.Div(f"Papers in selection: {total_papers}"),
            html.Div(f"With country data: {with_country} ({cov:.1f}%)",
                     style={"color": "#888"}),
            html.Div(f"Countries: {len(counts)}"),
            html.Div("Top: " + top_str, style={"fontSize": "10px",
                     "color": "#666", "marginTop": "4px"}),
        ])
        return fig, stats_div

    @app.callback(Output("m-info", "children"), Output("m-info", "style"),
                  Input("m-map", "clickData"), State("shared-venues", "data"),
                  State("m-info", "style"), prevent_initial_call=True)
    def _country(click, selected, cur):
        style = dict(cur or {})
        if not click or not click.get("points"):
            style["display"] = "none"
            return "", style
        a3 = click["points"][0].get("location")
        a2 = None
        if pycountry and a3:
            try:
                c = pycountry.countries.get(alpha_3=a3)
                a2 = c.alpha_2 if c else None
            except Exception:
                pass
        if not a2:
            style["display"] = "none"
            return "", style
        style["display"] = "block"
        selected = set(selected or [])

        cvc = _GEO["country_venue_count"].get(a2, {})
        cvp = _GEO["country_venue_papers"].get(a2, {})
        cvi = _GEO["country_venue_inst"].get(a2, {})

        venue_counts = {}
        a_n = b_n = 0
        for v, n in cvc.items():
            if v not in selected:
                continue
            venue_counts[v] = n
            if v in a_venues:
                a_n += n
            else:
                b_n += n
        total = sum(venue_counts.values())
        if total == 0:
            return html.Div([html.H3(_cname(a2), style={"fontSize": "15px"}),
                             html.P("No papers in current selection.",
                                    style={"fontSize": "12px",
                                           "color": "#888"})]), style

        inst = Counter()
        for v, insts in cvi.items():
            if v in selected:
                for name, n in insts.items():
                    inst[name] += n

        pair_counts = Counter()
        for v in selected:
            pair_counts.update(_GEO["venue_country_pairs"].get(v, {}))
        coauth = []
        for key, n in pair_counts.items():
            parts = key.split("|")
            if a2 in parts:
                other = parts[0] if parts[1] == a2 else parts[1]
                coauth.append((other, n))
        coauth.sort(key=lambda x: -x[1])

        all_pids = []
        for v, pids in cvp.items():
            if v in selected:
                all_pids.extend(pids)
        all_pids.sort(key=lambda pid: -_GEO["cit_total"].get(pid, 0))

        a_short = cfg.clusters["a"].short
        b_short = cfg.clusters["b"].short
        ch = [
            html.H3(_cname(a2), style={"fontSize": "16px", "margin": "0 0 2px",
                    "display": "inline"}),
            html.Span(a2, style={"fontSize": "11px", "color": "#fff",
                      "background": "#888", "padding": "1px 6px",
                      "borderRadius": "3px", "marginLeft": "6px"}),
            html.P(f"{total} papers · {a_short}: {a_n} · {b_short}: {b_n}",
                   style={"fontSize": "12px", "color": "#666",
                          "margin": "8px 0"}),
        ]
        if venue_counts:
            mx = max(venue_counts.values())
            ch.append(html.Div("By venue", style={"fontSize": "10px",
                      "fontWeight": "700", "color": "#888",
                      "textTransform": "uppercase", "margin": "8px 0 4px"}))
            for v, n in sorted(venue_counts.items(), key=lambda x: -x[1]):
                ch.append(html.Div(style={"display": "flex",
                    "alignItems": "center", "gap": "6px", "margin": "2px 0"},
                    children=[
                        html.Span(v.upper(), style={"fontSize": "10px",
                                  "width": "52px", "color": "#555"}),
                        html.Div(style={"flex": 1, "background": "#eee",
                            "borderRadius": "3px", "height": "10px"}, children=[
                            html.Div(style={"width": f"{n/mx*100:.0f}%",
                                "background": a_col if v in a_venues else b_col,
                                "height": "100%", "borderRadius": "3px"})]),
                        html.Span(str(n), style={"fontSize": "10px",
                                  "width": "30px", "textAlign": "right",
                                  "color": "#888"})]))
        if inst:
            ch.append(html.Div("Top institutions", style={"fontSize": "10px",
                      "fontWeight": "700", "color": "#888",
                      "textTransform": "uppercase", "margin": "12px 0 4px"}))
            for name, n in inst.most_common(10):
                ch.append(html.Div(style={"display": "flex",
                    "justifyContent": "space-between", "fontSize": "11px",
                    "padding": "2px 0", "color": "#555"}, children=[
                    html.Span(name, style={"overflow": "hidden",
                        "textOverflow": "ellipsis", "whiteSpace": "nowrap",
                        "maxWidth": "260px"}),
                    html.Strong(str(n), style={"color": "#222"})]))
        if coauth:
            ch.append(html.Div("Top co-authoring countries", style={
                "fontSize": "10px", "fontWeight": "700", "color": "#888",
                "textTransform": "uppercase", "margin": "12px 0 4px"}))
            for other, n in coauth[:5]:
                ch.append(html.Div(style={"display": "flex",
                    "justifyContent": "space-between", "fontSize": "11px",
                    "padding": "2px 0", "color": "#555"}, children=[
                    html.Span(_cname(other)),
                    html.Strong(str(n), style={"color": "#222"})]))
        ch.append(html.Div("Top papers", style={"fontSize": "10px",
                  "fontWeight": "700", "color": "#888",
                  "textTransform": "uppercase", "margin": "12px 0 4px"}))
        for pid in all_pids[:30]:
            p = _PAPERS[pid]
            col = a_col if p["cluster"] == "a" else b_col
            cit = _GEO["cit_total"].get(pid, 0)
            row = [html.Div(style={"display": "flex", "gap": "5px",
                   "alignItems": "baseline"}, children=[
                html.Span(p["venue"].upper(), style={"fontSize": "8px",
                    "fontWeight": "700", "color": "#fff", "background": col,
                    "padding": "1px 4px", "borderRadius": "2px"}),
                html.Span(f"{cit} cit", style={"fontSize": "9px",
                          "color": "#999"})]),
                html.Div(p["title"][:90] + ("..." if len(p["title"]) > 90
                         else ""), style={"fontSize": "11px", "color": "#333",
                         "lineHeight": "1.3"})]
            if p.get("url"):
                row.append(html.A("link", href=p["url"], target="_blank",
                           style={"fontSize": "9px", "color": "#1d6cc4"}))
            ch.append(html.Div(row, style={"padding": "4px 0",
                      "borderBottom": "1px solid #f0f0f0"}))
        return html.Div(ch), style

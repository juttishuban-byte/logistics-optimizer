"""
app.py
Indian Logistics Optimizer — Streamlit Interface
"""

import math
import streamlit as st
from engine import LogisticsGraph, RouteResult

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Indian Logistics Optimizer",
    page_icon="🗺",
    layout="wide",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.8rem; padding-bottom: 2rem; }

    /* Section label */
    .sec-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #94a3b8;
        margin-bottom: 0.3rem;
        margin-top: 1.1rem;
    }

    /* Route display box — dark, high-contrast */
    .route-box {
        background-color: #0f172a;
        color: #38bdf8;
        font-weight: bold;
        font-family: 'Courier New', monospace;
        font-size: 1.0rem;
        padding: 0.85rem 1.1rem;
        border-radius: 6px;
        border: 1px solid #1e293b;
        line-height: 1.7;
        word-break: break-word;
    }

    /* No-route state */
    .route-box-blocked {
        background-color: #1c0a0a;
        color: #f87171;
        font-weight: bold;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        padding: 0.85rem 1.1rem;
        border-radius: 6px;
        border: 1px solid #7f1d1d;
    }

    /* Divider */
    .hdiv { border: none; border-top: 1px solid #e2e8f0; margin: 1.4rem 0; }

    /* Suppress default table index */
    thead tr th:first-child { display: none; }
    tbody tr td:first-child  { display: none; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Graph — Indian city network
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def build_graph():
    g = LogisticsGraph()

    # (origin, dest, distance_km, risk_0_to_1, weather_ok)
    # Multiple corridors between major hubs give the risk slider real effect:
    # e.g. Delhi→Mumbai has a fast-high-risk direct route AND a safer detour.

    city_edges = [
        # ── Delhi corridors ───────────────────────────────────────────
        ("Delhi",      "Mumbai",     1400, 0.15, True),   # NH-48, reliable
        ("Delhi",      "Mumbai",     1380, 0.55, True),   # shorter but risky
        ("Delhi",      "Jaipur",      270, 0.08, True),
        ("Delhi",      "Lucknow",     555, 0.12, True),
        ("Delhi",      "Chandigarh",  260, 0.07, True),
        ("Delhi",      "Agra",        210, 0.10, True),
        ("Delhi",      "Bhopal",      780, 0.20, False),  # weather disruption

        # ── Mumbai corridors ──────────────────────────────────────────
        ("Mumbai",     "Pune",        150, 0.06, True),
        ("Mumbai",     "Ahmedabad",   530, 0.13, True),
        ("Mumbai",     "Goa",         590, 0.18, True),
        ("Mumbai",     "Nagpur",       840, 0.22, True),
        ("Mumbai",     "Hyderabad",   710, 0.30, True),
        ("Mumbai",     "Hyderabad",   730, 0.48, False),  # disrupted alternate

        # ── Bangalore corridors ───────────────────────────────────────
        ("Bangalore",  "Chennai",     350, 0.09, True),
        ("Bangalore",  "Hyderabad",   570, 0.17, True),
        ("Bangalore",  "Kochi",       530, 0.14, True),
        ("Bangalore",  "Pune",        840, 0.25, True),
        ("Bangalore",  "Mysuru",      145, 0.05, True),

        # ── Kolkata corridors ─────────────────────────────────────────
        ("Kolkata",    "Patna",       580, 0.20, True),
        ("Kolkata",    "Bhubaneswar", 440, 0.12, True),
        ("Kolkata",    "Hyderabad",  1500, 0.35, True),
        ("Kolkata",    "Delhi",      1470, 0.22, True),
        ("Kolkata",    "Guwahati",    990, 0.42, True),   # high risk NE route
        ("Kolkata",    "Guwahati",   1050, 0.18, False),  # safer but disrupted

        # ── Hyderabad corridors ───────────────────────────────────────
        ("Hyderabad",  "Chennai",     630, 0.14, True),
        ("Hyderabad",  "Nagpur",      500, 0.19, True),
        ("Hyderabad",  "Bengaluru",   570, 0.17, True),

        # ── Ahmedabad corridors ───────────────────────────────────────
        ("Ahmedabad",  "Jaipur",      660, 0.11, True),
        ("Ahmedabad",  "Surat",       270, 0.07, True),
        ("Ahmedabad",  "Bhopal",      640, 0.23, True),

        # ── Chennai corridors ─────────────────────────────────────────
        ("Chennai",    "Kochi",       700, 0.13, True),
        ("Chennai",    "Bhubaneswar", 950, 0.28, True),

        # ── Jaipur / Lucknow / Nagpur / Bhopal links ─────────────────
        ("Jaipur",     "Agra",        240, 0.09, True),
        ("Jaipur",     "Ahmedabad",   660, 0.11, True),
        ("Lucknow",    "Patna",       530, 0.16, True),
        ("Lucknow",    "Agra",        370, 0.12, True),
        ("Nagpur",     "Bhopal",      360, 0.15, True),
        ("Nagpur",     "Hyderabad",   500, 0.19, True),
        ("Bhopal",     "Agra",        500, 0.14, True),
        ("Agra",       "Lucknow",     370, 0.12, True),
        ("Surat",      "Mumbai",      280, 0.08, True),
        ("Surat",      "Ahmedabad",   270, 0.07, True),
        ("Goa",        "Bangalore",   560, 0.16, True),
        ("Kochi",      "Mysuru",      470, 0.12, True),
        ("Patna",      "Lucknow",     530, 0.16, True),
        ("Bhubaneswar","Hyderabad",   800, 0.26, True),
        ("Chandigarh", "Delhi",       260, 0.07, True),
        ("Chandigarh", "Lucknow",     700, 0.18, True),
        ("Mysuru",     "Kochi",       470, 0.12, True),
    ]

    for u, v, d, r, w in city_edges:
        g.add_edge(u, v, d, r, weather_ok=w, bidirectional=True)

    # ── Supply-chain directed edges (for DP) ──────────────────────────────────
    # Stage 0: Manufacturing Origin
    # Stage 1: Regional Warehouse
    # Stage 2: State Distribution Centre
    # Stage 3: Final Delivery Hub

    supply_edges = [
        # Origins → Regional Warehouses
        ("Origin_North", "Warehouse_A",  320, 0.08, True),
        ("Origin_North", "Warehouse_B",  280, 0.38, True),   # risky
        ("Origin_North", "Warehouse_C",  410, 0.05, True),
        ("Origin_South", "Warehouse_A",  650, 0.12, True),
        ("Origin_South", "Warehouse_B",  490, 0.10, True),
        ("Origin_South", "Warehouse_C",  380, 0.42, False),  # disrupted+risky

        # Regional Warehouses → Distribution Centres
        ("Warehouse_A",  "DistCentre_X", 220, 0.09, True),
        ("Warehouse_A",  "DistCentre_Y", 310, 0.06, True),
        ("Warehouse_B",  "DistCentre_X", 180, 0.14, False),  # disrupted
        ("Warehouse_B",  "DistCentre_Y", 240, 0.28, True),   # risky
        ("Warehouse_C",  "DistCentre_X", 290, 0.11, True),
        ("Warehouse_C",  "DistCentre_Y", 200, 0.07, True),

        # Distribution Centres → Delivery Hubs
        ("DistCentre_X", "Hub_Delhi",    150, 0.08, True),
        ("DistCentre_X", "Hub_Mumbai",   190, 0.18, True),
        ("DistCentre_X", "Hub_Kolkata",  260, 0.35, True),   # risky
        ("DistCentre_Y", "Hub_Delhi",    210, 0.05, True),
        ("DistCentre_Y", "Hub_Mumbai",   160, 0.09, True),
        ("DistCentre_Y", "Hub_Kolkata",  310, 0.11, True),
    ]

    for u, v, d, r, w in supply_edges:
        g.add_edge(u, v, d, r, weather_ok=w, bidirectional=False)

    stages = [
        ["Origin_North", "Origin_South"],
        ["Warehouse_A",  "Warehouse_B",  "Warehouse_C"],
        ["DistCentre_X", "DistCentre_Y"],
        ["Hub_Delhi",    "Hub_Mumbai",   "Hub_Kolkata"],
    ]

    return g, stages


# Sorted city list for dropdowns
CITIES = sorted([
    "Delhi", "Mumbai", "Bangalore", "Kolkata", "Hyderabad",
    "Ahmedabad", "Chennai", "Jaipur", "Lucknow", "Pune",
    "Nagpur", "Bhopal", "Surat", "Kochi", "Patna",
    "Goa", "Agra", "Chandigarh", "Bhubaneswar", "Mysuru", "Guwahati",
])


# ─────────────────────────────────────────────────────────────────────────────
# Render helpers
# ─────────────────────────────────────────────────────────────────────────────
def sec(text: str) -> None:
    st.markdown(f'<p class="sec-label">{text}</p>', unsafe_allow_html=True)


def route_box(path: list[str], blocked: bool) -> None:
    if blocked or not path:
        st.markdown(
            '<div class="route-box-blocked">'
            'No viable route under current risk and weather constraints.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        arrow = ' &nbsp;→&nbsp; '
        st.markdown(
            f'<div class="route-box">{arrow.join(path)}</div>',
            unsafe_allow_html=True,
        )


def segment_table(result: RouteResult, g: LogisticsGraph, risk_weight: float) -> None:
    """Minimalist breakdown — Segment and Cost only."""
    if not result.edges_used:
        return
    rows = []
    for e in result.edges_used:
        rows.append({
            "Segment": f"{e.source}  →  {e.destination}",
            "Distance (km)": int(e.distance),
            "Risk Score": f"{e.risk:.2f}",
            "Edge Cost": f"{g._blended_cost(e, risk_weight):.2f}",
        })
    st.table(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Indian Logistics Optimizer")
    st.markdown("---")

    st.markdown("**Point-to-Point Route**")
    start_node = st.selectbox("Origin",      CITIES, index=CITIES.index("Delhi"))
    end_node   = st.selectbox("Destination", CITIES, index=CITIES.index("Mumbai"))

    st.markdown("---")
    st.markdown("**Risk Parameters**")

    risk_weight = st.slider(
        "Risk Weight",
        min_value=0.0, max_value=1.0, value=0.30, step=0.05,
        help="How heavily risk is penalised in the blended cost calculation.",
    )
    risk_threshold = st.slider(
        "Max Allowable Risk",
        min_value=0.0, max_value=1.0, value=0.40, step=0.05,
        help="Routes exceeding this risk score are completely blocked.",
    )
    require_weather = st.checkbox("Block Weather-Disrupted Routes", value=True)

    st.markdown("---")
    run_btn = st.button("Run Optimization", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Indian Logistics Optimizer")
st.markdown(
    "Computes the safest, lowest-cost route across the Indian freight network. "
    "Adjust the risk sliders to see alternative corridors activate or deactivate in real time."
)
st.markdown('<hr class="hdiv">', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────
if run_btn:
    if start_node == end_node:
        st.warning("Origin and destination must be different cities.")
        st.stop()

    g, stages = build_graph()

    hybrid = g.get_optimized_route(
        start_node, end_node,
        risk_weight     = risk_weight,
        risk_threshold  = risk_threshold,
        require_weather = require_weather,
    )
    dp = g.get_dp_route(
        stages,
        risk_weight     = risk_weight,
        risk_threshold  = risk_threshold,
        require_weather = require_weather,
    )

    # ── Two-panel layout ──────────────────────────────────────────────────────
    col_a, spacer, col_b = st.columns([10, 0.4, 10])

    # ── Panel A : Point-to-Point ──────────────────────────────────────────────
    with col_a:
        st.markdown(f"#### Point-to-Point Route")
        st.caption(f"{start_node}  →  {end_node}")

        sec("Final Optimized Route")
        route_box(hybrid.path, hybrid.blocked)

        if not hybrid.blocked:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Cost",    f"{hybrid.total_cost:.2f}")
            c2.metric("Stops",         len(hybrid.path) - 1)
            c3.metric("Edges Removed", hybrid.filtered_count)

            sec("Segment Breakdown")
            segment_table(hybrid, g, risk_weight)
        else:
            st.caption(
                f"{hybrid.filtered_count} route(s) blocked by the current "
                "risk and weather settings. Try raising Max Allowable Risk "
                "or unchecking 'Block Weather-Disrupted Routes'."
            )

    with spacer:
        st.markdown(
            "<div style='border-left:1px solid #cbd5e1;height:520px;"
            "margin:0 auto;'></div>",
            unsafe_allow_html=True,
        )

    # ── Panel B : Multi-Stage DP ──────────────────────────────────────────────
    with col_b:
        st.markdown("#### Multi-Stage Supply Chain")
        st.caption("Origin  →  Warehouse  →  Distribution Centre  →  Hub")

        sec("Optimal Supply Chain Route")
        route_box(dp.path, dp.blocked)

        if not dp.blocked:
            c1, c2 = st.columns(2)
            c1.metric("Total Cost", f"{dp.total_cost:.2f}")
            c2.metric("Stages",     len(stages))

            sec("Segment Breakdown")
            segment_table(dp, g, risk_weight)
        else:
            st.caption(
                f"{dp.filtered_count} supply-chain route(s) blocked. "
                "Raise Max Allowable Risk or unblock weather routes to restore connectivity."
            )

    st.markdown('<hr class="hdiv">', unsafe_allow_html=True)

    # ── Summary table ─────────────────────────────────────────────────────────
    sec("Comparison Summary")
    costs = [r.total_cost for r in [hybrid, dp] if not r.blocked]
    g_min = min(costs) if costs else math.inf

    def verdict(r: RouteResult) -> str:
        if r.blocked:
            return "Blocked — no valid route"
        if r.total_cost == g_min:
            return "Lowest cost"
        return f"+{r.total_cost - g_min:.2f} above minimum"

    st.table([
        {
            "Optimization Type": "Point-to-Point Route",
            "Route": "  →  ".join(hybrid.path) if hybrid.path else "—",
            "Total Cost": f"{hybrid.total_cost:.2f}" if not hybrid.blocked else "—",
            "Edges Blocked": hybrid.filtered_count,
            "Status": verdict(hybrid),
        },
        {
            "Optimization Type": "Multi-Stage Supply Chain",
            "Route": "  →  ".join(dp.path) if dp.path else "—",
            "Total Cost": f"{dp.total_cost:.2f}" if not dp.blocked else "—",
            "Edges Blocked": dp.filtered_count,
            "Status": verdict(dp),
        },
    ])

# ─────────────────────────────────────────────────────────────────────────────
# Landing state
# ─────────────────────────────────────────────────────────────────────────────
else:
    if start_node == end_node:
        st.warning("Origin and destination must be different cities.")
    else:
        st.markdown("Configure the inputs in the sidebar and click **Run Optimization**.")

    st.markdown("")
    sec("Network Coverage")
    st.table([
        {"City / Node": c, "Role": "Freight Hub"}
        for c in CITIES
    ])
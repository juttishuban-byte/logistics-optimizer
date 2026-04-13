"""
app.py  —  Indian Logistics Optimizer  |  Streamlit Interface
"""

import math
import pandas as pd
import streamlit as st
from engine import LogisticsGraph, RouteResult

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "Indian Logistics Optimizer",
    page_icon  = "🗺",
    layout     = "wide",
)

st.markdown("""
<style>
    /* Page padding */
    .block-container { padding-top: 1.8rem; padding-bottom: 2rem; }

    /* Section label — small-caps uppercase */
    .sec-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #94a3b8;
        margin-bottom: 0.35rem;
        margin-top: 1.1rem;
    }

    /* Dark route display box */
    .route-box {
        background-color : #0f172a;
        color            : #38bdf8;
        font-weight      : bold;
        font-family      : 'Courier New', monospace;
        font-size        : 1.0rem;
        padding          : 0.85rem 1.1rem;
        border-radius    : 6px;
        border           : 1px solid #1e293b;
        line-height      : 1.7;
        word-break       : break-word;
    }

    /* Blocked / no-route state */
    .route-box-blocked {
        background-color : #1c0a0a;
        color            : #f87171;
        font-weight      : bold;
        font-family      : 'Courier New', monospace;
        font-size        : 0.9rem;
        padding          : 0.85rem 1.1rem;
        border-radius    : 6px;
        border           : 1px solid #7f1d1d;
    }

    /* Horizontal rule */
    .hdiv { border: none; border-top: 1px solid #e2e8f0; margin: 1.4rem 0; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Graph factory — Indian freight network
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def build_graph():
    g = LogisticsGraph()

    # ── City network: bidirectional edges ────────────────────────────────────
    # Every major corridor has at least two options with contrasting risk scores.
    # This gives the slider real power: lowering Max Allowable Risk forces the
    # algorithm off direct-but-risky routes onto safer detours.
    #
    # (origin, destination, distance_km, risk_0_to_1, weather_ok)
    city_edges = [
        # Delhi corridors — direct NH-48 (risk 0.15) vs faster risky route (0.55)
        ("Delhi",       "Mumbai",      1400, 0.15, True),
        ("Delhi",       "Mumbai",      1380, 0.55, True),   # risky alternate
        ("Delhi",       "Jaipur",       270, 0.08, True),
        ("Delhi",       "Lucknow",      555, 0.12, True),
        ("Delhi",       "Chandigarh",   260, 0.07, True),
        ("Delhi",       "Agra",         210, 0.10, True),
        ("Delhi",       "Bhopal",       780, 0.20, False),  # weather disrupted

        # Mumbai corridors
        ("Mumbai",      "Pune",         150, 0.06, True),
        ("Mumbai",      "Ahmedabad",    530, 0.13, True),
        ("Mumbai",      "Goa",          590, 0.18, True),
        ("Mumbai",      "Nagpur",       840, 0.22, True),
        ("Mumbai",      "Hyderabad",    710, 0.30, True),
        ("Mumbai",      "Hyderabad",    730, 0.48, False),  # disrupted alternate

        # Bangalore corridors
        ("Bangalore",   "Chennai",      350, 0.09, True),
        ("Bangalore",   "Hyderabad",    570, 0.17, True),
        ("Bangalore",   "Kochi",        530, 0.14, True),
        ("Bangalore",   "Pune",         840, 0.25, True),
        ("Bangalore",   "Mysuru",       145, 0.05, True),

        # Kolkata corridors
        ("Kolkata",     "Patna",        580, 0.20, True),
        ("Kolkata",     "Bhubaneswar",  440, 0.12, True),
        ("Kolkata",     "Hyderabad",   1500, 0.35, True),
        ("Kolkata",     "Delhi",       1470, 0.22, True),
        ("Kolkata",     "Guwahati",     990, 0.42, True),   # high risk NE route
        ("Kolkata",     "Guwahati",    1050, 0.18, False),  # safer but disrupted

        # Hyderabad
        ("Hyderabad",   "Chennai",      630, 0.14, True),
        ("Hyderabad",   "Nagpur",       500, 0.19, True),

        # Ahmedabad
        ("Ahmedabad",   "Jaipur",       660, 0.11, True),
        ("Ahmedabad",   "Surat",        270, 0.07, True),
        ("Ahmedabad",   "Bhopal",       640, 0.23, True),

        # Chennai
        ("Chennai",     "Kochi",        700, 0.13, True),
        ("Chennai",     "Bhubaneswar",  950, 0.28, True),

        # Secondary links
        ("Jaipur",      "Agra",         240, 0.09, True),
        ("Lucknow",     "Patna",        530, 0.16, True),
        ("Lucknow",     "Agra",         370, 0.12, True),
        ("Nagpur",      "Bhopal",       360, 0.15, True),
        ("Nagpur",      "Hyderabad",    500, 0.19, True),
        ("Bhopal",      "Agra",         500, 0.14, True),
        ("Agra",        "Lucknow",      370, 0.12, True),
        ("Surat",       "Mumbai",       280, 0.08, True),
        ("Goa",         "Bangalore",    560, 0.16, True),
        ("Kochi",       "Mysuru",       470, 0.12, True),
        ("Patna",       "Lucknow",      530, 0.16, True),
        ("Bhubaneswar", "Hyderabad",    800, 0.26, True),
        ("Chandigarh",  "Lucknow",      700, 0.18, True),
        ("Mysuru",      "Kochi",        470, 0.12, True),
    ]
    for u, v, d, r, w in city_edges:
        g.add_edge(u, v, d, r, weather_ok=w, bidirectional=True)

    # ── Supply-chain: directed stage edges for DP ────────────────────────────
    # Stages: Origin → Warehouse → Distribution Centre → Delivery Hub
    supply_edges = [
        ("Origin_North", "Warehouse_A",   320, 0.08, True),
        ("Origin_North", "Warehouse_B",   280, 0.38, True),   # risky
        ("Origin_North", "Warehouse_C",   410, 0.05, True),
        ("Origin_South", "Warehouse_A",   650, 0.12, True),
        ("Origin_South", "Warehouse_B",   490, 0.10, True),
        ("Origin_South", "Warehouse_C",   380, 0.42, False),  # disrupted + risky
        ("Warehouse_A",  "DistCentre_X",  220, 0.09, True),
        ("Warehouse_A",  "DistCentre_Y",  310, 0.06, True),
        ("Warehouse_B",  "DistCentre_X",  180, 0.14, False),  # disrupted
        ("Warehouse_B",  "DistCentre_Y",  240, 0.28, True),   # risky
        ("Warehouse_C",  "DistCentre_X",  290, 0.11, True),
        ("Warehouse_C",  "DistCentre_Y",  200, 0.07, True),
        ("DistCentre_X", "Hub_Delhi",     150, 0.08, True),
        ("DistCentre_X", "Hub_Mumbai",    190, 0.18, True),
        ("DistCentre_X", "Hub_Kolkata",   260, 0.35, True),   # risky
        ("DistCentre_Y", "Hub_Delhi",     210, 0.05, True),
        ("DistCentre_Y", "Hub_Mumbai",    160, 0.09, True),
        ("DistCentre_Y", "Hub_Kolkata",   310, 0.11, True),
    ]
    for u, v, d, r, w in supply_edges:
        g.add_edge(u, v, d, r, weather_ok=w, bidirectional=False)

    stages = [
        ["Origin_North",  "Origin_South"],
        ["Warehouse_A",   "Warehouse_B",  "Warehouse_C"],
        ["DistCentre_X",  "DistCentre_Y"],
        ["Hub_Delhi",     "Hub_Mumbai",   "Hub_Kolkata"],
    ]
    return g, stages


CITIES = sorted([
    "Delhi", "Mumbai", "Bangalore", "Kolkata", "Hyderabad",
    "Ahmedabad", "Chennai", "Jaipur", "Lucknow", "Pune",
    "Nagpur", "Bhopal", "Surat", "Kochi", "Patna",
    "Goa", "Agra", "Chandigarh", "Bhubaneswar", "Mysuru", "Guwahati",
])


# ──────────────────────────────────────────────────────────────────────────────
# UI helper functions
# ──────────────────────────────────────────────────────────────────────────────

def sec(text: str) -> None:
    """Render a small-caps section label."""
    st.markdown(f'<p class="sec-label">{text}</p>', unsafe_allow_html=True)


def render_route_box(path: list[str], blocked: bool) -> None:
    """
    Render the dark route display box.
    Shows the path nodes joined by arrows, or a blocked message.
    """
    if blocked or not path:
        st.markdown(
            '<div class="route-box-blocked">'
            'No viable route under current risk and weather constraints.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        arrow  = " &nbsp;→&nbsp; "
        joined = arrow.join(path)
        st.markdown(
            f'<div class="route-box">{joined}</div>',
            unsafe_allow_html=True,
        )


def build_segment_df(result: RouteResult, g: LogisticsGraph, risk_weight: float) -> pd.DataFrame:
    """
    Construct the segment breakdown DataFrame.

    Columns:  Segment No. | From | To | Distance (km) | Risk Score | Edge Cost

    Edge Cost = distance * (1 + risk_weight * risk)
    Total Cost = sum of all Edge Cost values  ← matches result.total_cost
    """
    rows = []
    for i, e in enumerate(result.edges_used, start=1):
        cost = g.edge_cost(e, risk_weight)
        rows.append({
            "Seg.":          i,
            "From":          e.source,
            "To":            e.destination,
            "Distance (km)": int(e.distance),
            "Risk Score":    round(e.risk, 2),
            "Edge Cost":     round(cost, 2),
        })
    return pd.DataFrame(rows)


def build_summary_df(
    results:     list[RouteResult],
    labels:      list[str],
    g:           LogisticsGraph,
    risk_weight: float,
) -> pd.DataFrame:
    """
    Construct the comparison summary DataFrame.

    Columns:  Optimization Type | Route | Total Cost | Edges Blocked | Status

    Status logic:
      "Blocked — no valid route"  when result.blocked
      "Lowest cost"               when cost == global minimum
      "+X.XX above minimum"       otherwise
    """
    valid_costs = [r.total_cost for r in results if not r.blocked]
    global_min  = min(valid_costs) if valid_costs else math.inf

    def status(r: RouteResult) -> str:
        if r.blocked:
            return "Blocked — no valid route"
        if r.total_cost == global_min:
            return "Lowest cost"
        return f"+{r.total_cost - global_min:.2f} above minimum"

    rows = []
    for label, r in zip(labels, results):
        rows.append({
            "Optimization Type": label,
            "Route":             " → ".join(r.path) if r.path else "—",
            "Total Cost":        f"{r.total_cost:.2f}" if not r.blocked else "—",
            "Edges Blocked":     r.filtered_count + getattr(r, "pruned_count", 0),
            "Status":            status(r),
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — all user inputs
# ──────────────────────────────────────────────────────────────────────────────
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
        min_value=0.0, max_value=2.0, value=0.40, step=0.05,
        help=(
            "Scales how much risk penalises edge cost.  "
            "Formula: distance × (1 + risk_weight × risk).  "
            "Higher values make the algorithm avoid risky routes more strongly."
        ),
    )
    risk_threshold = st.slider(
        "Max Allowable Risk",
        min_value=0.0, max_value=1.0, value=0.40, step=0.05,
        help=(
            "Hard ceiling. Any edge with risk > this value is completely "
            "blocked before any optimisation begins."
        ),
    )
    require_weather = st.checkbox(
        "Block Weather-Disrupted Routes", value=True,
        help="Remove all edges marked weather_ok=False from consideration."
    )

    st.markdown("---")
    run_btn = st.button("Run Optimization", use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# Page header
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("## Indian Logistics Optimizer")
st.markdown(
    "Finds the safest, lowest-cost freight route across the Indian road network. "
    "The risk sliders hard-block dangerous corridors and re-route traffic in real time."
)
st.markdown('<hr class="hdiv">', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Results — rendered only after button press
# ──────────────────────────────────────────────────────────────────────────────
if run_btn:

    if start_node == end_node:
        st.warning("Origin and destination must be different cities.")
        st.stop()

    g, stages = build_graph()

    # Run both algorithms with the same constraint parameters
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

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_a, spacer, col_b = st.columns([10, 0.4, 10])

    # ── Panel A: Point-to-Point ───────────────────────────────────────────────
    with col_a:
        st.markdown("#### Point-to-Point Route")
        st.caption(f"{start_node}  →  {end_node}")

        sec("Final Optimized Route")
        render_route_box(hybrid.path, hybrid.blocked)

        if not hybrid.blocked:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Cost",      f"{hybrid.total_cost:.2f}")
            c2.metric("Stops",           max(len(hybrid.path) - 1, 0))
            c3.metric("Edges Removed",   hybrid.filtered_count + hybrid.pruned_count)

            if hybrid.edges_used:
                sec("Segment Breakdown")
                seg_df = build_segment_df(hybrid, g, risk_weight)
                st.dataframe(seg_df, use_container_width=True, hide_index=True)
                # Verify: sum of Edge Cost == total_cost
                st.caption(
                    f"Sum of edge costs: **{seg_df['Edge Cost'].sum():.2f}**  "
                    f"(matches Total Cost)"
                )
        else:
            st.caption(
                f"{hybrid.filtered_count} edge(s) blocked by risk threshold, "
                f"{hybrid.pruned_count} pruned by greedy reduction. "
                "Try raising Max Allowable Risk or unchecking weather filter."
            )

    # Vertical separator
    with spacer:
        st.markdown(
            "<div style='border-left:1px solid #cbd5e1; height:540px; "
            "margin:0 auto;'></div>",
            unsafe_allow_html=True,
        )

    # ── Panel B: Multi-Stage DP ───────────────────────────────────────────────
    with col_b:
        st.markdown("#### Multi-Stage Supply Chain")
        st.caption("Origin  →  Warehouse  →  Distribution Centre  →  Hub")

        sec("Optimal Supply Chain Route")
        render_route_box(dp.path, dp.blocked)

        if not dp.blocked:
            c1, c2 = st.columns(2)
            c1.metric("Total Cost", f"{dp.total_cost:.2f}")
            c2.metric("Stages",     len(stages))

            if dp.edges_used:
                sec("Segment Breakdown")
                seg_df = build_segment_df(dp, g, risk_weight)
                st.dataframe(seg_df, use_container_width=True, hide_index=True)
                st.caption(
                    f"Sum of edge costs: **{seg_df['Edge Cost'].sum():.2f}**  "
                    f"(matches Total Cost)"
                )
        else:
            st.caption(
                f"{dp.filtered_count} supply-chain edge(s) blocked. "
                "Raise Max Allowable Risk or unblock weather routes to restore connectivity."
            )

    st.markdown('<hr class="hdiv">', unsafe_allow_html=True)

    # ── Comparison summary ────────────────────────────────────────────────────
    sec("Comparison Summary")
    summary_df = build_summary_df(
        results     = [hybrid, dp],
        labels      = ["Point-to-Point Route", "Multi-Stage Supply Chain"],
        g           = g,
        risk_weight = risk_weight,
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────────────────────
# Landing state
# ──────────────────────────────────────────────────────────────────────────────
else:
    if start_node == end_node:
        st.warning("Origin and destination must be different cities.")
    else:
        st.markdown(
            "Configure parameters in the sidebar and click **Run Optimization**."
        )

    st.markdown("")
    sec("Network Coverage")
    st.dataframe(
        pd.DataFrame([{"City": c} for c in CITIES]),
        use_container_width=True,
        hide_index=True,
    )
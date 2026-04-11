"""
app.py — Risk-Aware Logistics Optimizer · Streamlit UI
Matches the LogisticsGraph API in engine.py
"""

import math
import time
import streamlit as st
from engine import LogisticsGraph

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Risk-Aware Logistics Optimizer",
    page_icon="🚚",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Graph definition
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def build_graph() -> tuple[LogisticsGraph, list[list[str]]]:
    """
    Builds a demo supply-chain graph.

    General graph (for Dijkstra / Greedy)
    ──────────────────────────────────────
    Cities: Mumbai, Delhi, Chennai, Kolkata, Pune, Ahmedabad

    Multi-stage graph (for DP)
    ──────────────────────────
    Factory → Port → Hub → Customer
    """
    g = LogisticsGraph()

    # ── General city network (bidirectional) ─────────────────────────────────
    city_edges = [
        ("Mumbai",     "Delhi",      1400, 0.15),
        ("Mumbai",     "Pune",        150, 0.05),
        ("Mumbai",     "Ahmedabad",   530, 0.12),
        ("Delhi",      "Kolkata",    1300, 0.20),
        ("Delhi",      "Ahmedabad",   900, 0.18),
        ("Chennai",    "Kolkata",    1650, 0.25),
        ("Chennai",    "Pune",        840, 0.10),
        ("Kolkata",    "Pune",       1800, 0.30),
        ("Pune",       "Ahmedabad",   665, 0.08),
        ("Ahmedabad",  "Delhi",       900, 0.14),
    ]
    for u, v, d, r in city_edges:
        g.add_edge(u, v, d, r, bidirectional=True)

    # ── Multi-stage supply-chain edges (directed) ────────────────────────────
    supply_edges = [
        ("Factory", "Port_A",    320, 0.10),
        ("Factory", "Port_B",    280, 0.35),
        ("Factory", "Port_C",    410, 0.05),
        ("Port_A",  "Hub_X",     150, 0.20),
        ("Port_A",  "Hub_Y",     200, 0.08),
        ("Port_B",  "Hub_X",     130, 0.15),
        ("Port_B",  "Hub_Y",     170, 0.25),
        ("Port_C",  "Hub_X",     220, 0.12),
        ("Port_C",  "Hub_Y",     180, 0.07),
        ("Hub_X",   "Customer",   90, 0.18),
        ("Hub_Y",   "Customer",  110, 0.06),
    ]
    for u, v, d, r in supply_edges:
        g.add_edge(u, v, d, r, bidirectional=False)

    stages = [
        ["Factory"],
        ["Port_A", "Port_B", "Port_C"],
        ["Hub_X",  "Hub_Y"],
        ["Customer"],
    ]
    return g, stages


CITY_NODES = ["Mumbai", "Delhi", "Chennai", "Kolkata", "Pune", "Ahmedabad"]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def fmt_path(path):
    return " → ".join(path) if path else "No path found"

def run_timed(fn):
    t0 = time.perf_counter()
    path, cost = fn()
    ms = (time.perf_counter() - t0) * 1_000
    return path, cost, ms

def edge_breakdown(g, path, risk_weight):
    rows = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        for nbr, d, r in g.graph.get(u, []):
            if nbr == v:
                ec = g._edge_cost(d, r, risk_weight)
                rows.append({
                    "Leg":        f"{u} → {v}",
                    "Dist (km)":  d,
                    "Risk":       r,
                    "Edge Cost":  f"{ec:.2f}",
                })
                break
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Controls")
    st.markdown("---")

    st.subheader("🗺️ Route  (Dijkstra & Greedy)")
    start_node = st.selectbox("Start City", CITY_NODES, index=0)
    end_node   = st.selectbox("End City",   CITY_NODES, index=1)
    if start_node == end_node:
        st.warning("Start and End must differ.")

    st.markdown("---")

    st.subheader("⚖️ Risk / Cost Blending")
    risk_weight = st.slider(
        "Risk Weight  (w)",
        min_value=0.0, max_value=1.0, value=0.3, step=0.05,
        help="Blended edge cost = dist×(1−w) + risk×w×100",
    )
    cl, cr = st.columns(2)
    cl.metric("Distance wt.", f"{1 - risk_weight:.2f}")
    cr.metric("Risk wt.",     f"{risk_weight:.2f}")

    st.markdown("---")
    run_btn = st.button("🚀 Run Optimisation", use_container_width=True)

    st.markdown("---")
    with st.expander("📐 Cost formula"):
        st.latex(r"\text{cost} = d\,(1{-}w) + r\,w\,\times\,100")

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────
st.title("🚚 Risk-Aware Logistics Optimizer")
st.markdown(
    "Compare **Dijkstra**, **Greedy**, and **Multi-Stage DP** on a shared "
    "logistics graph — paths, costs, and execution time in one view."
)
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Main output  (only after button press)
# ─────────────────────────────────────────────────────────────────────────────
if run_btn and start_node != end_node:

    g, stages = build_graph()

    # Run all three algorithms
    dijk_path, dijk_cost, dijk_ms = run_timed(
        lambda: g.get_dijkstra(start_node, end_node, risk_weight)
    )
    grdy_path, grdy_cost, grdy_ms = run_timed(
        lambda: g.get_greedy(start_node, end_node, risk_weight)
    )
    dp_path, dp_cost, dp_ms = run_timed(
        lambda: g.get_dp(stages, risk_weight)
    )

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 1 — Dijkstra vs Greedy side-by-side
    # ═════════════════════════════════════════════════════════════════════════
    st.subheader("⚔️ Dijkstra  vs  Greedy")
    st.caption(f"Route: **{start_node}** → **{end_node}**   |   w = **{risk_weight}**")

    col_d, col_gap, col_g = st.columns([5, 0.25, 5])

    # ── Dijkstra ─────────────────────────────────────────────────────────────
    with col_d:
        st.markdown("### 🔵 Dijkstra")
        st.caption("Exact global optimum — O((V+E) log V)")
        if dijk_path:
            st.success(f"**Path:** {fmt_path(dijk_path)}")
            m1, m2 = st.columns(2)
            m1.metric("Total Cost", f"{dijk_cost:.4f}")
            m2.metric("Time",       f"{dijk_ms:.3f} ms")
            with st.expander("Edge breakdown"):
                st.table(edge_breakdown(g, dijk_path, risk_weight))
        else:
            st.error("No path found.")

    with col_gap:
        st.markdown(
            "<div style='border-left:2px solid #e0e0e0;height:250px;"
            "margin:0 auto'></div>",
            unsafe_allow_html=True,
        )

    # ── Greedy ───────────────────────────────────────────────────────────────
    with col_g:
        st.markdown("### 🟠 Greedy")
        st.caption("Myopic nearest-neighbour — may be sub-optimal")
        if grdy_path:
            st.success(f"**Path:** {fmt_path(grdy_path)}")
            m1, m2 = st.columns(2)
            delta_val = (
                f"+{grdy_cost - dijk_cost:.4f} vs Dijkstra"
                if grdy_cost != math.inf and dijk_cost != math.inf
                else None
            )
            m1.metric("Total Cost", f"{grdy_cost:.4f}",
                      delta=delta_val, delta_color="inverse")
            m2.metric("Time", f"{grdy_ms:.3f} ms")
            with st.expander("Edge breakdown"):
                st.table(edge_breakdown(g, grdy_path, risk_weight))
        else:
            st.error("No path found — greedy hit a dead end.")

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 2 — Multi-Stage DP
    # ═════════════════════════════════════════════════════════════════════════
    st.subheader("🏭 Multi-Stage Dynamic Programming")
    st.caption(
        "Fixed supply-chain:  **Factory → Port (A / B / C) → Hub (X / Y) → Customer**"
    )

    # Stage visualiser — highlight nodes on the optimal path
    stage_labels = ["🏭 Factory", "⚓ Port", "📦 Hub", "🏠 Customer"]
    stage_cols   = st.columns(len(stages))
    for sc, label, stage in zip(stage_cols, stage_labels, stages):
        with sc:
            st.markdown(f"**{label}**")
            for node in stage:
                on_path = dp_path and node in dp_path
                st.markdown(f"{'🟢' if on_path else '⚪'} `{node}`")

    st.markdown("")

    if dp_path:
        st.success(f"**Optimal path:** {fmt_path(dp_path)}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Cost", f"{dp_cost:.4f}")
        m2.metric("Stages",     len(stages))
        m3.metric("Time",       f"{dp_ms:.3f} ms")
        with st.expander("Edge breakdown (supply chain)"):
            st.table(edge_breakdown(g, dp_path, risk_weight))
    else:
        st.error("DP found no valid path through the supply-chain stages.")

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 3 — Comparison Table  (st.table)
    # ═════════════════════════════════════════════════════════════════════════
    st.subheader("📊 Comparison Table")

    valid_costs = [c for c in [dijk_cost, grdy_cost, dp_cost] if c != math.inf]
    global_best = min(valid_costs) if valid_costs else math.inf

    def optimum_tag(cost):
        if cost == math.inf:
            return "❌ No path"
        if cost == global_best:
            return "✅ Global optimum"
        pct = (cost - global_best) / global_best * 100
        return f"⚠️  +{pct:.1f}% vs best"

    st.table([
        {
            "Algorithm":     "Dijkstra",
            "Route":         f"{start_node} → {end_node}",
            "Path":          fmt_path(dijk_path),
            "Total Cost":    f"{dijk_cost:.4f}" if dijk_cost != math.inf else "∞",
            "Time (ms)":     f"{dijk_ms:.3f}",
            "Global Opt?":   optimum_tag(dijk_cost),
        },
        {
            "Algorithm":     "Greedy",
            "Route":         f"{start_node} → {end_node}",
            "Path":          fmt_path(grdy_path),
            "Total Cost":    f"{grdy_cost:.4f}" if grdy_cost != math.inf else "∞",
            "Time (ms)":     f"{grdy_ms:.3f}",
            "Global Opt?":   optimum_tag(grdy_cost),
        },
        {
            "Algorithm":     "Multi-Stage DP",
            "Route":         "Factory → Customer",
            "Path":          fmt_path(dp_path),
            "Total Cost":    f"{dp_cost:.4f}" if dp_cost != math.inf else "∞",
            "Time (ms)":     f"{dp_ms:.3f}",
            "Global Opt?":   optimum_tag(dp_cost),
        },
    ])

    if global_best != math.inf:
        st.info(f"🏆 **Lowest cost across all algorithms:** `{global_best:.4f}`")

# ─────────────────────────────────────────────────────────────────────────────
# Landing / guard states
# ─────────────────────────────────────────────────────────────────────────────
elif not run_btn:
    st.info(
        "👈  Pick a route and risk weight in the sidebar, "
        "then click **Run Optimisation**."
    )
    with st.expander("ℹ️ Algorithm reference", expanded=True):
        st.markdown("""
| Algorithm | Optimality | Complexity | Best for |
|---|---|---|---|
| **Dijkstra** | ✅ Global optimum | O((V+E) log V) | Any graph, accuracy critical |
| **Greedy** | ⚠️ Local optimum only | O(V·E) | Fast approximation |
| **Multi-Stage DP** | ✅ Global optimum (within stages) | O(S·N²) | Layered supply-chain networks |

Edge cost formula applied uniformly:

$$\\text{cost} = dist \\times (1 - w) \\;+\\; risk \\times w \\times 100$$
        """)

elif start_node == end_node:
    st.warning("⚠️  Start and End cities must be different — update the sidebar.")
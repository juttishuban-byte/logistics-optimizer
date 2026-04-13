"""
engine.py  —  Indian Logistics Optimizer  |  Core Engine
=========================================================

Algorithm architecture
-----------------------
get_optimized_route():
  Phase 1  FEASIBILITY FILTER
           Hard-block edges that exceed max_risk or are weather-disrupted.
           This is the constraint layer — no blocked edge can ever appear
           in the final route regardless of cost.

  Phase 2  GREEDY CORRIDOR REDUCTION
           For every node in the feasible graph, keep only the
           `top_k_per_node` safest outgoing edges (sorted by risk ASC,
           distance ASC as tie-breaker).  This simulates a logistics
           planner who, at each city, short-lists the safest onward
           corridors before handing the reduced graph to a solver.

  Phase 3  DIJKSTRA ON REDUCED GRAPH
           Exact shortest-path on the greedy-pruned edge set.
           Edge cost formula:  distance * (1 + risk_weight * risk)
           This penalises risky edges proportionally — a risk=0.5 edge
           with risk_weight=0.4 costs 20% more than the raw distance.

get_dp_route():
  Applies the same feasibility filter, then solves a multi-stage
  supply-chain problem using bottom-up Dynamic Programming.
  Recurrence:  cost(i,j) = min_k { cost(i-1,k) + c(k,j) }
  Path is reconstructed from a Stack (LIFO).
"""

import heapq
import math
from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
# Core data types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Edge:
    """One directed edge in the Edge List."""
    source:      str
    destination: str
    distance:    float       # kilometres
    risk:        float       # 0.0 – 1.0  (higher = more hazardous)
    weather_ok:  bool = True  # False = route is currently disrupted


@dataclass
class RouteResult:
    """Unified return type for every algorithm."""
    path:           list[str]
    total_cost:     float
    edges_used:     list[Edge] = field(default_factory=list)
    filtered_count: int  = 0    # edges removed during feasibility filter
    pruned_count:   int  = 0    # additional edges removed by greedy pruning
    blocked:        bool = False # True when no path exists under constraints


# ──────────────────────────────────────────────────────────────────────────────
# LogisticsGraph
# ──────────────────────────────────────────────────────────────────────────────

class LogisticsGraph:
    """
    Directed weighted graph for logistics optimisation.

    Internals
    ---------
    edge_list : list[Edge]   — canonical Edge List (single source of truth)
    nodes     : list[str]    — insertion-ordered node registry
    """

    def __init__(self):
        self.edge_list: list[Edge] = []
        self.nodes:     list[str]  = []

    # ── Graph construction ────────────────────────────────────────────────────

    def add_node(self, name: str) -> None:
        if name not in self.nodes:
            self.nodes.append(name)

    def add_edge(
        self,
        source: str, destination: str,
        distance: float, risk: float,
        weather_ok: bool = True,
        bidirectional: bool = True,
    ) -> None:
        self.add_node(source)
        self.add_node(destination)
        self.edge_list.append(Edge(source, destination, distance, risk, weather_ok))
        if bidirectional:
            self.edge_list.append(Edge(destination, source, distance, risk, weather_ok))

    # ── Cost formula ──────────────────────────────────────────────────────────

    @staticmethod
    def edge_cost(edge: Edge, risk_weight: float) -> float:
        """
        Intuitive penalty formula:
            cost = distance * (1 + risk_weight * risk)

        Examples with risk_weight = 0.4:
          risk=0.0  → cost = distance * 1.00   (no penalty)
          risk=0.5  → cost = distance * 1.20   (+20%)
          risk=1.0  → cost = distance * 1.40   (+40%)
        """
        return edge.distance * (1.0 + risk_weight * edge.risk)

    # ── Shared helper: feasibility filter ────────────────────────────────────

    def _feasible_edges(
        self,
        risk_threshold: float,
        require_weather: bool,
    ) -> tuple[list[Edge], int]:
        """
        Hard-block edges that violate operational constraints:
          • risk > risk_threshold  → always blocked
          • weather_ok == False    → blocked when require_weather is True

        Returns (surviving_edges, removed_count).
        This is the first pass in both the Dijkstra pipeline and the DP pipeline.
        """
        surviving, removed = [], 0
        for e in self.edge_list:
            if e.risk > risk_threshold:
                removed += 1
                continue
            if require_weather and not e.weather_ok:
                removed += 1
                continue
            surviving.append(e)
        return surviving, removed

    # ── Shared helper: greedy corridor reduction ──────────────────────────────

    @staticmethod
    def _greedy_reduce(
        edges: list[Edge],
        top_k: int,
    ) -> tuple[list[Edge], int]:
        """
        Greedy preprocessing: for every source node, retain only the
        `top_k` safest outgoing edges.

        Sorting key: (risk ASC, distance ASC)
          — prioritise safety first, break ties by shorter distance.

        This mimics a logistics planner who, at each city, short-lists the
        best corridors before committing to a full route calculation.

        Returns (reduced_edges, pruned_count).
        """
        # Group outgoing edges by source node
        by_source: dict[str, list[Edge]] = {}
        for e in edges:
            by_source.setdefault(e.source, []).append(e)

        kept, pruned = [], 0
        for src, outgoing in by_source.items():
            # Sort: safest first, shorter distance as tie-breaker
            ranked = sorted(outgoing, key=lambda e: (e.risk, e.distance))
            selected = ranked[:top_k]
            dropped  = len(ranked) - len(selected)
            kept.extend(selected)
            pruned += dropped

        return kept, pruned

    # ── Shared helper: adjacency map ─────────────────────────────────────────

    @staticmethod
    def _build_adj(
        nodes: list[str],
        edges: list[Edge],
    ) -> dict[str, list[tuple[str, Edge]]]:
        """Build {source: [(destination, edge), ...]} from an edge list."""
        adj: dict[str, list[tuple[str, Edge]]] = {n: [] for n in nodes}
        for e in edges:
            adj.setdefault(e.source, []).append((e.destination, e))
        return adj

    # ──────────────────────────────────────────────────────────────────────────
    # Algorithm 1 — Greedy Preprocessing + Dijkstra
    # ──────────────────────────────────────────────────────────────────────────

    def get_optimized_route(
        self,
        start:           str,
        end:             str,
        risk_weight:     float = 0.30,
        risk_threshold:  float = 0.40,
        require_weather: bool  = True,
        top_k_per_node:  int   = 3,
    ) -> RouteResult:
        """
        Three-phase point-to-point optimisation.

        Phase 1 — Feasibility filter
            Removes all edges that violate hard constraints
            (risk > threshold, or weather-disrupted if flag is set).

        Phase 2 — Greedy corridor reduction
            For each node in the feasible graph, retains only the
            `top_k_per_node` safest outgoing edges (risk ASC, dist ASC).
            This reduces the search space and enforces risk-aware routing.

        Phase 3 — Dijkstra on the greedy-reduced graph
            Finds the exact shortest path by accumulated edge cost.
            Edge cost formula:  distance * (1 + risk_weight * risk)

        Data structures:  Edge List → Array (distances) → Priority Queue
        """
        INF = math.inf

        # ── Phase 1: hard feasibility filter ─────────────────────────────────
        feasible, filtered_count = self._feasible_edges(risk_threshold, require_weather)

        # ── Phase 2: greedy per-node corridor reduction ───────────────────────
        reduced, pruned_count = self._greedy_reduce(feasible, top_k=top_k_per_node)

        # ── Phase 3: Dijkstra on the reduced graph ────────────────────────────
        adj       = self._build_adj(self.nodes, reduced)
        node_idx  = {n: i for i, n in enumerate(self.nodes)}
        src_i     = node_idx.get(start)
        dst_i     = node_idx.get(end)

        if src_i is None or dst_i is None:
            return RouteResult([], INF,
                               filtered_count=filtered_count,
                               pruned_count=pruned_count,
                               blocked=True)

        # Distance array — one slot per node, indexed by position
        dist: list[float]       = [INF]  * len(self.nodes)
        prev: list[str | None]  = [None] * len(self.nodes)
        dist[src_i] = 0.0

        # Priority queue: (accumulated_cost, node_name)
        pq: list[tuple[float, str]] = []
        heapq.heappush(pq, (0.0, start))

        # Track which edge was used to reach each (u→v) pair for reconstruction
        edge_used: dict[tuple[str, str], Edge] = {}

        while pq:
            cur_cost, u = heapq.heappop(pq)
            u_i = node_idx[u]

            # Skip stale heap entries
            if cur_cost > dist[u_i]:
                continue
            if u == end:
                break

            for v, e in adj.get(u, []):
                v_i      = node_idx[v]
                # Edge cost: distance penalised by risk
                step     = self.edge_cost(e, risk_weight)
                new_cost = dist[u_i] + step
                if new_cost < dist[v_i]:
                    dist[v_i]        = new_cost
                    prev[v_i]        = u
                    edge_used[(u,v)] = e
                    heapq.heappush(pq, (new_cost, v))

        if dist[dst_i] == INF:
            return RouteResult([], INF,
                               filtered_count=filtered_count,
                               pruned_count=pruned_count,
                               blocked=True)

        # Reconstruct path by walking prev[] backwards
        path, cursor = [], end
        while cursor is not None:
            path.append(cursor)
            cursor = prev[node_idx[cursor]]
        path.reverse()

        edges_used = [
            edge_used[(path[i], path[i+1])]
            for i in range(len(path)-1)
            if (path[i], path[i+1]) in edge_used
        ]

        # Total cost = sum of individual edge costs (consistent with table)
        total = sum(self.edge_cost(e, risk_weight) for e in edges_used)

        return RouteResult(
            path           = path,
            total_cost     = round(total, 2),
            edges_used     = edges_used,
            filtered_count = filtered_count,
            pruned_count   = pruned_count,
            blocked        = False,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Algorithm 2 — Multi-Stage Dynamic Programming
    # ──────────────────────────────────────────────────────────────────────────

    def get_dp_route(
        self,
        stages:          list[list[str]],
        risk_weight:     float = 0.30,
        risk_threshold:  float = 1.00,
        require_weather: bool  = False,
    ) -> RouteResult:
        """
        Bottom-up DP for a layered supply-chain graph.

        Recurrence:  cost(i, j) = min_k { cost(i-1, k) + c(k, j) }
          where  c(k, j) = edge_cost(k→j)  from the feasible edge set.

        dp_matrix[stage][node_idx]  stores the minimum cost to reach
        that node from any origin in stage 0.

        choice_mat[stage][node_idx] stores the predecessor index k,
        used for path reconstruction.

        Path is reconstructed by pushing nodes onto a Stack (LIFO) from
        the final stage back to stage 0, then draining in forward order.

        Data structures:  Edge List → Matrix (dp_matrix) → Stack
        """
        INF = math.inf

        if not stages or not any(stages):
            return RouteResult([], INF, blocked=True)

        # Feasibility filter applies here too — same constraints as Dijkstra
        feasible, removed_count = self._feasible_edges(risk_threshold, require_weather)

        # Build edge cost lookup from the feasible edge set
        # c(k, j) = distance * (1 + risk_weight * risk)
        cost_map: dict[tuple[str,str], float] = {}
        for e in feasible:
            key  = (e.source, e.destination)
            c    = self.edge_cost(e, risk_weight)
            if key not in cost_map or c < cost_map[key]:
                cost_map[key] = c

        num_stages = len(stages)
        max_width  = max(len(s) for s in stages)

        # Initialise DP matrix and predecessor matrix
        dp_mat  = [[INF] * max_width for _ in range(num_stages)]   # cost matrix
        ch_mat  = [[-1]  * max_width for _ in range(num_stages)]   # predecessor

        # Base case: reaching any origin node costs 0
        for j in range(len(stages[0])):
            dp_mat[0][j] = 0.0

        # Forward DP fill
        for i in range(1, num_stages):
            for j_idx, j_node in enumerate(stages[i]):
                for k_idx, k_node in enumerate(stages[i-1]):
                    prev_cost = dp_mat[i-1][k_idx]
                    if prev_cost == INF:
                        continue
                    c_kj = cost_map.get((k_node, j_node), INF)
                    if c_kj == INF:
                        continue
                    candidate = prev_cost + c_kj
                    if candidate < dp_mat[i][j_idx]:
                        dp_mat[i][j_idx] = candidate
                        ch_mat[i][j_idx] = k_idx

        # Find best endpoint in the final stage
        final_costs  = [dp_mat[num_stages-1][j] for j in range(len(stages[-1]))]
        best_end_idx = final_costs.index(min(final_costs))
        best_cost    = final_costs[best_end_idx]

        if best_cost == INF:
            return RouteResult([], INF, filtered_count=removed_count, blocked=True)

        # Stack-based path reconstruction (LIFO)
        stack:  list[str] = []
        j_idx = best_end_idx
        for i in range(num_stages-1, -1, -1):
            stack.append(stages[i][j_idx])      # push current node
            if i > 0:
                j_idx = ch_mat[i][j_idx]        # step to predecessor stage

        path: list[str] = []
        while stack:
            path.append(stack.pop())            # drain stack → forward order

        # Retrieve the actual Edge objects for the chosen path
        edges_used = []
        for i in range(len(path)-1):
            for e in self.edge_list:
                if e.source == path[i] and e.destination == path[i+1]:
                    edges_used.append(e)
                    break

        # Total = sum of edge costs (matches what the DP accumulated)
        total = sum(self.edge_cost(e, risk_weight) for e in edges_used)

        return RouteResult(
            path           = path,
            total_cost     = round(total, 2),
            edges_used     = edges_used,
            filtered_count = removed_count,
            blocked        = False,
        )
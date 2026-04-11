"""
engine.py
Indian Logistics Optimizer — Core Engine
"""

import heapq
import math
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Edge:
    source:      str
    destination: str
    distance:    float      # kilometres
    risk:        float      # 0.0 – 1.0  (higher = more dangerous)
    weather_ok:  bool = True


@dataclass
class RouteResult:
    path:           list[str]
    total_cost:     float
    edges_used:     list[Edge] = field(default_factory=list)
    filtered_count: int = 0
    blocked:        bool = False   # True when constraints make route impossible


# ─────────────────────────────────────────────────────────────────────────────
# LogisticsGraph
# ─────────────────────────────────────────────────────────────────────────────

class LogisticsGraph:
    """
    Directed weighted graph.

    Storage : Edge List  (self.edge_list)
    Nodes   : ordered list (self.nodes)
    """

    def __init__(self):
        self.edge_list: list[Edge] = []
        self.nodes:     list[str]  = []

    # ── Construction ─────────────────────────────────────────────────────────

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

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _blended_cost(edge: Edge, risk_weight: float) -> float:
        return edge.distance * (1 - risk_weight) + edge.risk * risk_weight * 100

    def _filter_edges(
        self, risk_threshold: float, require_weather: bool
    ) -> tuple[list[Edge], int]:
        """Return (surviving_edges, removed_count) after applying constraints."""
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

    def _build_adj(
        self, edges: list[Edge]
    ) -> dict[str, list[tuple[str, Edge]]]:
        adj: dict[str, list[tuple[str, Edge]]] = {n: [] for n in self.nodes}
        for e in edges:
            adj.setdefault(e.source, []).append((e.destination, e))
        return adj

    # ── 1. Hybrid: Risk Filter  +  Dijkstra ──────────────────────────────────
    #    Phase 1 — strip edges that violate risk / weather constraints
    #    Phase 2 — Dijkstra on surviving edge set
    #
    #    Internal data structures:
    #      Edge List  → source of truth
    #      Array      → dist_array  (indexed by node position)
    #      Priority Queue → min-heap open set

    def get_optimized_route(
        self,
        start: str, end: str,
        risk_weight: float = 0.3,
        risk_threshold: float = 0.4,
        require_weather: bool = True,
    ) -> RouteResult:

        INF = math.inf
        surviving, removed_count = self._filter_edges(risk_threshold, require_weather)
        adj = self._build_adj(surviving)

        node_index = {n: i for i, n in enumerate(self.nodes)}
        src_idx = node_index.get(start)
        dst_idx = node_index.get(end)
        if src_idx is None or dst_idx is None:
            return RouteResult([], INF, filtered_count=removed_count, blocked=True)

        # Array — distance table
        dist_array: list[float]      = [INF]  * len(self.nodes)
        prev_node:  list[str | None] = [None] * len(self.nodes)
        dist_array[src_idx] = 0.0

        # Priority Queue
        pq: list[tuple[float, str]] = []
        heapq.heappush(pq, (0.0, start))

        edge_map: dict[tuple[str, str], Edge] = {}

        while pq:
            cur_cost, u = heapq.heappop(pq)
            u_idx = node_index[u]
            if cur_cost > dist_array[u_idx]:
                continue
            if u == end:
                break
            for v, edge in adj.get(u, []):
                v_idx    = node_index[v]
                new_cost = dist_array[u_idx] + self._blended_cost(edge, risk_weight)
                if new_cost < dist_array[v_idx]:
                    dist_array[v_idx] = new_cost
                    prev_node[v_idx]  = u
                    edge_map[(u, v)]  = edge
                    heapq.heappush(pq, (new_cost, v))

        if dist_array[dst_idx] == INF:
            return RouteResult([], INF, filtered_count=removed_count, blocked=True)

        # Reconstruct path
        path, cursor = [], end
        while cursor is not None:
            path.append(cursor)
            cursor = prev_node[node_index[cursor]]
        path.reverse()

        edges_used = [
            edge_map[(path[i], path[i + 1])]
            for i in range(len(path) - 1)
            if (path[i], path[i + 1]) in edge_map
        ]

        return RouteResult(
            path           = path,
            total_cost     = round(dist_array[dst_idx], 4),
            edges_used     = edges_used,
            filtered_count = removed_count,
            blocked        = False,
        )

    # ── 2. Multi-Stage Dynamic Programming ───────────────────────────────────
    #    Recurrence: cost(i,j) = min { cost(i-1,k) + c(k,j) }
    #
    #    Internal data structures:
    #      Edge List  → cost lookup after constraint filtering
    #      Matrix     → dp_matrix[stage][node_idx]
    #      Stack      → LIFO path reconstruction

    def get_dp_route(
        self,
        stages: list[list[str]],
        risk_weight: float = 0.3,
        risk_threshold: float = 1.0,      # ← now honoured
        require_weather: bool = False,    # ← now honoured
    ) -> RouteResult:

        INF = math.inf

        if not stages or not any(stages):
            return RouteResult([], INF, blocked=True)

        # Filter Edge List by the same constraints as Dijkstra
        surviving, removed_count = self._filter_edges(risk_threshold, require_weather)

        # Build cost lookup from surviving edges only
        edge_cost_map: dict[tuple[str, str], float] = {}
        for e in surviving:
            key  = (e.source, e.destination)
            cost = self._blended_cost(e, risk_weight)
            if key not in edge_cost_map or cost < edge_cost_map[key]:
                edge_cost_map[key] = cost

        num_stages = len(stages)
        max_width  = max(len(s) for s in stages)

        # Matrix initialisation
        dp_matrix  = [[INF] * max_width for _ in range(num_stages)]   # Matrix
        choice_mat = [[-1]  * max_width for _ in range(num_stages)]   # Matrix

        # Base case
        for j in range(len(stages[0])):
            dp_matrix[0][j] = 0.0

        # Forward fill — recurrence: cost(i,j) = min{cost(i-1,k) + c(k,j)}
        for i in range(1, num_stages):
            for j_idx, j_node in enumerate(stages[i]):
                for k_idx, k_node in enumerate(stages[i - 1]):
                    prev = dp_matrix[i - 1][k_idx]
                    if prev == INF:
                        continue
                    c_kj = edge_cost_map.get((k_node, j_node), INF)
                    if c_kj == INF:
                        continue
                    candidate = prev + c_kj
                    if candidate < dp_matrix[i][j_idx]:
                        dp_matrix[i][j_idx]  = candidate
                        choice_mat[i][j_idx] = k_idx

        # Best endpoint in final stage
        last_costs   = [dp_matrix[num_stages - 1][j] for j in range(len(stages[-1]))]
        best_end_idx = last_costs.index(min(last_costs))
        best_cost    = last_costs[best_end_idx]

        if best_cost == INF:
            return RouteResult([], INF, filtered_count=removed_count, blocked=True)

        # Stack-based path reconstruction (LIFO)
        stack: list[str] = []
        j_idx = best_end_idx
        for i in range(num_stages - 1, -1, -1):
            stack.append(stages[i][j_idx])          # push
            if i > 0:
                j_idx = choice_mat[i][j_idx]

        path: list[str] = []
        while stack:
            path.append(stack.pop())                # pop → forward order

        # Enrich edges_used from original edge list
        edges_used = []
        for i in range(len(path) - 1):
            for e in self.edge_list:
                if e.source == path[i] and e.destination == path[i + 1]:
                    edges_used.append(e)
                    break

        return RouteResult(
            path           = path,
            total_cost     = round(best_cost, 4),
            edges_used     = edges_used,
            filtered_count = removed_count,
            blocked        = False,
        )
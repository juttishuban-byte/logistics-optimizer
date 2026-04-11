"""
engine.py — Risk-Aware Logistics Optimizer
LogisticsGraph: Dijkstra · Greedy · Multi-Stage DP
"""

import heapq
import math
from typing import Optional


class LogisticsGraph:
    """
    Weighted directed graph where every edge carries both a
    *distance* cost and a *risk* score (0–1 scale).

    Internal adjacency structure
    ----------------------------
    self.graph[u] = [(v, dist, risk), ...]
    """

    def __init__(self):
        self.graph: dict[str, list[tuple[str, float, float]]] = {}

    # ------------------------------------------------------------------
    # Graph construction helpers
    # ------------------------------------------------------------------

    def add_node(self, node: str) -> None:
        if node not in self.graph:
            self.graph[node] = []

    def add_edge(
        self,
        u: str,
        v: str,
        dist: float,
        risk: float,
        bidirectional: bool = True,
    ) -> None:
        """Add a directed (or bidirectional) edge with distance and risk."""
        self.add_node(u)
        self.add_node(v)
        self.graph[u].append((v, dist, risk))
        if bidirectional:
            self.graph[v].append((u, dist, risk))

    # ------------------------------------------------------------------
    # Shared cost formula
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_cost(dist: float, risk: float, risk_weight: float) -> float:
        """Blended cost = dist*(1-w) + risk*w*100."""
        return dist * (1 - risk_weight) + risk * risk_weight * 100

    # ------------------------------------------------------------------
    # 1. Dijkstra  (exact shortest path)
    # ------------------------------------------------------------------

    def get_dijkstra(
        self, start: str, end: str, risk_weight: float = 0.5
    ) -> tuple[Optional[list[str]], float]:
        """
        Standard Dijkstra using the blended cost as edge weight.

        Returns
        -------
        (path, total_cost)  — path is None when no route exists.
        """
        if start not in self.graph or end not in self.graph:
            return None, math.inf

        dist_map: dict[str, float] = {n: math.inf for n in self.graph}
        dist_map[start] = 0.0
        prev: dict[str, Optional[str]] = {n: None for n in self.graph}

        heap: list[tuple[float, str]] = [(0.0, start)]

        while heap:
            cur_cost, u = heapq.heappop(heap)
            if cur_cost > dist_map[u]:
                continue
            if u == end:
                break
            for v, d, r in self.graph[u]:
                new_cost = cur_cost + self._edge_cost(d, r, risk_weight)
                if new_cost < dist_map[v]:
                    dist_map[v] = new_cost
                    prev[v] = u
                    heapq.heappush(heap, (new_cost, v))

        if dist_map[end] == math.inf:
            return None, math.inf

        # Reconstruct path
        path, node = [], end
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        return path, round(dist_map[end], 4)

    # ------------------------------------------------------------------
    # 2. Greedy  (myopic best neighbour)
    # ------------------------------------------------------------------

    def get_greedy(
        self, start: str, end: str, risk_weight: float = 0.5
    ) -> tuple[Optional[list[str]], float]:
        """
        Greedy nearest-neighbour traversal.

        At every step the neighbour with the lowest *immediate* blended
        cost  ``dist*(1-w) + risk*w*100``  is chosen, regardless of the
        accumulated path cost.  Visited nodes are not revisited so the
        algorithm always terminates, but it may fail to find a path even
        when one exists, and the path found is rarely optimal.

        Returns
        -------
        (path, total_cost)
        """
        if start not in self.graph or end not in self.graph:
            return None, math.inf

        path = [start]
        visited = {start}
        total_cost = 0.0
        current = start

        while current != end:
            neighbours = [
                (v, d, r)
                for v, d, r in self.graph.get(current, [])
                if v not in visited
            ]
            if not neighbours:
                return None, math.inf  # Dead end — greedy failed

            # Pick neighbour with minimum immediate blended cost
            best_v, best_d, best_r = min(
                neighbours,
                key=lambda t: self._edge_cost(t[1], t[2], risk_weight),
            )
            total_cost += self._edge_cost(best_d, best_r, risk_weight)
            path.append(best_v)
            visited.add(best_v)
            current = best_v

        return path, round(total_cost, 4)

    # ------------------------------------------------------------------
    # 3. Multi-Stage DP  (bottom-up, Factory→Port→Hub→Customer)
    # ------------------------------------------------------------------

    def get_dp(
        self,
        stages: list[list[str]],
        risk_weight: float = 0.5,
    ) -> tuple[Optional[list[str]], float]:
        """
        Bottom-up Dynamic Programming for a multi-stage logistics graph.

        Parameters
        ----------
        stages : list of lists
            Each inner list is a stage (layer).  Example::

                stages = [
                    ["Factory"],            # stage 0
                    ["Port_A", "Port_B"],   # stage 1
                    ["Hub_X", "Hub_Y"],     # stage 2
                    ["Customer"],           # stage 3
                ]

        risk_weight : float
            Blending weight for risk vs distance.

        Returns
        -------
        (path, total_cost)

        Algorithm
        ---------
        For each node in the *last* stage, dp[node] = 0.
        Working backwards through stages, for each node u in stage s
        and each edge (u→v) where v is in stage s+1::

            dp[u] = min over v of (edge_cost(u,v) + dp[v])

        The optimal path is then reconstructed greedily forwards from
        stages[0][0].
        """
        if not stages or not stages[0]:
            return None, math.inf

        # Build a fast lookup: node → stage index
        node_to_stage: dict[str, int] = {}
        for s_idx, stage in enumerate(stages):
            for node in stage:
                node_to_stage[node] = s_idx

        # Validate all stage nodes exist in the graph
        all_stage_nodes = {n for stage in stages for n in stage}
        for n in all_stage_nodes:
            if n not in self.graph:
                self.add_node(n)

        # DP tables
        dp: dict[str, float] = {}
        next_node: dict[str, Optional[str]] = {}

        # Base case: last stage costs 0
        for node in stages[-1]:
            dp[node] = 0.0
            next_node[node] = None

        # Fill backwards through stages
        for s_idx in range(len(stages) - 2, -1, -1):
            next_stage_set = set(stages[s_idx + 1])
            for u in stages[s_idx]:
                best_cost = math.inf
                best_v = None
                for v, d, r in self.graph.get(u, []):
                    if v not in next_stage_set:
                        continue
                    candidate = self._edge_cost(d, r, risk_weight) + dp.get(v, math.inf)
                    if candidate < best_cost:
                        best_cost = candidate
                        best_v = v
                dp[u] = best_cost
                next_node[u] = best_v

        # Reconstruct path from stage 0
        start = stages[0][0]
        if dp.get(start, math.inf) == math.inf:
            return None, math.inf

        path = [start]
        cur = start
        while next_node.get(cur) is not None:
            cur = next_node[cur]
            path.append(cur)

        return path, round(dp[start], 4)
import logging
import random
from typing import List, Optional
from models import ServerInstance
from services.server_registry import server_registry

logger = logging.getLogger('load_balancer')

class LoadBalancer:
    def __init__(self, strategy: str = "latency_aware"):
        self.strategy = strategy # "latency_aware", "least_connections", "weighted_round_robin"
        self._rr_index = 0

    def select_target_server(self) -> Optional[ServerInstance]:
        """
        Select best healthy server node for an incoming request based on configured strategy.
        Filters out UNHEALTHY, OFFLINE, or maintenance servers.
        """
        healthy_nodes = server_registry.get_healthy_servers()
        if not healthy_nodes:
            logger.warning("[LOAD BALANCER] No healthy backend servers available!")
            return None
            
        if len(healthy_nodes) == 1:
            return healthy_nodes[0]

        if self.strategy == "least_connections":
            # Select node with minimum active requests
            return min(healthy_nodes, key=lambda s: s.active_requests or 0)
            
        elif self.strategy == "latency_aware":
            # Select node with best score (combining latency and active requests)
            return min(healthy_nodes, key=lambda s: (s.avg_latency_ms or 50.0) + (s.active_requests or 0) * 10)
            
        else: # weighted_round_robin
            weights = [max(s.weight or 1, 1) for s in healthy_nodes]
            total_weight = sum(weights)
            r = random.randint(1, total_weight)
            cum_weight = 0
            for node, w in zip(healthy_nodes, weights):
                cum_weight += w
                if r <= cum_weight:
                    return node
            return healthy_nodes[0]

    def export_nginx_upstream_config(self) -> str:
        """Generate dynamic Nginx upstream config block based on healthy active servers."""
        healthy_nodes = server_registry.get_healthy_servers()
        lines = ["upstream vkshop_backend_cluster {", "    least_conn;"]
        for node in healthy_nodes:
            weight = node.weight or 100
            url_part = node.api_endpoint.replace('https://', '').replace('http://', '')
            lines.append(f"    server {url_part} weight={weight} max_fails=3 fail_timeout=10s;")
        lines.append("}")
        return "\n".join(lines)

load_balancer = LoadBalancer()

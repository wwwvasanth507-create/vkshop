import os
import time
import logging
import requests
from datetime import datetime
from typing import List, Optional, Dict
from models import ServerInstance, ServerMetric
from database import db

logger = logging.getLogger('server_registry')

class ServerRegistry:
    @staticmethod
    def get_this_server_id() -> str:
        """Return unique ID for the current running backend instance."""
        srv_id = os.environ.get('VKSHOP_SERVER_ID')
        if not srv_id:
            # Fallback to Render instance ID or hostname
            render_id = os.environ.get('RENDER_INSTANCE_ID') or os.environ.get('HOSTNAME')
            srv_id = f"srv-{render_id[:16]}" if render_id else "srv-primary-node-1"
        return srv_id

    @staticmethod
    def register_server(
        server_id: str,
        name: str,
        api_endpoint: str,
        provider: str = "Render",
        region: str = "India",
        health_endpoint: str = "/ready",
        weight: int = 100
    ) -> ServerInstance:
        """Register or update a server instance in central PostgreSQL db."""
        try:
            srv = ServerInstance.query.filter_by(server_id=server_id).first()
            if not srv:
                srv = ServerInstance(server_id=server_id)
                db.session.add(srv)
                
            srv.name = name
            srv.provider = provider
            srv.region = region
            srv.api_endpoint = api_endpoint.rstrip('/')
            srv.health_endpoint = health_endpoint
            srv.weight = weight
            srv.status = 'ONLINE'
            srv.is_active = True
            srv.last_heartbeat = datetime.utcnow()
            srv.updated_at = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"[SERVER REGISTRY] Registered node: {server_id} ({api_endpoint})")
            return srv
        except Exception as e:
            db.session.rollback()
            logger.error(f"[SERVER REGISTRY FAIL] {e}")
            raise

    @staticmethod
    def record_heartbeat(
        server_id: str,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
        active_requests: int = 0,
        requests_per_min: int = 0,
        avg_latency_ms: float = 0.0,
        error_rate: float = 0.0
    ):
        """Record telemetry heartbeat from a running server node."""
        try:
            srv = ServerInstance.query.filter_by(server_id=server_id).first()
            if not srv:
                return
                
            srv.cpu_usage = cpu_usage
            srv.memory_usage = memory_usage
            srv.active_requests = active_requests
            srv.requests_per_min = requests_per_min
            srv.avg_latency_ms = avg_latency_ms
            srv.error_rate = error_rate
            srv.last_heartbeat = datetime.utcnow()
            srv.consecutive_failures = 0
            
            if srv.status in ['UNHEALTHY', 'OFFLINE'] and not srv.is_maintenance:
                srv.status = 'ONLINE'
                logger.info(f"[SERVER RECOVERY] Server {server_id} recovered to ONLINE status.")
                
            # Log metric point
            metric = ServerMetric(
                server_id=server_id,
                cpu_pct=cpu_usage,
                memory_pct=memory_usage,
                latency_ms=avg_latency_ms,
                requests_per_sec=round(requests_per_min / 60.0, 2),
                recorded_at=datetime.utcnow()
            )
            db.session.add(metric)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"[HEARTBEAT RECORD ERROR] {e}")

    @staticmethod
    def check_all_servers_health():
        """
        Background health monitor: pings all registered server instances.
        Marks server UNHEALTHY after 3 consecutive failures.
        """
        try:
            servers = ServerInstance.query.filter_by(is_active=True).all()
            for srv in servers:
                if srv.is_maintenance:
                    continue
                    
                target_url = f"{srv.api_endpoint.rstrip('/')}{srv.health_endpoint}"
                try:
                    t0 = time.time()
                    resp = requests.get(target_url, timeout=3)
                    latency = round((time.time() - t0) * 1000, 2)
                    
                    if resp.status_code == 200:
                        srv.last_successful_request = datetime.utcnow()
                        srv.avg_latency_ms = latency
                        srv.consecutive_failures = 0
                        if srv.status != 'ONLINE':
                            srv.status = 'ONLINE'
                            logger.info(f"[HEALTH MONITOR] Server {srv.server_id} recovered to ONLINE.")
                    else:
                        srv.consecutive_failures += 1
                        logger.warning(f"[HEALTH MONITOR] Server {srv.server_id} returned HTTP {resp.status_code} (failures={srv.consecutive_failures})")
                except Exception as req_err:
                    srv.consecutive_failures += 1
                    logger.warning(f"[HEALTH MONITOR] Server {srv.server_id} ping failed ({req_err}) (failures={srv.consecutive_failures})")
                    
                if srv.consecutive_failures >= 3:
                    if srv.status != 'UNHEALTHY':
                        srv.status = 'UNHEALTHY'
                        logger.error(f"[SERVER UNHEALTHY] Server {srv.server_id} marked UNHEALTHY and removed from active traffic.")
                        
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"[HEALTH MONITOR ERROR] {e}")

    @staticmethod
    def get_healthy_servers() -> List[ServerInstance]:
        """Return list of active, healthy servers ready for traffic routing."""
        try:
            return ServerInstance.query.filter(
                ServerInstance.is_active == True,
                ServerInstance.is_maintenance == False,
                ServerInstance.status.in_(['ONLINE', 'DEGRADED'])
            ).all()
        except Exception:
            return []

server_registry = ServerRegistry()

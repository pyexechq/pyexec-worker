"""
transport/http_transport.py — HTTP long-polling transport for the local agent.

The agent periodically GET /api/worker-agent/jobs/ to check for work,
then POST results and logs back to the server.
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class HttpTransport:
    def __init__(self, server_url: str, agent_token: str):
        self._base = server_url.rstrip('/')
        self._headers = {'Authorization': f'Bearer {agent_token}'}
        self._client = httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(35.0),  # > long-poll window of 29 s
        )

    async def close(self):
        await self._client.aclose()

    async def heartbeat(self, host_info: dict, capabilities: dict) -> bool:
        try:
            r = await self._client.post(
                f'{self._base}/api/worker-agent/heartbeat/',
                json={'host_info': host_info, 'capabilities': capabilities},
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning('Heartbeat failed: %s', exc)
            return False

    async def poll_for_step(self) -> Optional[dict]:
        """
        Long-poll the server for the next step.
        Returns the step payload dict or None if nothing was queued.
        """
        try:
            r = await self._client.get(f'{self._base}/api/worker-agent/jobs/')
            if r.status_code == 204:
                return None
            if r.status_code == 200:
                return r.json()
            logger.warning('Unexpected poll response: %s', r.status_code)
            return None
        except httpx.TimeoutException:
            return None
        except Exception as exc:
            logger.warning('Poll error: %s', exc)
            return None

    async def post_result(
        self,
        job_id: int,
        step_index: int,
        status: str,
        result=None,
        error: str = '',
        host_snapshot: dict = None,
    ) -> bool:
        try:
            r = await self._client.post(
                f'{self._base}/api/worker-agent/jobs/{job_id}/result/',
                json={
                    'step_index': step_index,
                    'status': status,
                    'result': result,
                    'error': error,
                    'worker_host_snapshot': host_snapshot or {},
                },
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning('post_result failed: %s', exc)
            return False

    async def post_logs(self, job_id: int, lines: list) -> bool:
        try:
            r = await self._client.post(
                f'{self._base}/api/worker-agent/jobs/{job_id}/logs/',
                json={'lines': lines},
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning('post_logs failed: %s', exc)
            return False

    async def get_env(self, job_id: int) -> dict:
        try:
            r = await self._client.get(f'{self._base}/api/worker-agent/env/{job_id}/')
            if r.status_code == 200:
                return r.json()
            logger.warning('get_env returned %s', r.status_code)
            return {}
        except Exception as exc:
            logger.warning('get_env error: %s', exc)
            return {}

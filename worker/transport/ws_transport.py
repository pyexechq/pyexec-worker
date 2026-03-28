"""
transport/ws_transport.py — WebSocket transport for the local agent.

Uses websockets library for persistent bidirectional communication.
Falls back to HTTP transport if WebSocket connection fails.
"""

import asyncio
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_PING_INTERVAL = 25  # seconds between keepalive pings


class WsTransport:
    def __init__(self, server_url: str, agent_token: str):
        # Convert http(s):// to ws(s)://
        ws_url = server_url.rstrip('/')
        if ws_url.startswith('https://'):
            ws_url = 'wss://' + ws_url[len('https://'):]
        elif ws_url.startswith('http://'):
            ws_url = 'ws://' + ws_url[len('http://'):]
        self._ws_url = f'{ws_url}/ws/worker-agent/?token={agent_token}'
        self._ws = None
        self._step_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False

    async def connect(self) -> bool:
        try:
            import websockets
            self._ws = await websockets.connect(
                self._ws_url,
                ping_interval=_PING_INTERVAL,
                open_timeout=10,
            )
            self._connected = True
            asyncio.ensure_future(self._receive_loop())
            logger.info('WsTransport: connected to %s', self._ws_url.split('?')[0])
            return True
        except Exception as exc:
            logger.warning('WsTransport: could not connect: %s', exc)
            self._connected = False
            return False

    async def close(self):
        if self._ws:
            await self._ws.close()
        self._connected = False

    async def _receive_loop(self):
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'step':
                        await self._step_queue.put(data['payload'])
                except Exception as exc:
                    logger.debug('WS receive parse error: %s', exc)
        except Exception as exc:
            logger.warning('WS receive loop ended: %s', exc)
            self._connected = False

    async def heartbeat(self, host_info: dict, capabilities: dict) -> bool:
        return await self._send({'type': 'heartbeat', 'host_info': host_info, 'capabilities': capabilities})

    async def poll_for_step(self, timeout: float = 29.0) -> Optional[dict]:
        """
        Wait for the next step pushed by the server.
        Returns None if nothing arrives within *timeout* seconds.
        """
        if not self._connected:
            return None
        try:
            return await asyncio.wait_for(self._step_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
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
        return await self._send({
            'type': 'result',
            'job_id': job_id,
            'step_index': step_index,
            'status': status,
            'result': result,
            'error': error,
            'worker_host_snapshot': host_snapshot or {},
        })

    async def post_logs(self, job_id: int, lines: list) -> bool:
        return await self._send({'type': 'log', 'job_id': job_id, 'lines': lines})

    async def _send(self, data: dict) -> bool:
        if not self._connected or not self._ws:
            return False
        try:
            await self._ws.send(json.dumps(data))
            return True
        except Exception as exc:
            logger.warning('WS send error: %s', exc)
            self._connected = False
            return False

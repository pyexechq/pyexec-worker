"""
agent.py — Main event loop for the pyexec local worker agent.

Responsibilities:
  1. Connect to the cloud backend (WebSocket preferred, HTTP fallback).
  2. Send periodic heartbeats with host metadata.
  3. Long-poll / receive step payloads.
  4. Decrypt environment secrets from the server.
  5. Execute each step inside Docker (see job_executor.py).
  6. Stream logs back to the server in near-real-time.
  7. Report step results back to the server.
"""

import asyncio
import logging
import signal

from . import config as cfg_mod
from . import host_info as host_mod
from .job_executor import execute_step
from .secret_decryptor import decrypt_env_bundle

logger = logging.getLogger(__name__)


class LocalWorkerAgent:
    def __init__(self):
        self.cfg = cfg_mod.load()
        self._transport = None
        self._host_info = host_mod.collect()
        self._capabilities = {
            'languages': ['python'],
            'docker': bool(self._host_info.get('docker_version')),
        }
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(
            self.cfg['max_concurrent_steps']
        )
        self._running = True

    async def run(self):
        self._transport = await self._build_transport()
        heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

        logger.info('pyexec-worker agent started (server=%s)', self.cfg['server_url'])

        try:
            while self._running:
                payload = await self._transport.poll_for_step()
                if payload:
                    asyncio.ensure_future(self._handle_step(payload))
        finally:
            heartbeat_task.cancel()
            await self._transport.close()
            logger.info('pyexec-worker agent stopped.')

    async def _build_transport(self):
        if self.cfg.get('use_websocket', True):
            from .transport.ws_transport import WsTransport
            ws = WsTransport(self.cfg['server_url'], self.cfg['agent_token'])
            if await ws.connect():
                return ws
            logger.warning('WebSocket unavailable, falling back to HTTP long-polling.')

        from .transport.http_transport import HttpTransport
        return HttpTransport(self.cfg['server_url'], self.cfg['agent_token'])

    async def _heartbeat_loop(self):
        while self._running:
            await asyncio.sleep(self.cfg['heartbeat_interval'])
            # Refresh host info on each heartbeat.
            self._host_info = host_mod.collect()
            ok = await self._transport.heartbeat(self._host_info, self._capabilities)
            if not ok:
                logger.warning('Heartbeat failed.')

    async def _handle_step(self, payload: dict):
        job_id = payload.get('job_id')
        step_index = payload.get('step_index')
        step = payload.get('step', {})
        context = payload.get('context', {})

        logger.info('Executing step job_id=%s step=%s type=%s', job_id, step_index, step.get('type'))

        async with self._semaphore:
            # 1. Fetch + decrypt secrets.
            env_secrets = {}
            try:
                enc_bundle = await self._transport.get_env(job_id) if hasattr(self._transport, 'get_env') else {}
                if enc_bundle:
                    env_secrets = decrypt_env_bundle(enc_bundle, self.cfg['private_key_path'])
            except Exception as exc:
                logger.warning('Could not load secrets for job %s: %s', job_id, exc)

            # 2. Execute step.
            outcome = await execute_step(step, context, env_secrets, self.cfg)

            # 3. Stream logs.
            logs = outcome.get('logs', [])
            if logs:
                await self._transport.post_logs(job_id, logs)

            # 4. Report result.
            await self._transport.post_result(
                job_id=job_id,
                step_index=step_index,
                status=outcome['status'],
                result=outcome.get('result'),
                error=outcome.get('error', ''),
                host_snapshot=self._host_info,
            )


def run():
    """Entry point called by `pyexec-worker start`."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    agent = LocalWorkerAgent()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(*_):
        agent._running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    try:
        loop.run_until_complete(agent.run())
    finally:
        loop.close()

"""
job_executor.py — Executes a step payload locally inside Docker.

Mirrors the Docker flags used by the cloud script_step.py executor.
Each step runs in an isolated container with the decrypted env vars injected.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time

logger = logging.getLogger(__name__)


async def execute_step(step: dict, context: dict, env_secrets: dict, cfg: dict) -> dict:
    """
    Execute a single workflow step locally.

    Returns:
      {"status": "success", "result": <any>, "logs": [...]}
      {"status": "error",   "error":  "...", "logs": [...]}
    """
    step_type = step.get('type', 'script')
    if step_type == 'script':
        return await _run_script_step(step, context, env_secrets, cfg)
    elif step_type in ('api', 'database'):
        return await _run_connector_step(step, context, env_secrets, cfg)
    else:
        return {'status': 'error', 'error': f'Step type "{step_type}" not supported for local execution.', 'logs': []}


# ---------------------------------------------------------------------------
# Script step
# ---------------------------------------------------------------------------

async def _run_script_step(step: dict, context: dict, env_secrets: dict, cfg: dict) -> dict:
    script_code = step.get('config', {}).get('code', '') or step.get('script_code', '')
    if not script_code:
        return {'status': 'error', 'error': 'No script code provided.', 'logs': []}

    docker_bin = shutil.which('docker')
    if not docker_bin:
        return {'status': 'error', 'error': 'Docker not found on PATH.', 'logs': []}

    logs = []
    with tempfile.TemporaryDirectory(prefix='pyexec_') as tmpdir:
        script_path = os.path.join(tmpdir, 'script.py')
        ctx_path = os.path.join(tmpdir, 'context.json')
        out_path = os.path.join(tmpdir, 'output.json')

        wrapper = _build_wrapper(script_code)
        with open(script_path, 'w') as f:
            f.write(wrapper)
        with open(ctx_path, 'w') as f:
            json.dump(context, f)

        docker_image = cfg.get('docker_image', 'python:3.11-slim')
        env_args = []
        for k, v in env_secrets.items():
            env_args += ['-e', f'{k}={v}']

        cmd = [
            docker_bin, 'run', '--rm',
            '--network', 'none',
            '--memory', '256m',
            '--cpus', '0.5',
            '--read-only',
            '--tmpfs', '/tmp',
            '-v', f'{script_path}:/app/script.py:ro',
            '-v', f'{ctx_path}:/app/context.json:ro',
            '-v', f'{out_path}:/app/output.json',
            *env_args,
            docker_image,
            'python', '/app/script.py',
        ]

        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            return {'status': 'error', 'error': 'Script timed out after 300 s.', 'logs': logs}

        duration_ms = int((time.monotonic() - start) * 1000)
        raw_output = (stdout or b'').decode(errors='replace')
        logs = [line for line in raw_output.splitlines() if line]
        logs.append(f'[DURATION] {duration_ms} ms')

        if proc.returncode != 0:
            return {
                'status': 'error',
                'error': f'Container exited with code {proc.returncode}',
                'logs': logs,
            }

        # Read output.json written by the wrapper.
        try:
            with open(out_path) as f:
                output = json.load(f)
            return {'status': 'success', 'result': output.get('result'), 'logs': logs}
        except (FileNotFoundError, json.JSONDecodeError):
            return {'status': 'success', 'result': None, 'logs': logs}


def _build_wrapper(script_code: str) -> str:
    """Wrap user script so it can read context and write output."""
    return f"""
import json, sys, os

with open('/app/context.json') as _f:
    context = json.load(_f)

# Expose context as global variable
__builtins__['context'] = context  # noqa

{script_code}

# Write result if user set `result` variable
_result = locals().get('result')
with open('/app/output.json', 'w') as _f:
    json.dump({{'result': _result}}, _f)
"""


# ---------------------------------------------------------------------------
# Connector step (API / Database) — basic implementations
# ---------------------------------------------------------------------------

async def _run_connector_step(step: dict, context: dict, env_secrets: dict, cfg: dict) -> dict:
    """
    Run an API or database step locally using the same logic as the cloud workers,
    but without Docker (these are network calls, not arbitrary code).
    """
    step_type = step.get('type')
    cfg_data = step.get('config', {})
    logs = []

    if step_type == 'api':
        try:
            import httpx
            method = cfg_data.get('method', 'GET').upper()
            url = cfg_data.get('url', '')
            if not url.startswith(('http://', 'https://')):
                return {'status': 'error', 'error': f'Invalid URL: {url}', 'logs': []}
            headers = {'Content-Type': 'application/json'}
            body_str = cfg_data.get('body', '{}')
            try:
                body = json.loads(body_str) if body_str.strip() else {}
            except json.JSONDecodeError:
                body = {}
            logs.append(f'[API] {method} {url}')
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method, url,
                    json=body if method != 'GET' else None,
                    headers=headers,
                )
            logs.append(f'[API] Response: {response.status_code}')
            response.raise_for_status()
            return {'status': 'success', 'result': response.json(), 'logs': logs}
        except Exception as exc:
            return {'status': 'error', 'error': str(exc), 'logs': logs}

    return {'status': 'error', 'error': f'Local execution of "{step_type}" not yet implemented.', 'logs': logs}

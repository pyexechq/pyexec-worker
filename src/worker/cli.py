"""
cli.py — Command-line interface for pyexec-worker.

Commands:
  pyexec-worker register  --server <url> --org-token <token> --name <name>
  pyexec-worker start     [--server <url>]
  pyexec-worker status
"""

import hashlib
import json
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import click

from . import config as cfg_mod
from . import host_info as host_mod


@click.group()
def cli():
    """pyexec-worker — local execution agent for PyExecutor."""


@cli.command()
@click.option('--server', default=None, help='PyExecutor server URL (e.g. https://pyexec.example.com)')
@click.option('--org-token', required=True, envvar='PYEXEC_ORG_TOKEN', help='Organisation registration token')
@click.option('--name', default=None, help='Human-readable agent name')
def register(server, org_token, name):
    """Register this machine as a local worker agent."""
    import requests  # lightweight HTTP

    cfg = cfg_mod.load()
    server_url = (server or cfg.get('server_url', 'http://localhost:8000')).rstrip('/')
    agent_name = name or platform.node()

    # Generate RSA-2048 key pair.
    click.echo('Generating RSA-2048 key pair…')
    config_dir = cfg_mod.config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = config_dir / 'private.pem'
    public_key_path = config_dir / 'public.pem'

    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        private_key_path.write_bytes(private_pem)
        private_key_path.chmod(0o600)
        public_key_path.write_text(public_pem)
        click.echo(f'  Private key → {private_key_path}')
        click.echo(f'  Public key  → {public_key_path}')
    except ImportError:
        click.echo('ERROR: cryptography package not installed.  Run: pip install cryptography', err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f'ERROR generating key pair: {exc}', err=True)
        sys.exit(1)

    click.echo(f'Registering with {server_url}…')
    h_info = host_mod.collect()
    payload = {
        'org_token': org_token,
        'name': agent_name,
        'public_key': public_pem,
        'capabilities': {'languages': ['python'], 'docker': bool(h_info.get('docker_version'))},
        'host_info': h_info,
    }

    try:
        resp = requests.post(f'{server_url}/api/worker-agent/register/', json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        click.echo(f'ERROR registering: {exc}', err=True)
        sys.exit(1)

    agent_token = data['agent_token']
    cfg_mod.save({'server_url': server_url, 'agent_name': agent_name})
    cfg_mod.save_agent_token(agent_token)

    click.echo(click.style('\nRegistration successful!', fg='green', bold=True))
    click.echo(f"  Agent ID   : {data['agent_id']}")
    click.echo(f"  Agent name : {agent_name}")
    click.echo(f"  Server     : {server_url}")
    click.echo('\nRun `pyexec-worker start` to begin processing jobs.')


@cli.command()
@click.option('--server', default=None, help='Override server URL')
def start(server):
    """Start the local worker agent."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    cfg = cfg_mod.load()
    if server:
        cfg['server_url'] = server

    if not cfg.get('agent_token'):
        click.echo('ERROR: No agent token found.  Run `pyexec-worker register` first.', err=True)
        sys.exit(1)

    click.echo(f"Starting pyexec-worker (server={cfg['server_url']})…")
    from .agent import LocalWorkerAgent
    import asyncio
    import signal

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


@cli.command()
def status():
    """Show local agent configuration and registration status."""
    cfg = cfg_mod.load()
    config_dir = cfg_mod.config_dir()
    click.echo('pyexec-worker configuration:')
    click.echo(f"  Server URL  : {cfg.get('server_url', '—')}")
    click.echo(f"  Agent name  : {cfg.get('agent_name', '—')}")
    click.echo(f"  Token file  : {'✓' if (config_dir / 'agent.token').exists() else '✗ (not registered)'}")
    click.echo(f"  Private key : {'✓' if (config_dir / 'private.pem').exists() else '✗ (not generated)'}")
    h_info = host_mod.collect()
    click.echo(f"  Host        : {h_info.get('hostname')} ({h_info.get('os')})")
    click.echo(f"  Docker      : {h_info.get('docker_version') or '✗ not found'}")


def main():
    cli()

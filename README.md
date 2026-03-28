# pyexec-worker

Local execution agent for [PyExecutor](https://github.com/pyexechq/).

Allows workflow steps to run on-premises instead of (or alongside) the cloud worker.

## Quick start

```bash
pip install pyexec-worker

# Generate keys + register with your PyExecutor server
pyexec-worker register \
  --server https://your-pyexec-server.example.com \
  --org-token <token-from-settings> \
  --name "Office Server"

# Start the agent
pyexec-worker start
```

## Installation

```bash
pip install pyexec-worker
```

## Requirements

- Python 3.9+
- Docker (for script step execution)
- Network access to your PyExecutor server

## Configuration

Settings are stored in `~/.pyexec-worker/config.json`.
The agent token is stored separately in `~/.pyexec-worker/agent.token` (chmod 600).

| Environment variable     | Description                              | Default                   |
|--------------------------|------------------------------------------|---------------------------|
| `PYEXEC_SERVER_URL`      | PyExecutor server URL                    | `http://localhost:8000`   |
| `PYEXEC_AGENT_TOKEN`     | Agent bearer token (overrides file)      | —                         |
| `PYEXEC_AGENT_NAME`      | Display name for this agent              | hostname                  |
| `PYEXEC_POLL_INTERVAL`   | HTTP poll interval (seconds)             | `5`                       |
| `PYEXEC_HEARTBEAT_INTERVAL` | Heartbeat interval (seconds)          | `30`                      |
| `PYEXEC_MAX_CONCURRENT`  | Maximum concurrent steps                 | `4`                       |
| `PYEXEC_DOCKER_IMAGE`    | Default Docker image for script steps    | `python:3.11-slim`        |
| `PYEXEC_USE_WEBSOCKET`   | Use WebSocket transport (`true`/`false`) | `true`                    |

## Security

- RSA-2048 key pair generated on first `register` — private key never leaves your machine.
- Org secrets are encrypted server-side under your agent's public key before delivery.
- The agent token is stored at `~/.pyexec-worker/agent.token` with mode 600.

## Commands

```
pyexec-worker register  --server URL --org-token TOKEN [--name NAME]
pyexec-worker start     [--server URL]
pyexec-worker status
```

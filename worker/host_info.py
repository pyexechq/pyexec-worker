"""
host_info.py — Collect host / runtime metadata reported to the server.
"""

import platform
import shutil
import subprocess


def collect() -> dict:
    info = {
        'hostname': platform.node(),
        'os': f'{platform.system()} {platform.release()}',
        'python_version': platform.python_version(),
        'cpu_count': None,
        'mem_total_gb': None,
        'docker_version': None,
        'worker_version': _worker_version(),
    }

    try:
        import psutil
        info['cpu_count'] = psutil.cpu_count(logical=True)
        info['mem_total_gb'] = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except ImportError:
        pass

    docker_bin = shutil.which('docker')
    if docker_bin:
        try:
            out = subprocess.check_output(
                ['docker', 'version', '--format', '{{.Server.Version}}'],
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            info['docker_version'] = out.decode().strip()
        except Exception:
            pass

    return info


def _worker_version() -> str:
    try:
        from importlib.metadata import version
        return version('pyexec-worker')
    except Exception:
        return 'dev'

"""Lectura real de recursos del host con psutil."""

from __future__ import annotations

import os
from typing import Dict

import psutil

_GB = 1024 ** 3
_MB = 1024 ** 2

psutil.cpu_percent(interval=None)


def read_system_resources() -> Dict[str, Dict[str, float]]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    net = psutil.net_io_counters()
    process = psutil.Process()
    freq = psutil.cpu_freq()
    return {
        "cpu": {
            "uso_porcentaje": psutil.cpu_percent(interval=None),
            "nucleos_logicos": psutil.cpu_count(logical=True) or 0,
            "frecuencia_mhz": round(freq.current, 0) if freq else 0.0,
        },
        "memoria": {
            "uso_porcentaje": memory.percent,
            "total_gb": round(memory.total / _GB, 2),
            "usada_gb": round(memory.used / _GB, 2),
            "disponible_gb": round(memory.available / _GB, 2),
        },
        "disco": {
            "uso_porcentaje": disk.percent,
            "total_gb": round(disk.total / _GB, 2),
            "usado_gb": round(disk.used / _GB, 2),
            "disponible_gb": round(disk.free / _GB, 2),
        },
        "red": {
            "enviados_mb": round(net.bytes_sent / _MB, 2),
            "recibidos_mb": round(net.bytes_recv / _MB, 2),
        },
        "proceso": {
            "memoria_mb": round(process.memory_info().rss / _MB, 2),
            "hilos": process.num_threads(),
        },
    }

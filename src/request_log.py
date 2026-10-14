"""Ring buffer of recent Modbus requests, shown on the UI 'Request log' page."""
import threading
import time
from collections import deque

FC_NAMES = {1: "Read Coils", 2: "Read Discrete Inputs", 3: "Read Holding", 4: "Read Input",
            5: "Write Coil", 6: "Write Register", 15: "Write Coils", 16: "Write Registers"}

_entries = deque(maxlen=500)
_lock = threading.Lock()
_seq = 0


def add(unit_id, fc, address, count, ok, error=None, client=None, device=None):
    global _seq
    with _lock:
        _seq += 1
        _entries.append({
            "seq": _seq,
            "ts": time.time(),
            "unit_id": unit_id,
            "device": device,
            "fc": fc,
            "fc_name": FC_NAMES.get(fc, f"FC{fc}") if fc else "-",
            "address": address,
            "count": count,
            "ok": ok,
            "error": error,
            "client": client,
        })


def recent(limit=500):
    with _lock:
        return list(_entries)[-limit:][::-1]


def clear():
    with _lock:
        _entries.clear()

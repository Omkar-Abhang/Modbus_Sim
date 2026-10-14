"""Simulated value generators and the default simulation guess for imported templates."""
import math
import random
import re
import zlib

MODES = ("random", "sine", "counter", "toggle")


def default_sim(reg):
    """Guess a realistic simulation for a register from its zone / measurement / type."""
    zone = str(reg.get("zone", "")).upper()
    measurement = str(reg.get("measurement", "")).lower()
    name = str(reg.get("name", "")).lower()

    if reg.get("decode_type") == "bit" or reg.get("input_type") == "state" or "STATUS" in zone:
        return {"mode": "toggle", "min": 0, "max": 1, "on_s": 300, "off_s": 60}
    if re.fullmatch(r"V[123]N|AVLN|VLN", zone):
        return {"mode": "random", "min": 228, "max": 236}
    if re.fullmatch(r"V12|V23|V31|AVLL|VLL", zone):
        return {"mode": "random", "min": 395, "max": 410}
    if re.fullmatch(r"I[123N]?|AI|IN", zone) or measurement == "current":
        return {"mode": "sine", "min": 5, "max": 30, "period_s": 3600}
    if re.fullmatch(r"(KWH|KVAH|KVARH|EXPKWH|IMPKWH|NETKWH).*", zone) or measurement == "energy":
        return {"mode": "counter", "start": 1000, "rate_per_hour": 5}
    if re.fullmatch(r"T?KW[123]?|MAXKW|MINKW", zone) or measurement == "power":
        return {"mode": "sine", "min": 1, "max": 15, "period_s": 3600}
    if re.fullmatch(r"T?KVAR?[123]?|MAXKVAR?|MINKVAR", zone):
        return {"mode": "sine", "min": 1, "max": 18, "period_s": 3600}
    if re.fullmatch(r"A?PF[123]?", zone):
        return {"mode": "random", "min": 0.85, "max": 0.99}
    if zone in ("F", "FREQ", "HZ") or "frequency" in name:
        return {"mode": "random", "min": 49.9, "max": 50.1}
    if measurement == "temperature" or "TEMP" in zone or "temperature" in name:
        return {"mode": "sine", "min": 22, "max": 30, "period_s": 86400}
    if measurement == "humidity" or "HUMI" in zone or "humidity" in name:
        return {"mode": "sine", "min": 40, "max": 60, "period_s": 86400}
    return {"mode": "random", "min": 0, "max": 100}


def _phase(key, period):
    """Stable per device+zone phase so devices of the same template don't move in lockstep."""
    return (zlib.crc32(key.encode()) % 10000) / 10000 * period


def _num(sim, key, default):
    """sim[key] as float; 0 is a valid value, only missing / empty falls back to the default."""
    value = sim.get(key)
    try:
        return float(default if value is None or value == "" else value)
    except (TypeError, ValueError):
        return float(default)


def generate(sim, t, key, started_at):
    """Engineering value of one zone at unix time t."""
    mode = sim.get("mode", "random")
    lo = _num(sim, "min", 0)
    hi = _num(sim, "max", 100)

    if mode == "sine":
        period = max(_num(sim, "period_s", 3600), 1)
        x = 2 * math.pi * (t + _phase(key, period)) / period
        value = lo + (hi - lo) * (0.5 + 0.5 * math.sin(x))
    elif mode == "counter":
        value = _num(sim, "start", 0) + _num(sim, "rate_per_hour", 1) * max(t - started_at, 0) / 3600
    elif mode == "toggle":
        on_s = max(_num(sim, "on_s", 60), 0)
        off_s = max(_num(sim, "off_s", 60), 0)
        cycle = on_s + off_s
        if cycle <= 0:
            return hi
        return hi if (t + _phase(key, cycle)) % cycle < on_s else lo
    else:
        value = random.uniform(lo, hi) if hi > lo else lo

    decimals = sim.get("decimals")
    return round(value, int(decimals)) if decimals is not None else round(value, 3)

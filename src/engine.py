"""
Simulation engine: current values and register images of every simulated device.

Values are generated lazily when a Modbus request arrives (or the UI asks), and cached for CACHE_S seconds so that
all batch reads of one gateway poll see the same snapshot (float32 halves never split between two values).
"""
import threading
import time
from collections import deque

from src import store
from src.encoding import build_image, decode_words, register_kind, register_span
from src.generators import generate
from src.templates import BIT_FUNC_TYPES

CACHE_S = 1.0

# Modbus function code -> register table
FC_TABLE = {1: "coil", 5: "coil", 15: "coil", 2: "discrete_input", 3: "holding", 6: "holding", 16: "holding",
            4: "input"}
SUB_REGISTER_TABLE = {"holding": "holding", "input": "input", "coils": "coil", "coil": "coil",
                      "discrete_input": "discrete_input"}


class DeviceStats:
    def __init__(self):
        self.polls = deque(maxlen=2000)  # timestamps of successful reads
        self.errors = 0
        self.last_poll = None
        self.last_error = None
        self.last_client = None


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.cache = {}  # device_id -> (timestamp, values, images)
        self.stats = {}  # device_id -> DeviceStats
        self.writes = {}  # device_id -> {(table, address): value}

    # ---- lookup -------------------------------------------------------------------------------------------
    def device_by_unit(self, unit_id):
        for d in store.devices.all():
            if d["unit_id"] == unit_id and d.get("enabled", True):
                return d
        return None

    def stats_for(self, device_id):
        with self.lock:
            return self.stats.setdefault(device_id, DeviceStats())

    def invalidate(self, device_id=None):
        with self.lock:
            if device_id is None:
                self.cache.clear()
            else:
                self.cache.pop(device_id, None)

    # ---- values -------------------------------------------------------------------------------------------
    def snapshot(self, device, force=False):
        """(values, images) for a device; images = {table: {address: word_or_bit}}."""
        now = time.time()
        with self.lock:
            cached = self.cache.get(device["id"])
            if cached and not force and now - cached[0] < CACHE_S:
                return cached[1], cached[2]

        template = store.templates.get(device["template_id"])
        if not template:
            return {}, {}

        overrides = device.get("overrides") or {}
        started_at = device.get("created_at", now)
        values = {}
        for reg in template["in_registers"]:
            sim = dict(reg.get("sim") or {}, **(overrides.get(reg["zone"]) or {}))
            values[reg["zone"]] = generate(sim, now, f"{device['id']}:{reg['zone']}", started_at)

        images = {}
        func_type = template["register_func_type"]
        for reg in template["in_registers"]:
            table = SUB_REGISTER_TABLE.get(reg.get("sub_register_type"), "holding") if func_type == "all" else func_type
            images.setdefault(table, []).append(reg)
        images = {
            table: build_image(regs, values, template["byte_order"], template["word_order"],
                               bit_mode=table in BIT_FUNC_TYPES)
            for table, regs in images.items()
        }

        # writes from the gateway (FC05/06/15/16) stay until cleared from the UI
        for (table, address), value in (self.writes.get(device["id"]) or {}).items():
            images.setdefault(table, {})[address] = value

        # every batch address must answer, unused ones read as 0
        for b in template.get("batches", []):
            table_img = images.setdefault(func_type if func_type != "all" else "holding", {})
            for a in range(b["address"], b["address"] + b["count"]):
                table_img.setdefault(a, 0)

        with self.lock:
            self.cache[device["id"]] = (now, values, images)
        return values, images

    def zone_view(self, device):
        """Per-zone engineering value + raw words, for the UI."""
        template = store.templates.get(device["template_id"]) or {"in_registers": []}
        values, images = self.snapshot(device)
        overrides = device.get("overrides") or {}
        func_type = template.get("register_func_type")
        rows = []
        for reg in template["in_registers"]:
            table = SUB_REGISTER_TABLE.get(reg.get("sub_register_type"), "holding") if func_type == "all" else func_type
            img = images.get(table, {})
            span = 1 if table in BIT_FUNC_TYPES else register_span(reg)
            words = [img.get(reg["register_address"] + i, 0) for i in range(span)]
            kind = "bit" if table in BIT_FUNC_TYPES else register_kind(reg)
            sent = values.get(reg["zone"])
            if kind not in ("bit",) and words:
                try:
                    sent = round(decode_words(kind, words, template["byte_order"], template["word_order"])
                                 * float(reg.get("multiplier") or 1), 3)
                except Exception:
                    pass
            rows.append({
                "zone": reg["zone"],
                "name": reg.get("name"),
                "measurement": reg.get("measurement"),
                "register_address": reg["register_address"],
                "table": table,
                "kind": kind,
                "bit": reg.get("size_bits") if kind == "bit" else None,
                "value": values.get(reg["zone"]),
                "gateway_value": sent,  # what the gateway will decode
                "words": [f"0x{w:04X}" if not isinstance(w, bool) else int(w) for w in words],
                "sim": dict(reg.get("sim") or {}, **(overrides.get(reg["zone"]) or {})),
                "overridden": reg["zone"] in overrides,
            })
        return rows

    # ---- modbus access ------------------------------------------------------------------------------------
    def read(self, device, fc, address, count):
        """Return list of values, or None if any address is not part of the device (-> IllegalAddress)."""
        _, images = self.snapshot(device)
        img = images.get(FC_TABLE.get(fc), {})
        out = []
        for a in range(address, address + count):
            if a not in img:
                return None
            out.append(img[a])
        return out

    def write(self, device, fc, address, values):
        table = FC_TABLE.get(fc)
        with self.lock:
            dev_writes = self.writes.setdefault(device["id"], {})
            for i, v in enumerate(values):
                dev_writes[(table, address + i)] = int(v)
            self.cache.pop(device["id"], None)

    def clear_writes(self, device_id):
        with self.lock:
            self.writes.pop(device_id, None)
            self.cache.pop(device_id, None)

    def writes_view(self, device_id):
        with self.lock:
            return [{"table": t, "address": a, "value": v} for (t, a), v in sorted((self.writes.get(device_id) or {}).items())]


engine = Engine()

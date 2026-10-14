"""Template helpers: gateway import/export, validation and automatic batches."""
import json

from src.config import MAX_BATCH
from src.encoding import register_kind, register_span
from src.generators import default_sim

# register_func_type values the gateway can poll over Modbus TCP (get_modbus_data_TCP)
TCP_FUNC_TYPES = ("input", "holding", "discrete_input")
BIT_FUNC_TYPES = ("coil", "discrete_input")

REGISTER_FIELDS = ("register_address", "zone", "measurement", "name", "size_bits", "count_registers",
                   "decode_type", "multiplier", "input_type", "min_alarm", "max_alarm", "hysteresis",
                   "sub_register_type")


def parse_batches(batches):
    if isinstance(batches, str):
        try:
            batches = json.loads(batches or "[]")
        except ValueError:
            batches = []
    return [{"address": int(b["address"]), "count": int(b["count"])} for b in batches or []
            if "address" in b and "count" in b]


def auto_batches(template):
    """Contiguous blocks covering every register (gaps <= 10 are bridged, max MAX_BATCH per block)."""
    spans = sorted(
        (int(r["register_address"]), int(r["register_address"]) + register_span(r))
        for r in template.get("in_registers", [])
    )
    batches = []
    for start, end in spans:
        if batches:
            last = batches[-1]
            last_end = last["address"] + last["count"]
            if start <= last_end + 10 and end - last["address"] <= MAX_BATCH:
                last["count"] = max(last_end, end) - last["address"]
                continue
        batches.append({"address": start, "count": end - start})
    return batches


def is_tcp_ready(template):
    return template.get("sub_type") == "MOD-TCP" and template.get("register_func_type") in TCP_FUNC_TYPES


def normalize_register(reg):
    out = {k: reg[k] for k in REGISTER_FIELDS if k in reg}
    out["register_address"] = int(out.get("register_address", 0))
    out["zone"] = str(out.get("zone", "")).strip()
    out.setdefault("measurement", "misc")
    out.setdefault("name", out["zone"])
    out.setdefault("decode_type", "int")
    out.setdefault("size_bits", 16)
    out.setdefault("count_registers", 1)
    out.setdefault("multiplier", 1)
    out.setdefault("input_type", "analog")
    out["sim"] = dict(reg.get("sim") or default_sim(out))
    return out


def normalize_template(tpl, source="custom"):
    out = {
        "name": str(tpl.get("name", "")).strip() or "Untitled",
        "source": tpl.get("source", source),
        "gateway_id": tpl.get("gateway_id"),
        "sub_type": tpl.get("sub_type", "MOD-TCP"),
        "register_func_type": tpl.get("register_func_type", "holding"),
        "byte_order": tpl.get("byte_order", "big"),
        "word_order": tpl.get("word_order", "big"),
        "poll_interval": int(tpl.get("poll_interval") or 10),
        "description": tpl.get("description", ""),
        "in_registers": [normalize_register(r) for r in tpl.get("in_registers", [])],
    }
    out["in_registers"].sort(key=lambda r: (r["register_address"], r.get("size_bits", 0)))
    out["batches"] = parse_batches(tpl.get("batches")) or auto_batches(out)
    return out


def validate_template(tpl):
    """Return a list of human readable problems (empty = OK)."""
    problems = []
    if tpl["byte_order"] not in ("big", "little") or tpl["word_order"] not in ("big", "little"):
        problems.append("byte_order / word_order must be 'big' or 'little'")
    if tpl["register_func_type"] not in ("input", "holding", "discrete_input", "coil", "all"):
        problems.append(f"Unknown register_func_type '{tpl['register_func_type']}'")

    zones = set()
    used = {}  # address -> zone (non-bit registers)
    bits = {}  # (address, bit) -> zone
    for r in tpl["in_registers"]:
        zone = r["zone"]
        if not zone:
            problems.append(f"Register at address {r['register_address']} has no zone")
        elif zone in zones:
            problems.append(f"Duplicate zone '{zone}'")
        zones.add(zone)

        if register_kind(r) == "bit" and tpl["register_func_type"] not in BIT_FUNC_TYPES:
            pos = int(r.get("size_bits") or 0)
            if not 1 <= pos <= 16:
                problems.append(f"{zone}: bit position must be 1-16 (got {pos})")
            if (r["register_address"], pos) in bits:
                problems.append(f"{zone}: bit {pos} of address {r['register_address']} "
                                f"already used by {bits[(r['register_address'], pos)]}")
            bits[(r["register_address"], pos)] = zone
            if r["register_address"] in used:
                problems.append(f"{zone}: address {r['register_address']} already used by {used[r['register_address']]}")
            continue

        for a in range(r["register_address"], r["register_address"] + register_span(r)):
            other = used.get(a) or next((z for (ba, _), z in bits.items() if ba == a), None)
            if other:
                problems.append(f"{zone}: address {a} overlaps {other}")
            used[a] = zone

    for b in tpl["batches"]:
        if not 1 <= b["count"] <= 125:
            problems.append(f"Batch at {b['address']} has count {b['count']} (must be 1-125)")
    covered = {a for b in tpl["batches"] for a in range(b["address"], b["address"] + b["count"])}
    for r in tpl["in_registers"]:
        missing = [a for a in range(r["register_address"], r["register_address"] + register_span(r)) if a not in covered]
        if missing:
            problems.append(f"{r['zone']}: address {missing[0]} is not in any batch - the gateway will never read it")
    return problems


def from_gateway_file(data):
    """Templates from a gateway templates.json (or a {"modbus_templates": [...]} export)."""
    items = data.get("modbus_templates", data if isinstance(data, list) else [])
    out = []
    for t in items:
        tpl = normalize_template(dict(t, source="gateway", gateway_id=t.get("id")), source="gateway")
        out.append(tpl)
    return out


def to_gateway(tpl):
    """One template in the exact shape iam-gateway /dbexpimp/import expects (modbus_templates item)."""
    sub_type = "MOD-TCP"
    total = max([r["register_address"] + register_span(r) for r in tpl["in_registers"]] or [0])
    return {
        "port": "localhost:502",
        "baud_rate": 9600,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "total_register": total,
        "register_offset": 0,
        "batches": json.dumps(tpl["batches"]),
        "word_order": tpl["word_order"],
        "byte_order": tpl["byte_order"],
        "batch_retry_times": 1,
        "timeout": 2,
        "poll_interval": tpl.get("poll_interval", 10),
        "save_interval": tpl.get("poll_interval", 10),
        "rt_interval": 30,
        "local_storage_enable": True,
        "cloud_storage_enable": True,
        "rt_enable": True,
        "register_func_type": tpl["register_func_type"],
        "device_type": "MOD",
        "sub_type": sub_type,
        "model": tpl["name"],
        "name": tpl["name"],
        "in_registers": [
            {
                "register_address": r["register_address"],
                "measurement": r.get("measurement", "misc"),
                "size_bits": r.get("size_bits", 16),
                "count_registers": r.get("count_registers", 1),
                "decode_type": r.get("decode_type", "int"),
                "sub_type": sub_type,
                "zone": r["zone"],
                "device_type": "MOD",
                "master_device_id": 0,
                "input_type": r.get("input_type", "analog"),
                "name": r.get("name") or r["zone"],
                "min_alarm": r.get("min_alarm", 0),
                "max_alarm": r.get("max_alarm", 0),
                "hysteresis": r.get("hysteresis", 0),
                "multiplier": r.get("multiplier", 1),
                "sub_register_type": r.get("sub_register_type"),
            }
            for r in tpl["in_registers"]
        ],
        "out_registers": [],
    }

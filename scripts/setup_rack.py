"""
Create the rack monitoring simulation in a running simulator: 4 templates + 6 devices for one rack,
export the templates for the gateway, and print the gateway commands + device_mapping.json entries.

    .venv/bin/python scripts/setup_rack.py --pc-ip 10.129.2.26 --gateway-ip 10.129.2.23 --panel-no TEST-PAN-0023

Safe to run again: templates are updated by name, existing devices (same name + unit) are kept.
Only talks to the simulator API - it never calls the gateway, it only prints the commands.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def reg(address, zone, name, measurement, kind, sim, multiplier=1):
    types = {"float32": (32, "float", 2), "int16": (16, "int", 1)}
    size_bits, decode_type, count = types[kind]
    return {"register_address": address, "zone": zone, "name": name, "measurement": measurement,
            "size_bits": size_bits, "decode_type": decode_type, "count_registers": count,
            "multiplier": multiplier, "input_type": "analog", "sim": sim}


def rnd(lo, hi):
    return {"mode": "random", "min": lo, "max": hi}


def sine(lo, hi, period_s):
    return {"mode": "sine", "min": lo, "max": hi, "period_s": period_s}


HOUR, DAY = 3600, 86400

TEMPLATES = {
    "Rack Energy Meter": [
        reg(0, "V1N", "Voltage L-N", "voltage", "float32", rnd(228, 236)),
        reg(2, "AI", "Average Current", "current", "float32", sine(4, 16, HOUR)),
        reg(4, "TKW", "Total kW", "power", "float32", sine(0.8, 3.5, HOUR)),
    ],
    "Rack Temperature Sensor": [
        reg(0, "CT", "Rack Temperature", "misc", "int16", sine(22, 28, DAY), multiplier=0.1),
    ],
    "Rack UPS": [
        reg(0, "ANALOGINPUT:1570", "UPS Output Load", "misc", "float32", rnd(30, 60)),
        reg(2, "ANALOGINPUT:2240", "UPS Battery Health", "misc", "float32", rnd(90, 100)),
        reg(4, "ANALOGINPUT:239", "UPS Health Status", "voltage", "float32", rnd(225, 235)),
    ],
    "Rack Cooling Panel": [
        reg(0, "STATUS", "Cooling Panel Status", "event", "int16",
            {"mode": "toggle", "min": 0, "max": 1, "on_s": 3600, "off_s": 300}),
        reg(2, "SUPPLYAIRTEMP", "Supply Air Temperature", "temperature", "float32", sine(16, 20, DAY)),
        reg(4, "RETAIRTEMP", "Return Air Temperature", "temperature", "float32", sine(24, 30, DAY)),
        reg(6, "SUPPLYAIRHUMI", "Supply Air Humidity", "humidity", "float32", sine(40, 50, DAY)),
        reg(8, "RETAIRHUMI", "Return Air Humidity", "humidity", "float32", sine(45, 60, DAY)),
        reg(10, "COMPHP", "Compressor High Pressure", "misc", "float32", rnd(15, 18)),
        reg(12, "COMPLP", "Compressor Low Pressure", "misc", "float32", rnd(4, 6)),
        reg(14, "COMPSPEED", "Compressor Speed", "misc", "float32", sine(40, 90, HOUR)),
        reg(16, "COMPI", "Compressor Current", "current", "float32", sine(3, 8, HOUR)),
    ],
}

# key -> (device name suffix, template, default unit id)
DEVICES = {
    "power_a": ("Power A meter", "Rack Energy Meter", 41),
    "power_b": ("Power B meter", "Rack Energy Meter", 42),
    "temp_front": ("Front temperature", "Rack Temperature Sensor", 43),
    "temp_rear": ("Rear temperature", "Rack Temperature Sensor", 44),
    "cooling": ("Cooling panel", "Rack Cooling Panel", 45),
    "ups": ("UPS", "Rack UPS", 46),
}

# rack dashboard parameters (device_mapping.json) -> (device key, zone, measurement)
DASHBOARD = [
    ("Power Source A", "power_a", "V1N", "voltage"),
    ("Power Source B", "power_b", "V1N", "voltage"),
    ("Power A Current", "power_a", "AI", "current"),
    ("Power A Voltage", "power_a", "V1N", "voltage"),
    ("Power A Kw", "power_a", "TKW", "power"),
    ("Power B Current", "power_b", "AI", "current"),
    ("Power B Voltage", "power_b", "V1N", "voltage"),
    ("Power B Kw", "power_b", "TKW", "power"),
    ("Front Temperature", "temp_front", "CT", "misc"),
    ("Rear Temperature", "temp_rear", "CT", "misc"),
    ("UPS Output Load", "ups", "ANALOGINPUT:1570", "misc"),
    ("UPS Battery Health", "ups", "ANALOGINPUT:2240", "misc"),
    ("UPS Health Status", "ups", "ANALOGINPUT:239", "voltage"),
    ("Cooling Panel Status", "cooling", "STATUS", "event"),
    ("Cooling Panel Supply Temperature", "cooling", "SUPPLYAIRTEMP", "temperature"),
    ("Cooling Panel Return Temperature", "cooling", "RETAIRTEMP", "temperature"),
    ("Cooling Panel Supply Humidity", "cooling", "SUPPLYAIRHUMI", "humidity"),
    ("Cooling Panel Return Humidity", "cooling", "RETAIRHUMI", "humidity"),
    ("Cooling Panel High Pressure", "cooling", "COMPHP", "misc"),
    ("Cooling Panel Low Pressure", "cooling", "COMPLP", "misc"),
    ("Cooling Panel Compressor Speed", "cooling", "COMPSPEED", "misc"),
    ("Cooling Panel Compressor Status", "cooling", "COMPI", "current"),
]


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        sys.exit(f"{method} {path} failed ({e.code}): {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach the simulator at {base} ({e.reason}). Is `python main.py` running?")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://127.0.0.1:15001", help="simulator URL")
    p.add_argument("--rack", default="Sim Rack 1", help="rack name used for device names and the mapping key")
    p.add_argument("--pc-ip", default="<pc-ip>", help="this PC's IP as seen from the gateway")
    p.add_argument("--modbus-port", type=int, default=5020)
    p.add_argument("--gateway-ip", default="<gateway-ip>")
    p.add_argument("--panel-no", default="<gateway PANEL_NO>", help="gateway panel_no tag, e.g. TEST-PAN-0023")
    p.add_argument("--influx-port", type=int, default=8086)
    for key, (_, _, unit) in DEVICES.items():
        p.add_argument(f"--{key.replace('_', '-')}-unit", type=int, default=unit, dest=f"{key}_unit")
    p.add_argument("--export", default="rack_templates_for_gateway.json", help="export file for the gateway import")
    args = p.parse_args()

    # ---- 1. templates (update by name, else create)
    existing = {t["name"]: t for t in call(args.api, "GET", "/api/templates")}
    template_ids = {}
    print("Templates")
    for name, registers in TEMPLATES.items():
        body = {"name": name, "register_func_type": "holding", "byte_order": "big", "word_order": "big",
                "poll_interval": 10, "batches": [], "in_registers": registers}
        if name in existing:
            saved = call(args.api, "PUT", f"/api/templates/{existing[name]['id']}", body)
            action = "updated"
        else:
            saved = call(args.api, "POST", "/api/templates", body)
            action = "created"
        template_ids[name] = saved["id"]
        status = "OK" if not saved["problems"] else "; ".join(saved["problems"])
        print(f"  {action:8} #{saved['id']:<4} {name:<26} {len(registers)} registers  {status}")

    # ---- 2. devices
    devices = call(args.api, "GET", "/api/devices")
    by_unit = {d["unit_id"]: d for d in devices}
    units = {}
    print("\nDevices")
    for key, (suffix, template, _) in DEVICES.items():
        unit = getattr(args, f"{key}_unit")
        name = f"{args.rack} {suffix}"
        units[key] = unit
        current = by_unit.get(unit)
        if current and current["name"] != name:
            sys.exit(f"Unit {unit} is already used by '{current['name']}'. Pick another with --{key.replace('_', '-')}-unit")
        body = {"name": name, "template_id": template_ids[template], "unit_id": unit, "enabled": True, "overrides": {}}
        if current:
            call(args.api, "PUT", f"/api/devices/{current['id']}", dict(body, overrides=current.get("overrides") or {}))
            action = "kept"
        else:
            call(args.api, "POST", "/api/devices", body)
            action = "created"
        print(f"  {action:8} unit {unit:<4} MOD{unit:02d}  {name:<34} ({template})")

    # ---- 3. export for the gateway
    ids = ",".join(str(i) for i in template_ids.values())
    with urllib.request.urlopen(f"{args.api}/api/templates/export?ids={ids}", timeout=10) as r:
        export = json.load(r)
    with open(args.export, "w") as f:
        json.dump(export, f, indent=1)
    print(f"\nGateway template file written: {args.export}")

    # ---- 4. gateway commands
    gw = f"http://{args.gateway_ip}:5001"
    port = f"{args.pc_ip}:{args.modbus_port}"
    print(f"""
================ ON THE GATEWAY ({args.gateway_ip}) ================
# a) import the 4 templates (ADDS them - never use delete_existing=true)
curl -X POST "{gw}/dbexpimp/import?template=modbus_templates&delete_existing=false" \\
  -H "Content-Type: application/json" -d @{args.export}

# b) note the new ids of: {', '.join(TEMPLATES)}
curl -s {gw}/devices/modbus/listTemplate | python3 -m json.tool | grep -B3 -A3 '"Rack '

# c) add the 6 devices (replace <id ...> with the ids from b)""")
    for key, (suffix, template, _) in DEVICES.items():
        body = json.dumps({"template_id": f"<id {template}>", "slave_id": units[key], "modbus_port": port,
                           "device_code": f"MOD{units[key]:02d}", "device_name": f"{args.rack} {suffix}"})
        print(f"curl -X POST {gw}/devices/modbus/addFromTemplate -H \"Content-Type: application/json\" \\\n  -d '{body}'")
    print("""
# d) restart the gateway service so it starts polling the new devices, then check one value:""")
    print(f'curl -s "{gw}/status_all_device/%7Bunique-tag%7D?unique_tag=MOD{units["power_a"]:02d}-V1N"')

    # ---- 5. rack dashboard mapping
    mapping = [
        {"device_name": name, "ip": args.gateway_ip, "port": args.influx_port, "panel_no": args.panel_no,
         "device_code": f"MOD{units[key]:02d}", "zone": zone, "measurement": measurement}
        for name, key, zone, measurement in DASHBOARD
    ]
    print(f"""
================ RACK DASHBOARD (api/config/device_mapping.json) ================
# add "{args.rack}" to a group in "rack_mapping", then add this key:""")
    print(json.dumps({args.rack: mapping}, indent=4)[2:-2] + ",")


if __name__ == "__main__":
    main()

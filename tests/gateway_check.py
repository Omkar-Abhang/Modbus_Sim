"""
Poll a running simulator exactly like the IESG gateway does, and compare with what the simulator says it serves.

Uses the gateway's own libraries, so run it in a separate venv:
    python3 -m venv .venv-gw && .venv-gw/bin/pip install -r requirements-dev.txt
    .venv-gw/bin/python tests/gateway_check.py --unit 4

Gateway code mirrored: iam-gateway src/devices/modbus/common_.py get_modbus_data_TCP (batch reads with
pyModbusTCP) and src/devices/modbus/mod_ups_tcp.py (BinaryPayloadDecoder + get_converted_value).
"""
import argparse
import json
import sys
import urllib.request

from pyModbusTCP.client import ModbusClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

ORDER = {"little": Endian.Little, "big": Endian.Big}


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return json.load(r)


def get_bit_converted_value(decoded, register):
    if register["decode_type"] == "bit":
        binary_conversion = bin(decoded.decode_16bit_int())
        if binary_conversion[:1] == "-":
            binary_conversion_str = binary_conversion[3:]
        else:
            binary_conversion_str = binary_conversion[2:]
        if register["count_registers"] == 1:
            val = binary_conversion_str.zfill(16)[::-1][register["size_bits"] - 1]
            return int(val, 2)
    return 1


def get_converted_value(decoded, register):
    if register["decode_type"] in ["bit"]:
        return get_bit_converted_value(decoded, register)
    if register["size_bits"] == 32:
        if register["decode_type"] == "float":
            return round(decoded.decode_32bit_float(), 2)
        if register["decode_type"] == "int":
            return decoded.decode_32bit_int()
    if register["size_bits"] == 16:
        if register["decode_type"] == "float":
            return round(decoded.decode_16bit_float(), 2)
        if register["decode_type"] == "int":
            return decoded.decode_16bit_int()
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--api", default="http://127.0.0.1:15001")
    p.add_argument("--unit", type=int, required=True)
    args = p.parse_args()

    device = next((d for d in api(args.api, "/api/devices") if d["unit_id"] == args.unit), None)
    if not device:
        sys.exit(f"No simulated device with unit id {args.unit}")
    template = api(args.api, f"/api/templates/{device['template_id']}")
    func_type = template["register_func_type"]
    print(f"Unit {args.unit}: {device['name']} · template '{template['name']}' · {func_type} · "
          f"byte {template['byte_order']} / word {template['word_order']} · {len(template['batches'])} batch(es)")

    # --- same as get_modbus_data_TCP
    client = ModbusClient(host=args.host, port=args.port, unit_id=args.unit, timeout=5)
    if not client.open():
        sys.exit(f"Cannot connect to {args.host}:{args.port}")
    data = {}
    for batch in template["batches"]:
        if func_type == "input":
            res = client.read_input_registers(batch["address"], batch["count"])
        elif func_type == "holding":
            res = client.read_holding_registers(batch["address"], batch["count"])
        elif func_type == "discrete_input":
            res = client.read_discrete_inputs(batch["address"], batch["count"])
        else:
            sys.exit(f"register_func_type '{func_type}' is not polled over TCP by the gateway")
        if not res:
            sys.exit(f"Batch {batch} failed: {client.last_error_txt() if hasattr(client, 'last_error_txt') else client.last_error()}")
        for j, i in enumerate(range(batch["address"], batch["address"] + batch["count"])):
            data[i] = res[j]
    client.close()

    expected = {z["zone"]: z for z in api(args.api, f"/api/devices/{device['id']}/values")["zones"]}

    # --- same as ModbusTCP.poll_thread decoding
    failures = 0
    for reg in template["in_registers"]:
        try:
            regs = [data[reg["register_address"] + i] for i in range(reg["count_registers"])]
        except KeyError as e:
            print(f"  ✗ {reg['zone']:<14} address {e} was not read by any batch")
            failures += 1
            continue
        decoder = BinaryPayloadDecoder.fromRegisters(regs, byteorder=ORDER[template["byte_order"]],
                                                     wordorder=ORDER[template["word_order"]])
        value = get_converted_value(decoder, reg)
        if value is None:
            print(f"  - {reg['zone']:<14} type ({reg['size_bits']},{reg['decode_type']},{reg['count_registers']}) "
                  f"is not decoded by the gateway either")
            continue
        if reg["decode_type"] != "bit":
            value = value * float(reg.get("multiplier") or 1)
        sim = expected[reg["zone"]]["value"]
        tolerance = max(0.02, abs(float(reg.get("multiplier") or 1)))
        ok = abs(float(value) - float(sim)) <= tolerance
        failures += not ok
        print(f"  {'✓' if ok else '✗'} {reg['zone']:<14} gateway reads {round(value, 3):>12}   simulator value {sim}")

    print(f"\n{len(template['in_registers'])} zones, {failures} mismatch(es)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

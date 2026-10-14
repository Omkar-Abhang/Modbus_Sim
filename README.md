# modbus_device_simulator

Simulates any Modbus TCP device (energy meter, UPS, PDU, cooling unit, door/fire inputs, ...) on your PC so the
**IESG gateway** (`realcount_new_stack/iam-gateway`) can poll it like real hardware. The gateway stores the values in
its InfluxDB as usual, so the rack dashboard and logbook show them.

```
 PC                                                     Raspberry Pi gateway
┌──────────────────────────────────────┐   Modbus TCP   ┌───────────────────────────────┐
│ modbus_device_simulator              │◀──────────────│ iam-gateway (MOD-TCP device,   │
│  UI / API   :15001                   │  unit = slave  │ port "<pc-ip>:5020")           │
│  Modbus TCP :5020 (unit 1-247)       │──────────────▶│   → InfluxDB → dashboard       │
└──────────────────────────────────────┘                └───────────────────────────────┘
```

- **Templates** describe a device type: registers, data type, byte/word order, multiplier, how each value is simulated.
  Import the gateway's own `templates.json` (exact register maps) or build your own in the UI.
- **Devices** are template instances on a unit id. Every device shares one TCP port; the gateway picks one with
  `slave_id`.
- **Values**: random in a range, sine wave (daily temperature or load curve), counter (kWh), and toggle (status, door, alarm bits).
  Set them per template, and optionally per device.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ui && npm install && npm run build && cd ..
.venv/bin/python main.py            # UI on http://localhost:15001, Modbus TCP on :5020
```

Docker:

```bash
PUBLIC_HOST=<this-pc-ip> docker compose up -d --build
```

Allow the gateway to reach the PC: `sudo ufw allow 5020/tcp` (if ufw is on). Settings are in `.env` (see
`.env.example`).

> **Rack monitoring setup** (4 templates + 6 devices for the rack dashboard, one command):
> see [docs/RACK_SIMULATION_SETUP.md](docs/RACK_SIMULATION_SETUP.md) and `scripts/setup_rack.py`.

## Step by step: see simulated data on the gateway

1. **Templates → Import templates.json**: upload `iam-gateway/templates.json`. 16 of the 89 templates are
   **TCP-ready** (shown by default).
2. **Devices → Add device**: choose a template and a unit id. To edit the simulation, use **Values**. Live view shows each
   zone's value, what the gateway will decode and the raw register words.
3. Click the **router icon** on the device. It generates the exact gateway commands with your IPs:
   - (custom or modified templates only) **import the template** on the gateway:
     `POST /dbexpimp/import?template=modbus_templates&delete_existing=false`.
     ⚠ Never use `delete_existing=true`: it deletes every template on the gateway.
   - find the template id: `GET /devices/modbus/listTemplate`. The gateway assigns new ids on import, so match by
     name and `MOD-TCP`.
   - `POST /devices/modbus/addFromTemplate` with `modbus_port: "<pc-ip>:5020"`, `slave_id: <unit id>`,
     `device_code: "MODxx"`.
4. Restart the gateway service if polling doesn't start. The Devices page switches to **Polled** when requests
   arrive, and **Request log** shows every read (function, address range, errors, client IP).
5. Data appears in the gateway's Influx with `device_code=MODxx` and the template's zones / measurements. The helper
   also prints `device_mapping.json` entries for the rack dashboard.

## Gateway compatibility (why some templates are "serial only")

The gateway polls over the network **only** for templates with `sub_type: MOD-TCP` and `register_func_type`
`input` (FC04), `holding` (FC03) or `discrete_input` (FC02). See `get_modbus_data_TCP` in
`iam-gateway/src/devices/modbus/common_.py`. `MOD-EM` and the others always open a serial port. To simulate one
of those devices, **clone** it: custom templates are always `MOD-TCP`, then export it to the gateway.

Values are encoded as the exact inverse of the gateway decoder (`mod_ups_tcp.py`, pymodbus 2.5.2
`BinaryPayloadDecoder`):

| Template (`size_bits`, `decode_type`, `count_registers`) | Type | Notes |
|---|---|---|
| 32, float, 2 | float32 | rounded to 2 dp by the gateway |
| 32, int, 2 | signed int32 | |
| 16, int, 1 (or 2) | signed int16 | second register is padding |
| 16, float, 1 | float16 | |
| N, bit, 1 | bit N (1-16) of a register | several zones can share one register |

The gateway multiplies by `multiplier` after decoding, so the simulator sends `value / multiplier`. It answers every
address of every template batch (unused addresses read 0), because one missing address makes the whole block read
fail. Unknown or disabled unit ids get no response, like a missing device.

Gateway writes (FC05/06/15/16) are accepted and shown in the device's values drawer until cleared.

Known gateway quirk: a bit register is decoded through a signed int16, so if **bit 16** is set together with other
bits the gateway misreads the others. Avoid putting bit 16 in a shared register.

## Tests

```bash
.venv/bin/python -m pytest tests                     # encoding vs pymodbus 2.5.2 reference values, generators

# poll a running simulator exactly like the gateway (its own libraries, separate venv)
python3 -m venv .venv-gw && .venv-gw/bin/pip install -r requirements-dev.txt
.venv-gw/bin/python tests/gateway_check.py --unit 4   # every zone: gateway-decoded value vs simulator value
```

## Layout

```
main.py              uvicorn (API + UI) and the Modbus TCP server in one asyncio loop
src/encoding.py      value -> register words (inverse of the gateway decoder)
src/generators.py    random / sine / counter / toggle + default guess from zone / measurement
src/engine.py        per-device register images, built on each request (1 s snapshot)
src/modbus_server.py pymodbus 3.6 server; unit id -> device lookup on every request
src/templates.py     gateway import / export, validation, automatic batches
src/api.py           REST API (/api, docs at /docs) + UI static files
src/store.py         data/templates.json, data/devices.json
scripts/setup_rack.py  creates the rack monitoring simulation (templates, devices, gateway commands, mapping)
ui/                  React + antd UI (Devices, Templates + editor, Request log)
```

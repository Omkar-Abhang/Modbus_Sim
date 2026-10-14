# Rack monitoring simulation: setup procedure

Goal: the PC simulates one complete rack (2 energy meters, 2 temperature sensors, cooling panel, UPS). A **test**
gateway polls it over Modbus TCP and writes to its InfluxDB. The rack dashboard and logbook show the data.

```
PC (modbus_device_simulator)            Test gateway (iam-gateway)              Rack dashboard
UI :15001, Modbus TCP :5020   ◀─poll──  6 MOD-TCP devices, port <pc-ip>:5020    API :14001 reads gateway Influx
units 41-46 = MOD41-MOD46     ──data─▶  InfluxDB (panel_no = gateway PANEL_NO)  ─▶ dashboard + logbook
```

| Device | Template | Unit / device code | Dashboard parameters |
|---|---|---|---|
| Power A meter | Rack Energy Meter | 41 / MOD41 | Power Source A, Power A Voltage / Current / Kw |
| Power B meter | Rack Energy Meter | 42 / MOD42 | Power Source B, Power B Voltage / Current / Kw |
| Front temperature | Rack Temperature Sensor | 43 / MOD43 | Front Temperature |
| Rear temperature | Rack Temperature Sensor | 44 / MOD44 | Rear Temperature |
| Cooling panel | Rack Cooling Panel | 45 / MOD45 | Cooling Panel * (9 parameters) |
| UPS | Rack UPS | 46 / MOD46 | UPS Output Load / Battery Health / Health Status |

> ⚠ Use a **test gateway**, or device codes no real device uses (the default MOD41-MOD46 are unused).
> Never add simulated devices to a production gateway with the codes of real meters (MOD04, MOD06, ...): simulated
> values would be written into the same Influx series as the real readings.

---

## Step 1: Start the simulator (PC)

```bash
cd ~/Desktop/IESG_BACKEND_API/modbus_device_simulator
.venv/bin/python main.py          # first time: see README "Quick start"
```
Open http://localhost:15001. The header shows the Modbus endpoint, e.g. `10.129.2.26:5020`.

Allow the gateway to reach the PC (only if the firewall is on):
```bash
sudo ufw status            # "inactive" → nothing to do
sudo ufw allow 5020/tcp
```

## Step 2: Import the gateway templates (once)

UI → **Templates → Import templates.json** → choose
`realcount_new_stack/iam-gateway/templates.json`. You can skip this if it's already done.

## Step 3: Create the rack in the simulator

```bash
.venv/bin/python scripts/setup_rack.py \
    --pc-ip 10.129.2.26 \
    --gateway-ip <test-gateway-ip> \
    --panel-no <test-gateway PANEL_NO> \
    --influx-port 8086
```
It creates or updates the 4 templates and 6 devices, writes `rack_templates_for_gateway.json`, and prints every
gateway command and the dashboard mapping with your values filled in. You can run it again safely.
- `--rack "Sim Rack 2"` together with `--power-a-unit 51 --power-b-unit 52 ...` creates a second rack.
- Values can be changed later in the UI: **Devices → Values** (one device) or **Templates → edit** (all devices).

Check: **Devices** page lists units 41-46 with status *Waiting for gateway*.

## Step 4: Import the 4 templates on the gateway

Copy `rack_templates_for_gateway.json` to a machine that can reach the gateway, then:
```bash
curl -X POST "http://<gateway-ip>:5001/dbexpimp/import?template=modbus_templates&delete_existing=false" \
  -H "Content-Type: application/json" -d @rack_templates_for_gateway.json
```
> ⚠ `delete_existing` must stay **false**. With `true`, the gateway deletes all of its existing templates.

## Step 5: Find the new template ids on the gateway

```bash
curl -s http://<gateway-ip>:5001/devices/modbus/listTemplate | python3 -m json.tool | grep -B3 -A3 '"Rack '
```
Write down the id of each: Rack Energy Meter, Rack Temperature Sensor, Rack UPS, Rack Cooling Panel.
The gateway assigns new ids on import. If you import twice you get duplicates, so use the **latest** ids.

## Step 6: Add the 6 devices on the gateway

Use the 6 `addFromTemplate` commands printed in step 3. Replace `<id Rack ...>` with the numbers from step 5:
```bash
curl -X POST http://<gateway-ip>:5001/devices/modbus/addFromTemplate -H "Content-Type: application/json" \
  -d '{"template_id": <id Rack Energy Meter>, "slave_id": 41, "modbus_port": "10.129.2.26:5020",
       "device_code": "MOD41", "device_name": "Sim Rack 1 Power A meter"}'
```
`slave_id` must equal the simulator unit id. `modbus_port` must be the PC IP and `:5020`.

## Step 7: Restart the gateway service

The gateway creates its pollers only at startup, so restart the iam-gateway service or container the way you
normally do. Within one poll interval (10 s):
- Simulator **Devices** page: each device shows **Polled …s ago**, and hovering shows the gateway IP.
- Simulator **Request log**: `Read Holding (FC03)` requests from the gateway IP, all **OK**.

## Step 8: Check the data on the gateway

```bash
# live value
curl -s "http://<gateway-ip>:5001/status_all_device/%7Bunique-tag%7D?unique_tag=MOD41-V1N"

# stored in Influx (on the gateway, or from the PC with the influx client)
influx -host <gateway-ip> -port 8086 -username admin -password admin123 -database data \
  -execute "SELECT LAST(value) FROM voltage WHERE device_code='MOD41' AND zone='V1N'"
```
The value should match **Gateway reads** in the simulator's **Values** drawer for that device.

## Step 9: Show it on the rack dashboard

1. Open `vidyutt/additional_code/custom_rack_dashboard/api/config/device_mapping.json`.
2. In `rack_mapping`, add a group, e.g. `"SIM": ["Sim Rack 1"]`.
3. Paste the `"Sim Rack 1": [...]` block that step 3 printed (22 parameters, MOD41-MOD46).
4. Restart the rack dashboard API, open the dashboard, and choose **SIM** in the sidebar. **Logbook** fills in at
   10-minute intervals. The current 10-minute slot shows data once the gateway has stored a value for it.

---

## Troubleshooting

| Symptom | Where to look | Fix |
|---|---|---|
| Device stays *Waiting for gateway* | Request log is empty | Gateway not restarted / wrong `modbus_port` / firewall: from the gateway run `nc -zv <pc-ip> 5020` |
| Request log: *No such unit id* | `unit_id` column | Gateway `slave_id` ≠ simulator unit id, or the device is disabled in the simulator |
| Request log: *Illegal data address* | address range | Gateway has an older or different copy of the template: export it again, import it, re-add the device with the new id |
| Values look wrong (e.g. 1.7e+34) | Values drawer → Raw | Byte / word order of the gateway template differs from the simulator template (re-export) |
| `status_all_device` empty but polled | gateway logs | Device added with the wrong template id (e.g. a MOD-EM one): `curl -X DELETE "http://<gw>:5001/devices/modbus/deleteByCode?device_code=MOD41"`, add again |
| Dashboard shows "-" | mapping | `panel_no`, `device_code` or `zone` in device_mapping.json doesn't match the Influx tags |
| UPS Health shows *Alarm* | Values drawer | Value must be > 219 (dashboard rule); the template default is 225-235 |

## Removing the simulation

1. Gateway: delete the 6 devices, then restart the gateway service:
   ```bash
   for c in MOD41 MOD42 MOD43 MOD44 MOD45 MOD46; do
     curl -X DELETE "http://<gateway-ip>:5001/devices/modbus/deleteByCode?device_code=$c"; done
   ```
2. Simulator UI: delete the 6 devices, then the 4 Rack templates.
3. Dashboard: remove the `SIM` group and the `Sim Rack 1` block from device_mapping.json.

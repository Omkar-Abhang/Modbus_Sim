"""REST API for the simulator UI (mounted under /api) + static UI."""
import json
import os
import socket
import subprocess
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import request_log, store
from src.config import MODBUS_PORT, UI_DIST
from src.engine import engine
from src.generators import MODES, default_sim
from src.templates import (auto_batches, from_gateway_file, is_tcp_ready, normalize_template, to_gateway,
                           validate_template)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- models
class SimConfig(BaseModel):
    mode: str = "random"
    min: float = 0
    max: float = 100
    period_s: Optional[float] = None
    rate_per_hour: Optional[float] = None
    start: Optional[float] = None
    on_s: Optional[float] = None
    off_s: Optional[float] = None
    decimals: Optional[int] = None


class DeviceIn(BaseModel):
    name: str
    template_id: int
    unit_id: int = Field(ge=1, le=247)
    enabled: bool = True
    overrides: Dict[str, SimConfig] = {}


class EnabledIn(BaseModel):
    enabled: bool


# ---------------------------------------------------------------- helpers
def template_summary(t):
    used_by = [d["name"] for d in store.devices.all() if d["template_id"] == t["id"]]
    return {
        "id": t["id"],
        "name": t["name"],
        "source": t.get("source"),
        "modified": t.get("modified", False),
        "gateway_id": t.get("gateway_id"),
        "sub_type": t.get("sub_type"),
        "register_func_type": t.get("register_func_type"),
        "byte_order": t.get("byte_order"),
        "word_order": t.get("word_order"),
        "registers": len(t.get("in_registers", [])),
        "batches": len(t.get("batches", [])),
        "tcp_ready": is_tcp_ready(t),
        "used_by": used_by,
    }


def device_summary(d):
    t = store.templates.get(d["template_id"]) or {}
    stats = engine.stats_for(d["id"])
    now = time.time()
    return dict(
        d,
        template_name=t.get("name", "(deleted template)"),
        tcp_ready=is_tcp_ready(t) if t else False,
        last_poll=stats.last_poll,
        requests_per_min=sum(1 for ts in stats.polls if now - ts <= 60),
        errors=stats.errors,
        last_error=stats.last_error,
        last_client=stats.last_client,
    )


def get_template_or_404(template_id):
    t = store.templates.get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


def get_device_or_404(device_id):
    d = store.devices.get(device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    return d


def check_device(body: DeviceIn, device_id=None):
    get_template_or_404(body.template_id)
    for mode in body.overrides.values():
        if mode.mode not in MODES:
            raise HTTPException(422, f"Unknown sim mode '{mode.mode}'")
    for d in store.devices.all():
        if d["unit_id"] == body.unit_id and d["id"] != device_id:
            raise HTTPException(409, f"Unit id {body.unit_id} is already used by '{d['name']}'")


def local_ips():
    ips = []
    if os.getenv("PUBLIC_HOST"):
        ips.append(os.getenv("PUBLIC_HOST"))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent, just picks the default interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        # "2: enp3s0    inet 10.129.2.26/24 ..." - skip docker / bridge / loopback interfaces
        out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True, timeout=2).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) > 3 and not parts[1].startswith(("lo", "docker", "br-", "veth", "virbr")):
                ips.append(parts[3].split("/")[0])
    except Exception:
        pass
    seen = []
    for ip in ips:
        if ip not in seen and not ip.startswith("127."):
            seen.append(ip)
    return seen


# ---------------------------------------------------------------- info
@router.get("/info")
def info():
    return {"modbus_port": MODBUS_PORT, "ips": local_ips(), "modes": MODES}


# ---------------------------------------------------------------- templates
@router.get("/templates")
def list_templates():
    return sorted((template_summary(t) for t in store.templates.all()), key=lambda t: t["name"].lower())


@router.get("/templates/export")
def export_templates(ids: str = Query(..., description="Comma separated template ids")):
    selected = [get_template_or_404(int(i)) for i in ids.split(",") if i.strip()]
    body = {"modbus_templates": [to_gateway(t) for t in selected]}
    return JSONResponse(body, headers={"Content-Disposition": 'attachment; filename="sim_modbus_templates.json"'})


@router.get("/templates/{template_id}")
def get_template(template_id: int):
    t = get_template_or_404(template_id)
    return dict(t, problems=validate_template(t), tcp_ready=is_tcp_ready(t))


@router.post("/templates")
def create_template(body: dict, clone_from: Optional[int] = None):
    if clone_from:
        src = get_template_or_404(clone_from)
        body = dict(src, name=body.get("name") or f"{src['name']} (copy)")
    # custom templates are always exported to the gateway as MOD-TCP, so they must be modelled as such
    tpl = normalize_template(dict(body, source="custom", gateway_id=None, sub_type="MOD-TCP", modified=False))
    if any(t["name"] == tpl["name"] for t in store.templates.all()):
        raise HTTPException(409, f"A template named '{tpl['name']}' already exists")
    saved = store.templates.add(tpl)
    return dict(saved, problems=validate_template(saved))


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: dict):
    old = get_template_or_404(template_id)
    tpl = normalize_template(dict(body, source=old.get("source", "custom"), gateway_id=old.get("gateway_id")))
    if any(t["name"] == tpl["name"] and t["id"] != template_id for t in store.templates.all()):
        raise HTTPException(409, f"A template named '{tpl['name']}' already exists")
    tpl["modified"] = old.get("source") == "gateway"
    saved = store.templates.put(template_id, tpl)
    engine.invalidate()
    return dict(saved, problems=validate_template(saved))


@router.post("/templates/{template_id}/auto-batches")
def make_batches(template_id: int):
    """Preview batches for the template (not saved)."""
    return auto_batches(get_template_or_404(template_id))


@router.post("/templates/preview")
def preview_template(body: dict):
    """Normalise + validate an unsaved template (used by the editor before saving)."""
    tpl = normalize_template(body)
    if not body.get("batches"):
        tpl["batches"] = auto_batches(tpl)
    return dict(tpl, problems=validate_template(tpl), tcp_ready=is_tcp_ready(tpl))


@router.post("/templates/default-sim")
def guess_sim(register: dict):
    return default_sim(register)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int):
    get_template_or_404(template_id)
    used = [d["name"] for d in store.devices.all() if d["template_id"] == template_id]
    if used:
        raise HTTPException(409, f"Template is used by: {', '.join(used)}")
    store.templates.delete(template_id)
    return {"deleted": template_id}


@router.post("/templates/import")
async def import_templates(file: UploadFile = File(...), only_tcp: bool = False):
    try:
        data = json.loads(await file.read())
    except ValueError:
        raise HTTPException(400, "File is not valid JSON")
    imported = from_gateway_file(data)
    if not imported:
        raise HTTPException(400, "No modbus_templates found in file")

    # gateway files can hold the same name twice (e.g. MOD-EM and MOD-TCP variants), so match on name + sub_type
    existing = {(t["name"], t.get("sub_type")): t for t in store.templates.all() if t.get("source") == "gateway"}
    added = updated = skipped = 0
    for tpl in imported:
        if only_tcp and not is_tcp_ready(tpl):
            skipped += 1
            continue
        old = existing.get((tpl["name"], tpl.get("sub_type")))
        if old:
            # keep the user's sim settings for registers that still exist
            old_sims = {r["zone"]: r.get("sim") for r in old.get("in_registers", [])}
            for r in tpl["in_registers"]:
                if old_sims.get(r["zone"]):
                    r["sim"] = old_sims[r["zone"]]
            store.templates.put(old["id"], tpl)
            updated += 1
        else:
            store.templates.add(tpl)
            added += 1
    engine.invalidate()
    return {"added": added, "updated": updated, "skipped": skipped}


# ---------------------------------------------------------------- devices
@router.get("/devices")
def list_devices():
    return sorted((device_summary(d) for d in store.devices.all()), key=lambda d: d["unit_id"])


@router.get("/devices/next-unit")
def next_unit():
    used = {d["unit_id"] for d in store.devices.all()}
    return {"unit_id": next((u for u in range(1, 248) if u not in used), None)}


@router.post("/devices")
def create_device(body: DeviceIn):
    check_device(body)
    data = body.model_dump()
    data["overrides"] = {z: s.model_dump(exclude_none=True) for z, s in body.overrides.items()}
    data["created_at"] = time.time()
    return device_summary(store.devices.add(data))


@router.put("/devices/{device_id}")
def update_device(device_id: int, body: DeviceIn):
    old = get_device_or_404(device_id)
    check_device(body, device_id)
    data = body.model_dump()
    data["overrides"] = {z: s.model_dump(exclude_none=True) for z, s in body.overrides.items()}
    data["created_at"] = old.get("created_at", time.time())
    saved = store.devices.put(device_id, data)
    engine.invalidate(device_id)
    return device_summary(saved)


@router.patch("/devices/{device_id}/enabled")
def set_enabled(device_id: int, body: EnabledIn):
    d = get_device_or_404(device_id)
    saved = store.devices.put(device_id, dict(d, enabled=body.enabled))
    engine.invalidate(device_id)
    return device_summary(saved)


@router.delete("/devices/{device_id}")
def delete_device(device_id: int):
    get_device_or_404(device_id)
    store.devices.delete(device_id)
    engine.invalidate(device_id)
    engine.clear_writes(device_id)
    return {"deleted": device_id}


@router.get("/devices/{device_id}/values")
def device_values(device_id: int):
    d = get_device_or_404(device_id)
    return {"zones": engine.zone_view(d), "writes": engine.writes_view(device_id)}


@router.delete("/devices/{device_id}/writes")
def clear_device_writes(device_id: int):
    get_device_or_404(device_id)
    engine.clear_writes(device_id)
    return {"cleared": device_id}


# ---------------------------------------------------------------- request log
@router.get("/logs")
def logs(limit: int = 500, unit_id: Optional[int] = None, errors_only: bool = False):
    entries = request_log.recent(limit)
    if unit_id is not None:
        entries = [e for e in entries if e["unit_id"] == unit_id]
    if errors_only:
        entries = [e for e in entries if not e["ok"]]
    return entries


@router.delete("/logs")
def clear_logs():
    request_log.clear()
    return {"cleared": True}


# ---------------------------------------------------------------- app
class SpaStaticFiles(StaticFiles):
    """Serve index.html for client-side routes like /templates/5 (browser refresh / deep link)."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


def create_app():
    app = FastAPI(title="Modbus Device Simulator")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)

    if os.path.isdir(UI_DIST):
        app.mount("/", SpaStaticFiles(directory=UI_DIST, html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_ui():
            return ("<h3>Modbus Device Simulator API is running.</h3>"
                    "<p>UI is not built yet: <code>cd ui &amp;&amp; npm install &amp;&amp; npm run build</code>. "
                    "API docs: <a href='/docs'>/docs</a></p>")
    return app


app = create_app()

import { useEffect, useMemo, useState } from "react";
import { Alert, App, AutoComplete, Button, Input, InputNumber, Modal, Select, Spin, Table, Tag, Tooltip } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { MdAdd, MdArrowBack, MdAutoFixHigh, MdCheck, MdContentPaste, MdDelete, MdSave } from "react-icons/md";
import { api } from "../api";
import { MEASUREMENTS, TYPE_PRESETS, applyType, spanOf, typeOf } from "../registerTypes";
import SimEditor from "../components/SimEditor";

const NEW_TEMPLATE = {
  name: "",
  sub_type: "MOD-TCP",
  register_func_type: "holding",
  byte_order: "big",
  word_order: "big",
  poll_interval: 10,
  description: "",
  in_registers: [],
  batches: [],
  source: "custom",
};

let keySeq = 0;
const withKey = (r) => ({ ...r, _key: ++keySeq });

const FUNC_OPTIONS = [
  { value: "holding", label: "Holding registers (FC03)" },
  { value: "input", label: "Input registers (FC04)" },
  { value: "discrete_input", label: "Discrete inputs (FC02)" },
];

const ORDER_OPTIONS = [
  { value: "big", label: "big" },
  { value: "little", label: "little" },
];

// "0,V1N,Voltage L1-N,voltage,float32,1"  /  "10,DOOR,Front door,event,bit:3"
function parseCsv(text) {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.toLowerCase().startsWith("address"))
    .map((line) => {
      const [address, zone, name, measurement, type = "int16", multiplier = "1"] = line.split(/[,;\t]/).map((s) => s.trim());
      const [kind, bit] = type.toLowerCase().split(":");
      let reg = {
        register_address: Number(address) || 0,
        zone: (zone || "").toUpperCase(),
        name: name || zone,
        measurement: measurement || "misc",
        multiplier: Number(multiplier) || 1,
        input_type: kind === "bit" ? "state" : "analog",
      };
      reg = applyType(reg, TYPE_PRESETS[kind] ? kind : "int16");
      if (kind === "bit") reg.size_bits = Math.min(16, Math.max(1, Number(bit) || 1));
      return reg;
    });
}

function TemplateEditor() {
  const { id } = useParams();
  const isNew = id === "new";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  const [tpl, setTpl] = useState(null);
  const [problems, setProblems] = useState(null);
  const [saving, setSaving] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["template", id],
    queryFn: () => api.get(`/templates/${id}`),
    enabled: !isNew,
  });

  useEffect(() => {
    const source = isNew ? NEW_TEMPLATE : data;
    if (!source) return;
    setTpl({ ...source, in_registers: source.in_registers.map(withKey) });
    setProblems(isNew ? null : source.problems);
  }, [isNew, data]);

  const isGateway = tpl?.source === "gateway";
  const regs = tpl?.in_registers || [];

  const setField = (patch) => setTpl((t) => ({ ...t, ...patch }));
  const setReg = (key, patch) =>
    setTpl((t) => ({ ...t, in_registers: t.in_registers.map((r) => (r._key === key ? { ...r, ...patch } : r)) }));
  const removeReg = (key) => setTpl((t) => ({ ...t, in_registers: t.in_registers.filter((r) => r._key !== key) }));

  const nextAddress = useMemo(
    () => regs.reduce((max, r) => Math.max(max, (r.register_address || 0) + spanOf(r)), 0),
    [regs],
  );

  const addRegister = () =>
    setTpl((t) => ({
      ...t,
      in_registers: [
        ...t.in_registers,
        withKey({
          register_address: nextAddress,
          zone: "",
          name: "",
          measurement: "misc",
          size_bits: 32,
          decode_type: "float",
          count_registers: 2,
          multiplier: 1,
          input_type: "analog",
          sim: { mode: "random", min: 0, max: 100 },
        }),
      ],
    }));

  const payload = () => {
    const body = { ...tpl, in_registers: tpl.in_registers.map(({ _key, ...r }) => r) };
    // the gateway polls with the batches of its own template, so only custom templates get recalculated batches
    if (!isGateway) body.batches = [];
    delete body.problems;
    return body;
  };

  const autoSim = async () => {
    const sims = await Promise.all(
      tpl.in_registers.map(({ _key, sim, ...r }) => api.post("/templates/default-sim", r)),
    );
    setTpl((t) => ({ ...t, in_registers: t.in_registers.map((r, i) => ({ ...r, sim: sims[i] })) }));
    message.success("Simulation guessed from zone / measurement for every register");
  };

  const validate = async () => {
    const r = await api.post("/templates/preview", payload());
    setProblems(r.problems);
    setTpl((t) => ({ ...t, batches: r.batches }));
    if (!r.problems.length) message.success("Template looks good");
  };

  const save = async () => {
    if (!tpl.name.trim()) return message.error("Template needs a name");
    setSaving(true);
    try {
      const saved = isNew ? await api.post("/templates", payload()) : await api.put(`/templates/${id}`, payload());
      setProblems(saved.problems);
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      queryClient.invalidateQueries({ queryKey: ["template", String(saved.id)] });
      message.success(saved.problems.length ? "Saved with warnings" : "Saved");
      if (isNew) navigate(`/templates/${saved.id}`, { replace: true });
      else setTpl({ ...saved, in_registers: saved.in_registers.map(withKey) });
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const importCsv = () => {
    const rows = parseCsv(pasteText);
    if (!rows.length) return message.warning("No rows found");
    Promise.all(rows.map((r) => api.post("/templates/default-sim", r))).then((sims) => {
      setTpl((t) => ({ ...t, in_registers: [...t.in_registers, ...rows.map((r, i) => withKey({ ...r, sim: sims[i] }))] }));
      setPasteOpen(false);
      setPasteText("");
      message.success(`${rows.length} register(s) added`);
    });
  };

  if (!tpl || (!isNew && isLoading)) return <Spin className="mt-10 block" />;

  const columns = [
    {
      title: "Address",
      dataIndex: "register_address",
      width: 90,
      render: (v, r) => <InputNumber size="small" min={0} max={65535} value={v} onChange={(a) => setReg(r._key, { register_address: a ?? 0 })} style={{ width: 80 }} />,
    },
    {
      title: "Zone",
      dataIndex: "zone",
      width: 130,
      render: (v, r) => (
        <Input
          size="small"
          value={v}
          status={!v ? "error" : undefined}
          placeholder="e.g. V1N"
          onChange={(e) => setReg(r._key, { zone: e.target.value.toUpperCase() })}
        />
      ),
    },
    {
      title: "Name",
      dataIndex: "name",
      width: 200,
      render: (v, r) => <Input size="small" value={v} onChange={(e) => setReg(r._key, { name: e.target.value })} />,
    },
    {
      title: "Measurement",
      dataIndex: "measurement",
      width: 130,
      render: (v, r) => (
        <AutoComplete size="small" value={v} options={MEASUREMENTS} onChange={(m) => setReg(r._key, { measurement: m })} style={{ width: 120 }} />
      ),
    },
    {
      title: "Type",
      key: "type",
      width: 200,
      render: (_, r) => (
        <div className="flex gap-1">
          <Select
            size="small"
            style={{ width: 128 }}
            value={typeOf(r)}
            options={Object.entries(TYPE_PRESETS).map(([value, p]) => ({ value, label: p.label }))}
            onChange={(type) => setReg(r._key, applyType(r, type))}
          />
          {r.decode_type === "bit" && (
            <Tooltip title="Bit position 1-16 inside the register">
              <InputNumber size="small" min={1} max={16} value={r.size_bits} prefix="b" style={{ width: 62 }} onChange={(b) => setReg(r._key, { size_bits: b ?? 1 })} />
            </Tooltip>
          )}
        </div>
      ),
    },
    {
      title: <Tooltip title="Gateway multiplies the decoded value by this (e.g. 0.1 for a value sent ×10)">Multiplier</Tooltip>,
      dataIndex: "multiplier",
      width: 90,
      render: (v, r) => <InputNumber size="small" value={v} step={0.1} style={{ width: 80 }} onChange={(m) => setReg(r._key, { multiplier: m ?? 1 })} />,
    },
    {
      title: "Input",
      dataIndex: "input_type",
      width: 95,
      render: (v, r) => (
        <Select size="small" style={{ width: 85 }} value={v} onChange={(i) => setReg(r._key, { input_type: i })} options={[{ value: "analog" }, { value: "state" }]} />
      ),
    },
    {
      title: "Simulation",
      dataIndex: "sim",
      width: 360,
      render: (sim, r) => <SimEditor value={sim} onChange={(s) => setReg(r._key, { sim: s })} />,
    },
    {
      title: "",
      key: "del",
      width: 40,
      render: (_, r) => <Button size="small" type="text" danger icon={<MdDelete />} onClick={() => removeReg(r._key)} />,
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button icon={<MdArrowBack />} onClick={() => navigate("/templates")} />
          <h2 className="text-lg font-semibold text-slate-800 m-0">{isNew ? "New template" : tpl.name}</h2>
          {isGateway ? <Tag className="m-0">gateway #{tpl.gateway_id}</Tag> : <Tag color="purple" className="m-0">custom</Tag>}
        </div>
        <div className="flex gap-2">
          <Button icon={<MdCheck />} onClick={validate}>
            Validate
          </Button>
          <Button type="primary" icon={<MdSave />} loading={saving} onClick={save}>
            Save
          </Button>
        </div>
      </div>

      {isGateway && (
        <Alert
          type="info"
          showIcon
          message="Imported from the gateway"
          description="Changing simulation settings is safe. If you change addresses / types, the gateway's copy of this template no longer matches: export it and import it on the gateway, or clone it as a custom template."
        />
      )}

      <div className="bg-white rounded-lg shadow-sm p-3 flex flex-wrap gap-4 items-end">
        <label className="text-xs text-slate-500">
          Name
          <Input value={tpl.name} onChange={(e) => setField({ name: e.target.value })} style={{ width: 260 }} className="block" />
        </label>
        <label className="text-xs text-slate-500">
          Registers
          <Select
            className="block"
            value={tpl.register_func_type}
            onChange={(v) => setField({ register_func_type: v })}
            style={{ width: 210 }}
            options={FUNC_OPTIONS}
          />
        </label>
        <label className="text-xs text-slate-500">
          <Tooltip title="Byte order inside each 16-bit register">Byte order</Tooltip>
          <Select className="block" value={tpl.byte_order} onChange={(v) => setField({ byte_order: v })} style={{ width: 90 }} options={ORDER_OPTIONS} />
        </label>
        <label className="text-xs text-slate-500">
          <Tooltip title="Order of the 2 registers of a 32-bit value. Most Selec / Elmeasure meters: byte big, word little">Word order</Tooltip>
          <Select className="block" value={tpl.word_order} onChange={(v) => setField({ word_order: v })} style={{ width: 90 }} options={ORDER_OPTIONS} />
        </label>
        <label className="text-xs text-slate-500">
          Poll interval (s)
          <InputNumber className="block" min={1} value={tpl.poll_interval} onChange={(v) => setField({ poll_interval: v ?? 10 })} style={{ width: 110 }} />
        </label>
        <div className="text-xs text-slate-500">
          <Tooltip title={isGateway ? "Batches of the gateway template (what the gateway reads)" : "Calculated automatically on save"}>
            Batches
          </Tooltip>
          <div className="flex flex-wrap gap-1 mt-1 max-w-md">
            {(tpl.batches || []).length ? (
              tpl.batches.map((b) => (
                <Tag key={b.address} className="m-0 font-mono">
                  {b.address}–{b.address + b.count - 1}
                </Tag>
              ))
            ) : (
              <span className="text-slate-400">auto</span>
            )}
          </div>
        </div>
      </div>

      {problems?.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`${problems.length} problem(s)`}
          description={
            <ul className="m-0 pl-4 text-xs">
              {problems.slice(0, 15).map((p) => (
                <li key={p}>{p}</li>
              ))}
              {problems.length > 15 && <li>… and {problems.length - 15} more</li>}
            </ul>
          }
        />
      )}

      <div className="bg-white rounded-lg shadow-sm">
        <div className="flex items-center justify-between p-2">
          <span className="text-sm font-semibold text-slate-700">Registers ({regs.length})</span>
          <div className="flex gap-2">
            <Tooltip title="Set every register's simulation from its zone / measurement (voltage 228-236, kWh counter, status toggle ...)">
              <Button size="small" icon={<MdAutoFixHigh />} onClick={autoSim} disabled={!regs.length}>
                Auto simulation
              </Button>
            </Tooltip>
            <Button size="small" icon={<MdContentPaste />} onClick={() => setPasteOpen(true)}>
              Paste CSV
            </Button>
            <Button size="small" type="primary" icon={<MdAdd />} onClick={addRegister}>
              Add register
            </Button>
          </div>
        </div>
        <Table
          rowKey="_key"
          size="small"
          columns={columns}
          dataSource={regs}
          pagination={false}
          scroll={{ x: 1450, y: "calc(100vh - 420px)" }}
          locale={{ emptyText: "No registers yet - add one or paste a CSV" }}
        />
      </div>

      <Modal title="Paste registers (CSV)" open={pasteOpen} onCancel={() => setPasteOpen(false)} onOk={importCsv} okText="Add rows" width={640}>
        <p className="text-xs text-slate-500 mb-2">
          One register per line: <code>address, zone, name, measurement, type, multiplier</code>. Type = float32, int32, int16, float16 or
          bit:N (N = 1-16). Copy straight from Excel works too (tab separated).
        </p>
        <Input.TextArea
          rows={10}
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          placeholder={"0,V1N,Voltage L1-N,voltage,float32,1\n2,AI,Average current,current,float32,1\n20,TEMP,Rack temperature,temperature,int16,0.1\n30,DOOR,Front door,event,bit:1\n30,FIRE,Fire alarm,event,bit:2"}
          className="font-mono text-xs"
        />
      </Modal>
    </div>
  );
}

export default TemplateEditor;

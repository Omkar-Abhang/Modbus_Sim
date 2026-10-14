import { InputNumber, Select, Tooltip } from "antd";

const MODES = [
  { value: "random", label: "Random" },
  { value: "sine", label: "Sine" },
  { value: "counter", label: "Counter" },
  { value: "toggle", label: "Toggle" },
];

const DEFAULTS = {
  random: { min: 0, max: 100 },
  sine: { min: 0, max: 100, period_s: 3600 },
  counter: { start: 0, rate_per_hour: 1 },
  toggle: { min: 0, max: 1, on_s: 60, off_s: 60 },
};

function Num({ label, tip, value, onChange, width = 72, min }) {
  return (
    <Tooltip title={tip}>
      <InputNumber
        size="small"
        style={{ width }}
        value={value}
        min={min}
        placeholder={label}
        prefix={<span className="text-[10px] text-slate-400">{label}</span>}
        onChange={(v) => onChange(v ?? 0)}
      />
    </Tooltip>
  );
}

// Compact inline editor for one register's simulation settings
function SimEditor({ value = {}, onChange }) {
  const sim = { mode: "random", ...value };
  const set = (patch) => onChange({ ...sim, ...patch });

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Select
        size="small"
        style={{ width: 92 }}
        value={sim.mode}
        options={MODES}
        onChange={(mode) => onChange({ mode, ...DEFAULTS[mode], ...pick(sim, mode) })}
      />
      {(sim.mode === "random" || sim.mode === "sine") && (
        <>
          <Num label="min" value={sim.min} onChange={(min) => set({ min })} tip="Lowest value" />
          <Num label="max" value={sim.max} onChange={(max) => set({ max })} tip="Highest value (min = max → constant)" />
        </>
      )}
      {sim.mode === "sine" && (
        <Num
          label="s"
          width={84}
          min={1}
          value={sim.period_s}
          onChange={(period_s) => set({ period_s })}
          tip="Period in seconds (3600 = 1 hour, 86400 = 1 day)"
        />
      )}
      {sim.mode === "counter" && (
        <>
          <Num label="start" width={84} value={sim.start} onChange={(start) => set({ start })} tip="Value when the device was added" />
          <Num label="/h" value={sim.rate_per_hour} onChange={(rate_per_hour) => set({ rate_per_hour })} tip="Increase per hour" />
        </>
      )}
      {sim.mode === "toggle" && (
        <>
          <Num label="on" value={sim.max} onChange={(max) => set({ max })} tip="Value while ON" />
          <Num label="s" min={0} value={sim.on_s} onChange={(on_s) => set({ on_s })} tip="Seconds ON" />
          <Num label="off" value={sim.min} onChange={(min) => set({ min })} tip="Value while OFF" />
          <Num label="s" min={0} value={sim.off_s} onChange={(off_s) => set({ off_s })} tip="Seconds OFF" />
        </>
      )}
    </div>
  );
}

// keep min / max when switching between random and sine
function pick(sim, mode) {
  if ((mode === "random" || mode === "sine") && sim.min != null && sim.max != null) {
    return { min: sim.min, max: sim.max };
  }
  return {};
}

export default SimEditor;

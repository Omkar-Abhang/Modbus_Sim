// Register data types as the IESG gateway decodes them (size_bits / decode_type / count_registers)
export const TYPE_PRESETS = {
  float32: { label: "Float 32", size_bits: 32, decode_type: "float", count_registers: 2 },
  int32: { label: "Int 32 (signed)", size_bits: 32, decode_type: "int", count_registers: 2 },
  int16: { label: "Int 16 (signed)", size_bits: 16, decode_type: "int", count_registers: 1 },
  float16: { label: "Float 16", size_bits: 16, decode_type: "float", count_registers: 1 },
  bit: { label: "Bit in register", decode_type: "bit", count_registers: 1 },
};

export function typeOf(reg) {
  if (reg.decode_type === "bit") return "bit";
  if (reg.decode_type === "float") return reg.size_bits === 32 ? "float32" : "float16";
  return reg.size_bits === 32 ? "int32" : "int16";
}

export function applyType(reg, type) {
  const preset = TYPE_PRESETS[type];
  const next = { ...reg, decode_type: preset.decode_type, count_registers: preset.count_registers };
  next.size_bits = type === "bit" ? (reg.decode_type === "bit" ? reg.size_bits : 1) : preset.size_bits;
  return next;
}

export function spanOf(reg) {
  const type = typeOf(reg);
  const words = type === "float32" || type === "int32" ? 2 : 1;
  return Math.max(reg.count_registers || 1, words);
}

export const MEASUREMENTS = [
  "voltage",
  "current",
  "power",
  "energy",
  "temperature",
  "humidity",
  "frequency",
  "event",
  "misc",
].map((m) => ({ value: m }));

export const MODE_COLORS = { random: "blue", sine: "purple", counter: "gold", toggle: "green" };

export function simSummary(sim = {}) {
  switch (sim.mode) {
    case "sine":
      return `${sim.min}–${sim.max} · ${sim.period_s ?? 3600}s`;
    case "counter":
      return `from ${sim.start ?? 0} · +${sim.rate_per_hour ?? 1}/h`;
    case "toggle":
      return `${sim.max ?? 1} for ${sim.on_s ?? 60}s / ${sim.min ?? 0} for ${sim.off_s ?? 60}s`;
    default:
      return sim.min === sim.max ? `fixed ${sim.min}` : `${sim.min}–${sim.max}`;
  }
}

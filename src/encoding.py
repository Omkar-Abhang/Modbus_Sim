"""
Value -> Modbus register words, as the exact inverse of what the IESG gateway does when it reads a device.

Gateway decode (iam-gateway src/devices/modbus/mod_ups_tcp.py, pymodbus 2.5.2):
    decoder = BinaryPayloadDecoder.fromRegisters(regs, byteorder=<byte_order>, wordorder=<word_order>)
    float32 -> decode_32bit_float(), int32 -> decode_32bit_int(), int16 -> decode_16bit_int(),
    float16 -> decode_16bit_float(), bit -> bit <size_bits> (1-based) of decode_16bit_int()
    value = decoded * multiplier

pymodbus 2.5.2 decoding of N words (N = 1 or 2) from the start of `regs`:
    words = regs[0:N]; if word_order == little: words reversed
    raw = b"".join(pack(<byte_order>H, w) for w in words); value = unpack("!" + fmt, raw)
So encoding is: raw = pack("!" + fmt, value) -> words via unpack(<byte_order>H) -> reverse if word_order little.
"""
import math
import struct

ORDER = {"big": ">", "little": "<"}

# kind -> (struct format, number of 16-bit words consumed by the gateway decoder)
KINDS = {
    "float32": ("f", 2),
    "int32": ("i", 2),
    "int16": ("h", 1),
    "float16": ("e", 1),
}

INT_LIMITS = {"int16": (-32768, 32767), "int32": (-2147483648, 2147483647)}


def register_kind(reg):
    """Data type the gateway will decode for this register (same branching as get_converted_value)."""
    decode_type = reg.get("decode_type")
    if decode_type == "bit":
        return "bit"
    size_bits = reg.get("size_bits", 16)
    if decode_type == "float":
        return "float32" if size_bits == 32 else "float16"
    return "int32" if size_bits == 32 else "int16"


def register_span(reg):
    """Number of registers this zone occupies (at least what the decoder reads)."""
    kind = register_kind(reg)
    words = 1 if kind == "bit" else KINDS[kind][1]
    return max(int(reg.get("count_registers") or 1), words)


def encode_words(kind, value, byte_order="big", word_order="big"):
    """Encode a raw (already divided by multiplier) value to the register words the decoder expects."""
    fmt, n_words = KINDS[kind]
    if kind in INT_LIMITS:
        lo, hi = INT_LIMITS[kind]
        value = int(max(lo, min(hi, round(value))))
    else:
        value = float(value)
        if kind == "float16":
            value = max(-65504.0, min(65504.0, value))
    raw = struct.pack("!" + fmt, value)
    words = [struct.unpack(ORDER[byte_order] + "H", raw[i:i + 2])[0] for i in range(0, 2 * n_words, 2)]
    if word_order == "little":
        words.reverse()
    return words


def decode_words(kind, words, byte_order="big", word_order="big"):
    """Same algorithm as pymodbus 2.5.2 BinaryPayloadDecoder - used for the UI 'raw' view and self tests."""
    fmt, n_words = KINDS[kind]
    words = list(words[:n_words])
    if word_order == "little":
        words.reverse()
    raw = b"".join(struct.pack(ORDER[byte_order] + "H", w) for w in words)
    return struct.unpack("!" + fmt, raw)[0]


def to_raw(value, multiplier):
    """Gateway multiplies after decoding, so we send value / multiplier."""
    try:
        m = float(multiplier)
    except (TypeError, ValueError):
        m = 1.0
    if m == 0 or math.isnan(m):
        m = 1.0
    return value / m


def build_image(registers, values, byte_order="big", word_order="big", bit_mode=False):
    """
    Build {address: word} for one device from its template registers and current engineering values.

    registers: template in_registers (dicts), values: {zone: engineering value}
    bit_mode: True for coil / discrete_input templates - one bit (0/1) per address.
    """
    image = {}
    bit_words = {}  # address -> decoded int16 value with bits OR-ed in

    for reg in registers:
        addr = int(reg["register_address"])
        value = values.get(reg["zone"])
        if value is None:
            continue

        if bit_mode:
            image[addr] = 1 if value else 0
            continue

        kind = register_kind(reg)
        if kind == "bit":
            pos = int(reg.get("size_bits") or 1)
            if 1 <= pos <= 16 and value:
                bit_words[addr] = bit_words.get(addr, 0) | (1 << (pos - 1))
            else:
                bit_words.setdefault(addr, 0)
            continue

        words = encode_words(kind, to_raw(value, reg.get("multiplier", 1)), byte_order, word_order)
        span = register_span(reg)
        words += [0] * (span - len(words))
        for i, w in enumerate(words):
            image[addr + i] = w

    # bit registers are decoded by the gateway as int16, so encode the combined bits the same way
    for addr, bits in bit_words.items():
        signed = bits - 0x10000 if bits & 0x8000 else bits
        image[addr] = encode_words("int16", signed, byte_order, word_order)[0]

    return image

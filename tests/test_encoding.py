"""
Encoding must be the exact inverse of the gateway decoder (pymodbus 2.5.2 BinaryPayloadDecoder).
REFERENCE rows were produced with the real pymodbus 2.5.2: decoding `words` with byte/word order gives `value`.
Run: .venv/bin/python -m pytest tests
"""
import itertools
import math

import pytest

from src.encoding import build_image, decode_words, encode_words, register_span
from src.generators import default_sim, generate

REFERENCE = [
    ("float32", [17255, 30802], "big", "big", 231.47000122070312),
    ("float32", [17255, 30802], "big", "little", 1.7058584722445272e+34),
    ("float32", [17255, 30802], "little", "big", 9.223827440849096e+23),
    ("float32", [17255, 30802], "little", "little", 266721083392.0),
    ("int32", [65534, 32307], "big", "big", -98765),
    ("int32", [65534, 32307], "big", "little", 2117337086),
    ("int32", [65534, 32307], "little", "big", -16829570),
    ("int32", [65534, 32307], "little", "little", 863960831),
    ("int16", [65413], "big", "big", -123),
    ("int16", [65413], "big", "little", -123),
    ("int16", [65413], "little", "big", -31233),
    ("int16", [65413], "little", "little", -31233),
]
ORDERS = list(itertools.product(("big", "little"), repeat=2))


@pytest.mark.parametrize("kind,words,byte_order,word_order,value", REFERENCE)
def test_decode_matches_pymodbus_252(kind, words, byte_order, word_order, value):
    assert decode_words(kind, words, byte_order, word_order) == value


@pytest.mark.parametrize("kind,words,byte_order,word_order,value", REFERENCE)
def test_encode_produces_gateway_words(kind, words, byte_order, word_order, value):
    assert encode_words(kind, value, byte_order, word_order) == words


@pytest.mark.parametrize("byte_order,word_order", ORDERS)
@pytest.mark.parametrize("kind,value", [("float32", -12.75), ("float32", 49.98), ("int32", 123456789),
                                        ("int32", -5), ("int16", 32767), ("int16", -32768), ("float16", 12.5)])
def test_round_trip(kind, value, byte_order, word_order):
    words = encode_words(kind, value, byte_order, word_order)
    assert all(0 <= w <= 0xFFFF for w in words)
    assert math.isclose(decode_words(kind, words, byte_order, word_order), value, rel_tol=1e-6)


def test_int_values_are_clamped_and_rounded():
    assert decode_words("int16", encode_words("int16", 99999)) == 32767
    assert decode_words("int16", encode_words("int16", 24.6)) == 25


@pytest.mark.parametrize("byte_order,word_order", ORDERS)
def test_image_multiplier_span_and_bits(byte_order, word_order):
    regs = [
        dict(register_address=0, zone="V1N", size_bits=32, count_registers=2, decode_type="float", multiplier=1),
        dict(register_address=2, zone="KWH", size_bits=32, count_registers=2, decode_type="int", multiplier=0.01),
        dict(register_address=4, zone="T", size_bits=16, count_registers=2, decode_type="int", multiplier=0.1),
        dict(register_address=6, zone="B1", size_bits=1, count_registers=1, decode_type="bit"),
        dict(register_address=6, zone="B3", size_bits=3, count_registers=1, decode_type="bit"),
        dict(register_address=6, zone="B4", size_bits=4, count_registers=1, decode_type="bit"),
    ]
    image = build_image(regs, {"V1N": 230.5, "KWH": 1234.56, "T": 24.5, "B1": 1, "B3": 0, "B4": 1},
                        byte_order, word_order)

    assert decode_words("float32", [image[0], image[1]], byte_order, word_order) == 230.5
    assert decode_words("int32", [image[2], image[3]], byte_order, word_order) == 123456  # 1234.56 / 0.01
    assert decode_words("int16", [image[4]], byte_order, word_order) == 245  # 24.5 / 0.1
    assert image[5] == 0  # second register of a (16,int,2) zone is padding
    assert decode_words("int16", [image[6]], byte_order, word_order) == 0b1001  # bits 1 and 4
    assert register_span(regs[2]) == 2


def test_bit_mode_for_discrete_inputs():
    regs = [dict(register_address=a, zone=f"DI{a}", decode_type="int", size_bits=16) for a in range(3)]
    assert build_image(regs, {"DI0": 1, "DI1": 0, "DI2": 5}, bit_mode=True) == {0: 1, 1: 0, 2: 1}


# ---------------------------------------------------------------- generators
def test_toggle_zero_durations_are_respected():
    assert {generate({"mode": "toggle", "min": 0, "max": 1, "on_s": 0, "off_s": 10}, t, "k", 0) for t in range(30)} == {0}
    assert {generate({"mode": "toggle", "min": 0, "max": 1, "on_s": 10, "off_s": 0}, t, "k", 0) for t in range(30)} == {1}


def test_random_with_equal_bounds_is_constant():
    assert generate({"mode": "random", "min": 7, "max": 7}, 1, "k", 0) == 7
    assert generate({"mode": "random", "min": 0, "max": 0}, 1, "k", 0) == 0


def test_sine_stays_in_range_and_counter_grows():
    values = [generate({"mode": "sine", "min": 20, "max": 30, "period_s": 60}, t, "k", 0) for t in range(120)]
    assert min(values) >= 20 and max(values) <= 30 and max(values) - min(values) > 9
    assert generate({"mode": "counter", "start": 100, "rate_per_hour": 60}, 1800, "k", 0) == 130


@pytest.mark.parametrize("reg,mode", [
    ({"zone": "V1N"}, "random"),
    ({"zone": "AI", "measurement": "current"}, "sine"),
    ({"zone": "KWH"}, "counter"),
    ({"zone": "STATUS"}, "toggle"),
    ({"zone": "X", "decode_type": "bit"}, "toggle"),
    ({"zone": "SUPPLYAIRTEMP", "measurement": "temperature"}, "sine"),
])
def test_default_sim_guess(reg, mode):
    assert default_sim(reg)["mode"] == mode

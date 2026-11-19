import logging

from duka_smartfan_sdk import responsepacket
from duka_smartfan_sdk.responsepacket import ResponsePacket
from tests.fake_fan import RESPONSE, frame


def parse(body: bytes) -> tuple[bool, ResponsePacket]:
    packet = ResponsePacket()
    ok = packet.initialize_from_data(frame("TESTFAN000000001", "1111", RESPONSE, body))
    return ok, packet


def test_unknown_param_after_known_keeps_known_fields():
    ok, packet = parse(bytes([0x2E, 55, 0x50, 0x01]))
    assert ok is True
    assert packet.humidity == 55


def test_prefixed_unknown_param_is_skipped():
    ok, packet = parse(bytes([0xFE, 0x03, 0x50, 0xAA, 0xBB, 0xCC, 0x31, 21]))
    assert ok is True
    assert packet.temperature == 21


def test_prefixed_known_param_skips_declared_size():
    ok, packet = parse(bytes([0xFE, 0x02, 0x2E, 77, 0x99, 0x31, 21]))
    assert ok is True
    assert packet.humidity == 77
    assert packet.temperature == 21


def test_unknown_param_warned_once(caplog):
    responsepacket._WARNED_PARAMS.clear()
    with caplog.at_level(logging.WARNING, logger="duka_smartfan_sdk"):
        parse(bytes([0x2E, 55, 0x50, 0x01]))
        parse(bytes([0x2E, 56, 0x50, 0x01]))
    warnings = [r for r in caplog.records if "0x50" in r.getMessage()]
    assert len(warnings) == 1


def test_battery_and_on_off_parsed_separately():
    ok, packet = parse(bytes([0x01, 1, 0x02, 0]))
    assert ok is True
    assert packet.is_on is True
    assert packet.battery_status == 0


def test_unsupported_marker_is_skipped():
    """Real fan replies 0xFD <param> for parameters it lacks (e.g. motion 0x0B)."""
    body = bytes([0x2E, 50, 0xFD, 0x0B, 0xFD, 0x12, 0x31, 24])
    packet = ResponsePacket()
    assert packet.initialize_from_data(frame("TESTFAN000000001", "", RESPONSE, body))
    assert packet.humidity == 50
    assert packet.temperature == 24


def test_real_fan_status_reply_parses():
    """Byte-for-byte status reply shape captured from a real fan (fw 2.2, unit type 6)."""
    body = bytes.fromhex("01 01 02 00 03 00 fe 02 04 00 00 2e 32 31 18 fe 02 b9 06 00")
    packet = ResponsePacket()
    assert packet.initialize_from_data(frame("002700224746570A", "", RESPONSE, body))
    assert (packet.is_on, packet.battery_status, packet.fan_speed) == (True, 0, 0)
    assert (packet.humidity, packet.temperature, packet.unit_type) == (50, 24, 6)

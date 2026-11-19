import pytest

from duka_smartfan_sdk.device import Device
from duka_smartfan_sdk.dukapacket import DukaPacket
from duka_smartfan_sdk.responsepacket import ResponsePacket
from tests.fake_fan import RESPONSE, frame

DEV_ID = "TESTFAN000000001"
PASSWORD = "1111"


def request(func: int, body: bytes) -> bytes:
    data = (
        bytes([0xFD, 0xFD, 0x02, len(DEV_ID)]) + DEV_ID.encode()
        + bytes([len(PASSWORD)]) + PASSWORD.encode()
        + bytes([func]) + body
    )
    total = sum(data[2:]) & 0xFFFF
    return data + bytes([total & 0xFF, total >> 8])


@pytest.fixture
def device():
    return Device(DEV_ID, PASSWORD)


@pytest.mark.parametrize(
    "method, func, body",
    [
        ("initialize_on_cmd", 0x03, b"\x01\x01"),
        ("initialize_off_cmd", 0x03, b"\x01\x00"),
        ("initialize_boost_on_cmd", 0x03, b"\x05\x01"),
        ("initialize_boost_off_cmd", 0x03, b"\x05\x00"),
        ("initialize_boost_toggle_cmd", 0x03, b"\x05\x02"),
        ("initialize_status_cmd", 0x01, bytes([0x01, 0x02, 0x03, 0x04, 0x2E, 0x31, 0xB9])),
        ("initialize_get_firmware_cmd", 0x01, bytes([0x86, 0xB9])),
    ],
)
def test_command_packets(device, method, func, body):
    packet = DukaPacket()
    getattr(packet, method)(device)
    assert bytes(packet.data) == request(func, body)


def test_search_packet():
    packet = DukaPacket()
    packet.initialize_search_cmd()
    expected = bytes([0xFD, 0xFD, 0x02, 16]) + b"DEFAULT_DEVICEID" + bytes([0, 0x01, 0x7C])
    total = sum(expected[2:]) & 0xFFFF
    assert bytes(packet.data) == expected + bytes([total & 0xFF, total >> 8])


def valid_reply() -> bytes:
    body = (
        bytes([0x2E, 55, 0x31, 21, 0x04]) + (1200).to_bytes(2, "little")
        + bytes([0x86, 1, 2, 19, 11]) + (2026).to_bytes(2, "little")
        + bytes([0xB9]) + (3).to_bytes(2, "little")
    )
    return frame(DEV_ID, PASSWORD, RESPONSE, body)


def test_parse_valid_reply():
    packet = ResponsePacket()
    assert packet.initialize_from_data(valid_reply())
    assert packet.device_id == DEV_ID
    assert packet.humidity == 55
    assert packet.temperature == 21
    assert packet.fan_speed == 1200
    assert packet.firmware_version == "1.2"
    assert packet.firmware_date == "19-11-2026"
    assert packet.unit_type == 3


def test_bad_checksum():
    data = bytearray(valid_reply())
    data[-1] ^= 0xFF
    assert not ResponsePacket().initialize_from_data(bytes(data))


def test_bad_header():
    data = bytearray(valid_reply())
    data[0] = 0x00
    assert not ResponsePacket().initialize_from_data(bytes(data))
    data = bytearray(valid_reply())
    data[2] = 0x09
    assert not ResponsePacket().initialize_from_data(bytes(data))


def test_truncated_reply():
    assert not ResponsePacket().initialize_from_data(valid_reply()[:10])
    assert not ResponsePacket().initialize_from_data(b"\xfd\xfd")

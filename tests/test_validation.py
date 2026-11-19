import pytest

from duka_smartfan_sdk.device import Device
from duka_smartfan_sdk.dukapacket import DukaPacket


def build(device_id="TESTFAN000000001", password="1111"):
    DukaPacket().initialize_on_cmd(Device(device_id, password))


def test_valid_inputs_ok():
    build()
    build("A" * 100, "p" * 50)


def test_non_ascii_device_id():
    with pytest.raises(ValueError, match="device ID.*ASCII"):
        build(device_id="FANæ")


def test_non_ascii_password():
    with pytest.raises(ValueError, match="password.*ASCII"):
        build(password="påss")


def test_device_id_too_long():
    with pytest.raises(ValueError, match="device ID.*255"):
        build(device_id="A" * 256)


def test_password_too_long():
    with pytest.raises(ValueError, match="password.*255"):
        build(password="p" * 256)


def test_byte_out_of_range():
    packet = DukaPacket()
    packet.initialize_on_cmd(Device("X", "1"))
    with pytest.raises(ValueError, match="byte.*0.*255"):
        packet._DukaPacket__add_byte(256)
    with pytest.raises(ValueError, match="byte.*0.*255"):
        packet._DukaPacket__add_byte(-1)


def test_packet_too_large():
    with pytest.raises(ValueError, match="exceeds.*200"):
        build("A" * 150, "p" * 100)


def test_invalid_device_is_not_registered(client):
    with pytest.raises(ValueError):
        client.add_device("FANæ", "1111", "127.0.0.1")
    assert client.get_device_count() == 0

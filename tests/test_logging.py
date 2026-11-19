import logging
import time

import pytest

from duka_smartfan_sdk.dukaclient import DukaClient
from duka_smartfan_sdk.responsepacket import ResponsePacket
from tests.fake_fan import RESPONSE, FakeFan, frame

PASSWORD = "s3cretPW"


def test_password_never_logged(caplog):
    fan = FakeFan(password=PASSWORD)
    client = DukaClient(device_port=fan.port, listen_port=0, bind_address="127.0.0.1")
    try:
        with caplog.at_level(logging.DEBUG, logger="duka_smartfan_sdk"):
            device = client.add_device(fan.device_id, PASSWORD, "127.0.0.1")
            client.turn_on(device)
            deadline = time.time() + 4
            while device.fan_speed is None and time.time() < deadline:
                time.sleep(0.05)
            assert device.fan_speed == 1200
    finally:
        client.close()
        fan.close()

    messages = [r.getMessage() for r in caplog.records]
    assert any("Sending" in m for m in messages)
    assert any("Received" in m for m in messages)
    hex_password = " ".join(f"{b:02x}" for b in PASSWORD.encode())
    for record in caplog.records:
        text = record.getMessage() + str(record.args) + str(record.exc_text)
        assert PASSWORD not in text
        assert hex_password not in text.lower()


def test_checksum_mismatch_logged_at_debug(caplog):
    data = bytearray(frame("TESTFAN000000001", PASSWORD, RESPONSE, bytes([0x2E, 5])))
    data[-1] ^= 0xFF
    with caplog.at_level(logging.DEBUG, logger="duka_smartfan_sdk"):
        assert not ResponsePacket().initialize_from_data(bytes(data))
    assert any("checksum" in r.getMessage().lower() for r in caplog.records)
    assert all(PASSWORD not in r.getMessage() for r in caplog.records)


def test_header_mismatch_logged_at_debug(caplog):
    data = bytearray(frame("TESTFAN000000001", PASSWORD, RESPONSE, bytes([0x2E, 5])))
    data[0] = 0
    with caplog.at_level(logging.DEBUG, logger="duka_smartfan_sdk"):
        assert not ResponsePacket().initialize_from_data(bytes(data))
    assert any("header" in r.getMessage().lower() for r in caplog.records)


def test_socket_wait_timeout_warns(caplog):
    client = DukaClient(device_port=9, listen_port=0, bind_address="127.0.0.1")
    client.close()  # notify thread gone, so the socket never comes back
    with caplog.at_level(logging.WARNING, logger="duka_smartfan_sdk"):
        with pytest.raises(Exception, match="Timeout waiting for socket"):
            client.search_devices(lambda _id: None, "127.0.0.1")
    assert any("socket" in r.getMessage().lower() for r in caplog.records)

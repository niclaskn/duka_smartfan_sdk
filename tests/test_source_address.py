import logging
import socket
import time

import pytest

from tests.fake_fan import RESPONSE, frame

DEV_ID = "TESTFAN000000001"
FORGED_HUMIDITY = bytes([0x2E, 99])


def wait_for(predicate, timeout=4.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def attacker():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.2", 0))
    yield sock
    sock.close()


def forge(attacker, client):
    port = client._sock.getsockname()[1]
    attacker.sendto(frame(DEV_ID, "1111", RESPONSE, FORGED_HUMIDITY), ("127.0.0.1", port))


def test_forged_reply_is_ignored(client, fan, attacker, caplog):
    device = client.add_device(DEV_ID, "1111", "127.0.0.1")
    assert wait_for(lambda: device.humidity == 55)
    with caplog.at_level(logging.WARNING, logger="duka_smartfan_sdk"):
        forge(attacker, client)
        assert wait_for(lambda: any("127.0.0.2" in r.getMessage() for r in caplog.records))
    assert device.humidity == 55
    assert device.ip_address == "127.0.0.1"


def test_forged_reply_warning_is_rate_limited(client, fan, attacker, caplog):
    device = client.add_device(DEV_ID, "1111", "127.0.0.1")
    assert wait_for(lambda: device.humidity == 55)
    with caplog.at_level(logging.WARNING, logger="duka_smartfan_sdk"):
        for _ in range(3):
            forge(attacker, client)
        assert wait_for(lambda: any("127.0.0.2" in r.getMessage() for r in caplog.records))
        time.sleep(0.3)
    assert len([r for r in caplog.records if "127.0.0.2" in r.getMessage()]) == 1


def test_broadcast_device_pins_first_responder(client, fan, attacker):
    device = client.add_device(DEV_ID, "1111", "<broadcast>")
    assert device.ip_address == "<broadcast>"
    # The fake cannot receive real broadcasts, so it answers unsolicited.
    fan.send_reply(("127.0.0.1", client._sock.getsockname()[1]))
    assert wait_for(lambda: device.ip_address == "127.0.0.1")
    assert wait_for(lambda: device.humidity == 55)
    forge(attacker, client)
    time.sleep(0.3)
    assert device.humidity == 55
    assert device.ip_address == "127.0.0.1"


def test_allow_ip_change_follows_new_address(client, fan, attacker):
    device = client.add_device(DEV_ID, "1111", "127.0.0.1", allow_ip_change=True)
    assert wait_for(lambda: device.humidity == 55)
    forge(attacker, client)
    assert wait_for(lambda: device.humidity == 99)
    assert device.ip_address == "127.0.0.2"

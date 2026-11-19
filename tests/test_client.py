import time


def wait_for(predicate, timeout=4.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_add_device_reads_firmware_and_unit_type(client, fan):
    device = client.add_device(fan.device_id, "1111", "127.0.0.1")
    assert wait_for(lambda: device.firmware_version is not None)
    assert device.firmware_version == "1.2"
    assert device.unit_type == 3


def test_status_polling(client, fan):
    device = client.add_device(fan.device_id, "1111", "127.0.0.1")
    assert wait_for(lambda: device.fan_speed is not None)
    assert device.humidity == 55
    assert device.temperature == 21
    assert device.fan_speed == 1200


def test_turn_off(client, fan):
    device = client.add_device(fan.device_id, "1111", "127.0.0.1")
    assert wait_for(lambda: device.is_active is True)
    client.turn_off(device)
    fan.state[0x04] = (0).to_bytes(2, "little")
    assert wait_for(lambda: device.is_active is False)


def test_search_devices(client, fan):
    found = []
    client.search_devices(found.append, "127.0.0.1")
    assert wait_for(lambda: found)
    assert found == [fan.device_id]


def test_on_off_state_and_battery_status(client, fan):
    changes = []
    device = client.add_device(fan.device_id, "1111", "127.0.0.1", changes.append)
    assert wait_for(lambda: device.is_on is not None)
    assert device.is_on is True
    assert device.battery_status == 1
    assert changes  # reported as a change event

    fan.state[0x01] = b"\x00"
    assert wait_for(lambda: device.is_on is False)

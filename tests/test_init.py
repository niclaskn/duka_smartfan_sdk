
from duka_smartfan_sdk.dukaclient import DukaClient
from tests.fake_fan import FakeFan


async def test_resends_firmware_request_until_answered():
    fan = FakeFan(drop_first=2)
    client = DukaClient(device_port=fan.port, listen_port=0, bind_address="127.0.0.1")
    try:
        device = client.add_device(fan.device_id, "1111", "127.0.0.1")
        assert await client.wait_for_initialize_async(device) is True
        assert len(fan.received) >= 3
        assert device.firmware_version == "1.2"
    finally:
        client.close()
        fan.close()


async def test_initialize_times_out_without_fan():
    client = DukaClient(device_port=9, listen_port=0, bind_address="127.0.0.1")
    try:
        device = client.add_device("NOFAN00000000001", "1111", "127.0.0.1")
        assert await client.wait_for_initialize_async(device, timeout=1.5) is False
    finally:
        client.close()


async def test_none_device(client):
    assert await client.wait_for_initialize_async(None) is False

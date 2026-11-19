import pytest

from duka_smartfan_sdk.dukaclient import DukaClient
from tests.fake_fan import FakeFan


@pytest.fixture
def fan():
    fan = FakeFan()
    yield fan
    fan.close()


@pytest.fixture
def client(fan):
    client = DukaClient(
        device_port=fan.port, listen_port=0, bind_address="127.0.0.1"
    )
    yield client
    client.close()

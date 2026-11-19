async def test_search_devices_async(client, fan):
    found = await client.search_devices_async(wait=0.5, search_address="127.0.0.1")
    assert found == [fan.device_id]

from trinket.request import Request


def test_can_store_arbitrary_keys_on_request():
    request = Request(None, None)
    request['custom'] = 'value'
    assert 'custom' in request
    assert request['custom'] == 'value'

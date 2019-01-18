import pytest
from http import HTTPStatus
from wsproto.frame_protocol import CloseReason


@pytest.mark.curio
async def test_websocket_communication(app, client):

    @app.websocket('/echo')
    async def echo(request, ws, **params):
        async for msg in ws:
            await ws.send(msg)

    async with client:
        async with client.websocket('/echo') as ws:
            for message in ('This', 'is', 'a', 'simple', 'test'):
                await ws.send(message)
                echoed = await ws.recv()
                assert echoed == message

        async with client.websocket('/echo') as ws:
            # no communication test
            pass


@pytest.mark.curio
async def test_websockets_store(app, client):

    @app.websocket('/null')
    async def blackhole(request, ws, **params):
        async for data in ws:
            del data

    async with client:
        async with client.websocket('/null'):
            assert len(app.websockets) == 1
            async with client.websocket('/null'):
                assert len(app.websockets) == 2


@pytest.mark.curio
async def test_websocket_binary(app, client):

    @app.websocket('/bin')
    async def binary(request, ws, **params):
        await ws.send(b'test')

    async with client:
        async with client.websocket('/bin') as ws:
            bdata = await ws.recv()
        assert bdata == b'test'


@pytest.mark.curio
async def test_websocket_upgrade(app, client):

    @app.websocket('/ws')
    async def handler(request, ws, **params):
        pass

    async with client:

        # Working upgrade
        async with client.query('GET', '/ws', headers={
                'Upgrade': 'websocket',
                'Connection': 'upgrade',
                'Sec-WebSocket-Key': 'hojIvDoHedBucveephosh8==',
                'Sec-WebSocket-Version': '13'}) as response:
            assert response.status == HTTPStatus.SWITCHING_PROTOCOLS

        # Unknown upgrade
        async with client.query('GET', '/ws', headers={
                'Upgrade': 'h2c',
                'Connection': 'upgrade',
                'Sec-WebSocket-Key': 'hojIvDoHedBucveephosh8==',
                'Sec-WebSocket-Version': '13'}) as response:
            assert response.status == HTTPStatus.BAD_REQUEST

        # No upgrade
        async with client.query('GET', '/ws', headers={
                'Connection': 'keep-alive'}) as response:
            assert response.status == HTTPStatus.UPGRADE_REQUIRED
            assert response.reason == 'Upgrade Required'

        # Connection upgrade with no upgrade header
        async with client.query('GET', '/ws', headers={
                'Connection': 'upgrade'}) as response:
            assert response.status == HTTPStatus.UPGRADE_REQUIRED
            assert response.reason == 'Upgrade Required'


@pytest.mark.curio
async def test_websocket_failure(app, client):

    @app.websocket('/failure')
    async def failme(request, ws, **params):
        raise NotImplementedError('OUCH')

    async with client:
        async with client.websocket('/failure') as ws:
            await ws.recv()

    assert ws.closure.code == CloseReason(1011)
    assert ws.closure.reason == 'Task died prematurely.'


@pytest.mark.curio
async def test_websocket_closure_from_within(app, client):

    @app.websocket('/failure')
    async def failme(request, ws, **params):
        await ws.close()
        await ws.recv()

    async with client:
        async with client.websocket('/failure') as ws:
            await ws.send(b'This shall never be received.')

    assert ws.closure.code == CloseReason(1000)
    assert ws.closure.reason == 'Closed.'

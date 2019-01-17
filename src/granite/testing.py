import http.client
from contextlib import asynccontextmanager

import pytest
import curio

from granite.app import Granite
from granite.websockets import WebsocketPrototype
from wsproto.connection import WSConnection, CLIENT
from wsproto.events import ConnectionEstablished


class Websocket(WebsocketPrototype):

    def __init__(self, host, path):
        super().__init__()
        self.host = host
        self.socket = curio.socket.socket(
            curio.socket.AF_INET, curio.socket.SOCK_STREAM)
        self.protocol = WSConnection(CLIENT, host, path)

    async def connect(self, host, port):
        await self.socket.connect((host, port))
        data = self.protocol.bytes_to_send()
        await self.socket.sendall(data)
        upgrade_response = await self.socket.recv(8096)
        self.protocol.receive_bytes(upgrade_response)
        event = next(self.protocol.events())
        if isinstance(event, ConnectionEstablished):
            print('WebSocket negotiation complete')
        else:
            raise Exception('Expected ConnectionEstablished event!')


class LiveClient:

    def __init__(self, app: Granite, port: int=42000):
        self.app = app
        self.port = port
        self.task = None

    async def __aenter__(self):
        self.task = await curio.spawn(self.app.serve, '', self.port)
        await curio.sleep(0.1)

    async def __aexit__(self, *args, **kwargs):
        await self.task.cancel()

    @asynccontextmanager
    async def query(self, method, uri, headers: dict=None, body=None):
        conn = http.client.HTTPConnection('localhost', self.port)

        def execute(method, uri, headers, body):
            if headers is None:
                headers = {}

            conn.request(method, uri, headers=headers, body=body)
            response = conn.getresponse()
            return response

        yield await curio.run_in_thread(execute, method, uri, headers, body)
        conn.close()

    @asynccontextmanager
    async def websocket(self, resource):
        ws = Websocket(f'localhost:{self.port}', resource)
        await ws.connect('localhost', self.port)
        task = await curio.spawn(ws.flow)
        yield ws
        try:
            await ws.socket.shutdown(curio.socket.SHUT_RDWR)
        except curio.socket.error:
            # socket was killed.
            pass
        await task.join()


@pytest.fixture
def app():
    return Granite()


@pytest.fixture
def client(app):
    return LiveClient(app)

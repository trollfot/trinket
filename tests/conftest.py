import inspect
import logging
import http.client
from contextlib import asynccontextmanager
from functools import partial

import pytest

import curio
from curio import spawn, tcp_server, run_in_thread, socket, Kernel, sleep
from curio.debug import longblock, logcrash
from curio.monitor import Monitor
from curio.socket import AF_INET, SOCK_STREAM

from granite.app import Granite
from granite.websockets import WebsocketPrototype
from granite.handler import request_handler

from wsproto.connection import WSConnection, CLIENT
from wsproto.events import ConnectionEstablished


logging.basicConfig(level=logging.DEBUG)


MARKER = 'curio'


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and inspect.iscoroutinefunction(obj):
        item = pytest.Function(name, parent=collector)
        if MARKER in item.keywords:
            return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):
    """Run tests marked `curio` in a Kernel
    """
    if MARKER in pyfuncitem.keywords:
        kernel = pyfuncitem.funcargs['kernel']
        funcargs = pyfuncitem.funcargs
        testargs = {arg: funcargs[arg]
                    for arg in pyfuncitem._fixtureinfo.argnames}
        kernel.run(pyfuncitem.obj(**testargs))
        return True


def pytest_runtest_setup(item):
    if MARKER in item.keywords and 'kernel' not in item.fixturenames:
        # inject a kernel fixture for all async tests
        item.fixturenames.append('kernel')


class Websocket(WebsocketPrototype):

    def __init__(self, host, path):
        super().__init__()
        self.host = host
        self.socket = socket.socket(AF_INET, SOCK_STREAM)
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
        self.task = await spawn(self.app.serve, '', self.port)
        await sleep(0.1)

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

        yield await run_in_thread(execute, method, uri, headers, body)
        conn.close()

    @asynccontextmanager
    async def websocket(self, resource):
        ws = Websocket(f'localhost:{self.port}', resource)
        await ws.connect('localhost', self.port)
        task = await spawn(ws.flow)
        yield ws
        try:
            await ws.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            # socket was killed.
            pass
        await task.join()


@pytest.fixture
def app():
    return Granite()


@pytest.fixture
def client(app):
    return LiveClient(app)


@pytest.fixture
def client(app):
    return LiveClient(app)


@pytest.fixture
def kernel(request):
    k = Kernel(debug=[longblock, logcrash])
    m = Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k

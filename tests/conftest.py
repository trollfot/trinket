import pytest
import inspect
import http.client
from contextlib import asynccontextmanager
from curio import Kernel
from curio import spawn, tcp_server, run_in_thread
from curio.debug import longblock, logcrash
from curio.monitor import Monitor
from functools import partial
from granite.app import Granite
from granite.handler import request_handler


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


@asynccontextmanager
async def aquery(client, method:bytes, uri: bytes, headers: dict, body: str):

    conn = http.client.HTTPConnection(client.host, client.port)

    def execute(method, uri, headers, body):
        if headers is None:
            headers = {}
        
        conn.request(method, uri, headers=headers, body=body)
        response = conn.getresponse()
        return response

    yield await run_in_thread(execute, method, uri, headers, body)
    conn.close()


class LiveClient:

    def __init__(self, app: Granite, host: bytes='127.0.0.1', port: int=42000):
        self.app = app
        self.port = port
        self.host = host
        self.task = None

    async def __aenter__(self):
        self.task = await spawn(self.app.serve, self.host, self.port)

    async def __aexit__(self, *args, **kwargs):
        await self.task.cancel()

    def query(self, method, uri, headers: dict=None, body=None):
        return aquery(self, method, uri, headers, body)


@pytest.fixture
def app():
    return Granite()


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

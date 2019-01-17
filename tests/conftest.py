import inspect
import pytest

from curio import Kernel
from curio.debug import longblock, logcrash
from curio.monitor import Monitor


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


@pytest.fixture
def kernel(request):
    k = Kernel(debug=[longblock, logcrash])
    m = Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k

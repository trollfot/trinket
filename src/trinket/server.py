import socket
import signal
import curio
from typing import Tuple
from curio.network import tcp_server_socket, run_server
from trinket.proto import Application


class Server:

    __slots__ = ('socket', 'ssl', 'ready')

    def __init__(self, host, port, *,
                 family=socket.AF_INET, backlog=100, ssl=None,
                 reuse_address=True, reuse_port=False):
        self.ssl = ssl
        self.socket = tcp_server_socket(
            host, port, family, backlog, reuse_address, reuse_port)
        self.ready = curio.Event()

    @property
    def sockaddr(self) -> Tuple[str, int]:
        family = self.socket._socket.family
        sockaddr = self.socket._socket.getsockname()
        if family in (socket.AF_INET, socket.AF_INET6):
            sockaddr = list(sockaddr)
        if sockaddr[0] == "0.0.0.0":
            sockaddr[0] = "127.0.0.1"
        if sockaddr[0] == "::":
            sockaddr[0] = "::1"
        return tuple(sockaddr)

    async def run(self, app: Application):
        await run_server(self.socket, app.handle_request, self.ssl)

    async def serve(self, app: Application):
        print('Trinket serving on {}:{}'.format(*self.sockaddr))
        Goodbye = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)
        await app.notify('startup')
        server = await curio.spawn(self.run, app)
        await self.ready.set()
        await Goodbye.wait()
        print('Server is shutting down.')
        await app.notify('shutdown')
        print('Please wait. The remaining tasks are being terminated.')
        await server.cancel()

    @classmethod
    def start(cls, app: Application, host: str, port: int, debug: bool=True):
        server = cls(host, port)
        curio.run(server.serve, app, with_monitor=debug)
        print('Trinket is crumbling away...')

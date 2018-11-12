import pytest
from socket import AF_INET, SOCK_STREAM
from granite.app import Granite
from granite.handler import request_handler
from curio import network, spawn, socket, tcp_server, sleep
from functools import partial


@pytest.fixture
def app():
    return Granite()


def test_simple_request(app, kernel):

    async def client(addr):
        sock = socket.socket(AF_INET, SOCK_STREAM)
        await sock.connect(addr)
        await sock.send(
            b'GET /feeds HTTP/1.1\r\n'
            b'Host: localhost:1707\r\n'
            b'Connection: keep-alive\r\n'
            b'\r\n'
        )
        data = await sock.recv(8192)
        await sock.close()
        assert data == (
            b'HTTP/1.1 404 Not Found\r\n'
            b'Content-Length: 6\r\n'
            b'\r\n/'
            b'feeds'
        )

    async def main():
        handler = partial(request_handler, app)
        server_task = await spawn(tcp_server, '127.0.0.1', 10000, handler)

        c = await spawn(client, ('localhost', 10000))

        await c.join()
        await server_task.cancel()
        
    kernel.run(main())

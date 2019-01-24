import json
import http.client
import mimetypes
from contextlib import asynccontextmanager

import pytest
import curio

from io import BytesIO
from uuid import uuid4
from urllib.parse import urlencode

from trinket.app import Trinket
from trinket.server import Server
from trinket.websockets import WebsocketPrototype
from wsproto import WSConnection, ConnectionType
from wsproto.events import Request, AcceptConnection


class MockWriteSocket:
    """Mock socket that can only write.
    """
    sent = b''

    async def sendall(self, data: bytes):
        self.sent += data


def encode_multipart(data, charset='utf-8'):
    # Ported from Werkzeug testing.
    boundary = '---------------Boundary%s' % uuid4().hex
    body = BytesIO()

    def write(string):
        body.write(string.encode(charset))

    if isinstance(data, dict):
        data = data.items()

    for key, values in data:
        if not isinstance(values, (list, tuple)):
            values = [values]
        for value in values:
            write('--%s\r\nContent-Disposition: form-data; name="%s"' %
                  (boundary, key))
            reader = getattr(value, 'read', None)
            if reader is not None:
                filename = getattr(value, 'filename',
                                   getattr(value, 'name', None))
                content_type = getattr(value, 'content_type', None)
                if content_type is None:
                    content_type = filename and \
                        mimetypes.guess_type(filename)[0] or \
                        'application/octet-stream'
                if filename is not None:
                    write('; filename="%s"\r\n' % filename)
                else:
                    write('\r\n')
                write('Content-Type: %s\r\n\r\n' % content_type)
                while 1:
                    chunk = reader(16384)
                    if not chunk:
                        break
                    body.write(chunk)
            else:
                if not isinstance(value, str):
                    value = str(value)
                else:
                    value = value.encode(charset)
                write('\r\n\r\n')
                body.write(value)
            write('\r\n')
    write('--%s--\r\n' % boundary)

    body.seek(0)
    content_type = 'multipart/form-data; boundary=%s' % boundary
    return body.read(), content_type


class RequestForger:

    @staticmethod
    def prepare_files(files):
        body = {}
        if isinstance(files, dict):
            files = files.items()
        for key, els in files:
            if not els:
                continue
            if not isinstance(els, (list, tuple)):
                # Allow passing a file instance.
                els = [els]
            file_ = els[0]
            if isinstance(file_, str):
                file_ = file_.encode()
            if isinstance(file_, bytes):
                file_ = BytesIO(file_)
            if len(els) > 1:
                file_.name = els[1]
            if len(els) > 2:
                file_.charset = els[2]
            body[key] = file_
        return 'multipart/form-data', body

    @staticmethod
    def encode_body(body, headers):
        if not body or isinstance(body, (str, bytes)):
            return body, headers

        content_type = headers.get('Content-Type')
        if content_type:
            if 'application/x-www-form-urlencoded' in content_type:
                body = urlencode(body)
            elif 'application/json' in content_type:
                body = json.dumps(body)
            elif 'multipart/form-data' in content_type:
                body, headers['Content-Type'] = encode_multipart(body)
            else:
                raise NotImplementedError('Content-Type not supported')
        return body, headers

    @classmethod
    def forge(cls, method, path, body, headers=None, content_type=None):
        headers = headers or {}
        if content_type:
            headers['Content-Type'] = content_type
        body, headers = cls.encode_body(body, headers)
        if isinstance(body, str):
            body = body.encode()
        if body and 'Content-Length' not in headers:
            headers['Content-Length'] = len(body)
        headers = '\r\n'.join('{}: {}'.format(*h) for h in headers.items())
        data = b'%b %b HTTP/1.1\r\n%b\r\n\r\n%b' % (
            method.encode(), path.encode(), headers.encode(), body or b'')
        return data

    @classmethod
    def post(cls, path, body=b'', headers=None, content_type=None, files=None):

        if not body:
            body = {}

        if files is not None:
            content_type, contents = cls.prepare_files(files)
            body.update(contents)

        return cls.forge('POST', path, body, headers, content_type)


class Websocket(WebsocketPrototype):

    def __init__(self):
        super().__init__()
        self.socket = curio.socket.socket(
            curio.socket.AF_INET, curio.socket.SOCK_STREAM)
        self.protocol = WSConnection(ConnectionType.CLIENT)

    async def connect(self, path, host, port):
        await self.socket.connect((host, port))
        request = Request(host=f'{host}:{port}', target=path)
        await self.socket.sendall(self.protocol.send(request))
        upgrade_response = await self.socket.recv(8096)
        self.protocol.receive_data(upgrade_response)
        event = next(self.protocol.events())
        if not isinstance(event, AcceptConnection):
            raise Exception('Websocket handshake failed.')


class LiveClient:

    task = None

    def __init__(self, server: Server, app: Trinket):
        self.app = app
        self.server = server

    async def __aenter__(self):
        self.task = await curio.spawn(self.server.serve, self.app)
        await self.server.ready.wait()

    async def __aexit__(self, *args, **kwargs):
        await self.task.cancel()
        self.task = None

    @asynccontextmanager
    async def query(self, method, uri, headers: dict=None, body=None):

        conn = http.client.HTTPConnection(*self.server.sockaddr)

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
        ws = Websocket()
        await ws.connect(resource, *self.server.sockaddr)
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
    return Trinket()


@pytest.fixture
def server():
    # Testing locally on a free port.
    return Server('', 0)


@pytest.fixture
def client(server, app):
    return LiveClient(server, app)

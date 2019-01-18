try:
    # In case you use json heavily, we recommend installing
    # https://pypi.org/project/python-rapidjson for better performances.
    import rapidjson as json
except ImportError:
    import json as json

import curio
from collections.abc import AsyncGenerator
from trinket.http import HTTPCode, HTTPStatus, Cookies


async def file_iterator(path):
    async with curio.aopen(path, 'rb') as reader:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            yield data


async def response_handler(client, response):
    """The bytes representation of the response
    contains a body only if there's no streaming
    In a case of a stream, it only contains headers.
    """
    await client.sendall(bytes(response))

    if response.stream is not None:
        if isinstance(response.stream, AsyncGenerator):
            async with curio.meta.finalize(response.stream):
                async for data in response.stream:
                    await client.sendall(
                        b"%x\r\n%b\r\n" % (len(data), data))
        else:
            for data in response.stream:
                await client.sendall(
                    b"%x\r\n%b\r\n" % (len(data), data))

        await client.sendall(b'0\r\n\r\n')


class Response:
    """A container for `status`, `headers` and `body`."""

    __slots__ = (
        'headers', 'body', 'bodyless', '_cookies', '_status', 'stream')

    BODYLESS_METHODS = frozenset(('HEAD', 'CONNECT'))
    BODYLESS_STATUSES = frozenset((
        HTTPStatus.CONTINUE, HTTPStatus.SWITCHING_PROTOCOLS,
        HTTPStatus.PROCESSING, HTTPStatus.NO_CONTENT,
        HTTPStatus.NOT_MODIFIED))

    def __init__(self, status=HTTPStatus.OK, body=b'', headers=None):
        self._cookies = None
        self.status = status
        self.body = body
        if headers is None:
            headers = {}
        self.headers = headers
        self.stream = None

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, http_code: HTTPCode):
        self._status = HTTPStatus(http_code)
        self.bodyless = self._status in self.BODYLESS_STATUSES

    @classmethod
    def json(cls, value: str, status=HTTPStatus.OK, headers=None):
        headers = headers is not None and headers or {}
        headers['Content-Type'] = 'application/json; charset=utf-8'
        body = json.dumps(value)
        return cls(status=status, body=body, headers=headers)

    @classmethod
    def raw(cls, body: bytes, status=HTTPStatus.OK, headers=None):
        headers = headers is not None and headers or {}
        headers['Content-Type'] = 'text/plain; charset=utf-8'
        return cls(status=status, body=body, headers=headers)

    @classmethod
    def html(cls, body: bytes, status=HTTPStatus.OK, headers=None):
        headers = headers is not None and headers or {}
        headers['Content-Type'] = 'text/html; charset=utf-8'
        return cls(status=status, body=body, headers=headers)

    @classmethod
    def streamer(self, gen, content_type="application/octet-stream"):
        headers = {
            'Content-Type': content_type,
            'Transfer-Encoding': 'chunked',
            'Keep-Alive': 10,
        }
        response = Response(headers=headers)
        response.stream = gen
        return response

    @property
    def cookies(self):
        if self._cookies is None:
            self._cookies = Cookies()
        return self._cookies

    def __bytes__(self):
        response = b'HTTP/1.1 %a %b\r\n' % (
            self.status.value, self.status.phrase.encode())

        if self._cookies:
            # https://tools.ietf.org/html/rfc7230#page-23
            for cookie in self.cookies.values():
                response += b'Set-Cookie: %b\r\n' % str(cookie).encode()

        # https://tools.ietf.org/html/rfc7230#section-3.3.2 :scream:
        for key, value in self.headers.items():
            response += b'%b: %b\r\n' % (key.encode(), str(value).encode())

        if not self.bodyless:
            if not isinstance(self.body, bytes):
                body = str(self.body).encode()
            else:
                body = self.body

            if self.stream is None and 'Content-Length' not in self.headers:
                response += b'Content-Length: %i\r\n' % len(body)

            response += b'\r\n'
            if body and self.stream is None:
                # We don't write the body if there's a stream.
                # It takes precedence
                response += body
        else:
            response += b'\r\n'
        return response

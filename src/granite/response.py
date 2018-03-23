try:
    # In case you use json heavily, we recommend installing
    # https://pypi.python.org/pypi/ujson for better performances.
    import ujson as json
except ImportError:
    import json as json

from .http import HttpCode, HTTPStatus, Cookies


class Response:
    """A container for `status`, `headers` and `body`."""

    __slots__ = ('headers', 'body', 'bodyless', '_cookies', '_status')

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

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, http_code: HttpCode):
        # Idempotent if `http_code` is already an `HTTPStatus` instance.
        self._status = HTTPStatus(http_code)
        self.bodyless = self._status in self.BODYLESS_STATUSES

    @classmethod
    def json(cls, value):
        body = json.dumps(value)
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        return cls(body=body, headers=headers)

    @classmethod
    def raw(cls, value: bytes):
        headers = {'Content-Type': 'text/plain; charset=utf-8'}
        return cls(body=value, headers=headers)

    @classmethod
    def html(cls, value: bytes):
        headers = {'Content-Type': 'text/html; charset=utf-8'}
        return cls(body=value, headers=headers)

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

            if 'Content-Length' not in self.headers:
                response += b'Content-Length: %i\r\n' % len(body)

            response += b'\r\n'
            if body:
                response += body
        else:
            response += b'\r\n'
        return response

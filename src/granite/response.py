try:
    # In case you use json heavily, we recommend installing
    # https://pypi.python.org/pypi/ujson for better performances.
    import ujson as json
except ImportError:
    import json as json

from .http import HttpCode, HTTPStatus, HttpError, Cookies


class Response:
    """A container for `status`, `headers` and `body`."""

    __slots__ = (
        'request', 'headers', 'body', 'bodyless', '_cookies', '_status',
    )

    BODYLESS_METHODS = frozenset(('HEAD', 'CONNECT'))
    BODYLESS_STATUSES = frozenset((
        HTTPStatus.CONTINUE, HTTPStatus.SWITCHING_PROTOCOLS,
        HTTPStatus.PROCESSING, HTTPStatus.NO_CONTENT,
        HTTPStatus.NOT_MODIFIED))

    def __init__(self, request, status=HTTPStatus.OK, body=b''):
        self._cookies = None
        self.request = request
        self.status = status  # Needs to be after request assignation.
        self.body = body
        self.headers = {}

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, http_code: HttpCode):
        # Idempotent if `http_code` is already an `HTTPStatus` instance.
        self._status = HTTPStatus(http_code)
        self.bodyless = (
            self._status in self.BODYLESS_STATUSES or
            (self.request is not None and
             self.request.method in self.BODYLESS_METHODS))

    def json(self, value: dict):
        # Shortcut from a dict to JSON with proper content type.
        self.headers['Content-Type'] = 'application/json; charset=utf-8'
        self.body = json.dumps(value)

    json = property(None, json)

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

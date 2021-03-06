from http import HTTPStatus
from io import BytesIO
from typing import TypeVar

from biscuits import Cookie
from multifruits import Parser, extract_filename, parse_content_disposition


HTTPCode = TypeVar('HTTPCode', HTTPStatus, int)


class HTTPError(Exception):
    """Exception meant to be raised when an error is occurring.

    E.g.:
        Within your view `raise HTTPError(HTTPStatus.BAD_REQUEST)` will
        direcly return a 400 HTTP status code with descriptive content.
    """

    __slots__ = ('status', 'message')

    def __init__(self, http_code: HTTPCode, message=None):
        # Idempotent if `http_code` is already an `HTTPStatus` instance.
        self.status = HTTPStatus(http_code)
        if isinstance(message, str):
            message = message.encode()
        self.message = message or self.status.phrase.encode()

    def __bytes__(self):
        return b'HTTP/1.1 %a %b\r\nContent-Length: %a\r\n\r\n%b' % (
            self.status.value, self.status.phrase.encode(),
            len(self.message), self.message)


class Multidict(dict):
    """Data structure to deal with several values for the same key.

    Useful for query string parameters or form-like POSTed ones.
    """

    def get(self, key: str, default=...):
        return self.list(key, [default])[0]

    def list(self, key: str, default=...):
        try:
            return self[key]
        except KeyError:
            if default is ... or default == [...]:
                raise HTTPError(HTTPStatus.BAD_REQUEST,
                                "Missing '{}' key".format(key))
            return default


class Query(Multidict):
    """Allow to access casted GET parameters from `request.query`.

    E.g.:
        `request.query.int('weight', 0)` will return an integer or zero.
    """

    TRUE_STRINGS = ('t', 'true', 'yes', '1', 'on')
    FALSE_STRINGS = ('f', 'false', 'no', '0', 'off')
    NONE_STRINGS = ('n', 'none', 'null')

    def bool(self, key: str, default=...):
        value = self.get(key, default)
        if value in (True, False, None):
            return value
        value = value.lower()
        if value in self.TRUE_STRINGS:
            return True
        elif value in self.FALSE_STRINGS:
            return False
        elif value in self.NONE_STRINGS:
            return None
        raise HTTPError(
            HTTPStatus.BAD_REQUEST,
            "Wrong boolean value for '{}={}'".format(key, self.get(key)))

    def int(self, key: str, default=...):
        try:
            return int(self.get(key, default))
        except ValueError:
            raise HTTPError(HTTPStatus.BAD_REQUEST,
                            "Key '{}' must be castable to int".format(key))

    def float(self, key: str, default=...):
        try:
            return float(self.get(key, default))
        except ValueError:
            raise HTTPError(HTTPStatus.BAD_REQUEST,
                            "Key '{}' must be castable to float".format(key))


class Form(Query):
    """Allow to access casted POST parameters from `request.body`."""


class Files(Multidict):
    """Allow to access POSTed files from `request.body`."""


class Multipart:
    """Responsible of the parsing of multipart encoded `request.body`."""

    __slots__ = ('app', 'form', 'files', '_parser', '_current',
                 '_current_headers', '_current_params')

    def __init__(self, app):
        self.app = app

    def initialize(self, content_type: str):
        self._parser = Parser(self, content_type.encode())
        self.form = self.app.Form()
        self.files = self.app.Files()
        return self.form, self.files

    def feed_data(self, data: bytes):
        self._parser.feed_data(data)

    def on_part_begin(self):
        self._current_headers = {}

    def on_header(self, field: bytes, value: bytes):
        self._current_headers[field] = value

    def on_headers_complete(self):
        disposition_type, params = parse_content_disposition(
            self._current_headers.get(b'Content-Disposition'))
        if not disposition_type:
            return
        self._current_params = params
        if b'Content-Type' in self._current_headers:
            self._current = BytesIO()
            self._current.filename = extract_filename(params)
            self._current.content_type = self._current_headers[b'Content-Type']
            self._current.params = params
        else:
            self._current = ''

    def on_data(self, data: bytes):
        if b'Content-Type' in self._current_headers:
            self._current.write(data)
        else:
            self._current += data.decode()

    def on_part_complete(self):
        name = self._current_params.get(b'name', b'').decode()
        if b'Content-Type' in self._current_headers:
            if name not in self.files:
                self.files[name] = []
            self._current.seek(0)
            self.files[name].append(self._current)
        else:
            if name not in self.form:
                self.form[name] = []
            self.form[name].append(self._current)
        self._current = None


class Cookies(dict):
    """A Cookies management class, built on top of biscuits."""

    def set(self, name, *args, **kwargs):
        self[name] = Cookie(name, *args, **kwargs)

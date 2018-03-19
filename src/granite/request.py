try:
    # In case you use json heavily, we recommend installing
    # https://pypi.python.org/pypi/ujson for better performances.
    import ujson as json
    JSONDecodeError = ValueError
except ImportError:
    import json as json
    from json.decoder import JSONDecodeError

from urllib.parse import parse_qs, unquote
from httptools import parse_url
from biscuits import parse
from .http import HTTPStatus, HttpError, Multipart


class Request(dict):
    """A container for the result of the parsing on each request.

    The default parsing is made by `httptools.HttpRequestParser`.
    """
    __slots__ = (
        'app', '_url', 'path', 'query_string', '_query', 'upgrade_protocol',
        'method', 'body', 'headers', 'route', '_cookies', '_form', '_files',
        'keep_alive',
    )

    def __init__(self):
        self.method = 'GET'
        self.headers = {}
        self.body = b''
        self._cookies = None
        self._query = None
        self._form = None
        self._files = None
        self._url = None
        self.keep_alive = False

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, url):
        self._url = url
        parsed = parse_url(url)
        self.path = unquote(parsed.path.decode())
        self.query_string = (parsed.query or b'').decode()

    @property
    def cookies(self):
        if self._cookies is None:
            self._cookies = parse(self.headers.get('COOKIE', ''))
        return self._cookies

    @property
    def query(self):
        if self._query is None:
            parsed_qs = parse_qs(self.query_string, keep_blank_values=True)
            self._query = self.app.Query(parsed_qs)
        return self._query

    def _parse_multipart(self):
        parser = Multipart(self.app)
        self._form, self._files = parser.initialize(self.content_type)
        try:
            parser.feed_data(self.body)
        except ValueError:
            raise HttpError(HTTPStatus.BAD_REQUEST,
                            'Unparsable multipart body')

    def _parse_urlencoded(self):
        try:
            parsed_qs = parse_qs(self.body.decode(), keep_blank_values=True,
                                 strict_parsing=True)
        except ValueError:
            raise HttpError(HTTPStatus.BAD_REQUEST,
                            'Unparsable urlencoded body')
        self._form = self.app.Form(parsed_qs)

    @property
    def form(self):
        if self._form is None:
            if 'multipart/form-data' in self.content_type:
                self._parse_multipart()
            elif 'application/x-www-form-urlencoded' in self.content_type:
                self._parse_urlencoded()
            else:
                self._form = self.app.Form()
        return self._form

    @property
    def files(self):
        if self._files is None:
            if 'multipart/form-data' in self.content_type:
                self._parse_multipart()
            else:
                self._files = self.app.Files()
        return self._files

    @property
    def json(self):
        try:
            return json.loads(self.body.decode())
        except (UnicodeDecodeError, JSONDecodeError):
            raise HttpError(HTTPStatus.BAD_REQUEST, 'Unparsable JSON body')

    @property
    def content_type(self):
        return self.headers.get('CONTENT-TYPE', '')

    @property
    def host(self):
        return self.headers.get('HOST', '')

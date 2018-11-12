from urllib.parse import parse_qs
from biscuits import parse
from granite.http import HTTPStatus, HttpError, Query


class Request(dict):
    
    __slots__ = (
        '_cookies',
        '_query',
        'body',
        'body_size',
        'files',
        'form',
        'headers',
        'keep_alive',
        'method',
        'parse_body',
        'path',
        'query_string',
        'socket',
        'upgrade',
        'url'
    )

    def __init__(self, **headers):
        self._cookies = None
        self._query = None
        self.body_size = 0
        self.url = None
        self.query_string = None
        self.path = None
        self.body = b''
        self.files = None
        self.form = None
        self.headers = headers
        self.keep_alive = False
        self.method = 'GET'
        self.socket = None
        self.upgrade = False
        self.parse_body = None

    @property
    def cookies(self):
        if self._cookies is None:
            self._cookies = parse(self.headers.get('Cookie', ''))
        return self._cookies

    @property
    def query(self):
        if self._query is None:
            parsed_qs = parse_qs(self.query_string, keep_blank_values=True)
            self._query = Query(parsed_qs)
        return self._query

    @property
    def content_type(self):
        return self.headers.get('Content-Type', '')

    @property
    def host(self):
        return self.headers.get('Host', '')

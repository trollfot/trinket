try:
    # In case you use json heavily, we recommend installing
    # https://pypi.python.org/pypi/ujson for better performances.
    import ujson as json
    JSONDecodeError = ValueError
except ImportError:
    import json as json
    from json.decoder import JSONDecodeError

from io import BytesIO
from urllib.parse import parse_qs, unquote

from biscuits import parse
from curio.errors import TaskTimeout
from curio import timeout_after
from httptools import parse_url
from multifruits import Parser, extract_filename, parse_content_disposition

from .http import HTTPStatus, HttpError, Form, Files, Query


class Multipart:
    """Responsible of the parsing of multipart encoded `request.body`."""

    __slots__ = ('form', 'files', '_parser', '_current',
                 '_current_headers', '_current_params')

    def __init__(self, content_type: str):
        self._parser = Parser(self, content_type.encode())
        self.form = Form()
        self.files = Files()

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


async def multipart(expected_size, stream, content_type):
    try:
        read = 0
        parser = Multipart(content_type)
        while read < expected_size:
            try:
                chunk = await timeout_after(2, stream.read, 4096)
                parser.feed_data(chunk)
                read += len(chunk)
            except TaskTimeout:
                break

            if not chunk:
                break

        import pdb
        pdb.set_trace()
            
        return read, parser.form, parser.files
    except ValueError:
        raise HttpError(HTTPStatus.BAD_REQUEST,
                        'Unparsable multipart body')


async def url_encoded(expected_size, stream, *args):

    read = 0
    data = b''
    while read < expected_size:
        try:
            chunk = await timeout_after(2, stream.read, 8192)
            if not chunk:
                break
        except TaskTimeout:
            break

        read += len(chunk)
        data += chunk

    try:
        parsed = parse_qs(data, keep_blank_values=True, strict_parsing=True)
        return read, Form(parsed), Files()
    except ValueError:
        raise HttpError(HTTPStatus.BAD_REQUEST,
                        'Unparsable urlencoded body')


class Request(dict):

    COMPLEX_CONTENT_TYPES = {
        'multipart/form-data': multipart,
        'application/x-www-form-urlencoded': url_encoded,
        }
    
    __slots__ = (
        '_cookies',
        '_files',
        '_form',
        '_query',
        '_read_body_size',
        '_url',
        'body',
        'headers',
        'keep_alive',
        'method',
        'path',
        'query_string',
        'stream',
    )

    def __init__(self):
        self.stream = None
        self.method = 'GET'
        self.headers = {}
        self.body = b''
        self._cookies = None
        self._query = None
        self._form = None
        self._files = None
        self._url = None
        self.keep_alive = False
        self._read_body_size = 0

    async def parse_body(self):
        expected = int(self.headers.get('CONTENT-LENGTH', 0))
        if not self._read_body_size and expected:
            disposition = self.content_type.split(';', 1)[0]
            parser = self.COMPLEX_CONTENT_TYPES.get(disposition)
            if parser is None:
                import pdb
                pdb.set_trace()
                raise NotImplementedError("Don't know how to parse")
            else:
                (self._read_body_size, self._form, self._files
                ) = await parser(expected, self.stream, self.content_type)
                if not self._read_body_size:
                    raise TypeError('Empty body !')

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
            self._query = Query(parsed_qs)
        return self._query

    @property
    def content_type(self):
        return self.headers.get('CONTENT-TYPE', '')

    @property
    def host(self):
        return self.headers.get('HOST', '')

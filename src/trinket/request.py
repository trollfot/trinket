from biscuits import parse
from trinket.http import HTTPStatus, HTTPError, Query
from trinket.parsers import CONTENT_TYPES_PARSERS
from httptools import HttpParserUpgrade, HttpParserError, HttpRequestParser
from httptools.parser.errors import HttpParserInvalidMethodError
from httptools import parse_url
from urllib.parse import parse_qs, unquote


class Channel:

    __slots__ = (
        'parser',
        'request',
        'complete',
        'headers_complete',
        'socket',
        'reader',
    )

    def __init__(self, socket):
        self.complete = False
        self.headers_complete = False
        self.parser = HttpRequestParser(self)
        self.request = None
        self.socket = socket
        self.reader = self._reader()

    def data_received(self, data: bytes):
        try:
            self.parser.feed_data(data)
        except HttpParserUpgrade:
            self.request.upgrade = True
        except (HttpParserError, HttpParserInvalidMethodError) as exc:
            # We should log the exc.
            raise HTTPError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')

    async def read(self, parse: bool=True) -> bytes:
        data = await self.socket.recv(1024)
        if data:
            if parse:
                self.data_received(data)
            return data

    async def _reader(self) -> bytes:
        while not self.complete:
            data = await self.read()
            if not data:
                break
            yield data

    async def _drainer(self) -> bytes:
        while True:
            data = await self.read(parse=False)
            if not data:
                break
            yield data

    def on_header(self, name: bytes, value: bytes):
        value = value.decode()
        if value:
            name = name.decode().title()
            if name in self.request.headers:
                self.request.headers[name] += ', {}'.format(value)
            else:
                self.request.headers[name] = value

    def on_body(self, data: bytes):
        self.request.body += data

    def on_message_begin(self):
        self.complete = False
        self.request = Request(self.socket, self.reader)

    def on_message_complete(self):
        self.complete = True

    def on_url(self, url: bytes):
        self.request.url = url
        parsed = parse_url(url)
        self.request.path = unquote(parsed.path.decode())
        self.request.query_string = (parsed.query or b'').decode()

    def on_headers_complete(self):
        self.request.keep_alive = self.parser.should_keep_alive()
        self.request.method = self.parser.get_method().decode().upper()
        self.headers_complete = True

    async def __aiter__(self):
        keep_alive = True
        while keep_alive:
            data = await self.read()
            if data is None:
                break
            if self.headers_complete:
                yield self.request
                keep_alive = self.request.keep_alive
                if keep_alive:
                    if not self.complete:
                        await self.reader.aclose()
                        # We drain if there's an uncomplete request.
                        async for _ in self._drainer():
                            pass
                    self.request = None
                    self.complete = False
                    self.headers_complete = False
                    self.reader = self._reader()


class Request(dict):

    __slots__ = (
        '_cookies',
        '_query',
        '_reader',
        'body',
        'files',
        'form',
        'headers',
        'keep_alive',
        'method',
        'path',
        'query_string',
        'socket',
        'upgrade',
        'url'
    )

    def __init__(self, socket, reader, **headers):
        self._cookies = None
        self._query = None
        self._reader = reader
        self.body = b''
        self.files = None
        self.form = None
        self.headers = headers
        self.keep_alive = False
        self.method = None
        self.path = None
        self.query_string = None
        self.socket = socket
        self.upgrade = False
        self.url = None

    @property
    async def raw_body(self):
        async for data in self._reader:
            # Everything ends up in self.body due to the
            # parsing feeding the on_body.
            pass
        return self.body

    async def parse_body(self):
        disposition = self.content_type.split(';', 1)[0]
        parser_type = CONTENT_TYPES_PARSERS.get(disposition)
        if parser_type is None:
            raise NotImplementedError(f"Don't know how to parse {disposition}")
        content_parser = parser_type(self.content_type)
        next(content_parser)
        try:
            if self.body:
                content_parser.send(self.body)

            async for data in self._reader:
                # This will populate self.body
                # It can be a problem for large requests.
                # we might want to do something like : self.body = b''
                # at each iteration.
                content_parser.send(data)
        except Exception as exc:
            # do log
            raise
        else:
            self.form, self.files = next(content_parser)
        finally:
            content_parser.close()

    @property
    def cookies(self):
        if self._cookies is None:
            self._cookies = parse(self.headers.get('Cookie', b''))
        return self._cookies

    @property
    def query(self) -> Query:
        if self._query is None:
            parsed_qs = parse_qs(self.query_string, keep_blank_values=True)
            self._query = Query(parsed_qs)
        return self._query

    @property
    def content_type(self) -> bytes:
        return self.headers.get('Content-Type', b'')

    @property
    def host(self) -> bytes:
        return self.headers.get('Host', b'')

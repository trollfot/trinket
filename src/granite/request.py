from urllib.parse import parse_qs
from biscuits import parse
from granite.http import HTTPStatus, HttpError, Query
from granite.parsers import CONTENT_TYPES_PARSERS
from http_parser.parser import HttpParser


async def socket_reader(socket, parser):
    while not parser.is_message_complete():
        socket_ttl = socket._socket.gettimeout()
        socket._socket.settimeout(10)
        data = await socket.recv(1024)
        socket._socket.settimeout(socket_ttl)
        if not data:
            break

        received = len(data)
        nparsed = parser.execute(data, received)
        if nparsed != received:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')
        yield data


class ClientRequest:

    def __init__(self, socket):
        self.socket = socket
        self.parser = HttpParser()
        self.reader = socket_reader(socket, self.parser)

    async def __aenter__(self):
        async for data in self.reader:
            if self.parser.is_headers_complete():
                request = Request(
                    self.socket, self.reader, **self.parser.get_headers())
                request.url = self.parser.get_url()
                request.method = self.parser.get_method()
                request.path = self.parser.get_path()
                request.query_string = self.parser.get_query_string()
                request.keep_alive = bool(self.parser.should_keep_alive())
                request.upgrade = bool(self.parser.is_upgrade())

                if self.parser.is_partial_body():
                    request.body = self.parser.recv_body()
                    request.body_size = len(request.body)

                self.request = request
                return request
        return None

    async def __aexit__(self, exc_type, exc, tb):
        # Drain and close.
        async for _ in self.reader:
            pass
        else:
            await self.reader.aclose()

        if exc is not None:
            if isinstance(exc, HttpError):
                await self.socket.sendall(bytes(exc))
            else:
                raise exc


class Request(dict):
    
    __slots__ = (
        '_cookies',
        '_query',
        '_reader',
        'body',
        'body_size',
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
        self.body_size = 0
        self.files = None
        self.form = None
        self.headers = headers
        self.keep_alive = False
        self.method = 'GET'
        self.path = None
        self.query_string = None
        self.socket = socket
        self.upgrade = False
        self.url = None

    async def raw_body(self):
        async for data in self._reader:
            self.body += data
            self.body_size += len(data)
        return self.body

    async def parse_body(self):
        disposition = self.content_type.split(';', 1)[0]
        parser_type = CONTENT_TYPES_PARSERS.get(disposition)
        if parser_type is None:
            raise NotImplementedError(f"Don't know how to parse {disposition}")
        content_parser = parser_type(self.content_type)
        next(content_parser)
        if self.body:
            content_parser.send(self.body)

        async for data in self._reader:
            content_parser.send(data)
            self.body_size += len(data)

        self.form, self.files = next(content_parser)
        content_parser.close()

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

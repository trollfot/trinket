# -*- coding: utf-8 -*-

import signal
from curio import run, spawn, socket, ssl, tcp_server, current_task
from curio import SignalQueue, Event, CancelledError, TaskGroup
from collections import namedtuple, defaultdict
from autoroutes import Routes
from httptools import (
    HttpParserUpgrade, HttpParserError, HttpRequestParser, parse_url)
from .request import Request
from .response import Response
from .http import HTTPStatus, HttpError

from pycohttpparser.api import Parser as HTTPParser



class ConnectionManager:

    max_head_size = 8**5  # 4096*8

    def __init__(self, app, client):
        self.client = client
        self.parser = HttpRequestParser(self)
        self.complete = False
        self.request = None
        
    async def receive(self):

        data = await self.client.recv(self.max_head_size)
        # Data should contain the entirety of the headers.
        try:
            self.parser.feed_data(data)
            if self.complete:
                return self.request
        except HttpParserError:
            return HttpError(
                HTTPStatus.BAD_REQUEST,
                message=b'Unparsable request')

    def on_message_begin(self):
        self.request = Request()

    def on_header(self, name: bytes, value: bytes):
        value = value.decode()
        if value:
            name = name.decode().upper()
            if name in self.request.headers:
                self.request.headers[name] += ', {}'.format(value)
            else:
                self.request.headers[name] = value

    def on_headers_complete(self):
        self.request.method = self.parser.get_method().decode().upper()

    def on_body(self, body: bytes):
        self.request.body += body

    def on_url(self, url: bytes):
        self.request.url = url

    def on_message_complete(self):
        self.complete = True



async def http_handler(app, client):

    connection = ConnectionManager(app, client)
    async with client:
        while True:
            try:
                request = await connection.receive()
                if isinstance(request, HttpError):
                    await client.send(bytes(request))
                else:
                    response = await app(request)
                    await client.send(bytes(response))
            except (ConnectionResetError, BrokenPipeError):
                break


async def pebble_server(app, address):

    def create_listening_socket(address):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen()
        return sock

    sock = create_listening_socket(address)
    print("Now listening on %s:%d" % address)

    async with SignalQueue(signal.SIGHUP) as restart:
        async with sock:
            while True:
                client, _ = await sock.accept()
                await spawn(http_handler, app, client, daemon=True)


Route = namedtuple('Route', ['payload', 'vars'])
            
class Granite:

    def __init__(self):
        self.routes = Routes()

    async def on_error(self, request: Request, response: Response, error):
        if not isinstance(error, HttpError):
            error = HttpError(HTTPStatus.INTERNAL_SERVER_ERROR,
                              str(error).encode())
        response.status = error.status
        response.body = error.message

    async def lookup(self, request: Request, response: Response):
        route = Route(*self.routes.match(request.path))
        if not route.payload:
            raise HttpError(HTTPStatus.NOT_FOUND, request.path)
        # Uppercased in order to only consider HTTP verbs.
        if request.method.upper() not in route.payload:
            raise HttpError(HTTPStatus.METHOD_NOT_ALLOWED)
        return route.payload[request.method.upper()], route.vars

    async def __call__(self, request: Request) -> Response:
        response = Response(self, request)
        try:
            found = await self.lookup(request, response)
            if found is not None:
                handler, params = found
                await handler(request, response, **params)
        except Exception as error:
            await self.on_error(request, response, error)
        return response

    def serve(self, host='127.0.0.1', port=5000):
         run(pebble_server(self, (host, port)))

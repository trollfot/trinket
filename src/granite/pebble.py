# -*- coding: utf-8 -*-

import signal
from curio import run, spawn, socket, ssl, tcp_server, run_in_thread
from curio import Queue, SignalQueue, Event, CancelledError, TaskGroup
from collections import namedtuple, defaultdict
from autoroutes import Routes
from httptools import (
    HttpParserUpgrade, HttpParserError, HttpRequestParser, parse_url)
from .request import Request
from .response import Response
from .http import HTTPStatus, HttpError
from functools import partial
import httpparser


class Parser:

    def __init__(self):
        self.parser = httpparser.Request(self)
        self.request = None
        self.complete = False

    def on_header(self, name, value):
        value = value.decode()
        if value:
            name = name.decode().upper()
            if name in self.request.headers:
                self.request.headers[name] += ', {}'.format(value)
            else:
                self.request.headers[name] = value

    def on_uri(self, uri):
        self.request.url = uri

    def on_body(self, body):
        self.request.body += body

    def on_complete(self):
        self.request.keep_alive = self.parser.should_keep_alive()
        self.complete = True

    def data_received(self, data):
        if self.request is None:
            self.request = Request()
        self.parser.parse(data)


class RequestHandler:

    def __init__(self, app):
        self.app = app

    async def receive(self, client):
        parser = Parser()
        while True:
            data = await client.recv(4096)
            if not data:
                break
            
            parser.data_received(data)
            if parser.complete:
                yield parser.request
                parser.request = None
                parser.complete = False

    async def __call__(self, client, addr):
        try:
            async with client:
                client._socket.settimeout(10.0)
                try:
                    keep_alive = True
                    async for request in self.receive(client):
                        if request is None:
                            break 
                        if isinstance(request, HttpError):
                            await client.sendall(bytes(request))
                        else:
                            response = await self.app(request)
                            await client.sendall(bytes(response))
                            keep_alive = request.keep_alive
                        if keep_alive:
                            client._socket.settimeout(10.0)
                        else:
                            break
                except (ConnectionResetError, BrokenPipeError):
                    pass
        except socket.timeout:
            print('Closed for inactivity')


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
         #run(pebble_server(self, (host, port)))
        handler = RequestHandler(self)
        try:
            run(tcp_server(host, port, handler))
        except KeyboardInterrupt:
            pass

# -*- coding: utf-8 -*-

import signal
from curio import run, spawn, socket, ssl, tcp_server, run_in_thread
from curio import SignalQueue, Event, CancelledError, TaskGroup
from collections import namedtuple, defaultdict
from autoroutes import Routes
from httptools import (
    HttpParserUpgrade, HttpParserError, HttpRequestParser, parse_url)
from .request import Request
from .response import Response
from .http import HTTPStatus, HttpError

from pycohttpparser.api import Parser as HTTPParser, ParseError


async def http_handler(app, client):

    parser = HTTPParser()
    max_head_size = 8**4

    async with client:
        while True:
            data = await client.recv(max_head_size)
            if not data:
                break
            try:
                parsed = parser.parse_request(memoryview(data))
            except:
                await client.sendall(bytes(
                    HttpError(
                        HTTPStatus.BAD_REQUEST,
                        message=b'Unparsable request')))

            headers = {}
            for name, value in parsed.headers:
                headers[name.tobytes().decode()] = value.tobytes().decode()
            request = Request(
                parsed.path.tobytes(),
                parsed.method.tobytes().decode().upper(),
                headers=headers,
                body=data[parsed.consumed:],
                stream=client.as_stream())

            response = await app(request)
            await client.sendall(bytes(response))


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





class RequestHandler:

    def __init__(self, app):
        self.app = app
        self.parser = HTTPParser()
        self.max_head_size = 8**5

    def make_request(self, data):
        try:
            parsed = self.parser.parse_request(memoryview(data))
        except ParseError:
            return HttpError(
                HTTPStatus.BAD_REQUEST,
                message=b'Unparsable request')

        if parsed:
            headers = {}
            for name, value in parsed.headers:
                headers[name.tobytes().decode()] = value.tobytes().decode()
                
            request = Request(
                parsed.path.tobytes(),
                parsed.method.tobytes().decode().upper(),
                headers=headers,
                body=data[parsed.consumed:])
            return request

    async def http_cycle(self, client):
        data = await client.recv(self.max_head_size)
        if not data:
            return
        request = await run_in_thread(self.make_request, data)
        if request is not None:
            if isinstance(request, HttpError):
                await client.sendall(bytes(request))
            else:
                response = await self.app(request)
                await client.sendall(bytes(response))

    async def __call__(self, client, addr):
        async with client:
            while True:
                try:
                    await self.http_cycle(client)
                except ConnectionResetError:
                    break
                

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
        run(tcp_server(host, port, handler))

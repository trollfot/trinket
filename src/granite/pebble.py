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



class Receiver:

    def __init__(self):
        self.parser = httpparser.Request(self)

    def on_header(self, name, value):
        pass

    def on_headers(self, headers):
        pass

    def on_uri(self, uri):
        pass

    def on_body(self, body):
        pass

    def on_complete(self):
        pass

    def data_received(self, data):
        self.parser.parse(data)




class RequestHandler:

    def __init__(self, app):
        self.app = app
        self.max_head_size = 8**5

    async def receive(self, client):
        p = HttpParser()
        while True:
            data = await client.recv(4096)
            if not data:
                break

            recved = len(data)
            nparsed = p.execute(data, recved)
            assert nparsed == recved

            if p.is_message_begin():
                client._socket.settimeout(None)
            
            if p.is_headers_complete():
                request = Request(
                    p.get_url().encode(),
                    method=p.get_method(),
                    headers=p.get_headers())

            if p.is_partial_body():
                request.body += p.recv_body()

            if p.is_message_complete():
                yield request
                p = HttpParser()

    async def __call__(self, client, addr):
        try:
            async with client:
                client._socket.settimeout(10.0)
                try:
                    async for request in self.receive(client):
                        if request is None:
                            break 
                        if isinstance(request, HttpError):
                            await client.sendall(bytes(request))
                        else:
                            response = await self.app(request)
                            await client.sendall(bytes(response))
                            client._socket.settimeout(10.0)
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

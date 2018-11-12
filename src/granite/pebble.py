# -*- coding: utf-8 -*-

import signal
from functools import wraps, partial
from collections import defaultdict
from collections.abc import AsyncGenerator

import curio
from curio import TaskGroup, SignalEvent
from curio import run, spawn, socket, tcp_server

from autoroutes import Routes
from http_parser.parser import HttpParser

from granite import lifecycle
from granite.request import Request
from granite.response import Response
from granite.http import HTTPStatus, HttpError
from granite.websockets import Websocket
from granite.parsers import CONTENT_TYPES_PARSERS


async def response_handler(client, response):
    """The bytes representation of the response
    contains a body only if there's no streaming
    In a case of a stream, it only contains headers.
    """
    await client.sendall(bytes(response))

    if response.stream is not None:
        if isinstance(response.stream, AsyncGenerator):
            async with curio.meta.finalize(response.stream):
                async for data in response.stream:
                    await client.sendall(
                        b"%x\r\n%b\r\n" % (len(data), data))
        else:
            for data in response.stream:
                await client.sendall(
                    b"%x\r\n%b\r\n" % (len(data), data))

        await client.sendall(b'0\r\n\r\n')


async def read_request_body(request, http_parser, flush=False):

    if http_parser.is_message_complete():
        # This request is already handled.
        return

    if not flush:
        disposition = request.content_type.split(';', 1)[0]
        parser_type = CONTENT_TYPES_PARSERS.get(disposition)
        if parser_type is None:
            raise NotImplementedError(f"Don't know how to parse {disposition}")
        content_parser = parser_type(request.content_type)
        next(content_parser)
        if request.body:
            # if there's already a piece of body
            # parse it.
            content_parser.send(request.body)  

    while True:
        socket_ttl = request.socket._socket.gettimeout()
        request.socket._socket.settimeout(10)
        data = await request.socket.recv(1024)
        request.socket._socket.settimeout(socket_ttl)
        if not data:
            break

        received = len(data)
        request.body_size += received
        nparsed = http_parser.execute(data, received)
        if nparsed != received:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')

        if not flush:
            content_parser.send(data)

        if http_parser.is_message_complete():
            if not flush:
                request.form, request.files = next(content_parser)
                content_parser.close()
            break


async def make_request(client):
    parser = HttpParser()
    while True:
        socket_ttl = client._socket.gettimeout()
        client._socket.settimeout(10)
        data = await client.recv(1024)
        client._socket.settimeout(socket_ttl)
        if not data:
            break
        received = len(data)
        nparsed = parser.execute(data, received)

        if nparsed != received:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')

        if parser.is_headers_complete():
            request = Request(**parser.get_headers())
            request.url = parser.get_url()
            request.method = parser.get_method()
            request.path = parser.get_path()
            request.query_string = parser.get_query_string()
            request.keep_alive = bool(parser.should_keep_alive())
            request.upgrade = bool(parser.is_upgrade())
            request.socket = client
            request.parse_body = partial(read_request_body, request, parser)

            if parser.is_partial_body():
                # We read past the headers
                # Save the chunk we currently got.
                request.body = parser.recv_body()
                request.body_size = len(request.body)

            return request
                

def socket_shield(handler):
    @wraps(handler)
    async def shielded_handler(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except (ConnectionResetError, BrokenPipeError):
            # The client disconnected or the network is suddenly
            # unreachable.
            pass
    return shielded_handler


@socket_shield
async def request_handler(app, client, addr):
    keep_alive = True
    async with client:
        while keep_alive:
            try:
                request = await make_request(client)
            except HttpError as exc:
                return await client.sendall(bytes(exc))
            except curio.TaskTimeout:
                return
            else:
                keep_alive = request is not None and request.keep_alive
                if request is not None:
                    # We write the response or stream it.
                    response = await app(request)
                    await response_handler(client, response)
                    await request.parse_body(flush=True)


Goodbye = SignalEvent(signal.SIGINT, signal.SIGTERM)


class Granite:

    __slots__ = ('hooks', 'routes', 'websockets')

    def __init__(self):
        self.routes = Routes()
        self.websockets = set()
        self.hooks = defaultdict(list)

    async def on_error(self, request: Request, error):
        response = Response()
        if not isinstance(error, HttpError):
            error = HttpError(HTTPStatus.INTERNAL_SERVER_ERROR,
                              str(error).encode())
        response.status = error.status
        response.body = error.message
        return response

    async def lookup(self, request: Request):
        payload, params = self.routes.match(request.path)

        if not payload:
            raise HttpError(HTTPStatus.NOT_FOUND, request.path)

        # Uppercased in order to only consider HTTP verbs.
        handler = payload.get(request.method.upper(), None)
        if handler is None:
            raise HttpError(HTTPStatus.METHOD_NOT_ALLOWED)

        # We check if the route is for a websocket handler.
        # If it is, we make sure we were asked for an upgrade.
        if payload.get('websocket', False) and not request.upgrade:
            raise HttpError(
                HTTPStatus.UPGRADE_REQUIRED,
                'This is a websocket endpoint, please upgrade.')
        
        return handler, params

    @lifecycle.handler_events
    async def __call__(self, request: Request):
        try:
            handler, params = await self.lookup(request)
            return await handler(request, **params)
        except Exception as error:
            return await self.on_error(request, error)

    def route(self, path: str, methods: list=None, **extras: dict):
        if methods is None:
            methods = ['GET']

        def wrapper(func):
            payload = {method: func for method in methods}
            payload.update(extras)
            self.routes.add(path, **payload)
            return func

        return wrapper

    def websocket(self, path: str, **extras: dict):

        def wrapper(func):
            @wraps(func)
            async def websocket_handler(request, **params):
                websocket = Websocket(request)
                await websocket.upgrade()                    
                self.websockets.add(websocket)

                async with TaskGroup(wait=any) as ws:
                    await ws.spawn(func, request, websocket, **params)
                    await ws.spawn(websocket.run)
                self.websockets.discard(websocket)

            payload = {'GET': websocket_handler, 'websocket': True}
            payload.update(extras)
            self.routes.add(path, **payload)
            return func

        return wrapper

    def listen(self, name: str):
        def wrapper(func):
            self.hooks[name].append(func)
        return wrapper

    async def notify(self, name, *args, **kwargs):
        if name in self.hooks:
            for hook in self.hooks[name]:
                result = await hook(*args, **kwargs)
                if result is not None:
                    # Allows to shortcut the chain.
                    return result
        return None

    @lifecycle.server_events
    async def serve(self, host, port):
        print('Granite serving on {}:{}'.format(host, port))
        handler = partial(request_handler, self)
        server = await spawn(tcp_server, host, port, handler)
        await Goodbye.wait()
        print('Server is shutting down.')
        print('Please wait. The remaining tasks are being terminated.')
        await server.cancel()

    def start(self, host='127.0.0.1', port=5000, debug=True):
        run(self.serve, host, port, with_monitor=debug)
        print('Granite is crumbling away...')

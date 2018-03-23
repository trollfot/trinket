# -*- coding: utf-8 -*-

import signal
from functools import wraps, partial
from collections import defaultdict

from curio import run, spawn, socket, tcp_server
from curio import TaskGroup, SignalEvent
from autoroutes import Routes
from httptools import HttpParserUpgrade, HttpParserError, HttpRequestParser

from .request import Request
from .response import Response
from .http import HTTPStatus, HttpError
from .websockets import Websocket


class HTTPParser:

    __slots__ = ('parser', 'request', 'complete')
    
    def __init__(self):
        self.parser = HttpRequestParser(self)
        self.complete = False

    def data_received(self, data):
        try:
            self.parser.feed_data(data)
        except HttpParserUpgrade as upgrade:
            self.request.upgrade = True

    def on_header(self, name, value):
        value = value.decode()
        if value:
            name = name.decode().upper()
            if name in self.request.headers:
                self.request.headers[name] += ', {}'.format(value)
            else:
                self.request.headers[name] = value

    def on_message_begin(self):
        self.complete = False
        self.request = Request()

    def on_url(self, url):
        self.request.url = url

    def on_headers_complete(self):
        self.request.keep_alive = self.parser.should_keep_alive()
        self.request.method = self.parser.get_method().decode().upper()
        self.complete = True


async def read_headers(stream, max_field_size=2**16):
    httpparser = HTTPParser()
    async for line in stream:
        if not line:
            break
        if len(line) > max_field_size:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Request headers too large.')
        try:
            httpparser.data_received(line)
        except HttpParserError as exc:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')
        if not line.strip():
            # End of the headers section.
            break

    if httpparser.complete:
        return httpparser.request


async def request_handler(app, client, addr):
    stream = client.makefile('rb')
    async with client:
        try:
            keep_alive = True
            client._socket.settimeout(10.0)
            while keep_alive:
                try:
                    request = await read_headers(stream)
                except HttpError as exc:
                    await client.sendall(bytes(exc))
                    continue
                else:
                    if request is None:
                        break
                    keep_alive = request.keep_alive
                    request.socket = client
                    client._socket.settimeout(None)  # Suspend timeout
                    response = await app(request)
                    if response:
                        await client.sendall(bytes(response))
                finally:
                    if keep_alive:
                        # We answered. The socket timeout is reset.
                        client._socket.settimeout(10.0)
        except HttpError as exc:
            # An error occured during the processing of the request.
            # We write down an error for the client.
            await client.sendall(bytes(exc))
        except (ConnectionResetError, BrokenPipeError):
            # The client disconnected or the network is suddenly
            # unreachable.
            pass
        except socket.timeout:
            # Our socket timed out, due to the lack of activity.
            pass


def handler_lifecycle(func):
    @wraps(func)
    async def lifecycle(app, request, *args, **kwargs):
        response = await app.notify('request', request)
        if response is None:
            response = await func(app, request, *args, **kwargs)
        if response is not None:
            await app.notify('response', request, response)
        return response
    return lifecycle


def app_lifecycle(func):
    @wraps(func)
    async def lifecycle(app, *args, **kwargs):
        await app.notify('startup')
        await func(app, *args, **kwargs)
        await app.notify('shutdown')
    return lifecycle


Goodbye = SignalEvent(signal.SIGINT, signal.SIGTERM)


class Granite:

    __slots__ = ('hooks', 'routes', 'websockets')

    def __init__(self):
        self.routes = Routes()
        self.websockets = set()
        self.hooks = defaultdict(list)

    async def on_error(self, request: Request, error):
        response = Response(request)
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

    @handler_lifecycle
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
            @wraps(func)
            async def handler(request, **params):
                response = Response(request)
                await func(request, response, **params)
                return response

            payload = {method: handler for method in methods}
            payload.update(extras)
            self.routes.add(path, **payload)
            return handler

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

    @app_lifecycle
    async def serve(self, host, port):
        print('Granite serving on {}:{}'.format(host, port))
        handler = partial(request_handler, self)
        server = await spawn(tcp_server, host, port, handler)
        await Goodbye.wait()
        print('Server is shutting down.')
        print('Please wait. The remaining tasks are being terminated.')
        await server.cancel()

    def start(self, host='127.0.0.1', port=5000, debug=False):
        run(self.serve, host, port, with_monitor=debug)
        print('Granite is crumbling away...')

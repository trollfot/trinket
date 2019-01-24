from abc import ABC
from curio import socket, Queue, Event, TaskGroup
from trinket.http import HTTPStatus, HTTPError
from wsproto import WSConnection, ConnectionType
from wsproto.connection import ConnectionState
from wsproto.utilities import RemoteProtocolError
from wsproto.events import (
    Request, AcceptConnection, CloseConnection, Message, Ping)


class WebsocketClosedError(Exception):
    pass


class WebsocketPrototype(ABC):

    __slots__ = (
        'socket',
        'protocol',
        'outgoing',
        'incoming',
        'closure',
        'closing'
    )

    def __init__(self):
        self.outgoing = Queue()
        self.incoming = Queue()
        self.closure = None
        self.closing = Event()

    @property
    def closed(self):
        return self.closing.is_set()

    async def send(self, data):
        if self.closed:
            raise WebsocketClosedError()
        await self.outgoing.put(Message(data=data))

    async def recv(self):
        if not self.closed:
            async with TaskGroup(wait=any) as g:
                receiver = await g.spawn(self.incoming.get)
                await g.spawn(self.closing.wait)
            if g.completed is receiver:
                return receiver.result

    async def __aiter__(self):
        async for msg in self.incoming:
            yield msg

    async def close(self, code=1000, reason='Closed.'):
        await self.outgoing.put(
            CloseConnection(code=code, reason=reason))

    async def _handle_incoming(self):
        events = self.protocol.events()
        while not self.closed:
            try:
                data = await self.socket.recv(4096)
            except ConnectionResetError:
                return await self.closing.set()

            self.protocol.receive_data(data)
            try:
                event = next(events)
            except StopIteration:
                # Connection dropped unexpectedly
                return await self.closing.set()

            if isinstance(event, CloseConnection):
                self.closure = event
                await self.outgoing.put(event.response())
                await self.closing.set()
            elif isinstance(event, Message):
                await self.incoming.put(event.data)
            elif isinstance(event, Ping):
                await self.outgoing.put(event.response())

    async def _handle_outgoing(self):
        async for event in self.outgoing:

            if event is None or self.protocol.state is ConnectionState.CLOSED:
                return await self.closing.set()

            data = self.protocol.send(event)
            try:
                await self.socket.sendall(data)
                if isinstance(data, CloseConnection):
                    self.closure = event
                    return await self.closing.set()
            except socket.error:
                return await self.closing.set()

    async def flow(self, *tasks):
        async with TaskGroup(tasks=tasks) as ws:
            incoming = await ws.spawn(self._handle_incoming)
            outgoing = await ws.spawn(self._handle_outgoing)
            finished = await ws.next_done()

            if finished is incoming:
                await self.outgoing.put(None)
                await outgoing.join()
            elif finished in tasks:
                # Task is finished.
                # We ask for the outgoing to finish
                if finished.exception:
                    await self.close(1011, 'Task died prematurely.')
                else:
                    await self.close()
                await outgoing.join()


class Websocket(WebsocketPrototype):
    """Server-side websocket running a handler parallel to the I/O.
    """
    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.protocol = WSConnection(ConnectionType.SERVER)

    async def upgrade(self, request):
        data = '{} {} HTTP/1.1\r\n'.format(
            request.method, request.url)
        data += '\r\n'.join(
            ('{}: {}'.format(k, v)
             for k, v in request.headers.items())) + '\r\n\r\n'

        data = data.encode()

        try:
            self.protocol.receive_data(data)
        except RemoteProtocolError:
            raise HTTPError(HTTPStatus.BAD_REQUEST)
        else:
            event = next(self.protocol.events())
            if not isinstance(event, Request):
                raise HTTPError(HTTPStatus.BAD_REQUEST)
            data = self.protocol.send(AcceptConnection())
            await self.socket.sendall(data)

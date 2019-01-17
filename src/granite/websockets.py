from abc import ABC
from curio import socket, Queue, Event, TaskGroupError, TaskGroup, TaskCancelled
from granite.http import HTTPStatus, HTTPError
from wsproto.connection import WSConnection, SERVER
from wsproto import events
from wsproto.extensions import PerMessageDeflate


DATA_TYPES = (events.TextReceived, events.BytesReceived)


class WebsocketClosedError(Exception):
    pass


class WebsocketPrototype(ABC):

    socket = None
    protocol = None

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
        await self.outgoing.put(data)

    async def recv(self):
        if not self.closed:
            async with TaskGroup(wait=any) as g:
                receiver = await g.spawn(self.incoming.get)
                closing = await g.spawn(self.closing.wait)
            if g.completed is receiver:
                return receiver.result

    async def __aiter__(self):
        async for msg in self.incoming:
            yield msg

    async def close(self, code=1000, reason='Closed.'):
        await self.outgoing.put(events.ConnectionClosed(code, reason))

    async def _handle_incoming(self):
        while not self.closed:
            data = await self.socket.recv(4096)
            self.protocol.receive_bytes(data)
            if not data:
                await self.closing.set()
            for event in self.protocol.events():
                cl = event.__class__
                if cl in DATA_TYPES:
                    await self.incoming.put(event.data)
                elif cl is events.ConnectionClosed:
                    # The client has closed the connection gracefully.
                    self.closure = event
                    await self.closing.set()

    async def _handle_outgoing(self):
        async for data in self.outgoing:
            if data is None:
                await self.closing.set()
            elif isinstance(data, events.ConnectionClosed):
                self.protocol.close(code=data.code, reason=data.reason)
                self.closure = data
                await self.closing.set()
            else:
                self.protocol.send_data(data)
            try:
                await self.socket.sendall(self.protocol.bytes_to_send())
            except socket.error:
                await self.closing.set()
            if self.closed:
                return

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
            try:
                await self.socket.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass


class Websocket(WebsocketPrototype):
    """Server-side websocket running a handler parallel to the I/O.
    """
    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.protocol = WSConnection(SERVER, extensions=[PerMessageDeflate()])

    async def upgrade(self, request):
        data = '{} {} HTTP/1.1\r\n'.format(
            request.method, request.url)
        data += '\r\n'.join(
            ('{}: {}'.format(k, v)
             for k, v in request.headers.items())) + '\r\n\r\n'

        data = data.encode()
        self.protocol.receive_bytes(data)
        event = next(self.protocol.events())
        if not isinstance(event, events.ConnectionRequested):
            raise HTTPError(HTTPStatus.BAD_REQUEST)

        self.protocol.accept(event)
        data = self.protocol.bytes_to_send()
        await self.socket.sendall(data)

    async def handler(self, func, request, params):
        await func(request, self, **params)

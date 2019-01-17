from abc import ABC
from curio import Queue, Event, TaskGroupError, TaskGroup, TaskCancelled
from granite.http import HTTPStatus, HTTPError
from wsproto.connection import WSConnection, SERVER
from wsproto import events


DATA_TYPES = (events.TextReceived, events.BytesReceived)


class WebsocketPrototype(ABC):

    socket = None
    protocol = None

    def __init__(self):
        self.outgoing = Queue()
        self.incoming = Queue()
        self.closed = None
        self.muted = False

    async def send(self, data):
        await self.outgoing.put(data)

    async def recv(self):
        return await self.incoming.get()

    async def __aiter__(self):
        async for msg in self.incoming:
            yield msg

    async def close(self, code=1000, reason='Closed.'):
        await self.incoming.put(None)  # EOF
        if not self.protocol.closed:
            closure = events.ConnectionClosed(code, reason)
            await self.outgoing.put(closure)

    async def _handle_incoming(self):
        while not self.muted:
            data = await self.socket.recv(8096)            
            if not data:
                # Socket was closed.
                self.muted = True
                await self.outgoing.put(None)
                return
            self.protocol.receive_bytes(data)
            for event in self.protocol.events():
                cl = event.__class__
                if cl in DATA_TYPES:
                    await self.incoming.put(event.data)
                elif cl is events.ConnectionClosed:
                    # The client has closed the connection gracefully.
                    await self.outgoing.put(None)
                    self.closed = event
                    return
            msg = self.protocol.bytes_to_send()
            await self.socket.sendall(msg)

    async def _handle_outgoing(self):
        async for data in self.outgoing:
            if isinstance(data, events.ConnectionClosed):
                self.protocol.close(code=data.code, reason=data.reason)
                if not self.muted:
                    payload = self.protocol.bytes_to_send()
                    await self.socket.sendall(payload)
                    self.closed = data
                return
            elif data is None or self.muted is True:
                # Socket is closed, we can't send.
                return
            else:
                self.protocol.send_data(data)
                await self.socket.sendall(self.protocol.bytes_to_send())

    async def flow(self, *tasks):
        async with TaskGroup(tasks=tasks) as ws:
            incoming = await ws.spawn(self._handle_incoming)
            outgoing = await ws.spawn(self._handle_outgoing)
            async for t in ws:
                if t in tasks:
                    # Task is finished. We close the incoming.
                    # We ask for the outgoing to finish.
                    await incoming.cancel()
                    await self.close()
            

class Websocket(WebsocketPrototype):
    """Server-side websocket running a handler parallel to the I/O.
    """
    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.protocol = WSConnection(SERVER)

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
        try:
            await func(request, self, **params)
        except TaskCancelled:
            # Handler was cancelled, most likely by the taskgroup.
            # This could be due to a client socket closure or an
            # error in the websocket low levels.
            pass
        except Exception as error:
            # A more serious error happened.
            # The websocket handler was untimely terminated
            # by an unwarranted exception. Warn the client.
            await self.close(1011, 'Handler died prematurely.')

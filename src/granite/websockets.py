
from curio import spawn, Queue, TaskGroup
from wsproto.connection import WSConnection, CLIENT, SERVER
from wsproto.events import TextReceived, BytesReceived
from wsproto.events import (
    ConnectionEstablished, ConnectionFailed, ConnectionRequested
)
from wsproto.connection import WSConnection, SERVER


DATA_TYPES = (TextReceived, BytesReceived)


class Websocket:

    def __init__(self, request):
        self.request = request
        self.protocol = WSConnection(SERVER)
        self.outgoing = Queue()
        self.incoming = Queue()

    async def upgrade(self):

         # Workaround wsproto silly check on the connection header
         # they forgot that Browsers tend to send 'keep-alive' too.        
         if 'CONNECTION' in self.request.headers:
             if 'upgrade' in self.request.headers['CONNECTION'].lower():
                 self.request.headers['CONNECTION'] = 'upgrade'

         data = '{} {} HTTP/1.1\r\n'.format(
             self.request.method, self.request.url.decode())
         data += '\r\n'.join(
             ('{}: {}'.format(k, v)
              for k, v in self.request.headers.items())) + '\r\n\r\n'

         data = data.encode()
         self.protocol.receive_bytes(data)
         event = next(self.protocol.events())
         assert isinstance(event, ConnectionRequested)
         self.protocol.accept(event)
         data = self.protocol.bytes_to_send()
         await self.request.socket.sendall(data)

    async def send(self, data):
        await self.outgoing.put(data)

    async def recv(self):
        return await self.incoming.get()

    async def run(self):
        closed = False
        read_size = 2**16
        stream = self.request.socket.as_stream()
        while not closed:
            async with TaskGroup(wait=any) as ws:
                receiver = await ws.spawn(stream.read, read_size)
                sender = await ws.spawn(self.outgoing.get)

            msg = ws.completed.result
            if ws.completed is receiver:
                self.protocol.receive_bytes(msg)
                for event in self.protocol.events():
                    cl = event.__class__
                    if cl in DATA_TYPES:
                        await self.incoming.put(event.data)
                    elif cl is ConnectionClosed:
                        # The client has closed the connection.
                        await self.incoming.put(None)
                        self.closed = True
                await stream.write(self.protocol.bytes_to_send())
            else:
                if msg is None:
                    # Terminate the connection.
                    print("Closing the connection.")
                    self.protocol.close()
                    self.closed = True
                else:
                    self.protocol.send_data(msg)
                    payload = self.protocol.bytes_to_send()
                    await stream.write(payload)

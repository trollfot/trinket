import socket
from curio.io import Socket
from trinket.request import Channel
from trinket.response import response_handler
from trinket.http import HTTPError
from typing import Callable


async def request_handler(app: Callable, client: Socket, *args):
    async with client:
        try:
            async for request in Channel(client):
                response = await app(request)
                if response is None:
                    break
                await response_handler(client, response)
        except HTTPError as exc:
            await client.sendall(bytes(exc))
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            # The client disconnected or the network is suddenly
            # unreachable.
            pass

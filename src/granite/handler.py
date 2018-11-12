import socket
from granite.request import ClientRequest, Request
from granite.response import Response, response_handler
from granite.http import HTTPStatus, HttpError


async def request_handler(app, client, addr):
    keep_alive = True
    try:
        async with client:
            while keep_alive:
                try:
                    async with ClientRequest(client) as request:
                        if request is not None:
                            keep_alive = request.keep_alive
                            response = await app(request)
                        else:
                            # We close the connection.
                            break
                    await response_handler(client, response)
                except HttpError as exc:
                    await client.sendall(bytes(exc))

    except (ConnectionResetError, BrokenPipeError, socket.timeout):
        # The client disconnected or the network is suddenly
        # unreachable.
        pass

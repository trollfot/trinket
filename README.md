Granite
=======

Chiseled for duration

Example
-------

    from granite.pebble import Granite
    from granite.extensions import logger

    pebble = logger(Granite())


    @pebble.route('/')
    async def hello(request, response):
        response.body = b'Hello World !'


    @pebble.websocket('/chat')
    async def chat_client(request, websocket):
        """Broadcasting websocket.
        Try connecting two or more, to chat.
        """
        while True:
            msg = await websocket.recv()
            for ws in pebble.websockets:
                if ws is not websocket:
                    await ws.send(msg)

    pebble.start()


Acknowledgments
---------------

Granite's Request, Response, Parsers and HTTP entities (Query, MultiPart...) are based on Roll's code.
See : https://github.com/pyrates/roll

It was tuned and modified very slightly to accomodate my ideas: a new workflow for the request/response and the streaming of the request's body at the handler's leisure.

Compared to my Roll's fork, the whole upgrade and websockets parts were re-written with a new library, 'wsproto'.

Why ?
-----

I like Curio's async concepts, syntax and philosophy.
The performances were not a focus on this proof of concept, but they are on par with Roll on asyncio.

What now ?
----------

A lot of tests to write. Performances to enhance. Have a look at http2 using h2.

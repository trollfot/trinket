Granite
=======

Chiseled for duration

Example
-------


    from granite import Granite, Response
    from granite.response import file_iterator
    from granite.extensions import logger

    pebble = logger(Granite())


    @pebble.route('/')
    async def hello(request):
        return Response.raw(b'Hello World !')


    @pebble.route('/feed', methods=['POST'])
    async def feed(request):
        return Response.raw(b'You got here')


    @pebble.route('/read', methods=['POST'])
    async def feed(request):
        await request.parse_body()
        files = list(request.files.keys())
        return Response.raw("You got here and it's all read: {}".format(files))


    @pebble.route('/hello/full/with/{one}/and/{two}')
    async def json(request, one, two):    
        response = Response.json({
            'parameters': f'{one} and {two}',
            'query': request.query.get('query'),
            'cookie': request.cookies['test'],
        })
        response.cookies.set(name='bench', value='value')
        return response


    @pebble.route('/websocket')
    async def serve_websocket(request):
        response = Response.streamer(file_iterator('myfile.ext'))
        return response


    @pebble.websocket('/chat')
    async def feed(request, websocket):
        while True:
            msg = await websocket.recv()
            for ws in pebble.websockets:
                if ws is not websocket:
                    await ws.send(msg)


    pebble.start()


Acknowledgments
---------------

Granite's Request, Response, Parsers and HTTP entities (Query,
MultiPart...) are based on Roll's code.

See : https://github.com/pyrates/roll

It was tuned and modified very slightly to accomodate my ideas: a new
workflow for the request/response and the streaming of the request's
body at the handler's leisure.

Compared to my Roll's fork, the whole upgrade and websockets parts
were re-written with a new library, 'wsproto'.

Why ?
-----

I like Curio's async concepts, syntax and philosophy.
The performances were not a focus on this proof of concept, but they
are 1/3 slower than Roll on asyncio.

What now ?
----------

  - A lot of tests to write.
  - Performances to enhance.
  - Have a look at http2 using h2.

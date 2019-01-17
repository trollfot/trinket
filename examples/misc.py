"""
Examples of usages.
"""
from trinket import Trinket, Response
from trinket.response import file_iterator
from trinket.extensions import logger

pebble = Trinket()


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


@pebble.route('/ignore', methods=['POST'])
async def ignore(request):
    # A post where we ignore the body
    return Response.raw("You got here and all was ignored.")


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
    return Response.streamer(
        file_iterator('websocket.html'),
        content_type="text/html")


@pebble.websocket('/chat')
async def feed(request, websocket):
    async for msg in websocket:
        for ws in pebble.websockets:
            if ws is not websocket:
                await ws.send(msg)


pebble.start()

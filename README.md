Trinket
=======

A Curio HTTP server.

![State of master branch in Travis](https://travis-ci.com/trollfot/trinket.svg?branch=master)


Installation
------------

Trinket requires python3.7+

    $> git clone https://github.com/trollfot/trinket.git
    $> python3.7 -m venv trinket_env
    $> source trinket_env/bin/activate
    $> pip install -e trinket trinket[test]
    $> pytest trinket/tests


Example
-------

    from trinket import Trinket, Response
    from trinket.response import file_iterator
    from trinket.extensions import logger

    bauble = logger(Trinket())


    @bauble.route('/')
    async def hello(request):
        return Response.raw(b'Hello World !')


    @bauble.route('/feed', methods=['POST'])
    async def feed(request):
        return Response.raw(b'You got here')


    @bauble.route('/read', methods=['POST'])
    async def feed(request):
        await request.parse_body()
        files = list(request.files.keys())
        return Response.raw("You got here and it's all read: {}".format(files))


    @bauble.route('/hello/full/with/{one}/and/{two}')
    async def json(request, one, two):    
        response = Response.json({
            'parameters': f'{one} and {two}',
            'query': request.query.get('query'),
            'cookie': request.cookies['test'],
        })
        response.cookies.set(name='bench', value='value')
        return response


    @bauble.route('/websocket')
    async def serve_websocket(request):
        response = Response.streamer(file_iterator('myfile.ext'))
        return response


    @bauble.websocket('/chat')
    async def feed(request, websocket):
        while True:
            msg = await websocket.recv()
            for ws in bauble.websockets:
                if ws is not websocket:
                    await ws.send(msg)


    bauble.start()


Acknowledgments
---------------

Trinket relies heavily on packages from https://github.com/pyrates:
very good re-useable components with Cython-improved performances.

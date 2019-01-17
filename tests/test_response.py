import pytest
from http import HTTPStatus
from trinket import Response


pytestmark = pytest.mark.curio


def test_can_set_status_from_numeric_value():
    response = Response(202)
    assert response.status == HTTPStatus.ACCEPTED


def test_raises_if_code_is_unknown():
    with pytest.raises(ValueError):
        Response(999)


def test_bytes_representation_bodyless():
    response = Response(HTTPStatus.ACCEPTED)
    assert bytes(response) == \
        b'HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n'


def test_representation_with_body():
    response = Response(HTTPStatus.OK, body="Super")
    assert bytes(response) == \
        b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nSuper'


def test_representation_bodyless_with_body():
    response = Response(HTTPStatus.NO_CONTENT, body="Super")
    assert bytes(response) == \
        b'HTTP/1.1 204 No Content\r\n\r\n'


def test_304_no_content_type():
    response = Response(HTTPStatus.NOT_MODIFIED)
    assert bytes(response) == \
        b'HTTP/1.1 304 Not Modified\r\n\r\n'


def test_1XX_no_content_type():
    response = Response(HTTPStatus.CONTINUE)
    assert bytes(response) == \
        b'HTTP/1.1 100 Continue\r\n\r\n'


async def test_not_found(client):

    async with client:
        async with client.query('GET', '/') as response:
            assert response.status == HTTPStatus.NOT_FOUND
            assert response.read() == b'/'


async def test_simple_GET(app, client):

    @app.route('/hello')
    async def hello(request):
        return Response.raw(b'Hello World !')

    async with client:
        async with client.query('GET', '/hello') as response:
            assert response.status == HTTPStatus.OK
            assert response.read() == b'Hello World !'

            
async def test_bodyless_response(app, client):

    @app.route('/bodyless')
    async def bodyless(request):
        return Response(status=HTTPStatus.ACCEPTED)

    async with client:
        async with client.query('GET', '/bodyless') as response:
            assert response.status == HTTPStatus.ACCEPTED
            assert response.read() == b''


async def test_unallowed_method(app, client):

    @app.route('/hello')
    async def hello(request):
        return Response.raw(b'Hello World !')

    async with client:
        async with client.query('POST', '/hello') as response:
            assert response.status == HTTPStatus.METHOD_NOT_ALLOWED


async def test_simple_POST(client, app):

    @app.route('/test', methods=['POST'])
    async def post(request):
        body = await request.raw_body        
        return Response.raw(body)

    async with client:
        content = b'{"key": "value"}'
        async with client.query('POST', '/test', body=content) as response:
            assert response.status == HTTPStatus.OK
            assert response.read() == content


async def test_can_define_twice_a_route_with_different_payloads(client, app):

    @app.route('/test', methods=['GET'])
    async def get(request):
        return Response.raw(b'GET')

    @app.route('/test', methods=['POST'])
    async def post(request):
        return Response.raw(b'POST')

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.OK
            assert response.read() == b'GET'

        async with client.query('POST', '/test') as response:
            assert response.status == HTTPStatus.OK
            assert response.read() == b'POST'

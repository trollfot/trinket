import pytest
from http import HTTPStatus
from granite import Response


async def bodyless(request):
    return Response(status=HTTPStatus.ACCEPTED)


async def hello(request):
    return Response.raw(b'Hello World !')


@pytest.mark.curio
async def test_GET_responses(app, client):
    async with client:

        async with client.query('GET', '/') as response:
            assert response.status == HTTPStatus.NOT_FOUND
            assert response.read() == b''

        app.route('/bodyless')(bodyless)
        async with client.query('GET', '/bodyless') as response:
            assert response.status == HTTPStatus.ACCEPTED
            assert response.read() == b''
            
        app.route('/')(hello)
        async with client.query('GET', '/') as response:
            assert response.status == HTTPStatus.OK
            assert response.read() == b'Hello World !'

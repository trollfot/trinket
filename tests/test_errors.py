import pytest
from http import HTTPStatus
from trinket import HTTPError


pytestmark = pytest.mark.curio


async def test_simple_error(client, app):

    @app.route('/test')
    async def get(request):
        raise HTTPError(500, 'Oops.')

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.read() == b'Oops.'


async def test_httpstatus_error(client, app):

    @app.route('/test')
    async def get(request):
        raise HTTPError(HTTPStatus.BAD_REQUEST, 'Really bad.')

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.BAD_REQUEST
            assert response.read() == b'Really bad.'


async def test_error_only_with_status(client, app):

    @app.route('/test')
    async def get(request):
        raise HTTPError(500)

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.read() == b'Internal Server Error'


async def test_error_only_with_httpstatus(client, app):

    @app.route('/test')
    async def get(request):
        raise HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR)

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.read() == b'Internal Server Error'


async def test_error_subclasses_with_super(client, app):

    class CustomHTTPError(HTTPError):
        def __init__(self, code):
            super().__init__(code)
            self.message = b'<h1>Oops.</h1>'

    @app.route('/test')
    async def get(request):
        raise CustomHTTPError(HTTPStatus.INTERNAL_SERVER_ERROR)

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.read() == b'<h1>Oops.</h1>'


async def test_error_subclasses_without_super(client, app):

    class CustomHTTPError(HTTPError):
        def __init__(self, code):
            self.status = HTTPStatus(code)
            self.message = b'<h1>Oops.</h1>'

    @app.route('/test')
    async def get(request):
        raise CustomHTTPError(HTTPStatus.INTERNAL_SERVER_ERROR)

    async with client:
        async with client.query('GET', '/test') as response:
            assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.read() == b'<h1>Oops.</h1>'

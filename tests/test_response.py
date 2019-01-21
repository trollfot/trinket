import pytest
import curio
from http import HTTPStatus
from trinket.response import Response, response_handler
from trinket.testing import MockWriteSocket


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


def test_json_response():
    structure = {
        'Trinket': 'bauble',
        'python3.7': True,
        'version': 0.1
    }
    response = Response.json(structure)
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/json; charset=utf-8\r\n'
        b'Content-Length: 56\r\n\r\n'
        b'{"Trinket": "bauble", "python3.7": true, "version": 0.1}')

    response = Response.json(structure, headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: application/json; charset=utf-8\r\n'
        b'Content-Length: 56\r\n\r\n'
        b'{"Trinket": "bauble", "python3.7": true, "version": 0.1}')

    response = Response.json(structure, status=HTTPStatus.ACCEPTED,
                             headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: application/json; charset=utf-8\r\n'
        b'Content-Length: 56\r\n\r\n'
        b'{"Trinket": "bauble", "python3.7": true, "version": 0.1}')

    response = Response.json(structure, status=HTTPStatus.ACCEPTED,
                             headers={'Content-Type': 'wrong/content'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Content-Type: application/json; charset=utf-8\r\n'
        b'Content-Length: 56\r\n\r\n'
        b'{"Trinket": "bauble", "python3.7": true, "version": 0.1}')


def test_json_errors():
    with pytest.raises(TypeError):
        Response.json(object())


def test_html_response():
    HTML = b"""<!DOCTYPE html>
<html>
  <body>
    <h1>Sample HTML</h1>
    <p>This is a sample.</p>
  </body>
</html>"""

    response = Response.html(HTML)
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: text/html; charset=utf-8\r\n'
        b'Content-Length: 103\r\n\r\n' + HTML)

    response = Response.html(HTML, headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: text/html; charset=utf-8\r\n'
        b'Content-Length: 103\r\n\r\n' + HTML)

    response = Response.html(HTML, status=HTTPStatus.ACCEPTED,
                             headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: text/html; charset=utf-8\r\n'
        b'Content-Length: 103\r\n\r\n' + HTML)

    response = Response.html(HTML, status=HTTPStatus.ACCEPTED,
                             headers={'Content-Type': 'wrong/content'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Content-Type: text/html; charset=utf-8\r\n'
        b'Content-Length: 103\r\n\r\n' + HTML)


def test_raw_response():
    CONTENT = b"Some meaningful content."

    response = Response.raw(CONTENT)
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: 24\r\n\r\n' + CONTENT)

    response = Response.raw(CONTENT, headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: 24\r\n\r\n' + CONTENT)

    response = Response.raw(CONTENT, status=HTTPStatus.ACCEPTED,
                            headers={'Custom-Header': 'Test'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Custom-Header: Test\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: 24\r\n\r\n' + CONTENT)

    response = Response.raw(CONTENT, status=HTTPStatus.ACCEPTED,
                            headers={'Content-Type': 'wrong/content'})
    assert bytes(response) == (
        b'HTTP/1.1 202 Accepted\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: 24\r\n\r\n' + CONTENT)


@pytest.mark.curio
async def test_stream_response():
    STREAM = (chunk for chunk in [b'This', b'is', b'a', b'chunked', b'body'])

    response = Response.streamer(STREAM)
    assert bytes(response) == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/octet-stream\r\n'
        b'Transfer-Encoding: chunked\r\n'
        b'Keep-Alive: 10\r\n\r\n')

    assert response.stream is STREAM

    socket = MockWriteSocket()
    await response_handler(socket, response)
    assert socket.sent == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/octet-stream\r\n'
        b'Transfer-Encoding: chunked\r\n'
        b'Keep-Alive: 10\r\n\r\n'
        b'4\r\nThis\r\n'
        b'2\r\nis\r\n'
        b'1\r\na\r\n'
        b'7\r\nchunked\r\n'
        b'4\r\nbody\r\n'
        b'0\r\n\r\n'
    )


@pytest.mark.curio
async def test_async_stream_response():

    async def astream():
        for chunk in [b'This', b'is', b'a', b'chunked', b'body']:
            yield chunk
            await curio.sleep(0)

    response = Response.streamer(astream())
    socket = MockWriteSocket()
    await response_handler(socket, response)
    assert socket.sent == (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/octet-stream\r\n'
        b'Transfer-Encoding: chunked\r\n'
        b'Keep-Alive: 10\r\n\r\n'
        b'4\r\nThis\r\n'
        b'2\r\nis\r\n'
        b'1\r\na\r\n'
        b'7\r\nchunked\r\n'
        b'4\r\nbody\r\n'
        b'0\r\n\r\n'
    )

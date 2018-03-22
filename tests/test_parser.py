import pytest
from granite.pebble import HTTPParser
from httptools.parser.errors import HttpParserInvalidMethodError


@pytest.fixture
def parser():
    return HTTPParser()


def test_request_parse_simple_get_response(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Accept: */*\r\n'
        b'Accept-Language: en-US,en;q=0.5\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Referer: http://localhost:7777/\r\n'
        b'DNT: 1\r\n'
        b'Connection: keep-alive\r\n'
        b'\r\n')
    assert parser.request.method == 'GET'
    assert parser.request.path == '/feeds'
    assert parser.request.headers['ACCEPT'] == '*/*'
    assert parser.complete is True


def test_request_headers_are_uppercased(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Accept: */*\r\n'
        b'Accept-Language: en-US,en;q=0.5\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Referer: http://localhost:7777/\r\n'
        b'DNT: 1\r\n'
        b'Connection: keep-alive\r\n'
        b'\r\n')
    assert parser.request.headers['ACCEPT-LANGUAGE'] == 'en-US,en;q=0.5'
    assert parser.request.headers['ACCEPT'] == '*/*'
    assert parser.request.headers.get('HOST') == 'localhost:1707'
    assert 'DNT' in parser.request.headers
    assert parser.request.headers.get('accept') is None
    assert parser.complete is True


def test_request_path_is_unquoted(parser):
    parser.data_received(
        b'GET /foo%2Bbar HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: HTTPie/0.9.8\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: */*\r\n'
        b'Connection: keep-alive\r\n'
        b'\r\n')
    assert parser.request.path == '/foo+bar'
    assert parser.complete is True


def test_request_parse_query_string(parser):
    parser.data_received(
        b'GET /feeds?foo=bar&bar=baz HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: HTTPie/0.9.8\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: */*\r\n'
        b'Connection: keep-alive\r\n'
        b'\r\n')
    assert parser.request.path == '/feeds'
    assert parser.request.query['foo'][0] == 'bar'
    assert parser.request.query['bar'][0] == 'baz'
    assert parser.complete is True


def test_request_parse_multivalue_query_string(parser):
    parser.data_received(
        b'GET /feeds?foo=bar&foo=baz HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: HTTPie/0.9.8\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: */*\r\n'
        b'Connection: keep-alive\r\n'
        b'\r\n')
    assert parser.request.path == '/feeds'
    assert parser.request.query['foo'] == ['bar', 'baz']
    assert parser.complete is True


def test_request_content_type_shortcut(parser):
    parser.data_received(
        b'POST /feed HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: HTTPie/0.9.8\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: application/json, */*\r\n'
        b'Connection: keep-alive\r\n'
        b'Content-Type: application/json\r\n'
        b'Content-Length: 31\r\n'
        b'\r\n'
        b'{"link": "https://example.org"}')
    assert parser.request.content_type == 'application/json'
    assert parser.complete is True


def test_request_host_shortcut(parser):
    parser.data_received(
        b'POST /feed HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: HTTPie/0.9.8\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: application/json, */*\r\n'
        b'Connection: keep-alive\r\n'
        b'Content-Type: application/json\r\n'
        b'Content-Length: 31\r\n'
        b'\r\n'
        b'{"link": "https://example.org"}')
    assert parser.request.host == 'localhost:1707'
    assert parser.complete is True


def test_malformed_request(parser):

    with pytest.raises(HttpParserInvalidMethodError):
        parser.data_received(
            b'Batushka'
            b'\r\n'
            b'{"link": "https://example.org"}')
    assert parser.complete is False

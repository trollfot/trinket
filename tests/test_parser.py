import pytest
from trinket.request import Channel
from trinket.http import HTTPError


@pytest.fixture
def parser():
    return Channel(None)


def test_request_parse_simple(parser):
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
    assert parser.request.headers['Accept'] == '*/*'
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
    assert parser.request.headers['Accept-Language'] == 'en-US,en;q=0.5'
    assert parser.request.headers['Accept'] == '*/*'
    assert parser.request.headers.get('Host') == 'localhost:1707'
    assert 'Dnt' in parser.request.headers
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
    with pytest.raises(HTTPError):
        parser.data_received(
            b'Batushka'
            b'\r\n'
            b'{"link": "https://example.org"}')
    assert parser.complete is False


def test_invalid_request_method(parser):
    with pytest.raises(HTTPError):
        parser.data_received(
            b'SPAM /path HTTP/1.1\r\nContent-Length: 8\r\n\r\nblahblah')

    assert parser.complete is False
    assert parser.request.method is None


def test_query_get_should_return_value(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=value')
    assert parser.request.query.get('key') == 'value'


def test_query_get_should_return_first_value_if_multiple(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=value&key=value2')
    assert parser.request.query.get('key') == 'value'


def test_query_get_should_raise_if_no_key_and_no_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=value')
    with pytest.raises(HTTPError):
        parser.request.query.get('other')


def test_query_getlist_should_return_list_of_values(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=value&key=value2')
    assert parser.request.query.list('key') == ['value', 'value2']


def test_query_get_should_return_default_if_key_is_missing(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=value')
    assert parser.request.query.get('other', None) is None
    assert parser.request.query.get('other', 'default') == 'default'


@pytest.mark.parametrize('input,expected', [
    (b't', True),
    (b'true', True),
    (b'True', True),
    (b'1', True),
    (b'on', True),
    (b'f', False),
    (b'false', False),
    (b'False', False),
    (b'0', False),
    (b'off', False),
    (b'n', None),
    (b'none', None),
    (b'null', None),
    (b'NULL', None),
])
def test_query_bool_should_cast_to_boolean(input, expected, parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=' + input)
    assert parser.request.query.bool('key') == expected


def test_query_bool_should_return_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=1')
    assert parser.request.query.bool('other', default=False) is False


def test_query_bool_should_raise_if_not_castable(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.bool('key')


def test_query_bool_should_raise_if_not_key_and_no_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.bool('other')


def test_query_bool_should_return_default_if_key_not_present(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    assert parser.request.query.bool('other', default=False) is False


def test_query_int_should_cast_to_int(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=22')
    assert parser.request.query.int('key') == 22


def test_query_int_should_return_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=1')
    assert parser.request.query.int('other', default=22) == 22


def test_query_int_should_raise_if_not_castable(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.int('key')


def test_query_int_should_raise_if_not_key_and_no_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.int('other')


def test_query_int_should_return_default_if_key_not_present(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    assert parser.request.query.int('other', default=22) == 22


def test_query_float_should_cast_to_float(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=2.234')
    assert parser.request.query.float('key') == 2.234


def test_query_float_should_return_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=1')
    assert parser.request.query.float('other', default=2.234) == 2.234


def test_query_float_should_raise_if_not_castable(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.float('key')


def test_query_float_should_raise_if_not_key_and_no_default(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    with pytest.raises(HTTPError):
        assert parser.request.query.float('other')


def test_query_float_should_return_default_if_key_not_present(parser):
    parser.on_message_begin()
    parser.on_url(b'/?key=one')
    assert parser.request.query.float('other', default=2.234) == 2.234


def test_request_parse_cookies(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Cookie: key=value\r\n'
        b'\r\n')
    assert parser.request.cookies['key'] == 'value'


def test_request_parse_multiple_cookies(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Cookie: key=value; other=new_value\r\n'
        b'\r\n')
    assert parser.request.cookies['key'] == 'value'
    assert parser.request.cookies['other'] == 'new_value'


def test_request_cookies_get(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Cookie: key=value\r\n'
        b'\r\n')
    cookie = parser.request.cookies.get('key')
    cookie == 'value'


def test_request_cookies_get_unknown_key(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Cookie: key=value\r\n'
        b'\r\n')
    cookie = parser.request.cookies.get('foo')
    assert cookie is None


def test_request_get_unknown_cookie_key_raises_keyerror(parser):
    parser.data_received(
        b'GET /feeds HTTP/1.1\r\n'
        b'Host: localhost:1707\r\n'
        b'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:54.0) '
        b'Gecko/20100101 Firefox/54.0\r\n'
        b'Origin: http://localhost:7777\r\n'
        b'Cookie: key=value\r\n'
        b'\r\n')
    with pytest.raises(KeyError):
        parser.request.cookies['foo']

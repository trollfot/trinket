from datetime import datetime
from http import HTTPStatus
from trinket import Response


def test_cookies():
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set(name='name', value='value')
    assert b'\r\nSet-Cookie: name=value; Path=/\r\n' in bytes(response)


def test_multiple_cookies():
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value')
    response.cookies.set('other', 'value2')
    assert b'\r\nSet-Cookie: name=value; Path=/\r\n' in bytes(response)
    assert b'\r\nSet-Cookie: other=value2; Path=/\r\n' in bytes(response)


def test_cookies_with_path():
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set(name='name', value='value', path='/foo')
    assert b'\r\nSet-Cookie: name=value; Path=/foo\r\n' in bytes(response)


def test_cookies_with_expires():
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set(
        'name', 'value',
        expires=datetime(2027, 9, 21, 11, 22)
    )

    assert (
        b'\r\nSet-Cookie: name=value; '
        b'Expires=Tue, 21 Sep 2027 11:22:00 GMT; Path=/\r\n'
    ) in bytes(response)


def test_cookies_with_max_age(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value', max_age=600)
    assert (
        b'\r\nSet-Cookie: name=value; Max-Age=600; Path=/\r\n'
    ) in bytes(response)


def test_cookies_with_domain(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value', domain='www.example.com')
    assert (
        b'\r\nSet-Cookie: name=value; Domain=www.example.com; '
        b'Path=/\r\n'
    ) in bytes(response)


def test_cookies_with_http_only(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value', httponly=True)
    assert (
        b'\r\nSet-Cookie: name=value; Path=/; HttpOnly\r\n'
    ) in bytes(response)


def test_cookies_with_secure(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value', secure=True)
    assert (
        b'\r\nSet-Cookie: name=value; Path=/; Secure\r\n'
    ) in bytes(response)


def test_cookies_with_multiple_attributes(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value', secure=True, max_age=300)
    assert (
        b'\r\nSet-Cookie: name=value; Max-Age=300; Path=/; '
        b'Secure\r\n'
    ) in bytes(response)


def test_delete_cookies(client, app):
    response = Response(HTTPStatus.OK, body="body")
    response.cookies.set('name', 'value')
    del response.cookies['name']
    assert b'Set-Cookie:' not in bytes(response)

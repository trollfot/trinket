from trinket.http import Form, Files, HTTPError, HTTPStatus
from urllib.parse import parse_qs


def read_urlencoded(content_type):
    data = b''
    while True:
        chunk = yield
        if not chunk:
            try:
                parsed = parse_qs(
                    data, keep_blank_values=True, strict_parsing=True)
            except ValueError:
                raise HTTPError(
                    HTTPStatus.BAD_REQUEST,
                    'Unparsable urlencoded body')
            yield Form(parsed), Files()
            raise StopIteration
        data += chunk

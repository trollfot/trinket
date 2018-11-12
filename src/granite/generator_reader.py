async def make_request(client):
    parser = HttpParser()
    reader = body_reader(client, parser)
    data = await reader.__anext__()
    request = Request(**parser.get_headers())
    request.url = parser.get_url()
    request.method = parser.get_method()
    request.path = parser.get_path()
    request.query_string = parser.get_query_string()
    request.keep_alive = bool(parser.should_keep_alive())
    request.upgrade = bool(parser.is_upgrade())
    request.socket = client
    request.parse_body = partial(read_request_body, request, reader)
    request.body_size, request.body = data
    return request


async def body_reader(socket, parser):
    body_read = 0
    while True:
        socket_ttl = socket._socket.gettimeout()
        socket._socket.settimeout(10)
        data = await socket.recv(1024)
        socket._socket.settimeout(socket_ttl)
        if not data:
            yield (body_read, data)
            break

        received = len(data)
        nparsed = parser.execute(data, received)
        if nparsed != received:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, 'Unparsable request.')

        import pdb
        pdb.set_trace()
        if parser.is_partial_body():
            if body_read == 0:
                # We started reading the body.
                # This is the first chunk
                body_read += received
                yield (body_read, parser.recv_body())
            else:
                body_read += received
                yield (body_read, data)

        if parser.is_message_complete():
            # If the message ends here, we return the last chunk
            # and we stop the iteration.
            body_read += received
            yield (body_read, data)
            break


async def read_request_body(request, reader, flush=False):

    if flush:
        async for data in reader:
            pass
        return
    else:
        disposition = request.content_type.split(';', 1)[0]
        parser_type = CONTENT_TYPES_PARSERS.get(disposition)
        if parser_type is None:
            raise NotImplementedError(f"Don't know how to parse {disposition}")
        content_parser = parser_type(request.content_type)
        next(content_parser)
        if request.body:
            # if there's already a piece of body
            # parse it.
            content_parser.send(request.body)

        async for size, data in reader:
            content_parser.send(data)

        request.body_size = size
        request.form, request.files = next(content_parser)
        content_parser.close()
        print(size)

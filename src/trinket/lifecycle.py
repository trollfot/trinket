from functools import wraps


def handler_events(func):
    @wraps(func)
    async def dispatch(app, request, *args, **kwargs):
        response = await app.notify('request', request)
        if response is None:
            response = await func(app, request, *args, **kwargs)
        if response is not None:
            await app.notify('response', request, response)
        return response
    return dispatch

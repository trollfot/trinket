import logging


def logger(app, level=logging.DEBUG):

    logger = logging.getLogger('trinket')
    logger.setLevel(level)
    handler = logging.StreamHandler()

    @app.listen('request')
    async def log_request(request):
        logger.info('%s %s', request.method, request.url.decode())

    @app.listen('startup')
    async def startup():
        logger.addHandler(handler)

    @app.listen('shutdown')
    async def shutdown():
        logger.removeHandler(handler)

    return app

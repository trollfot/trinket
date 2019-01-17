from .multipart import read_multipart
from .urlencoded import read_urlencoded


CONTENT_TYPES_PARSERS = {
    'multipart/form-data': read_multipart,
    'application/x-www-form-urlencoded': read_urlencoded,
}


__all__ = ['CONTENT_TYPES_PARSERS']

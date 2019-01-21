from abc import ABC, abstractmethod
from curio.io import Socket
from trinket.request import Request
from typing import Tuple, Callable
from trinket.response import Response


class Application(ABC):
    """Trinket application abstraction.
    """

    @abstractmethod
    async def notify(self, event: str):
        pass

    @abstractmethod
    async def lookup(self, request: Request) -> Tuple[Callable, dict]:
        pass

    @abstractmethod
    async def __call__(self, request: Request) -> Response:
        pass

    @abstractmethod
    async def handle_request(self, client: Socket, addr: Tuple[str, int]):
        pass

from abc import ABC, abstractmethod


class AsyncCleanupable(ABC):
    @abstractmethod
    async def cleanup(self, *args, **kwargs): ...


class Subscribable(ABC):
    @abstractmethod
    def subscribe(self, *args, **kwargs): ...


class Pushable(ABC):
    @abstractmethod
    def push(self, *args, **kwargs): ...

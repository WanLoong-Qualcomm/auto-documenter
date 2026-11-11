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


class AsyncPutable(ABC):
    @abstractmethod
    async def put(self, *args, **kwargs): ...


class AsyncGetable(ABC):
    @abstractmethod
    async def get(self, *args, **kwargs): ...


class Releasable(ABC):
    @abstractmethod
    def release(self, *args, **kwargs): ...

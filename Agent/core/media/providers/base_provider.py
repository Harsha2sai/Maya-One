from __future__ import annotations

from abc import ABC, abstractmethod

from core.media.media_models import MediaCommand, MediaResult


class BaseMediaProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def can_handle(self, command: MediaCommand, user_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, command: MediaCommand, user_id: str) -> MediaResult:
        raise NotImplementedError

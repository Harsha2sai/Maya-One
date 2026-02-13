from abc import ABC, abstractmethod
from typing import Tuple

class HealthCheck(ABC):
    """
    Abstract base class for all startup health checks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the health check."""
        pass

    @abstractmethod
    async def run(self) -> Tuple[bool, str]:
        """
        Runs the health check.

        Returns:
            Tuple[bool, str]: A tuple containing:
                - bool: True if the check passed, False otherwise.
                - str: A message describing the result (success or failure reason).
        """
        pass

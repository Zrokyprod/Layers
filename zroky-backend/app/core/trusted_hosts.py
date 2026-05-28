from collections.abc import Callable
from typing import Any

from fastapi.middleware.trustedhost import TrustedHostMiddleware


class LivenessBypassTrustedHostMiddleware(TrustedHostMiddleware):
    """Allow platform health probes while enforcing trusted hosts elsewhere."""

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/health/live":
            await self.app(scope, receive, send)
            return

        await super().__call__(scope, receive, send)

"""
Per-request user context for principal propagation.

The HTTP middleware validates the caller's XSUAA token and stores the result in
a ContextVar. Everything downstream (token exchange, cache scoping) reads it
from here, so tool handlers do not have to be changed or pass a user around.

Kept dependency-free on purpose: cache_manager imports it, and it must not pull
in aiohttp/PyJWT.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class UserContext:
    """The authenticated caller of the current request."""

    user_id: str                      # unique identifier, e.g. the e-mail address
    user_token: str = field(repr=False)  # raw XSUAA access token (secret, never log)
    groups: Tuple[str, ...] = ()
    expires_at: float = 0.0           # unix time the XSUAA token expires


current_user: ContextVar[Optional[UserContext]] = ContextVar("current_user", default=None)


def cache_scope() -> str:
    """Key prefix that keeps cached data separate per user.

    Empty in service mode (no user context), so existing behaviour and cache
    keys are unchanged there.
    """
    user = current_user.get()
    return f"user={user.user_id.lower()}|" if user else ""

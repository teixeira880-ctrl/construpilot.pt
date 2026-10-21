from contextvars import ContextVar
from types import MappingProxyType

_EMPTY = MappingProxyType({})
_actor = ContextVar("expense_actor", default=_EMPTY)


def actor():
    return dict(_actor.get())


def bind(user):
    if user and user.get("user_id"):
        _actor.set(MappingProxyType({"user_id": user["user_id"], "company_id": user.get("organization_id")}))


class ExpenseContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = _actor.set(_EMPTY)
        try:
            await self.app(scope, receive, send)
        finally:
            _actor.reset(token)
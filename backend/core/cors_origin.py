class CanonicalOriginMiddleware:
    """Normalize one explicitly configured ingress alias, without broad origin reflection."""

    def __init__(self, app, proxy_origin, public_origin):
        self.app = app
        self.proxy_origin = proxy_origin.encode("ascii")
        self.public_origin = public_origin.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "headers": [
                (name, self.public_origin if name.lower() == b"origin" and value == self.proxy_origin else value)
                for name, value in scope["headers"]
            ]}
        await self.app(scope, receive, send)
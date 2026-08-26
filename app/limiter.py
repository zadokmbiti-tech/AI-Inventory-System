"""
Shared slowapi Limiter instance. Lives in its own module (rather than
main.py) so routers can import it without a circular import  main.py
imports the routers, and the routers need the limiter for endpoint
decorators like @limiter.limit("10/minute").
"""
from slowapi import Limiter


def get_client_ip(request) -> str:
    """
    Behind a reverse proxy (Vercel, nginx, etc.), request.client.host is
    the proxy's own IP for every request  using it directly would put
    every visitor in the same rate-limit bucket. Prefer X-Forwarded-For
    (set by the proxy to the real client IP) when present.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)

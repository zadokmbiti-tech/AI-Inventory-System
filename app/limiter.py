"""
Shared slowapi Limiter instance. Lives in its own module (rather than
main.py) so routers can import it without a circular import — main.py
imports the routers, and the routers need the limiter for endpoint
decorators like @limiter.limit("10/minute").
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

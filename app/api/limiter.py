"""Shared rate limiter.

Lives in its own module so the routes and the app can both import it without a cycle.

LLM endpoints cost real money per call — one runaway effect hook in the frontend can
drain an OpenAI budget overnight, which is why the chat routes are limited by default.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

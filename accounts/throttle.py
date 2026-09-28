"""Failed-login throttling based on Django's cache framework."""
from django.conf import settings
from django.core.cache import cache


def _key(identifier, ip):
    return f"login-fail:{(identifier or '').lower()}:{ip or '-'}"


def is_locked(identifier, ip):
    return cache.get(_key(identifier, ip), 0) >= settings.LOGIN_MAX_ATTEMPTS


def register_failure(identifier, ip):
    key = _key(identifier, ip)
    try:
        cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)
        return 1


def reset(identifier, ip):
    cache.delete(_key(identifier, ip))


def remaining(identifier, ip):
    return max(0, settings.LOGIN_MAX_ATTEMPTS - cache.get(_key(identifier, ip), 0))

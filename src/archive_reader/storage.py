"""Module to store and cache data locally."""
from diskcache import Cache
from textual import log

SUBSCRIBED_ML = 'mailinglists'

cache = Cache('.store/')

def cache_set(key, value):
    cache.close()
    with Cache(cache.directory) as reference:
        log(f'Setting {key}')
        reference.set(key, value)

def cache_get(key, default=None):
    log(f'Getting {key}')
    cache.close()
    value = cache.get(key)
    if value is not None:
        return value
    return default
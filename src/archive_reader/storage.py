"""Module to store and cache data locally."""
from diskcache import Cache
from textual import log

SUBSCRIBED_ML = 'mailinglists'

cache = Cache('.store/')

def cache_set(key, value):
    log(f'Setting {key} to {value}')
    with Cache(cache.directory) as reference:
        reference.set(key, value)

def cache_get(key):
    value = cache.get(key)
    log(f'Fetched {key} as {value}')
    return value
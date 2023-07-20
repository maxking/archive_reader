"""Module to store and cache data locally."""
from diskcache import Cache

SUBSCRIBED_ML = 'mailinglists'

cache = Cache('.store/')

def cache_set(key, value):
    with Cache(cache.directory) as reference:
        reference.set(key, value)

def cache_get(key):
    return cache.get(key)
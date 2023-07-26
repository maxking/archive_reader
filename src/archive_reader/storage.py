"""Module to store and cache data locally."""
from diskcache import Cache
from textual import log

#: This is the key used to store the subscribed MailingLists in the
#: the local cache.
SUBSCRIBED_ML = 'mailinglists'

cache = Cache('.store/')


def cache_set(key, value):
    with Cache(cache.directory) as reference:
        reference.pop(key)
        log(f'Setting {key}')
        return reference.set(key, value, retry=True)


def cache_get(key, default=None):
    log(f'Getting {key}')
    cache.close()
    value = cache.get(key)
    if value is not None:
        return value
    return default

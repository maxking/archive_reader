import asyncio

import httpx

from .schemas import EmailSchema, MailingListPage, ThreadsPage

__all__ = [
    'fetch_urls',
    'Hyperkitty',
]


class HyperkittyAPI:

    async def _call(self, url, schema):
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            # self._lists_json = {item.get("name"): item for item in results.json().get("results")}
            obj = schema()
            return obj.load(data=results.json())
        results.raise_for_status()

    async def lists(self, base_url):
        url = f"{base_url}/api/lists?format=json"
        return self._call(url, MailingListPage)

    async def threads(self, ml):
        """Given a ML object, return the threads for that Mailinglist."""
        return self._call(ml.threads, ThreadsPage)

    async def emails(self, thread):
        return self._call(thread.emails, MailingListPage)


class Hyperkitty:
    """
    Hyperkitty is a client for Hyperkitty. It returns objects that can be
    used in the UI elements.

    This is limiting in the fact that it takes in the base_url, which implies
    it is linked to a single server.

    :param base_url: Base URL for Hyperkitty Instance.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._lists_json = {}
        self._list_threads = {}
        self._thread_emails = {}

    async def lists(self):
        """Return a list of MailingLists.

        It will cache the results for next use, until :py:meth:`refresh` is
        called on the HK instance.
        """
        if self._lists_json:
            return self._lists_json

        url = f"{self.base_url}/api/lists?format=json"
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._lists_json = {item.get("name"): item for item in results.json().get("results")}
            return self._lists_json
        return {}

    async def threads(self, list_id: str):
        if list_id in self._list_threads:
            return self._list_threads[list_id]
        url = self._lists_json[list_id].get("threads")
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._list_threads[list_id] = results.json().get("results")
            return self._list_threads[list_id]
        return {}

    async def emails(self, mlist_id: str, thread_id: str):
        url = f"{self.base_url}/api/lists/{mlist_id}/threads/{thread_id}?format=json"
        if thread_id in self._thread_emails:
            return self._thread_emails[thread_id]
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._thread_emails[thread_id] = results.json().get("results")
            return self._thread_emails[thread_id]
        return {}



async def fetch_urls(urls, logger=None):
    success = []
    failed = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for url in urls:
            tasks.append(asyncio.ensure_future(client.get(url, follow_redirects=True)))

        results = await asyncio.gather(*tasks)

        for resp in results:
            if resp.status_code == 200:
               success.append(resp.json())
            else:
                logger(resp)
                failed.append(resp)
    return success, failed

    # if results.status_code == 200:
    #     return results.json()
    # if logger:
    #     logger(results.status_code)
    #     logger(results)
    # return {}
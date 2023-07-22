import asyncio

import httpx

from .schemas import EmailsPage, MailingListPage, ThreadsPage

__all__ = [
    'fetch_urls',
    'Hyperkitty',
]


class HyperkittyAPI:
    """Hyperkitty is a client for Hyperkitty. It returns objects that can be
    used in the UI elements.
    """

    async def _call(self, url, schema):
        async with httpx.AsyncClient() as client:
            results = await client.get(url, follow_redirects=True)
        if results.status_code == 200:
            # self._lists_json = {item.get("name"): item for item in results.json().get("results")}
            obj = schema()
            return obj.load(data=results.json())
        results.raise_for_status()

    async def lists(self, base_url):
        url = f'{base_url}/api/lists?format=json'
        return await self._call(url, MailingListPage)

    async def threads(self, ml):
        """Given a ML object, return the threads for that Mailinglist."""
        return await self._call(ml.get('threads'), ThreadsPage)

    async def emails(self, thread):
        return await self._call(thread.get('emails'), EmailsPage)


async def fetch_urls(urls, logger=None):
    success = []
    failed = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for url in urls:
            tasks.append(
                asyncio.ensure_future(client.get(url, follow_redirects=True))
            )

        results = await asyncio.gather(*tasks)

        for resp in results:
            if resp.status_code == 200:
                success.append(resp.json())
            else:
                logger(resp)
                failed.append(resp)
    return success, failed

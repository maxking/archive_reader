import asyncio

import httpx

from .schemas import EmailsPage, MailingListPage, ThreadsPage

__all__ = [
    'fetch_urls',
    'HyperkittyAPI',
]


DEFAULT_PAGINATION_COUNT = 25


class HyperkittyAPI:
    """Hyperkitty is a client for Hyperkitty. It returns objects that can be
    used in the UI elements.
    """

    async def _call(self, url, schema):
        async with httpx.AsyncClient() as client:
            results = await client.get(url, follow_redirects=True)
        if results.status_code == 200:
            obj = schema()
            return obj.load(data=results.json())
        results.raise_for_status()

    async def lists(self, base_url):
        url = f'{base_url}/api/lists?format=json'
        return await self._call(url, MailingListPage)

    async def threads(
        self, threads_url, offset=1, limit=DEFAULT_PAGINATION_COUNT
    ):
        """Given a ML object, return the threads for that Mailinglist."""
        return await self._call(
            f'{threads_url}&limit={limit}&offset={offset}', ThreadsPage
        )

    async def emails(self, thread, page=1, count=DEFAULT_PAGINATION_COUNT):
        return await self._call(
            f'{thread.emails}&page={page}&count={count}', EmailsPage
        )


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


hyperktty_client = HyperkittyAPI()

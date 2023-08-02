"""Core business logic."""
import asyncio
import httpx
from textual import log
from .models import MailingList, Thread, EmailManager
from .hyperkitty import hyperktty_client, fetch_urls


class RemoteURLFetchException(Exception):
    """Exception fetching remote URLs."""


class ThreadsManager:
    """The purpose of threads manager is to create Thread model
    objects and deal with their local storage into sqlite3 database.

    This provides a high level layer to the UI, which doesn't need
    to be concerned about fetching, caching, storage and such related
    mechanisms.

    Each manager instance works typically for one mailinglist. Each
    list will keep an instance of their ThreadsManager, which handles the
    fetching, caching etc for that list.
    """

    def __init__(self, mailinglist: MailingList) -> None:
        self.ml = mailinglist
        self.email_mgr = EmailManager()

    # ================= Public API =================================
    async def threads(self):
        """This is the top level Public API for this method. This
        will return threads for the Mailinglist this manager manages.
        """
        return await self._load_threads_from_db()

    async def update_threads(self):
        return await self._fetch_threads()

    async def emails(self, thread):
        """Return all the Emails for a give Thread."""
        return await self._load_emails_from_db(thread=thread)

    async def update_emails(self, thread):
        """Load New Emails from remote."""
        try:
            replies, _ = await fetch_urls([thread.emails], log)
        except httpx.ConnectError:
            log(f'Failed to get Email URLs {thread.emails}')
            raise RemoteURLFetchException(thread.emails)
        reply_urls = [each.get('url') for each in replies[0].get('results')]
        log(f'Retrieved email urls {reply_urls}')
        existing_emails = await self.email_mgr.filter(thread=thread.url)
        existing_email_urls = set(email.url for email in existing_emails)
        new_urls = list(
            url for url in reply_urls if url not in existing_email_urls
        )
        if not new_urls:
            # There are no updated.
            return []
        log(f'Fetching {new_urls}')
        replies, _ = await fetch_urls(new_urls)
        tasks = []
        for reply in replies:
            tasks.append(self.email_mgr.create(reply))
        results = await asyncio.gather(*tasks)
        return [result[0] for result in results]

    # ================= Private API ================================

    async def _load_emails_from_db(self, thread):
        return await self.email_mgr.filter(thread=thread.url)

    async def _load_threads_from_db(self):
        """Load all the existing threads from the db."""
        return await Thread.objects.filter(mailinglist=self.ml.url).all()

    async def _fetch_threads(self, page: int = 1):
        """Fetch threads from the remote server.

        :param page: The page no. to fetch.
        """
        threads = await hyperktty_client.threads(self.ml.threads)
        thread_objs = []
        for thread in threads.get('results'):
            obj = await Thread.objects.get_or_create(
                thread_id=thread['thread_id'], defaults=thread
            )
            thread_objs.append(obj[0])
        return thread_objs


class ListManager:
    def __init__(self) -> None:
        pass

    async def fetch_lists(self, server_url):
        """Given a server URL, return JSON response for
        Mailing lists.

        Note that this doesn't return MailingList objects as these
        lists aren't subscribed to yet.
        """
        return await hyperktty_client.lists(server_url)

    async def lists(self):
        """This returns a list of subscribed MailingLists.

        Lists that have been subscribed to are added to the
        database. This will return only those.
        """
        return await MailingList.objects.all()

    async def subscribe_lists(self, lists):
        """Subscribe these lists by storing them in DB.

        :param lists: A list of dicts with JSON response from API
            for the lists that need to subscribed.
        """
        objs = []
        for ml in lists:
            obj = await MailingList.objects.get_or_create(
                url=ml['url'], defaults=ml
            )
            objs.append(obj[0])
        return objs

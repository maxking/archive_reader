"""Core business logic."""
from .models import MailingList, Thread
from .hyperkitty import hyperktty_client


class ThreadsManager:
    """The purpose of threads manager is to create Thread models
    and deal with local storage into sqlite3 database.

    This provides a high level layer to the UI, which doesn't need
    to be concerned anything about caching and such related mechanisms.

    Each manager works typically for one mailinglist. Each list will
    keep an instance of their ThreadsManager, which handles the
    fetching, caching etc for that list.
    """

    def __init__(self, mailinglist: MailingList) -> None:
        self.ml = mailinglist

    # ================= Public API =================================
    async def threads(self):
        """This is the top level Public API for this method. This
        will return threads for the Mailinglist this manager manages.
        """
        return await self._fetch_threads()

    # ================= Private API ================================

    async def _load_from_db(self):
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

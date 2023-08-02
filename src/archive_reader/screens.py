import asyncio

from textual import log, work
from textual.app import ComposeResult
from textual.containers import Horizontal

from textual.screen import Screen
from textual.widgets import (
    Footer,
    Input,
    ListItem,
    ListView,
    LoadingIndicator,
    SelectionList,
    Static,
)
from .widgets import (
    MailingListChoose,
    Header,
    EmailItem,
)
from .core import ListManager

DEFAULT_NOTIFY_TIMEOUT = 2


class ThreadReadScreen(Screen):
    """The main screen to read Email threads.

    This is composed of multiple Emails, which are embedded inside a listview.
    """

    BINDINGS = [
        ('escape', 'app.pop_screen', 'Close thread'),
        ('r', 'update_emails', 'Refresh Emails'),
    ]

    def __init__(self, *args, thread=None, thread_mgr=None, **kw):
        self.thread = thread
        self.thread_mgr = thread_mgr
        super().__init__(*args, **kw)

    def compose(self) -> ComposeResult:
        header = Header()
        header.text = self.thread.subject
        yield header
        yield LoadingIndicator()
        with Horizontal(classes='main'):
            yield ListView(id='thread-emails')
            yield ListView(id='thread-authors')
        yield Footer()

    async def on_mount(self):
        """Runs as soon as the Widget is mounted.

        It first loads the Emails for this thread that are stored in
        the database. If total emails in the database is less than
        the (replies_count + 1, 1 for the starting_email), then invoke
        the API to call remote server to fetch new emails.
        """
        stored_replies = await self.load_stored_emails().wait()
        if stored_replies < self.thread.replies_count + 1:
            self.action_update_emails()

    @work
    async def load_stored_emails(self, show_loading=True):
        """Load emails from Database and schedule emails to be fetched
        from remote if needed.

        Since this is decorated with @work, this runs inside a worker.
        """
        if show_loading:
            self._show_loading()
        reply_objs = await self.thread_mgr.emails(self.thread)
        # if not reply_objs:
        #     self.notify(f'No saved emails for {self.thread.subject}. Fetching from remote.')
        reply_emails = [
            EmailItem(
                email=reply,
                id='message-id-{}'.format(reply.message_id_hash),
            )
            for reply in reply_objs
        ]
        await self.add_emails_to_view(reply_emails)
        self._hide_loading()
        return len(reply_emails)

    @work
    async def action_update_emails(self):
        """Fetch new emails in the existing thread in a worker.

        This will ensure not to load email content that are already
        loaded in database.
        """
        replies = await self.thread_mgr.update_emails(self.thread)
        # self.load_emails(show_loading=False)
        reply_emails = [
            EmailItem(
                email=reply,
                id='message-id-{}'.format(reply.message_id_hash),
            )
            for reply in replies
        ]
        await self.add_emails_to_view(reply_emails)

    async def add_emails_to_view(self, emails):
        view = self.query_one('#thread-emails', ListView)
        author_view = self.query_one('#thread-authors', ListView)
        awaitables = []
        for email in emails:
            try:
                awaitables.append(view.append(email))
                awaitables.append(
                    author_view.append(
                        ListItem(Static(f'{email.sender}', classes='sender'))
                    )
                )
            except Exception as ex:
                log(ex)
        await asyncio.gather(*awaitables)

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False


class MailingListAddScreen(Screen):
    """A new screen where you can search and subscribe to MailingLists.

    This page will take the server as the input and load all the mailing lists on
    that server.
    """

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [('escape', 'app.pop_screen', 'Pop screen')]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.list_manager = ListManager()
        self._list_cache = {}

    def compose(self):
        yield Static('Hyperkitty Server URL', classes='label')
        yield Input(placeholder='https://')
        yield Static()
        yield MailingListChoose(id='pick-mailinglist')
        yield Footer()

    @work(exclusive=True)
    async def update_mailinglists(self, base_url):
        """Given a Hyperkitty remote URL, fetch and show MailingLists
        in Selection list.

        This also adds them to a dict, which is primarily used to
        share data between this method and when the ML is actually
        selected. We do this since SelectionList options can't include
        the ML objects.
        """
        lists_json = await self.list_manager.fetch_lists(base_url)
        selection_list = self.query_one(SelectionList)
        for ml in lists_json.get('results'):
            self._list_cache[ml.get('name')] = ml
            selection_list.add_option(
                (
                    f"{ml.get('display_name')} <\"{ml.get('name')}\">",
                    ml.get('name'),
                )
            )

    async def on_input_submitted(self, message: Input.Submitted):
        """Handle the Hyperkitty URL input from user.

        This calls py:meth:`update_mailinglist` method which will
        actually fetch all available lists and show to the user in a
        selection list.
        """
        self.base_url = message.value
        self.update_mailinglists(self.base_url)

    def on_mailing_list_choose_selected(self, message):
        """Return the chosen mailinglist back to the previous screen."""
        log(f'User chose {message.data=}')
        self.dismiss(
            [self._list_cache.get(listname) for listname in message.data]
        )

import asyncio
from contextlib import suppress
from collections import defaultdict

from textual import log, work
from textual._node_list import DuplicateIds
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches

from textual.reactive import var
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

from .models import initialize_database
from .widgets import (
    Threads,
    MailingListItem,
    MailingListChoose,
    MailingLists,
    ThreadItem,
    Header,
    EmailItem,
)
from .core import ListManager, ThreadsManager

DEFAULT_NOTIFY_TIMEOUT = 2


class ThreadReadScreen(Screen):
    """The main screen to read Email threads.

    This is composed of multiple Emails, which are embedded inside a listview.
    """

    BINDINGS = [
        ('escape', 'app.pop_screen', 'Close thread'),
        ('r', 'update_emails', 'Refresh Emails'),
    ]

    DEFAULT_CSS = """
    .main {
        layout: grid;
        grid-size: 2;
        grid-columns: 9fr 1fr;
    }
    .sender {
        padding: 0 1;
    }
    """

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

    def on_mount(self):
        """Runs as soon as the Widget is mounted."""
        self.load_emails()
        self.action_update_emails()

    @work
    async def load_emails(self, show_loading=True):
        """Load emails from Database and schedule emails to be fetched
        from remote if needed.

        TODO: We don't currently have the if-needed criteria working too
        well since we don't yet compare the replies_count.
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
        try:
            self.add_emails(reply_emails)
            self.add_email_authors(reply_emails)
        except Exception as ex:
            log(ex)
        self._hide_loading()

    @work
    async def action_update_emails(self):
        replies = await self.thread_mgr.update_emails(self.thread)
        # self.load_emails(show_loading=False)
        reply_emails = [
            EmailItem(
                email=reply,
                id='message-id-{}'.format(reply.message_id_hash),
            )
            for reply in replies
        ]
        try:
            self.add_emails(reply_emails)
            self.add_email_authors(reply_emails)
        except Exception as ex:
            log(ex)
        self.notify('Thread refresh complete.')

    def add_emails(self, emails):
        view = self.query_one('#thread-emails', ListView)
        for email in emails:
            view.append(email)

    def add_email_authors(self, emails):
        view = self.query_one('#thread-authors', ListView)
        for email in emails:
            view.append(ListItem(Static(f'{email.sender}', classes='sender')))

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
        self.base_url = message.value
        self.update_mailinglists(self.base_url)

    def on_mailing_list_choose_selected(self, message):
        log(f'User chose {message.data=}')
        self.dismiss(
            [self._list_cache.get(listname) for listname in message.data]
        )

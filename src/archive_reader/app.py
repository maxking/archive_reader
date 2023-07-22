from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

import timeago
from rich.console import RenderableType
from textual import events, log, work
from textual._node_list import DuplicateIds
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive, var
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    ListItem,
    ListView,
    LoadingIndicator,
    Placeholder,
    SelectionList,
    Static,
)

from .hyperkitty import HyperkittyAPI, fetch_urls
from .storage import SUBSCRIBED_ML, cache_get, cache_set

hk = HyperkittyAPI()


def rich_bold(in_string):
    """Add rich markup for bold to the input string."""
    return f'[bold]{in_string}[/bold]'


class Header(Placeholder):
    """A generic header class with configurable text.

    You can set the text attribute on the class to update the content
    and `text` attribute is a reactive element so it is updated without
    any refresh or update operation.
    """

    DEFAULT_CSS = """
    Header {
        height: 3;
        dock: top;
    }
    """

    text = reactive('Archive Reader')

    def render(self) -> RenderableType:
        return self.text


class Email(ListItem):
    """Email class represents rendering of a single Email.

    This is currently used in the ThreadReadScreen() to render all the Emails
    from the first one to the last one.

    The JSON metadata from Hyperkitty is stored in the `email_contents` attr
    of the instance. You can get the values of those using the `.get()` method.
    """

    DEFAULT_CSS = """
    Email {
        width: 1fr;
        margin: 1 1;
        height: auto;
    }
    Label {
        padding: 1 2;
    }
    ListView > ListItem.--highlight {
        background: $secondary-background-lighten-3 20%;
    }
    ListView:focus > ListItem.--highlight {
        background: $secondary-background-lighten-3 50%;
    }
    """

    def __init__(self, *args, email_contents=None, **kw):
        super().__init__(*args, **kw)
        self.email_contents = email_contents

    def get(self, attr):
        return self.email_contents.get(attr)

    @property
    def sender(self):
        """Return the sender name"""
        # TODO: Return the sender's address too.
        return f"{self.get('sender_name')}"

    @property
    def message_id_hash(self):
        return f"{self.get('message_id_hash')}"

    def compose(self):
        yield Static(rich_bold(f'From: {self.sender}'))
        yield Static(rich_bold(f'Date: {self.get("date")}'))
        yield Static()
        yield Static(self.get('content'))


class ThreadReadScreen(Screen):
    """The main screen to read Email threads.

    This is composed of multiple Emails, which are embedded inside a listview.
    """

    BINDINGS = [('escape', 'app.pop_screen', 'Close thread')]
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

    def __init__(self, *args, thread=None, **kw):
        self.thread = thread
        super().__init__(*args, **kw)

    def compose(self) -> ComposeResult:
        header = Header()
        header.text = self.thread.subject()
        yield header
        yield LoadingIndicator()
        with Horizontal(classes='main'):
            yield ListView(id='thread-emails')
            yield ListView(id='thread-authors')
        yield Footer()

    @work
    async def load_emails(self):
        # TODO: Don't assume the requests are going to pass always!!!
        log('Fetching Emails URLs')
        replies, _ = await fetch_urls([self.thread.get('emails')], log)
        reply_urls = [each.get('url') for each in replies[0].get('results')]
        log(f'Retrieved email urls {reply_urls}')
        replies, _ = await fetch_urls(reply_urls)
        log(f'Received email contents...')
        reply_emails = [
            Email(
                email_contents=reply,
                id='message-id-{}'.format(reply.get('message_id_hash')),
            )
            for reply in replies
        ]
        try:
            self.add_emails(reply_emails)
            self.add_email_authors(reply_emails)
        except Exception as ex:
            log(ex)
        self._hide_loading()

    def add_emails(self, emails):
        view = self.query_one('#thread-emails', ListView)
        for email in emails:
            view.append(email)

    def add_email_authors(self, emails):
        view = self.query_one('#thread-authors', ListView)
        for email in emails:
            view.append(ListItem(Static(f'{email.sender}', classes='sender')))

    def on_mount(self):
        self.load_emails()

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False


class MailingListChoose(ScrollableContainer):
    """Pick a mailing list from the available ones."""

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }

    SelectionList {
        padding: 1;
        border: solid $accent;
        width: 80%;
        height: 80%;
    }
    """

    class Selected(Message):
        """Message when a thread is clicked on, so that main app
        can handle the event by loading thread screen.
        """

        def __init__(self, lists):
            self.data = lists
            super().__init__()

    def on_mount(self) -> None:
        self.query_one(
            SelectionList
        ).border_title = 'Select Mailing lists to subscribe to'

    def compose(self):
        yield SelectionList()
        yield Button(
            'Subscribe Selected', variant='primary', id='select_mailinglist'
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == 'select_mailinglist':
            self.post_message(
                self.Selected(self.query_one(SelectionList).selected)
            )
            event.stop()


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

    def compose(self):
        yield Static('Hyperkitty Server URL', classes='label')
        yield Input(placeholder='https://')
        yield Static()
        yield MailingListChoose(id='pick-mailinglist')
        yield Footer()

    @work(exclusive=True)
    async def update_mailinglists(self, base_url):
        lists_json = await hk.lists(base_url)
        selection_list = self.query_one(SelectionList)
        for ml in lists_json.get('results'):
            cache_set(ml.get('name'), ml)
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
        self.dismiss(message.data)


class Thread(ListItem):
    """Represents a thread on the Main screen."""

    DEFAULT_CSS = """
    Thread {
        height: 3;
        width: 1fr;
        layout: grid;
        grid-size: 4;
        grid-columns: 1fr 14fr 1fr 2fr;
        content-align: left middle;
        padding: 1 1;
    }
    """
    read = reactive(False, layout=True)

    class Selected(Message):
        """Message when a thread is clicked on, so that main app
        can handle the event by loading thread screen.
        """

        def __init__(self, thread_data):
            self.data = thread_data
            super().__init__()

    def __init__(self, *args, thread_data=None, **kw) -> None:
        super().__init__(*args, **kw)
        self.data = thread_data

    def get(self, attr):
        return self.data.get(attr)

    def subject(self):
        return self.get('subject')

    def time_format(self):
        return self.data.get('date_active')

    def mark_read(self):
        self.read = True

    def compose(self):
        yield Static(f':envelope:')
        yield Static(self.subject())
        yield Static(
            ':speech_balloon: {}'.format(self.data.get('replies_count'))
        )
        now = datetime.now(tz=ZoneInfo('Asia/Kolkata'))
        thread_date = self.time_format()
        yield Static(
            ':two-thirty: {}'.format(timeago.format(thread_date, now))
        )

    async def _on_click(self, _: events.Click) -> None:
        self.post_message(self.Selected(self))


class ArchiveApp(App):
    """Textual reader app to read Hyperkitty (GNU Mailman's official Archiver) email archives."""

    CSS_PATH = 'archiver.css'
    BINDINGS = [
        ('a', 'add_mailinglist', 'Add MailingList'),
        ('d', 'app.toggle_dark', 'Toggle Dark mode'),
        ('s', 'app.screenshot()', 'Screenshot'),
        ('q', 'quit', 'Quit'),
    ]
    TITLE = 'Archive Reader'
    SUB_TITLE = 'An app to reach Hyperkitty archives in Terminal!'
    SCREENS = {'threadview': ThreadReadScreen}
    show_tree = var(True)

    def watch_show_tree(self, show_tree: bool) -> None:
        """Called when show_tree is modified."""
        self.set_class(show_tree, '-show-tree')

    def compose(self) -> ComposeResult:
        """Compose our UI."""
        yield Header(id='header')
        yield Vertical(MailingLists(id='lists'), id='lists-view')
        yield LoadingIndicator()
        yield ListView(id='threads')
        yield Footer()

    def on_mount(self):
        self._hide_loading()
        self._load_subscribed_lists()

    def _store_subscribed_lists(self, lists):
        stored = cache_get(SUBSCRIBED_ML, [])
        for each in lists:
            if each not in stored:
                stored.append(each)
        cache_set(SUBSCRIBED_ML, stored)

    def action_add_mailinglist(self):
        def get_lists(lists):
            self._store_subscribed_lists(lists)
            for ml in lists:
                self._add_ml(ml)

        self.push_screen(MailingListAddScreen(), get_lists)

    def _add_ml(self, ml):
        ml_json = cache_get(ml)
        log(ml, ml_json)
        if ml_json:
            self.query_one(MailingLists).append(MailingList(ml_json))

    def _load_subscribed_lists(self):
        subscribed = cache_get(SUBSCRIBED_ML)
        if subscribed:
            for ml in subscribed:
                self._add_ml(ml)

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False

    async def _load_saved_threads(self, ml):
        """If there are any saved threads for this ML, set those.

        Return total no. of loaded threads.
        """
        key = f'{ml}_threads'
        existing_threads = cache_get(key, {})
        if not existing_threads:
            # More importantly, if you are not loading threads from
            # local cache then do not unhide the loading screen.
            log('There are no cached threads')
            return 0
        self._existing_threads = existing_threads
        await self._refresh_threads_view()
        self._hide_loading()
        return len(existing_threads)

    async def _refresh_threads_view(self):
        """Update the Threads view with the threads that are defined in
        self._existing_threads.
        """
        for _, thread in self._existing_threads.items():
            await self._set_thread(thread)

    async def _set_thread(self, thread):
        try:
            threads_container = self.query_one('#threads', ListView)
        except NoMatches:
            # This can potentially happen when we have switched to a different
            # screen and we aren't able to find the `threads` in the current DOM.
            log(f'Failed to find threads_container when setting {thread}')
            return
        with suppress(DuplicateIds):
            widget = Thread(
                id=f"thread-{thread.get('thread_id')}", thread_data=thread
            )
            if widget not in threads_container.children:
                await threads_container.append(widget)

    def _save_threads(self):
        ml = self.current_mailinglist
        key = f'{ml.name}_threads'
        cached_threads = cache_get(key, {})
        if not cached_threads:
            log('Saving new found threads since there are no existing.')
            cache_set(key, self._existing_threads)
        log(
            f'Merging old and new threads. {len(cached_threads)} cached threads.'
        )
        cached_threads.update(self._existing_threads)
        log(f'Saving merged threads. {len(cached_threads)} threads.')
        cache_set(key, cached_threads)
        self.notify(f'Saved Cached threads for {ml.name}', title='Saved')

    async def _load_new_threads(self, threads):
        # TODO: Sort the threads.
        # threads.update(self._existing_threads)
        self._existing_threads.update(threads)
        # Sort the threads so that new ones are on top.
        self._existing_threads = dict(
            sorted(
                self._existing_threads.items(),
                key=lambda item: item[1]['date_active'],
                reverse=True,
            )
        )
        await self._clear_threads()
        await self._refresh_threads_view()

    async def _clear_threads(self):
        threads_container = self.query_one('#threads', ListView)
        # First, clear the threads.
        clear_resp = threads_container.clear()
        log(type(clear_resp))
        # .clear() returns an awaitable and gives the control back to
        # DOM to perform the action.
        await clear_resp

    @work()
    async def update_threads(self, ml):
        header = self.query_one('#header', Header)
        header.text = ml.name
        await self._clear_threads()
        self._show_loading()
        # loaded = was some new cached threads loaded.
        loaded = await self._load_saved_threads(ml.name)
        threads = await hk.threads(ml._data)
        # Then add all the new threads that were found.
        list_threads = {}
        for thread in threads.get('results'):
            list_threads[thread.get('thread_id')] = thread
        # Set the new threads in the view.
        await self._load_new_threads(list_threads)
        self._save_threads()
        if not loaded:
            # If the cached threads weren't loaded then hide those.
            self._hide_loading()
        self.notify(
            f'Finished refreshing new threads for {self.current_mailinglist.name}.',
            title='Thread refresh complete',
            timeout=3,
        )

    async def on_list_view_selected(self, item):
        # Handle the list item selected for MailingList.
        if isinstance(item.item, MailingList):
            self.current_mailinglist = item.item
            # Since update_threads runs in a worker, we don't need
            # to await the below.
            self.update_threads(item.item)
        elif isinstance(item.item, Thread):
            log(f'Thread {item.item} was selected.')
            # Make sure that we cancel the workers so that nothing will interfere after
            # we have moved on to the next screen.
            self.workers.cancel_all()
            # Mark the threads as read.
            self.push_screen(ThreadReadScreen(thread=item.item))
            item.item.mark_read()


class MailingLists(ListView):
    """Represents the left side with Subscribed MailingLists."""


class MailingList(ListItem):
    """Represents an item in the left sidebar with the MailingLists."""

    DEFAULT_CSS = """
    MailingList {
        padding: 1 1;
    }
    """

    def __init__(self, data):
        if data is None:
            raise ValueError('Empty mailinglist json response')
        self._data = data
        super().__init__()

    def render(self):
        return self.name

    @property
    def name(self):
        return self._data.get('name')

    def get(self, key):
        return self._data.get(key)


def main():
    app = ArchiveApp()
    app.run()

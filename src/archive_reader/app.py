from contextlib import suppress
from collections import defaultdict
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
from textual.widget import Widget
from .hyperkitty import HyperkittyAPI, fetch_urls
from .storage import SUBSCRIBED_ML, cache_get, cache_set

hk = HyperkittyAPI()

DEFAULT_NOTIFY_TIMEOUT = 2


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
        log('Received email contents...')
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


class ThreadReplies(Widget):

    has_new = reactive(0)
    count = reactive(0)

    def __init__(self, count, has_new, *args, **kw):
        super().__init__(*args, **kw)
        self.count = count
        self.has_new = has_new

    def render(self):
        return f':speech_balloon: {self.count} ({self.has_new})'


class Thread(ListItem):
    """Represents a thread on the Main screen."""

    DEFAULT_CSS = """
    Thread {
        height: 3;
        width: 1fr;
        layout: grid;
        grid-size: 3;
        grid-columns: 14fr 1fr 2fr;
        content-align: left middle;
        padding: 1 1;
    }
    """
    #: Represents whether this thread has been opened in the current
    #: reader before. This is computed locally and turned to 'read'
    #: as soon as the thread is opened.
    read = reactive(False)
    #: Represents whether an existing thread has new emails after the
    #: refresh operation is complete.
    has_new = reactive(0)
    #: If a thread is entirely new, i.e. not loaded from the local
    #: cache, then this is turned on. This implies that this was
    #: just fetched from the remote server.
    is_new = reactive(False)

    class Selected(Message):
        """Message when a thread is clicked on, so that main app
        can handle the event by loading thread screen.
        """

        def __init__(self, thread_data):
            self.data = thread_data

            super().__init__()

    class Updated(Message):
        def __init__(self, thread_data):
            self.data = thread_data
            super().__init__()

    def __init__(
        self, *args, thread_data=None, mailinglist=None, **kw
    ) -> None:
        super().__init__(*args, **kw)
        self.mailinglist = mailinglist
        self.is_new = thread_data.get('is_new', False)
        self.has_new = thread_data.get('has_new', 0)
        self.data = thread_data

    def get(self, attr):
        return self.data.get(attr)

    def subject(self):
        return self.get('subject')

    def time_format(self):
        return self.data.get('date_active')

    def watch_read(self, old, new):
        if old is False and new is True:
            self.styles.background = 'gray'
            # Regardless of the current value, just turn these two off since
            # they are not required anymore.
            self.is_new = False
            self.has_new = 0
            self.data['is_new'] = False
            self.data['has_new'] = 0
            log(f'Sending ThreadUpdated for {self}')
            self.post_message(self.Updated(self.data))
        self._save_read_status(new)

    def _save_read_status(self, new):
        # Update the thread.read() status in the storage.
        # XXX(abraj): This is a relatively complex operation. The reason
        # for which is the fact that we are using a caching solution as a
        # trivial json database in a way that doesn't provide tons of data
        # access patterns that we want to have.
        # This can be solved easily with a local Sqlite database in future,
        # infact, the current caching solution utilizes sqlite underneath.
        pass

    def watch_has_new(self, _, new):
        # It is possible that this is b
        try:
            self.query_one(ThreadReplies).has_new = new
        except Exception:
            log(f'Failed to Find & Update thread replies')

    def compose(self):
        yield Static(self.subject())
        yield ThreadReplies(
            count=self.data.get('replies_count'), has_new=self.has_new
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
        ('u', 'update_threads', 'Update threads'),
    ]
    TITLE = 'Archive Reader'
    SUB_TITLE = 'An app to reach Hyperkitty archives in Terminal!'
    SCREENS = {'threadview': ThreadReadScreen}
    show_tree = var(True)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._existing_threads = defaultdict(dict)

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
        self.notify(
            f'Loaded {len(existing_threads)} threads for {ml} from cache.'
        )
        if not existing_threads:
            # More importantly, if you are not loading threads from
            # local cache then do not unhide the loading screen.
            log('There are no cached threads')
            return 0
        self._existing_threads['ml'] = existing_threads
        await self._refresh_threads_view()
        self._hide_loading()
        return len(existing_threads)

    async def _refresh_threads_view(self):
        """Update the Threads view with the threads that are defined in
        self._existing_threads.
        """
        for _, thread in self._existing_threads.get(
            self.current_mailinglist.name, {}
        ).items():
            await self._set_thread(thread)
        self.notify('Finished displaying loaded threads.')

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
                id=f"thread-{thread.get('thread_id')}",
                thread_data=thread,
                mailinglist=self.current_mailinglist,
            )
            if widget not in threads_container.children:
                await threads_container.append(widget)

    def _save_threads(self):
        ml = self.current_mailinglist
        key = f'{ml.name}_threads'
        cached_threads = cache_get(key, {})
        if not cached_threads:
            log('Saving new found threads since there are no existing.')
            cache_set(key, self._existing_threads[ml.name])
        log(
            f'Merging old and new threads. {len(cached_threads)} cached threads.'
        )
        cached_threads.update(self._existing_threads)
        log(f'Saving merged threads. {len(cached_threads)} threads.')
        cache_set(key, cached_threads)
        self.notify(f'Saved Cached threads for {ml.name}', title='Saved')

    async def _load_new_threads(self, threads):
        current_ml_threads = self._existing_threads[
            self.current_mailinglist.name
        ]
        for thread_id, thread in threads.items():
            if thread_id not in current_ml_threads:
                thread['is_new'] = True
                current_ml_threads[thread_id] = thread
            elif (
                thread['replies_count']
                > current_ml_threads[thread_id]['replies_count']
            ):
                # This thread exists already in the cache.
                # Check if there are any new replies in this
                # thread.
                log(thread)
                current_ml_threads[thread_id]['has_new'] = (
                    thread['replies_count']
                    - current_ml_threads[thread_id]['replies_count']
                )
                current_ml_threads[thread_id]['replies_count'] = thread[
                    'replies_count'
                ]
            else:
                # Thread exists in cache and there aren't any new replies in it.
                # We will simply skip the thread in this case.
                pass

        # Sort the threads so that new ones are on top.
        current_ml_threads = dict(
            sorted(
                current_ml_threads.items(),
                key=lambda item: item[1]['date_active'],
                reverse=True,
            )
        )
        self._existing_threads[
            self.current_mailinglist.name
        ] = current_ml_threads
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

    async def action_update_threads(self):
        self.notify(
            f'Updating threads for {self.current_mailinglist.name}',
            title='Update starting',
            timeout=DEFAULT_NOTIFY_TIMEOUT,
        )
        self.update_threads(self.current_mailinglist)
        self._notify_update_complete()

    def _notify_update_complete(self):
        self.notify(
            f'Finished refreshing new threads for {self.current_mailinglist.name}.',
            title='Thread refresh complete',
            timeout=DEFAULT_NOTIFY_TIMEOUT,
        )

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
        self._notify_update_complete()

    async def on_list_view_selected(self, item):
        # Handle the list item selected for MailingList.
        if isinstance(item.item, MailingList):
            self.current_mailinglist = item.item
            # Since update_threads runs in a worker, we don't need
            # to await the below.
            self.update_threads(item.item)
        elif isinstance(item.item, Thread):
            item.item.read = True
            log(f'Thread {item.item} was selected.')
            # Make sure that we cancel the workers so that nothing will interfere after
            # we have moved on to the next screen.
            self.workers.cancel_all()
            # Mark the threads as read.
            self.push_screen(ThreadReadScreen(thread=item.item))

    async def on_thread_updated(self, item):
        self._existing_threads[self.current_mailinglist.name][
            item.data['thread_id']
        ] = item.data


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

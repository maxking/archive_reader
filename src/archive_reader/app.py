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
from .hyperkitty import HyperkittyAPI, fetch_urls
from .models import initialize_database
from .widgets import (
    rich_bold,
    Threads,
    MailingListItem,
    MailingListChoose,
    MailingLists,
    ThreadItem,
    Header,
)
from .core import ListManager, ThreadsManager

hk = HyperkittyAPI()

DEFAULT_NOTIFY_TIMEOUT = 2


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
        header.text = self.thread.subject
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
        replies, _ = await fetch_urls([self.thread.emails], log)
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
        self.list_manager = ListManager()
        self.thread_mgrs = {}

    def watch_show_tree(self, show_tree: bool) -> None:
        """Called when show_tree is modified."""
        self.set_class(show_tree, '-show-tree')

    def compose(self) -> ComposeResult:
        """Compose our UI."""
        yield Header(id='header')
        yield Vertical(MailingLists(id='lists'), id='lists-view')
        yield LoadingIndicator()
        yield Threads(id='threads')
        yield Footer()

    async def on_mount(self):
        self._hide_loading()
        await self._load_subscribed_lists()

    def action_add_mailinglist(self):
        async def subscribe_lists(lists):
            list_objs = await self.list_manager.subscribe_lists(lists)
            log(f'Subscribed list objects {list_objs}')
            for ml in list_objs:
                self._show_new_subscribed_lists(ml)

        self.push_screen(MailingListAddScreen(), subscribe_lists)

    async def _load_subscribed_lists(self):
        lists = await self.list_manager.lists()
        list_view = self.query_one(MailingLists)
        for list in lists:
            await list_view.append(MailingListItem(list))

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

    # async def _refresh_threads_view(self, threads):
    #     """Update the Threads view with the threads that are defined in
    #     self._existing_threads.
    #     """
    #     for thread in threads:
    #         await self._set_thread(thread)

    async def _set_thread(self, thread):
        try:
            threads_container = self.query_one('#threads', Threads)
        except NoMatches:
            # This can potentially happen when we have switched to a different
            # screen and we aren't able to find the `threads` in the current DOM.
            log(f'Failed to find threads_container when setting {thread}')
            return
        with suppress(DuplicateIds):
            widget = ThreadItem(
                id=f'thread-{thread.thread_id}',
                thread=thread,
                mailinglist=self.current_mailinglist,
            )
            log(f'Created widget {widget} for {thread}')
            await threads_container.append(widget)
            log(f'Finished adding widget for {thread} to {threads_container}')

    async def _load_new_threads(self, threads):
        # Fetch all the threads loaded form the cache.
        current_ml_threads = self._existing_threads[
            self.current_mailinglist.name
        ]
        for thread_id, thread in threads.items():
            # If this thread is not in the cache,
            # Set the `is_new` flag on it and also
            # read = False.
            if thread_id not in current_ml_threads:
                thread['is_new'] = True
                thread['read'] = False
                # All the replies are unread.
                thread['has_new'] = thread['replies_count']
                current_ml_threads[thread_id] = thread
            elif (
                thread['replies_count']
                > current_ml_threads[thread_id]['replies_count']
            ):
                # This thread exists already in the cache and
                # there are any new replies in this thread set
                # the total no. of new replies.
                current_ml_threads[thread_id]['has_new'] = (
                    thread['replies_count']
                    - current_ml_threads[thread_id]['replies_count']
                )
                # Also, update the replies_count & date_active field, which
                # are the only two fields which can change.
                current_ml_threads[thread_id]['replies_count'] = thread[
                    'replies_count'
                ]
                current_ml_threads[thread_id]['date_active'] = thread[
                    'date_active'
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
        # self._show_loading()
        # If a threads manager doesn't already exist, create a new.
        if (mgr := self.thread_mgrs.get(ml.name)) is None:
            mgr = ThreadsManager(ml)
            self.thread_mgrs[ml.name] = mgr

        threads = await mgr.threads()
        # Set the new threads in the view.
        await self._clear_threads()
        # await self._refresh_threads_view(threads)
        threads_container = self.query_one('#threads', Threads)
        for thread in threads:
            await self._set_thread(thread)
            # widget = ThreadItem(
            #     id=f"thread-{thread.thread_id}",
            #     thread=thread,
            #     mailinglist=self.current_mailinglist,
            # )
            # log(f'Adding widget {widget} for {thread} to {threads_container}')
            # await threads_container.append(widget)
        # If the cached threads weren't loaded then hide those.
        # self._hide_loading()
        self._notify_update_complete()

    async def on_list_view_selected(self, item):
        # Handle the list item selected for MailingList.
        if isinstance(item.item, MailingListItem):
            self.current_mailinglist = item.item.mlist
            # Since update_threads runs in a worker, we don't need
            # to await the below.
            self.update_threads(item.item.mlist)
        elif isinstance(item.item, ThreadItem):
            item.item.read = True
            log(f'Thread {item.item} was selected.')
            # Make sure that we cancel the workers so that nothing will interfere after
            # we have moved on to the next screen.
            self.workers.cancel_all()
            # Mark the threads as read.
            self.push_screen(ThreadReadScreen(thread=item.item.thread))

    @work
    async def on_thread_updated(self, item):
        self._existing_threads[self.current_mailinglist.name][
            item.data['thread_id']
        ] = item.data
        log(f'Received thread updated event for {item=} {item.data=}')
        self._save_threads()


def main():
    # Run the initialization routine in asyncio.run since the method
    # is async and main is supposed to be sync method.
    asyncio.run(initialize_database())
    app = ArchiveApp()
    app.run()

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
from .screens import ThreadReadScreen, MailingListAddScreen

DEFAULT_NOTIFY_TIMEOUT = 2


class ArchiveApp(App):
    """Textual reader app to read Hyperkitty (GNU Mailman's official Archiver) email archives."""

    CSS_PATH = 'archiver.css'
    BINDINGS = [
        ('a', 'add_mailinglist', 'Add MailingList'),
        ('d', 'app.toggle_dark', 'Toggle Dark mode'),
        ('s', 'app.screenshot()', 'Screenshot'),
        ('q', 'quit', 'Quit'),
        ('u', 'load_new_threads', 'Update threads'),
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
            list_view = self.query_one(MailingLists)
            for ml in list_objs:
                await list_view.append(MailingListItem(ml))

        self.push_screen(MailingListAddScreen(), subscribe_lists)

    async def _load_subscribed_lists(self):
        lists = await self.list_manager.lists()
        list_view = self.query_one(MailingLists)
        for ml in lists:
            await list_view.append(MailingListItem(ml))

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False

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

    async def _clear_threads(self):
        threads_container = self.query_one('#threads', ListView)
        # First, clear the threads.
        clear_resp = threads_container.clear()
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

    def _notify_update_complete(self):
        self.notify(
            f'Finished refreshing new threads for {self.current_mailinglist.name}.',
            title='Thread refresh complete',
            timeout=DEFAULT_NOTIFY_TIMEOUT,
        )

    def thread_mgr(self):
        """Return a ThreadManager instance for the "current_mailinglist"."""
        # If a threads manager doesn't already exist, create a new.
        ml = self.current_mailinglist
        if (mgr := self.thread_mgrs.get(ml.name)) is None:
            mgr = ThreadsManager(ml)
            self.thread_mgrs[ml.name] = mgr
        return mgr

    @work()
    async def update_threads(self, ml):
        header = self.query_one('#header', Header)
        header.text = '{} ({})'.format(ml.display_name, ml.name)
        await self._clear_threads()
        self._show_loading()
        self.current_mailinglist = ml
        mgr = self.thread_mgr()
        threads = await mgr.threads()
        # Set the new threads in the view.
        for thread in threads:
            await self._set_thread(thread)
        self._hide_loading()
        self._notify_update_complete()

    @work()
    async def action_load_new_threads(self):
        ml = self.current_mailinglist
        mgr = self.thread_mgr()
        await mgr.update_threads()
        self.update_threads(ml)

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
            # self.workers.cancel_all()
            # Mark the threads as read.
            self.push_screen(
                ThreadReadScreen(
                    thread=item.item.thread, thread_mgr=self.thread_mgr()
                )
            )

    # @work
    # async def on_thread_updated(self, item):
    #     self._existing_threads[self.current_mailinglist.name][
    #         item.data['thread_id']
    #     ] = item.data
    #     log(f'Received thread updated event for {item=} {item.data=}')
    #     self._save_threads()


def main():
    # Run the initialization routine in asyncio.run since the method
    # is async and main is supposed to be sync method.
    asyncio.run(initialize_database())
    app = ArchiveApp()
    app.run()

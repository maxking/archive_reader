import sys
from contextlib import contextmanager
from functools import lru_cache

import httpx
from rich.console import RenderableType
from rich.pretty import Pretty
from rich.syntax import Syntax
from rich.text import Text
from rich.traceback import Traceback
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.message import Message, MessageTarget
from textual.reactive import var
from textual.widgets import (Button, DataTable, DirectoryTree, Footer, Header,
                             Input, Static, TreeControl)
from textual.widgets._tree_control import TreeNode


@contextmanager
def show_traceback(view):
    try:
        yield
    except:
        view.update(Traceback(theme="github-dark", width=None))


class ArchiveApp(App):
    """Textual code browser app."""

    CSS_PATH = "archiver.css"
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    show_tree = var(True)

    def watch_show_tree(self, show_tree: bool) -> None:
        """Called when show_tree is modified."""
        self.set_class(show_tree, "-show-tree")

    def compose(self) -> ComposeResult:
        """Compose our UI."""
        hk_url = None if len(sys.argv) < 2 else sys.argv[1]
        # if not hk_url:
        yield Input(placeholder="Hyperkitty URL:", id="input-view")
        # else:
        #     self.call_later(self.update_lists(hk_url))
        yield Vertical(Container(id="lists"), id="lists-view")
        yield Vertical(DataTable(id="mail"), id="mail-view")
        yield

    async def on_input_submitted(self, message: Input.Submitted):
        await self.update_lists(message.value)

    async def update_lists(self, hk_url):
        lists_view = self.query_one("#lists")
        self.hk_server = Hyperkitty(hk_url)
        with show_traceback(lists_view):
            lists_json = await self.hk_server.lists()
            for _, mlist  in lists_json.items():
                lists_view.mount(MailingList(mlist))

    def on_mount(self, event: events.Mount) -> None:
        self.query_one(Input).focus()

    async def on_button_pressed(self, event: Button.Pressed):
        mail_table = self.query_one("#mail", DataTable)
        # mails.update(Text(f"Button pressed in {self.__class__.__name__}:\n {event.sender._data}"))
        mail_table.add_columns("subject", "replies", "date,")
        mlist_id = event.sender._data.get("name")
        threads = await self.hk_server.threads(mlist_id)
        for thread in threads:
            mail_table.add_row(thread.get("subject"), thread.get("replies"), thread.get("date"))


class MailingList(Button):

    def __init__(self, data):
        self._data = data
        super().__init__()

    def render(self):
        return self._data.get("name")


class Hyperkitty:

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._lists_json = {}
        self._list_threads = {}

    async def lists(self):
        """Return a list of MailingLists.

        It will cache the results for next use, until :py:meth:`refresh` is
        called on the HK instance.
        """
        if self._lists_json:
            return self._lists_json

        url = f"{self.base_url}/api/lists?format=json"
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._lists_json = {item.get("name"): item for item in results.json().get("results")}
            return self._lists_json
        return {}

    async def threads(self, list_id: str):
        if list_id in self._list_threads:
            return self._list_threads[list_id]
        url = self._lists_json[list_id].get("threads")
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._list_threads[list_id] = results.json().get("results")
            return self._list_threads[list_id]
        return {}


if __name__ == "__main__":
    ArchiveApp().run()
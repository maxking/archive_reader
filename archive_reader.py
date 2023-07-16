import logging
import sys
from contextlib import contextmanager, suppress

import httpx
from rich.console import RenderableType
from rich.traceback import Traceback
from textual import events, log
from textual._node_list import DuplicateIds
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive, var
from textual.screen import Screen
from textual.validation import ValidationResult, Validator
from textual.widgets import Input, ListItem, ListView, Placeholder, Static

# logging.basicConfig(
#     level="NOTSET",
#     handlers=[TextualHandler()],
# )

@contextmanager
def show_traceback(view):
    try:
        yield
    except:
        view.update(Traceback(theme="github-dark", width=None))

class Header(Placeholder):
    DEFAULT_CSS = """
    Header {
        height: 2;
        dock: top;
    }
    """


class Footer(Placeholder):
    DEFAULT_CSS = """
    Footer {
        height: 2;
        dock: bottom;
    }
    """


class ColumnsContainer(VerticalScroll):
    DEFAULT_CSS = """
    ColumnsContainer {
        width: 1fr;
        height: 1fr;
        border: solid white;
    }
    """


class ThreadReadScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def compose(self) -> ComposeResult:
        yield Static("You can read the thread in this page!")


class ArchiveApp(App):
    """Textual code browser app."""

    CSS_PATH = "archiver.css"
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]
    TITLE = "Archive Reader"
    SUB_TITLE = "An app to reach Hyperkitty archives in Terminal!"
    SCREENS = {'threadview': ThreadReadScreen}
    show_tree = var(True)

    def watch_show_tree(self, show_tree: bool) -> None:
        """Called when show_tree is modified."""
        self.set_class(show_tree, "-show-tree")

    def compose(self) -> ComposeResult:
        """Compose our UI."""
        hk_url = None if len(sys.argv) < 2 else sys.argv[1]
        yield Header(id="Header")
        yield Vertical(MailingLists(id="lists"), id="lists-view")
        yield URLInput(
            placeholder="Enter Hyperkitty URL...",
            validators=[HyperkittyUrlValidator()],
        )
        yield ScrollableContainer(id="threads")
        yield Footer(id="footer")

    async def on_input_submitted(self, message: Input.Submitted):
        await self.update_lists(message.value)
        # self.query_one('#urlinput', URLInput).display = False

    async def update_lists(self, hk_url):
        self.hk_server = Hyperkitty(hk_url)
        lists_view = self.query_one("#lists")
        lists_view.hk_server = self.hk_server
        lists_json = await self.hk_server.lists()
        mailinglist_widget = self.query_one('#lists')
        for _, mlist  in lists_json.items():
            mailinglist_widget.append(MailingList(mlist))

    # async def handle_selected(self, event):
    #     mail_table = self.query_one("#threads", Threads)
    #     mail_table.add_columns("Subject", "Replies", "Date")
    #     threads = await self.hk_server.threads(event.button._data.get("name"))
    #     for thread in threads:
    #         mail_table.add_row(
    #             thread.get("subject"),
    #             thread.get("replies_count"),
    #             thread.get("date_active"),
    #             )

    async def on_list_view_selected(self, item):
        threads_container = self.query_one("#threads", ScrollableContainer)
        threads = await self.hk_server.threads(item.item.name)
        for thread in threads:
            with suppress(DuplicateIds):
                threads_container.mount(
                    Thread(id=f"thread-{thread.get('thread_id')}", thread_data=thread)
                    )

    async def on_data_table_cell_selected(self, selected):
        thread_id, mlist_id = selected.cell_key.row_key.value.split(':')
        emails = await self.hk_server.emails(thread_id=thread_id, mlist_id=mlist_id)

    def on_thread_selected(self, message):
        self.push_screen(ThreadReadScreen())


class HyperkittyUrlValidator(Validator):
    def validate(self, value: str) -> ValidationResult:
        # TODO: Validate using sync call to Hyperkitty since there isn't current
        # support for async validation.
        return self.success()


class URLInput(Input):
    ...


class MailingLists(ListView):
    def __init__(self, hk_server=None, *args, **kw):
        super().__init__(*args, **kw)
        self.hk_server = hk_server


class MailingList(ListItem):
    def __init__(self, data):
        self._data = data
        super().__init__()

    def render(self):
        return self._data.get("name")

    @property
    def name(self):
        return self._data.get('name')


class Thread(Static):
    DEFAULT_CSS = """
    Thread {
        height: 3;
        width: 1fr;
        border: solid white;
    }
    """
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

    def render(self):
        return self.data.get('subject')

    async def _on_click(self, _: events.Click) -> None:
        self.post_message(self.Selected(self))


class Hyperkitty:
    """
    Hyperkitty is a client for Hyperkitty. It returns objects that can be
    used in the UI elements.

    This is limiting in the fact that it takes in the base_url, which implies
    it is linked to a single server.

    :param base_url: Base URL for Hyperkitty Instance.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._lists_json = {}
        self._list_threads = {}
        self._thread_emails = {}

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

    async def emails(self, mlist_id: str, thread_id: str):
        url = f"{self.base_url}/api/lists/{mlist_id}/threads/{thread_id}?format=json"
        if thread_id in self._thread_emails:
            return self._thread_emails[thread_id]
        async with httpx.AsyncClient() as client:
            results = (await client.get(url, follow_redirects=True))
        if results.status_code == 200:
            self._thread_emails[thread_id] = results.json().get("results")
            return self._thread_emails[thread_id]
        return {}


if __name__ == "__main__":
    ArchiveApp().run()
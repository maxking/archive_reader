
import sys
from contextlib import suppress

from rich.console import RenderableType
from textual import events, log, work
from textual._node_list import DuplicateIds
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive, var
from textual.screen import Screen
from textual.widgets import (Button, Input, ListItem, ListView,
                             LoadingIndicator, Placeholder, SelectionList,
                             Static)

from .hyperkitty import Hyperkitty


class Header(Placeholder):
    DEFAULT_CSS = """
    Header {
        height: 2;
        dock: top;
    }
    """

    text = reactive("Heading")

    def render(self) -> RenderableType:
        return self.text


class Footer(Placeholder):
    DEFAULT_CSS = """
    Footer {
        height: 2;
        dock: bottom;
    }
    """

class ThreadReadScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def compose(self) -> ComposeResult:
        yield Static("You can read the thread in this page!")



class MailingListChoose(ScrollableContainer):
    """Pick a mailing list from the available ones."""
    DEFAULT_CSS = """
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
        self.query_one(SelectionList).border_title = "Select Mailing lists to subscribe to"

    def compose(self):
        yield SelectionList()
        yield Button("Subscribe Selected", variant="primary", id="select_mailinglist")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "select_mailinglist":
            self.post_message(self.Selected(self.query_one(SelectionList).selected))
            event.stop()


class MailingListAddScreen(Screen):
    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def compose(self):
        yield Static("Hyperkitty Server URL", classes="label")
        yield Input(placeholder="https://")
        yield Static()
        yield Button("Fetch", variant="primary")
        yield MailingListChoose(id="pick-mailinglist")

    @work(exclusive=True)
    async def update_mailinglists(self, base_url):
        self.hk_server = Hyperkitty(base_url=base_url)
        lists_json = await self.hk_server.lists()
        selection_list = self.query_one(SelectionList)
        for _, ml in lists_json.items():
            selection_list.add_option(( f"{ml.get('display_name')} <\"{ml.get('name')}\">", ml.get('name')))

    async def on_input_submitted(self, message: Input.Submitted):
        self.base_url = message.value
        self.update_mailinglists(self.base_url)

    def on_mailing_list_choose_selected(self, message):
        self.dismiss((message.data, self.hk_server))

class ArchiveApp(App):
    """Textual code browser app."""

    CSS_PATH = "archiver.css"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "add_mailinglist", "Add MailingList")
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
        yield Header(id="header")
        yield Vertical(MailingLists(id="lists"), id="lists-view")
        yield LoadingIndicator()
        yield ListView(id="threads")
        # yield Footer(id="footer")

    def on_mount(self):
        self._hide_loading()

    def action_add_mailinglist(self):
        def get_lists(returns):
            lists, hk_server, = returns
            self.hk_server = hk_server
            for ml in lists:
                self.query_one(MailingLists).append(MailingList(ml))
        self.push_screen(MailingListAddScreen(), get_lists)

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False

    @work()
    async def update_threads(self, ml_name):
        header = self.query_one("#header", Header)
        header.text = ml_name
        self._show_loading()
        threads_container = self.query_one("#threads", ListView)
        threads = await self.hk_server.threads(ml_name)
        # First, clear the threads.
        threads_container.clear()
        # Then add all the new threads that were found.
        for thread in threads:
            with suppress(DuplicateIds):
                threads_container.append(
                    Thread(id=f"thread-{thread.get('thread_id')}", thread_data=thread)
                    )
        self._hide_loading()

    async def on_list_view_selected(self, item):
        # Handle the list item selected for MailingList.
        if isinstance(item.item, MailingList):
            self.update_threads(item.item.name)
        elif isinstance(item.item, Thread):
            self.push_screen(ThreadReadScreen())

    async def on_data_table_cell_selected(self, selected):
        thread_id, mlist_id = selected.cell_key.row_key.value.split(':')
        emails = await self.hk_server.emails(thread_id=thread_id, mlist_id=mlist_id)



class MailingLists(ListView):
    def __init__(self, hk_server=None, *args, **kw):
        super().__init__(*args, **kw)
        self.hk_server = hk_server


class MailingList(ListItem):

    DEFAULT_CSS = """
    MailingList {
        border: solid red;
    }
    """
    def __init__(self, data):
        self._data = data
        super().__init__()

    def render(self):
        return self._data

    @property
    def name(self):
        return self._data


class Thread(ListItem):
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


def main():
    app = ArchiveApp()
    app.run()
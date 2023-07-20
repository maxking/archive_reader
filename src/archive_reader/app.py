from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

import timeago
from rich.console import RenderableType
from textual import events, log, work
from textual._node_list import DuplicateIds
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive, var
from textual.screen import Screen
from textual.widgets import (Button, Footer, Input, ListItem, ListView,
                             LoadingIndicator, Markdown, Placeholder,
                             SelectionList, Static)

from .hyperkitty import Hyperkitty, fetch_urls


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

    text = reactive("Archive Reader")

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
    BINDINGS = [("escape", "app.pop_screen", "Close thread")]
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
        with Horizontal(classes="main"):
            yield ListView(id="thread-emails")
            yield ListView(id="thread-authors")
        yield Footer()

    @work
    async def load_emails(self):
        # TODO: Don't assume the requests are going to pass always!!!
        replies, _ = await fetch_urls([self.thread.get('emails')], log)
        reply_urls = [each.get('url') for each in replies[0].get('results')]
        replies, _ = await fetch_urls(reply_urls)
        reply_emails = [
            Email(
                email_contents=reply,
                id='message-id-{}'.format(reply.get('message_id_hash'))
                )
            for reply in replies
            ]
        self.add_emails(reply_emails)
        self.add_email_authors(reply_emails)
        self._hide_loading()

    def add_emails(self, emails):
        view = self.query_one('#thread-emails', ListView)
        for email in emails:
            view.append(email)

    def add_email_authors(self, emails):
        view = self.query_one('#thread-authors', ListView)
        for email in emails:
            view.append(
                ListItem(
                    Static(f"{email.sender}", classes="sender")))

    def on_mount(self):
        self.load_emails()

    def _show_loading(self):
        self.query_one(LoadingIndicator).display = True

    def _hide_loading(self):
        self.query_one(LoadingIndicator).display = False


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
    """A new screen where you can search and subscribe to MailingLists.

    This page will take the server as the input and load all the mailing lists on
    that server.
    """

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
        yield MailingListChoose(id="pick-mailinglist")
        yield Footer()

    @work(exclusive=True)
    async def update_mailinglists(self, base_url):
        self.hk_server = Hyperkitty(base_url=base_url)
        lists_json = await self.hk_server.lists()
        selection_list = self.query_one(SelectionList)
        for _, ml in lists_json.items():
            selection_list.add_option((f"{ml.get('display_name')} <\"{ml.get('name')}\">", ml.get('name')))

    async def on_input_submitted(self, message: Input.Submitted):
        self.base_url = message.value
        self.update_mailinglists(self.base_url)

    def on_mailing_list_choose_selected(self, message):
        self.dismiss((message.data, self.hk_server))


class Thread(ListItem):
    """Represents a thread on the Main screen.
    """

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
        return datetime.fromisoformat(self.data.get('date_active'))

    def compose(self):
        yield Static(self.subject())
        yield Static(":speech_balloon: {}".format(self.data.get("replies_count")))
        now = datetime.now(tz=ZoneInfo('Asia/Kolkata'))
        thread_date = self.time_format()
        yield Static(":two-thirty: {}".format(timeago.format(thread_date, now)))

    async def _on_click(self, _: events.Click) -> None:
        self.post_message(self.Selected(self))


class ArchiveApp(App):
    """Textual reader app to read Hyperkitty (GNU Mailman's official Archiver) email archives."""

    CSS_PATH = "archiver.css"
    BINDINGS = [
        ("a", "add_mailinglist", "Add MailingList"),
        ("d", "app.toggle_dark", "Toggle Dark mode"),
        ("s", "app.screenshot()", "Screenshot"),
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
        yield Header(id="header")
        yield Vertical(MailingLists(id="lists"), id="lists-view")
        yield LoadingIndicator()
        yield ListView(id="threads")
        yield Footer()

    def on_mount(self):
        self._hide_loading()

    def action_add_mailinglist(self):
        def get_lists(returns):
            lists, hk_server, = returns
            self.hk_server = hk_server
            for ml in lists:
                self.query_one(MailingLists).append(MailingList(ml))
        self.push_screen(MailingListAddScreen(), get_lists)

    # def action_focus_email(self, msgid):
    #     threads_view = self.query_one('#thread-emails', ListView)

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
            self.current_mailinglist = item.item
            self.update_threads(item.item.name)
        elif isinstance(item.item, Thread):
            self.push_screen(ThreadReadScreen(thread=item.item))

class MailingLists(ListView):
    """Represents the left side with Subscribed MailingLists."""

    def __init__(self, hk_server=None, *args, **kw):
        super().__init__(*args, **kw)
        self.hk_server = hk_server


class MailingList(ListItem):
    """Represents an item in the left sidebar with the MailingLists."""

    DEFAULT_CSS = """
    MailingList {
        padding: 1 1;
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


def main():
    app = ArchiveApp()
    app.run()
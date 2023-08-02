from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from textual.app import ComposeResult

import timeago
from rich.console import RenderableType
from textual import events, log
from textual.containers import ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Button,
    ListItem,
    ListView,
    Placeholder,
    SelectionList,
    Static,
)
from textual.widget import Widget


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


class ThreadReplies(Widget):

    has_new = reactive(0)
    count = reactive(0)

    def __init__(self, count, has_new, *args, **kw):
        super().__init__(*args, **kw)
        self.count = count
        self.has_new = has_new

    def render(self):
        return f':speech_balloon: {self.count} ({self.has_new})'


class ThreadItem(ListItem):
    """Represents a thread on the Main screen."""

    DEFAULT_CSS = """
    ThreadItem {
        height: 3;
        width: 1fr;
        layout: grid;
        grid-size: 3;
        grid-columns: 14fr 1fr 2fr;
        content-align: left middle;
        padding: 1 1;
    }

    .read {
        background: gray;
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

        def __init__(self, thread):
            self.thread = thread

            super().__init__()

    class Updated(Message):
        def __init__(self, thread_data):
            self.data = thread_data
            super().__init__()

    def __init__(self, *args, thread=None, mailinglist=None, **kw) -> None:
        super().__init__(*args, **kw)
        self.mailinglist = mailinglist
        # self.is_new = thread_data.get('is_new', False)
        # self.has_new = thread_data.get('has_new', 0)
        # self.read = thread_data.get('read', False)
        self.thread = thread
        if self.read:
            self.add_class('read')

    def get(self, attr):
        return getattr(self.thread, attr)

    @property
    def subject(self):
        return self.thread.subject

    def time_format(self):
        return self.thread.date_active

    # def watch_read(self, old, new):
    #     if old is False and new is True:
    #         self.add_class('read')
    #         # Regardless of the current value, just turn these two off since
    #         # they are not required anymore.
    #         self.is_new = False
    #         self.has_new = 0
    #         self.data['is_new'] = False
    #         self.data['has_new'] = 0
    #         self.data['read'] = True
    #         self.read = True
    #         log(f'Sending ThreadUpdated for {self}')
    #         self._notify_updated()
    #     self._save_read_status(new)

    def _notify_updated(self):
        self.post_message(self.Updated(self.thread))

    def _save_read_status(self, new):
        # Update the thread.read() status in the storage.
        # XXX(abraj): This is a relatively complex operation. The reason
        # for which is the fact that we are using a caching solution as a
        # trivial json database in a way that doesn't provide tons of data
        # access patterns that we want to have.
        # This can be solved easily with a local Sqlite database in future,
        # infact, the current caching solution utilizes sqlite underneath.
        pass

    # def watch_has_new(self, _, new):
    #     # It is possible that this is b
    #     try:
    #         self.query_one(ThreadReplies).has_new = new
    #     except Exception:
    #         log(f'Failed to Find & Update thread replies')

    def compose(self):
        yield Static(self.subject)
        yield ThreadReplies(
            count=self.thread.replies_count, has_new=self.has_new
        )
        # now = datetime.now(tz=ZoneInfo('Asia/Kolkata'))
        thread_date = self.time_format()
        yield Static(':two-thirty: {}'.format(self.get('date_active')))

    async def _on_click(self, _: events.Click) -> None:
        self.post_message(self.Selected(self))


class Threads(ListView):
    """Represents a listview with the threads listed."""


class MailingLists(ListView):
    """Represents the left side with Subscribed MailingLists."""


class MailingListItem(ListItem):
    """Represents an item in the left sidebar with the MailingLists."""

    DEFAULT_CSS = """
    MailingList {
        padding: 1 1;
    }
    """

    def __init__(self, mlist):
        if mlist is None:
            raise ValueError('Received None instead of MailingList.')
        self.mlist = mlist
        super().__init__()

    def render(self):
        return '{}\n{}'.format(self.get('display_name'), self.name)

    @property
    def name(self):
        return self.get('name')

    def get(self, key):
        return getattr(self.mlist, key)


class EmailItem(ListItem):
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
        padding: 2;
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

    def __init__(self, *args, email=None, **kw):
        super().__init__(*args, **kw)
        self.email = email

    def get(self, attr):
        return getattr(self.email, attr)

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

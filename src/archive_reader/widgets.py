from rich.console import RenderableType
from textual import events
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
        """Handle MailingList selected event.

        This will simply post a MailingListChoose.Selected message, which will
        be then handled by the handler in the ArchiveApp() to subscribe the
        lists chosen by the user.
        """
        if event.button.id == 'select_mailinglist':
            self.post_message(
                self.Selected(self.query_one(SelectionList).selected)
            )
            event.stop()


class ThreadReplies(Widget):
    """Represents total no. of messages in the Threads."""

    #: Represents if this thread has new messages since it was
    #: last opened. Currently this is un-used.
    has_new = reactive(0)
    #: Total no of replies in the thread.
    count = reactive(0)

    def __init__(self, count, has_new=0, *args, **kw):
        super().__init__(*args, **kw)
        self.count = count
        self.has_new = has_new

    def render(self):
        return f':speech_balloon: {self.count}'


class ThreadItem(ListItem):
    """Represents a thread on the Main screen."""

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
        """Represents an updated Event for the thread. This is sent
        out so that any handlers that exist can refresh the view.
        """

        def __init__(self, thread_data):
            self.data = thread_data
            super().__init__()

    def __init__(self, *args, thread=None, mailinglist=None, **kw) -> None:
        super().__init__(*args, **kw)
        self.mailinglist = mailinglist
        self.thread = thread
        if self.read:
            self.add_class('read')

    def get(self, attr):
        """Get the attribute of the owned Thread object."""
        return getattr(self.thread, attr)

    @property
    def subject(self):
        return self.thread.subject

    def time_format(self):
        """Return thread's active_time formatted properly to show in UI."""
        return self.thread.date_active

    def _notify_updated(self):
        """Sends out Message for thread's updated event."""
        self.post_message(self.Updated(self.thread))

    def compose(self):
        yield Static(self.subject)
        yield ThreadReplies(count=self.thread.replies_count)
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

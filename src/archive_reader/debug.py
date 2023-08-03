import os
from textual import log as textual_log


DEBUG = bool(os.getenv('ARCHIVE_DEV', False))


def log(value):
    """By default, the log doesn't do anything."""
    pass


if DEBUG:

    def log(value):
        """Log to dev console when in debug mode."""
        textual_log(value)

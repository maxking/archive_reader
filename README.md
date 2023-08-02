Archive Reader
==============

A terminal based archive reader for Hyperkitty, GNU Mailman's official archiver.

Screenshots
-----------

![Page Add Mailinglist](https://raw.githubusercontent.com/maxking/archive_reader/main/screenshots/page_subscribe_mailinglist.svg)

![Page View threads](https://raw.githubusercontent.com/maxking/archive_reader/main/screenshots/page_threads_list.svg)

![Page Read Thread](https://raw.githubusercontent.com/maxking/archive_reader/main/screenshots/page_read_thread.svg)

Using
-----

To run the app, you can install it using [Pipx](https://pypa.github.io/pipx/):

```bash
# Install using pipx.
$ pipx install areader

# Run the app:
$ areader
```

If you don't have Pipx, you can install directly in a venv to run:

```bash
# Setup a virtualenv to install the package.
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install areader

# Run the app:
$ areader
```

Hyperkitty Configuration
------------------------

In order to use this app, the Pagination on the Hyperkitty's API needs to be set correctly.

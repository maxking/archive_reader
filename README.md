Archive Reader
==============

A terminal based archive reader for Hyperkitty, GNU Mailman's official archiver.


Running
-------
To run the app, first you need to create a virtualenv and then finally install dependencies.

```bash
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
$ python archive_reader.py
```


Development
-----------

If you are developing, you want to install dev dependencies defined in `dev-requirements.txt`
as well.

```bash
$ source .venv/bin/activate
$ pip install -r dev-requirements.txt
$ textual run archive_reader.py
```
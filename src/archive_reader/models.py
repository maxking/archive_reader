import databases
import orm

databases = databases.Database('sqlite:///db.sqlite')
models = orm.ModelRegistry(database=databases)


async def initialize_database():
    await models.create_all()


class MailingList(orm.Model):
    tablename = 'mailinglist'
    registry = models
    fields = {
        'id': orm.Integer(primary_key=True),
        'url': orm.URL(max_length=1000),
        'name': orm.String(max_length=1000),
        'display_name': orm.String(max_length=1000),
        'description': orm.String(max_length=10000),
        'subject_prefix': orm.String(max_length=1000),
        'archive_policy': orm.String(max_length=1000),
        'created_at': orm.DateTime(),
        'threads': orm.URL(max_length=1000),
        'emails': orm.URL(max_length=1000),
    }


class Thread(orm.Model):
    tablename = 'thread'
    registry = models
    fields = {
        'id': orm.Integer(primary_key=True),
        'url': orm.URL(max_length=1000),
        'mailinglist': orm.URL(max_length=1000),
        'thread_id': orm.String(max_length=200),
        'subject': orm.String(max_length=1000),
        'date_active': orm.DateTime(),
        'starting_email': orm.URL(max_length=1000),
        'emails': orm.URL(max_length=1000),
        'votes_total': orm.Integer(),
        'replies_total': orm.Integer(),
        'next_thread': orm.URL(max_length=1000),
        'prev_thread': orm.URL(max_length=1000),
    }


class Sender(orm.Model):
    tablename = 'sender'
    registry = models
    fields = {
        'id': orm.Integer(primary_key=True),
        'address': orm.String(max_length=500),
        'mailman_id': orm.String(max_length=100),
        'emails': orm.URL(max_length=1000),
    }


class Email(orm.Model):
    tablename = 'email'
    registry = models
    fields = {
        'id': orm.Integer(primary_key=True),
        'url': orm.URL(max_length=1000),
        'mailinglist': orm.URL(max_length=1000),
        'message_id': orm.String(max_length=200),
        'message_id_hash': orm.String(max_length=200),
        'thread': orm.URL(max_length=1000),
        'sender_name': orm.String(max_length=500),
        'sender': orm.ForeignKey(Sender),
        'subject': orm.String(max_length=5000),
        'date': orm.DateTime(),
        'parent': orm.URL(max_length=1000),
    }

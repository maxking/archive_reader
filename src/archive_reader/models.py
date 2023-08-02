import databases
import orm
from sqlite3 import IntegrityError

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

    def __repr__(self):
        return f'<Mailinglist ({self.url.split("/")[-2]})>'


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
        'replies_count': orm.Integer(),
        'next_thread': orm.URL(max_length=1000, allow_null=True),
        'prev_thread': orm.URL(max_length=1000, allow_null=True),
    }


class Sender(orm.Model):
    tablename = 'sender'
    registry = models
    fields = {
        'id': orm.Integer(primary_key=True),
        'address': orm.String(max_length=500),
        'mailman_id': orm.String(max_length=100, unique=True),
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
        'parent': orm.URL(max_length=1000, allow_null=True),
        'content': orm.Text(),
    }


class EmailManager:
    """Manager class for constucting Email objects."""

    async def create(self, json_data):
        sender = json_data.get('sender')
        try:
            sender_obj = await Sender.objects.get_or_create(
                mailman_id=sender.get('mailman_id'), defaults=sender
            )
            sender_obj = sender_obj[0]
        except IntegrityError:
            # This means we somehow got into a race condition since multiple
            # get_or_create calls are running in async loops.
            sender_obj = await Sender.objects.get(
                mailman_id=sender.get('mailman_id'),
            )
        json_data['sender'] = sender_obj
        return await Email.objects.get_or_create(
            message_id_hash=json_data['message_id_hash'], defaults=json_data
        )

    get = Email.objects.get

    async def filter(self, *args, **kw):
        return await Email.objects.filter(*args, **kw).all()

from marshmallow import Schema, fields


class MailingListSchema(Schema):
    url = fields.URL()
    name = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    subject_prefix = fields.Str()
    archive_policy = fields.Str()
    created_at = fields.DateTime()
    threads = fields.URL()
    emails = fields.URL()


class MailingListPage(Schema):
    count = fields.Int()
    next = fields.Int()
    previous = fields.URL()
    results = fields.List(fields.Nested(MailingListSchema))


class ThreadSchema(Schema):
    url = fields.URL()
    mailinglist = fields.URL()
    thread_id = fields.Str()
    subject = fields.Str()
    date_active = fields.DateTime()
    starting_email = fields.URL()
    emails = fields.URL()
    votes_total = fields.Int()
    replies_count = fields.Int()
    next_thread = fields.URL()
    prev_thread = fields.URL()


class ThreadsPage(Schema):
    count = fields.Int()
    next = fields.Int()
    previous = fields.URL()
    results = fields.List(fields.Nested(ThreadSchema))


class SenderSchema(Schema):
    address = fields.Str()
    mailman_id = fields.Str()
    emails = fields.URL()

class EmailSchema(Schema):
    url = fields.URL()
    mailinglist = fields.URL()
    message_id = fields.Str()
    message_id_hash = fields.Str()
    thread = fields.URL()
    sender = fields.Nested(SenderSchema())
    sender_name = fields.Str()
    subject = fields.Str()
    date = fields.DateTime()
    parent = fields.URL()
    children = fields.List(fields.Nested(fields.URL))



class EmailsPage(Schema):
    count = fields.Int()
    next = fields.Int()
    previous = fields.URL()
    results = fields.List(fields.Nested(EmailSchema))
import mongoengine as me
from datetime import datetime
from uuid import uuid4


class Memory(me.Document):
    id = me.UUIDField(primary_key=True, default=uuid4)
    text = me.StringField(required=True)
    high_dim_embedding = me.ListField(
        me.FloatField()
    )  # Better for tasks requiring nuanced semantic understanding
    low_dim_embedding = me.ListField(
        me.FloatField()
    )  # Better for tasks requiring low latency
    created_at = me.DateTimeField(required=True)

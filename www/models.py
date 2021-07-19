# -*- coding: utf-8 -*-

import time

from orm import Model, StringField, BooleanField, IntegerField, FloatField, TextField

class User(Model):
    __table__ = 'user'

    id = IntegerField(primary_key=True, auto_increment=True)
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(default=time.time)

class Blog(Model):
    __table__ = 'blog'

    id = IntegerField(primary_key=True, auto_increment=True)
    user_id = IntegerField()
    user_name = StringField(ddl='varchar(50)')
    user_image =StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(50)')
    content = TextField()
    created_at = FloatField(default = time.time)

class Comment(Model):
    __table__='comment'

    id = IntegerField(primary_key=True, auto_increment=True)
    parent_id = IntegerField()
    blog_id = IntegerField()
    user_id = IntegerField()
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(50)')
    content = StringField(ddl="text")
    created_at = FloatField(default=time.time)
    is_deleted = IntegerField()
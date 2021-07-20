# -*- coding: utf-8 -*-

import asyncio
from datetime import date
from unittest.case import skip
import aiomysql
import logging
import unittest
from pymysql.err import OperationalError


logging.basicConfig(level=logging.INFO)

def log(sql, args =()):
    logging.info('SQL:%s, ARGS:%s' % (sql, args))

# SQL操作
__pool = None

async def create_pool(**kw):
    logging.info('Create database connection pool...')
    global __pool
    try:
        __pool = await aiomysql.create_pool(
            host=kw.get('host', 'localhost'),
            port=kw.get('port', 3306),
            user=kw['user'],
            password=kw['password'],
            db=kw['db'],
            auth_plugin='mysql_native_password',
            charset=kw.get('charset', 'utf8'),
            autocommit=kw.get('autocommit', True),
            maxsize=kw.get('maxsize', 10),
            minsize=kw.get('minsize', 1),
            loop= asyncio.get_event_loop()
        )
    except OperationalError as e:
        print('operational error {%s}' % e)
    return __pool

async def close_pool():
    logging.info('Close database connection pool...')
    global __pool
    __pool.close()
    await __pool.wait_closed()

async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    async with __pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?', '%s'), args or ())
            if size:
                # 获取指定数量记录
                rows = await cur.fetchmany(size)
            else:
                # 获取所有记录
                rows = await cur.fetchall()
            logging.info('Rows returned: %s' % len(rows))
            return rows

async def execute(sql, args):
    log(sql)
    async with __pool.acquire() as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            affected, lastid = cur.rowcount, cur.lastrowid
            await cur.close()
        except BaseException as e:
            raise
        return affected, lastid

# 类定义

def create_args_string(num):
    return ','.join(['?'] * num)

class Field(object):
    def __init__(self, name, column_type, primary_key, default): 
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s: %s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):
    def __init__(self,name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0, auto_increment=False):
        self.auto_increment = auto_increment
        super().__init__(name, 'bigint', primary_key, default)
    
    def __str__(self):
        return '<%s, %s: %s, auto_increment: %s>' %(self.__class__.__name__, self.column_type, self.name, self.auto_increment)

class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除Model类本身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)

        # 获取table名称
        table_name = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, table_name))
        # 获取所有的Field和主键名
        mappings = dict()
        fields = []
        primary_key = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s --> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键
                    if primary_key:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primary_key = k
                else:
                    fields.append(k)
        if not primary_key: 
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = table_name 
        attrs['__primary_key__'] = primary_key # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primary_key, ','.join(escaped_fields), table_name)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (table_name, ','.join(escaped_fields), primary_key, create_args_string(len(escaped_fields)+1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (table_name, ','.join(map(lambda f: '`%s`=?' %(mappings.get(f).name or f),fields)), primary_key)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (table_name, primary_key)
        return type.__new__(cls, name, bases, attrs)

class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kwargs):
        # ** 传入关键字参数
        super().__init__(**kwargs)
    
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"Model's object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def get_value(self, key):
        return getattr(self, key, None)

    def get_value_or_default(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def find_all(cls, where=None, args=None, **kwargs):
        """
        Find objects by `WHERE` clauss

        :param where:
        :param args:
        :param kwargs:
        :return:
        """
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        order_by = kwargs.get('order_by', None)
        if order_by:
            sql.append('order_by')
            sql.append(order_by)
        limit = kwargs.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?,?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rows = await select(' '.join(sql), args)
        return [cls(**row) for row in rows]

    @classmethod
    async def find_number(cls, select_field, where=None, args=None):
        """
        Find number by `SELECT` and `WHERE`

        :param select_field
        :param where:
        :param args:
        :return:
        """

        sql = ['select %s _num_ from %s' % (select_field, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rows = await select(' '.join(sql), args, 1)
        if len(rows) == 0:
            return None
        return rows[0]['_num_']

    @classmethod
    async def find(cls, primary_key):
        """
        Find Object by primary key

        :param primary_key:
        :return:
        """

        rows = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [primary_key], 1)
        if len(rows) == 0:
            return None
        return cls(**rows[0])

    async def save(self):
        args = list(map(self.get_value_or_default, self.__fields__))
        args.append(self.get_value_or_default(self.__primary_key__))
        rows, lastid = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('Failed to insert record: affected rows: %s' % rows)

        pkey = self.__mappings__[self.__primary_key__]
        if pkey is not None and isinstance(pkey, IntegerField) and pkey.auto_increment:
            self[self.__primary_key__] = lastid

        return lastid

    async def update(self):
        args = list(map(self.get_value_or_default, self.__fields__))
        args.append(self.get_value_or_default(self.__primary_key__))
        rows, _ = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('Failed to update by primary key: affected rows: %s' % rows)
        return rows

    async def remove(self):
        args = [self.get_value_or_default(self.__primary_key__)]
        print ('args: %s' % args)
        rows,_ = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('Failed to remove by primary key: affected rows %s' % rows)
        return rows

# --单元测试
class User(Model):
    __table__='user'

    id = IntegerField(primary_key=True, auto_increment=True)
    user_name = StringField(ddl='varchar(30)')
    nick_name = StringField(ddl='varchar(30)')
    email = StringField(ddl='varchar(50)')
    phone = StringField(ddl='varchar(20)')
    login_date =StringField(default=':01')

class TestORM(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        global pool
        pool = None

    async def asyncSetUp(self):
        print('creating pool...')
        global pool
        pool = await create_pool(user='root', password='root', db='blog')
        self.assertIsNotNone(pool)
        print('created pool done')

    async def asyncTearDown(self):
        print('closing pool...')
        pool.close()
        await pool.wait_closed()
        print('closed pool done.')

    @skip
    async def test_select(self):
        user = await User.find(1)
        self.assertEqual(1, user.id)
        print('find the user with <id:1>, and is: %s' % user)
        print("\n")
        self.assertEqual(1, user.id if user.id != 0 else user.id)

        c = await User.find_number('count(*)')
        print('the number of users is %d' % c)

        c = await User.find_number('count(*)', 'id=? and nick_name like ?', [1, '%ad%'])
        print('find the user <id:1> with nick name contain `ad` string, result: %d' % c)

        user_list = await User.find_all('dept_id=?', [2])
        print('all of user are: ')
        if len(user_list) == 0:
            print('None')
        for user in user_list:
            print('\t %s' % user)

    @skip
    async def test_get_value(self):
        user  = await User.find(1)
        self.assertIsNotNone(user)

        try:
            attr = user.unknow_attr
        except BaseException as e:
            self.assertTrue(isinstance(e, AttributeError))

    @skip
    async def test_get_value_or_default(self):
        user = await User.find(4)
        self.assertIsNotNone(user)
        login_date = user.get_value_or_default('login_date')
        print("the user' login_date default value:%s" % user.login_date)
        self.assertEqual(":01", user.login_date)


    @skip
    async def test_update(self):
        user = await User.find(1)
        self.assertIsNotNone(user)

        user.nick_name = 'John Halden Swift'
        affected = await user.update()
        print('update affected: %d' % affected)

        user2 = await User.find(1)
        self.assertEqual(user2.nick_name,user.nick_name)

    async def test_insert(self):
        exists = await User.find_number('count(*)', 'user_name=?', ['EzBella'])
        if exists == 0:
            user = User(
                user_name='EzBella',
                nick_name='ezb',
                email='71@qq.com'
            )
            lastid = await user.save()
            print(user)
            self.assertIsNotNone(lastid)
            self.assertEqual(lastid, user.id)

    @skip
    async def test_delete(self):
        user =await User.find(6)
        await user.remove()
    
    # @asyncio.coroutine
    def test_get(self):
        user = yield from User.find(1)
        print(user)

if __name__=='__main__':
    unittest.main()
    @asyncio.coroutine
    def go():
        pool = yield from create_pool(user='root', password='root', db='blog')
        user = yield from User.find(1)  
        print (user)
        pool.close()
        yield from pool.wait_closed()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(go())
    loop.close()

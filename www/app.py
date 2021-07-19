# -*- coding: utf-8 -*-

import logging, json, os, time
from aiohttp import web
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import orm
from coroweb import add_routes, add_static
from config import configs
from handlers import cookie2user, COOKIE_NAME

def init_jinja2(app: web.Application, **kw):
    logging.info('Init jinja2...')
    options = dict(
        autoescape = kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        # /www/templates
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
    logging.info('Set jinja2 template path: %s' % path)
    # Load templates from a directory in the file system
    env = Environment(loader=FileSystemLoader(path),**options)
    filters = kw.get('filters', None)
    if filters is not None:
        # Filters are python functions
        for name, f in filters.items():
            env.filters[name] =f
    app['__templating__'] = env

async def logger_factory(app: web.Application, handler):
    async def logger(request: web.Request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return await handler(request)
    return logger

async def auth_factory(app : web.Application, handler):
    async def auth(request : web.Request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s' % user.email)
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
                return web.HTTPFound('/signin')
        return await handler(request)
    return auth

async def data_factory(app : web.Application, handler):
    async def parse_data(request: web.Request):
        # JSON 数据格式
        if request.content_type.startswith('application/json'):
            # Read request body decoded as json
            request.__data__ = await request.json()
            logging.info('Request json: %s' % str(request.__data__))
        elif request.content_type.startswith('application/x-www-form-urlencoded'):
            # Read POST parameters from request body
            request.__data__ = await request.post()
            logging.info('Request form: %s' % str(request.__data__))
        return await handler(request)
    return parse_data

async def response_factory(app: web.Application, handler):
    async def response(request: web.Request):
        logging.info('Response handler...')
        r = await handler(request)
        # The base class for the HTTP response handling
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            # 二进制数据流
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            # HTML格式
            resp.content_type = 'text/html;charset=UTF-8'
            return resp

        # Response classes aredict like objects
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(
                    # ensure_ascii: if false then return value can contain non-ASCII characters
                    # __dict__: store an object’s (writable) attributes
                     # 序列化 r 为 json 字符串，default 把任意一个对象变成一个可序列为 JSON 的对象
                     body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8')
                )
                # JSON数据
                resp.content_type = 'application/json; charset=UTF-8'
                return resp
            else:
                r['__user__'] = request.__user__
                # app[__templating__] 是一个 Environment 对象，加载模板，渲染模板
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html; charset=UTF-8'
                return resp
        # Status code
        if isinstance(r, int) and 100 <= r < 600:
            return web.Response(status=r)
        # Status code and reason phrase
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and 100 <= t < 600:
                # 1xx: Informational - Request received, continuing process
                # ...
                return web.Response(status=t, reason=str(m))
        # Default
        resp = web.Response(body=str(r).encode('utf-8'))
        # 纯文本格式
        resp.content_type = 'text/plain; charset=UTF-8'
        return resp
    return response

def datetime_filter(t):
    delta =int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return '%s年%s月%s日' % (dt.year, dt.month, dt.day)

def format_timestamp(timestamp: float, fmt='%Y-%m-%d %H:%M:%S'):
    if timestamp <=0:
        return ''
    return datetime.fromtimestamp(timestamp).strftime(fmt)

async def init_db(app):
    await orm.create_pool(
        host=configs.db.host,
        port=configs.db.port,
        user=configs.db.user,
        password=configs.db.password,
        db=configs.db.database
    )

logging.basicConfig(level=logging.INFO)

app = web.Application(middlewares=[
    logger_factory,
    auth_factory,
    response_factory
])
init_jinja2(app, filters=dict(datetime=datetime_filter, formattime=format_timestamp))
add_routes(app, 'handlers')
add_static(app)
app.on_startup.append(init_db)
web.run_app(app, host='0.0.0.0', port=9000)
# -*- coding: utf-8 -*-

import functools, inspect ,logging , os, asyncio,unittest
from urllib import parse
from aiohttp import web

from exception import APIError

def get(path):
    '''
    Define decorator @get('/path')
    
    :param path:
    :return:
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

def post(path):
    """
    Define decorator @post('path')

    :param path:
    :return:
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

def get_required_kw_args(fn):
    """
    获取函数命名关键参数,且非默认参数

    :param fn: function
    :return:
    """
    args = []
    # 获取函数fn的参数, orderd mapping
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # *或者 *args 后面的参数, 且没有默认值
        if param.kind == param.KEYWORD_ONLY and param.default is param.empty:
            args.append(name)
    return tuple(args)

def get_named_kw_args(fn):
    """
    获取函数命名关键字参数

    :param fn: function
    :return:
    """

    args =[]
    # 获取函数fn的参数, orderd mapping
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # * 或者 *args 后面的参数
        if param.kind == param.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

def has_named_kw_args(fn):
    """
    判断是否有命名关键字参数

    :param fn: function
    :return:
    """
    # 获取函数fn的参数, ordered mapping
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # * 或者 *args 后面的参数
        if param.kind == param.KEYWORD_ONLY:
            return True

def has_var_kw_arg(fn):
    """
    判断是否有关键字参数
    
    :param fn: function
    :return:
    """
    # 
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # **args后面的参数
        if param.kind == param.VAR_KEYWORD:
            return True

def has_request_arg(fn):
    """
    判断是否有请求参数

    :param fn: function
    :return:
    """
    # 获取函数fn的签名
    sig = inspect.signature(fn)
    # 获取函数fn参数, ordered mapping
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind is not param.VAR_POSITIONAL and 
                            param.kind is not param.KEYWORD_ONLY and
                            param.kind is not param.VAR_KEYWORD):
            # fn(*args, **kwargs), fn.__name__, 
            raise ValueError(
                'Request parameter must be the last named parameter in function: %s%s' %(fn.__name__, str(sig))
            )
    return found

class RequestHandler(object):
    def __init__(self, app, fn):
        self.__app = app
        self.__func = fn
        self.__has_request_arg = has_request_arg(fn)
        self.__has_var_kw_arg = has_var_kw_arg(fn)
        self.__has_named_kw_args = has_named_kw_args(fn)
        self.__named_kw_args = get_named_kw_args(fn)
        self.__required_kw_args = get_required_kw_args(fn)

    # Make RequestHandler callable
    async def __call__(self, request : web.Request):
        kw = None
        if self.__has_var_kw_arg or self.__has_named_kw_args or self.__required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest(text='Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest(text='JSON body must be oject.')
                    kw=params
                elif ct.startswith('application/x-www-form-urlencode') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest(text='Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw=dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self.__has_var_kw_arg and self.__named_kw_args:
                # remove all unamed kw:
                copy = dict()
                for name in self.__named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check name arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self.__has_request_arg:
            kw['request'] = request
        # check required kw:
        if self.__required_kw_args:
            for name in self.__required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest(text='Missing argument:%s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = await self.__func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)

def add_static(app: web.Application):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('Add static %s => %s' % ('/static/', path))


def add_route(app: web.Application, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))

def add_routes(app: web.Application, module_name: str):
    n = module_name.rfind('.')
    if n == (-1):
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'): # 过滤掉私有方法
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn,'__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)

# 单元测试
class TestCoroweb(unittest.TestCase):
    def test_get(self):
        @get('/')
        def index():
            pass
        fn = index
        self.assertEqual(fn.__name__, 'index')
        self.assertEqual(fn.__method__, 'GET')
        self.assertEqual(fn.__route__, '/')

    def test_post(self):
        @post('/post')
        def store():
            pass
        fn = store
        self.assertEqual(fn.__name__, 'store')
        self.assertEqual(fn.__method__, 'POST')
        self.assertEqual(fn.__route__, '/post')

    def test_get_required_kw_args(self):
        def foo(*, name, age, sex='F', **kw):
            pass
        args = get_required_kw_args(foo)
        self.assertEqual(args, ('name', 'age'))
        self.assertTrue(has_var_kw_arg(foo))
    
    def test_get_named_kw_args(self):
        def foo(*, name, age, sex='F', score=60):
            pass
        args = get_named_kw_args(foo)
        self.assertEqual(args, ('name', 'age', 'sex', 'score'))
        self.assertTrue(has_named_kw_args(foo))

    def test_add_route(self):
        @get('/foo/{name}')
        async def foo_(name):
            pass
        app = web.Application()
        add_route(app, foo_)

if __name__=='__main__':
    unittest.main()

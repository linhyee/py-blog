# -*- coding: utf-8 -*-

' url handlers '

import time, hashlib, time, logging, json, re, io, os, random,sys

from aiohttp import web
from exception import APIResourceNotFoundError, APIValueError, APIError, APIPermissionError
from coroweb import get, post
from models import User, Blog, Comment
from config import configs
from page import Page, pagination
from PIL import Image
from orm import select
from datetime import datetime

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret
_NAKED_DIR = 'D:\sex'

def chack_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('permission deny')

def get_page_index(page_str):
    p= 1
    try:
        p=int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p =1
    return p

def text2html(text):
    lines = map(lambda s : '<p>%s<p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), 
        filter(lambda s : s.strip() != '', text.split('\n')))
    return ''.join(lines)

def user2cookie(user, max_age):
    """
    Generate cookie str by user.
    """
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (str(user.id), user.passwd, expires, _COOKIE_KEY)
    L = [str(user.id), expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

async def cookie2user(cookie_str):
    """
    Parse cookie and load user if cookie is valid
    """
    if not cookie_str:
        return None
    try:
        L= cookie_str.split('-')
        if len(L) != 3:
            return None
        id, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(id)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (str(user.id), user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None

async def get_blog_comments(blog_id):
    comments = await Comment.find_all('blog_id=?', [blog_id], orderBy='created_at desc')
    if comments is None or len(comments) == 0:
        return []
    for c in comments:
        c.html_content = text2html(c.content)
    def visit(data, pid = 0,level=0):
        for c in comments:
            if c.parent_id == pid:
                c.level = level
                data.append(c)
                visit(data, c.id, level+1)
        return data
    L = []
    for c in comments:
        if c.is_deleted == 1:
            c.html_content = '<s>该评论已被删除</s>'
        if c.parent_id == 0:
            c.replies = visit([], pid=c.id)
            L.append(c)
    return L

@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.find_number('count(id)')
    page = Page(num, page_index)
    if num ==0:
        blogs = []
    else:
        blogs =await Blog.find_all(orderBy='created_at desc', limit=(page.offset, page.limit))
        comments_count = await select(
            r'select `blog_id`, count(id) as `c` from `comment` where blog_id in %s group by blog_id',
            [[x.id for x in blogs]]
        )
        cc = {x['blog_id']: x['c'] for x in comments_count}
        for blog in blogs:
            blog.comments_count = cc.get(str(blog.id), 0)
        
    return {
        '__template__': 'index.html',
        'blogs': blogs,
        'pagination': pagination(page, '/', {})
    }

@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    blog.html_content= text2html(blog.content)
    return {
        '__template__': 'blog.html',
        'blog':blog,
        'comments': await get_blog_comments(id) 
    }

@get('/naked')
async def naked():
    md5 = hashlib.md5()
    md5.update("xyz".encode('utf-8'))
    return {
        '__template__': 'naked.html',
        'image_url': '/image/'+md5.hexdigest()
    }

def random_naked_image():
    if not os.path.isdir(_NAKED_DIR):
        return None
    def g():
        return (x for x in os.listdir(_NAKED_DIR) if os.path.isfile(_NAKED_DIR+'\\'+x))
    count = sum(1 for _ in g())
    if count == 0:
        return None
    elif count == 1:
        num = 1
    else:
        num = random.randint(0, count-1)
    
    i = 0
    name = None
    for v in g():
        if i == num:
            name = v
            break
        i = i + 1
    return name
    
# eg: 2021-07-15@path
naked_today = ''

@get('/image/{md5:[a-z0-9]{32}}')
async def naked_pic(md5):
    path = ''
    now = datetime.now().strftime(r'%Y-%m-%d')
    global naked_today
    if naked_today != '':
        splits = naked_today.split('@')
        if splits[0] == now:
            path = splits[-1]
    if path == '':
        name = random_naked_image()
        if name is None:
            base_dir = os.path.dirname(sys.argv[0])
            path = '.' if base_dir=='' else base_dir + r'/static/images/default.jpg'
        else:
            path = r'%s\%s' % ( _NAKED_DIR , random_naked_image())
            naked_today = r'%s@%s' % (now, path)

    image = Image.open(path)
    mime_type = image.get_format_mimetype()
    bytes = io.BytesIO()
    image.save(bytes, format=mime_type.split('/')[-1].upper())
    resp = web.Response(body=bytes.getvalue(), content_type=mime_type)
    return resp

@get('/signin')
async def signin(request):
    return {
        '__template__': 'signin.html',
    }

@get('/signout')
async def signout(request):
    refer = request.headers.get('Referer')
    r = web.HTTPFound(refer or '/')
    r.set_cookie(COOKIE_NAME, '-delete-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

@get('/register')
async def register():
    return {
        '__template__': 'register.html'
    }

@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.find_all('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exists.')
    user = users[0]
    # check passwd
    sha1 = hashlib.sha1()
    sha1.update(user.name.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticated ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

@get('/signout')
async def signout(request):
    referer = request.headers.get('Refer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

@get('/manage/blogs/create')
async def manage_create_blog():
    return {
        '__template__' : 'manage_blogs_form.html',
        'blog': Blog(id=0),
        'action': '/api/blogs'
    } 

@get('/manage/blogs/{id}')
async def manage_edit_blog(id):
    blog = await Blog.find(id)
    if blog is None:
        return web.HTTPNotFound(text="record not found")
    return {
        '__template__' : 'manage_blogs_form.html',
        'blog': blog,
        'action' : '/api/blogs/%s' % id
    }

@get('/manage/comments')
async def manage_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.find_number('count(id)')
    p = Page(num, page_index)
    if num ==0:
        comments = ()
    else:
        comments = await Comment.find_all( orderBy='created_at desc', limit=(p.offset, p.limit))
        if len(comments) > 0:
            blogs = await Blog.find_all('id in ?', [[x.blog_id for x in comments]])
            comment_blog = {x.id: x.name for x in blogs}
            for c in comments:
                c.blog_title = comment_blog.get(c.blog_id, "")
    return {
        '__template__': 'manage_comments.html',
        'pagination': pagination(p, '/manage/comments', {'Page': page}),
        'comments': comments
    }

@get('/manage/blogs')
async def manage_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.find_number('count(id)')
    p = Page(num, page_index)
    if num == 0:
        blogs = ()
    else:
        blogs = await Blog.find_all(orderBy='created_at desc', limit=(p.offset, p.limit))
    return {
        '__template__': 'manage_blogs.html',
        'pagination': pagination(p, '/manage/blogs', {'page': page}),
        'blogs': blogs
    }

@get('/manage/users')
async def manage_users(*,page='1'):
    page_index = get_page_index(page)
    num = await User.find_number('count(id)')
    p = Page(num,page_index)
    if num == 0:
        users = ()
    else:
        users = await User.find_all(orderBy='created_at desc', limit=(p.offset, p.limit))
    return {
        '__template__': 'manage_users.html',
        'pagination':pagination(p, '/manage/users', {'page': page}),
        'users':users
    }

@post('/api/blog/{id}/comments')
async def api_create_comment(id, request, *, parent_id, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(
        blog_id=blog.id,
        user_id=user.id,
        user_name=user.name,
        user_image=user.image,
        content=content
    )
    if int(parent_id) > 0:
        parent = await Comment.find(parent_id)
        if parent is None:
            raise APIResourceNotFoundError('Reply to')
        comment.parent_id = parent.id
    await comment.save()
    return comment

@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    chack_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    # await c.remove()
    c.is_deleted = 1
    await c.update()
    return dict(id=id)

@get('/api/user/{id}/delete')
async def api_user_delete(request, *, id):
    chack_admin(request)
    try:
        id = int(id)
    except ValueError as e:
        return e
    user = await User.find(id)
    if user is None:
        raise APIValueError(message='record not found')
    await user.remove()
    return dict(id=id)

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

@post('/api/register')
async def register_user(*, email, name: str, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.find_all('email=?', [email])
    if len(users) >0:
        raise APIError('register:failed', 'email','邮箱已被注册.')
    sha1_passwd = '%s:%s' %(name, passwd)
    user = User(
        name=name.strip(), 
        email=email,
        passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
        image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest()
    )
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd='******'
    r.content_type ='application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    chack_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    # if not summary or not summary.strip():
    #     raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(
        user_id=request.__user__.id, 
        user_name=request.__user__.name, 
        user_image=request.__user__.image, 
        name=name.strip(),
        summary=summary.strip(),
        content=content.strip()
    )
    await blog.save()
    return blog

@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary,content):
    chack_admin(request)
    blog = await Blog.find(id)
    if blog is None:
        raise APIError(message='record not found.')
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog.name = name
    blog.summary = summary
    blog.content = content
    await blog.update()
    return blog

@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    chack_admin(request)
    blog = await Blog.find(id)
    if blog is None:
        raise APIError(message='record not found.')
    await blog.remove()
    return dict(id=id)

@post('/api/blogs/delete')
async def api_delete_blogs(request, *, id):
    chack_admin(request)
    if id is None or len(id)==0:
        raise APIValueError('id', 'id cannot be empty.')
    
    for i in id:
        blog = await Blog.find(i)
        if blog is not None:
            await blog.remove()
    return dict(id=id)
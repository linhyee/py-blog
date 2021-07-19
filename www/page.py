# -*- coding: utf-8 -*-

"""
JSON API definition.
"""

import math
from urllib import parse


class Page(object):
    '''
    Page object for display pages.
    '''
    def __init__(self, item_count, page_index=1,page_size=10):
        '''
        Init Pagination by item count, page_index and page_size
        >>> p1 =Page(100, 1)
        >>> p1.page_count
        10
        >>> p1.offset
        0
        >>> p1.limit
        10
        >>> p2 = Page(90, 9, 10)
        >>> p2.page_count
        9
        >>> p2.offset
        80
        >>> p2.limit
        10
        >>> p3 = Page(91,10, 10)
        >>> p3.page_count
        10
        >>> p3.offset
        90
        >>> p3.limit
        10
        '''
        self.item_count = item_count
        self.page_size = page_size
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)
        if (item_count == 0) or (page_index > self.page_count):
            self.offset = 0
            self.limit = 0
            self.page_index = 0
        else:
            self.page_index = page_index
            self.offset = self.page_size * (page_index - 1)
            self.limit = self.page_size
        self.has_next = self.page_index < self.page_count
        self.has_previous = self.page_index > 1

    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % (
            self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)
    
    __repr__ = __str__


def pagination(page : Page, base_url, query={}):
    if page.page_count == 0:
        return ''
    s = '<ul class="uk-pagination uk-flex-center" uk-margin>'
    if page.has_previous:
        previous = page.page_index - 1
        if previous <= 0:
            previous = 1
        query['page'] = page.page_index-1 if page.page_index > 1 else 0
        s += '<li><a href="%s?%s"><span uk-pagination-previous></span></a></li>' % (base_url, parse.urlencode(query))

    count = 5
    if count > page.page_count:
        count = page.page_count
    page_start = (math.ceil(page.page_index / count) - 1) * count + 1
    for i in range(page_start, page_start +count):
        if i > page.page_count:
            break

        if i == page.page_index:
            s += '<li class="uk-active"><span>%d</span></li>' % page.page_index
        else:
            query['page'] = i
            s += '<li><a href="%s?%s">%d</a>' % (base_url, parse.urlencode(query), i)

    if page.has_next:
        next = page.page_index + 1
        if next > page.page_count:
            next =page.page_count
        query['page'] = next
        s += '<li><a href="%s?%s"><span uk-pagination-next></span></a></li>' % (base_url, parse.urlencode(query))
    return s

if __name__ == '__main__':
    import doctest
    doctest.testmod()
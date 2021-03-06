# -*- coding: utf-8 -*-
"""
    jinja2htmlpretty
    ~~~~~~~~~~~~~~~~~~

    A Jinja2 extension that pretty prints html at template
    compilation time without extra overhead.

    :copyright: (c) 2016 by Vitaly Kezlya.
    :license: BSD, see LICENSE for more details.
"""
import re
from jinja2.ext import Extension
from jinja2.lexer import Token, describe_token
from jinja2 import TemplateSyntaxError


_tag_re = re.compile(r'(?:<(/?)([a-zA-Z0-9_-]+)\s*|(\s*>\s*))(?s)')
_ws_normalize_re = re.compile(r'[ \t\r\n]+')

_ws_around_equal_re = re.compile(r'[ \t\r\n]*=[ \t\r\n]*')
_ws_open_bracket_re = re.compile(r'[ \t\r\n]*<[ \t\r\n]*')
_ws_open_bracket_slash_re = re.compile(r'[ \t\r\n]*<[ \t\r\n]*/[ \t\r\n]*')
_ws_close_bracket_re = re.compile(r'[ \t\r\n]*>[ \t\r\n]*')
_ws_close_bracket_slash_re = re.compile(r'[ \t\r\n]*/[ \t\r\n]*>[ \t\r\n]*')


class StreamProcessContext(object):

    def __init__(self, stream):
        self.stream = stream
        self.token = None
        self.stack = []

    def fail(self, message):
        raise TemplateSyntaxError(message, self.token.lineno,
                                  self.stream.name, self.stream.filename)


def _make_dict_from_listing(listing):
    rv = {}
    for keys, value in listing:
        for key in keys:
            rv[key] = value
    return rv


class HTMLPretty(Extension):
    isolated_elements = set(['script', 'style', 'noscript', 'textarea'])
    void_elements = set(['br', 'img', 'area', 'hr', 'param', 'input',
                         'embed', 'col', 'meta', 'link', 'path'])
    block_elements = set(['div', 'p', 'form', 'ul', 'ol', 'li', 'table', 'tr',
                          'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'dl',
                          'dt', 'dd', 'blockquote', 'h1', 'h2', 'h3', 'h4',
                          'h5', 'h6', 'pre'])
    #TODO this called on each page, need to extract outside of class
    breaking_rules = _make_dict_from_listing([
        (['p'], set(['#block'])),
        (['li'], set(['li'])),
        (['td', 'th'], set(['td', 'th', 'tr', 'tbody', 'thead', 'tfoot'])),
        (['tr'], set(['tr', 'tbody', 'thead', 'tfoot'])),
        (['thead', 'tbody', 'tfoot'], set(['thead', 'tbody', 'tfoot'])),
        (['dd', 'dt'], set(['dl', 'dt', 'dd']))
    ])

    last_tag = ''
    depth = 0
    just_closed = False

    def is_isolated(self, stack):
        for tag in reversed(stack):
            if tag in self.isolated_elements:
                return True
        return False

    def is_breaking(self, tag, other_tag):
        breaking = self.breaking_rules.get(other_tag)
        return breaking and (tag in breaking or
            ('#block' in breaking and tag in self.block_elements))

    def enter_tag(self, tag, ctx):
        while ctx.stack and self.is_breaking(tag, ctx.stack[-1]):
            self.leave_tag(ctx.stack[-1], ctx)
        if tag not in self.void_elements:
            ctx.stack.append(tag)
            self.last_tag = tag
            self.depth += 1
            self.just_closed = False

    def leave_tag(self, tag, ctx):
        if not ctx.stack:
            ctx.fail('Tried to leave "%s" but something closed '
                     'it already' % tag)
        if tag == ctx.stack[-1]:
            ctx.stack.pop()
            return
        for idx, other_tag in enumerate(reversed(ctx.stack)):
            if other_tag == tag:
                for num in xrange(idx + 1):
                    ctx.stack.pop()
            elif not self.breaking_rules.get(other_tag):
                break

    def normalize(self, ctx):
        pos = 0
        buffer = []
        def write_data(value):
            if not self.is_isolated(ctx.stack):
                value = _ws_open_bracket_re.sub('<', value)
                value = _ws_open_bracket_slash_re.sub('</', value)
                value = _ws_close_bracket_re.sub('>', value)
                value = _ws_close_bracket_slash_re.sub('/>', value)
                value = _ws_around_equal_re.sub('=', value)
                value = _ws_normalize_re.sub(' ', value)
            buffer.append(value)

        for match in _tag_re.finditer(ctx.token.value):
            closes, tag, sole = match.groups()
            preamble = ctx.token.value[pos:match.start()]
            write_data(preamble)
            if sole:
                write_data(sole)
            else:


                v = match.group()
                v = _ws_normalize_re.sub(' ', v)
                if v.startswith("</"):
                    self.depth -= 1
                    if tag != self.last_tag or self.just_closed:

                        buffer.append(u'\n')
                        [buffer.append(u'  ') for _ in xrange(self.depth)]
                    else:
                        self.just_closed = True

                elif v.startswith("<") and pos > 0:
                    buffer.append(u'\n')
                    [buffer.append(u'  ') for _ in xrange(self.depth)]




                buffer.append(v)
                (closes and self.leave_tag or self.enter_tag)(tag, ctx)
            pos = match.end()

        write_data(ctx.token.value[pos:])
        return u''.join(buffer)

    def filter_stream(self, stream):
        ctx = StreamProcessContext(stream)
        for token in stream:
            if token.type != 'data':
                yield token
                continue
            ctx.token = token
            value = self.normalize(ctx)
            yield Token(token.lineno, 'data', value)

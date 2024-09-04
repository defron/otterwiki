#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set et ts=8 sts=4 sw=4 ai:

import re

from mistune.inline_parser import LINK_LABEL
from mistune.util import unikey, ESCAPE_TEXT

__all__ = ['plugin_task_lists', 'plugin_footnotes']


class mistunePluginFootnotes:
    """
    mistune footnote plugin

    fixed to match bitnotes like[^bignote]

    [^bignote]: Here's one with multiple paragraphs and code.

        Indent paragraphs to include them in the footnote.

        `{ my code }`

        Add as many paragraphs as you like.
    """

    #: inline footnote syntax looks like::
    #:
    #:    [^key]
    INLINE_FOOTNOTE_PATTERN = r'\[\^(' + LINK_LABEL + r')\]'

    #: define a footnote item like::
    #:
    #:    [^key]: paragraph text to describe the note
    DEF_FOOTNOTE = re.compile(
        r'( {0,3})\[\^(' + LINK_LABEL + r')\]:[ \t]*('
        r'[^\n]*\n+'
        r'(?:\1 {1,4}(?! )[^\n]*\n*)*'
        r')'
    )

    def _letter_from_index(self, num):
        """
        1->a, 2->b, 26->z, 27->aa, 28->ab, 54->bb
        """

        num2alphadict = dict(zip(range(1, 27), 'abcdefghijklmnopqrstuvwxyz'))
        outval = ""
        numloops = (num - 1) // 26

        if numloops > 0:
            outval = outval + self._letter_from_index(numloops)

        remainder = num % 26
        if remainder > 0:
            outval = outval + num2alphadict[remainder]
        else:
            outval = outval + "z"
        return outval

    def parse_inline_footnote(self, inline, m, state):
        key = unikey(m.group(1))
        def_footnotes = state.get('def_footnotes')
        if not def_footnotes or key not in def_footnotes:
            return 'text', m.group(0)

        index = state.get('footnote_index', 0)
        index += 1
        state['footnote_index'] = index
        state['footnotes'].append(key)
        # footnote number
        fn = list(state['def_footnotes'].keys()).index(key) + 1
        return 'footnote_ref', key, fn, index

    def parse_def_footnote(self, block, m, state):
        key = unikey(m.group(2))
        if key not in state['def_footnotes']:
            state['def_footnotes'][key] = m.group(3)

    def parse_footnote_item(self, block, k, refs, state):
        def_footnotes = state['def_footnotes']
        text = def_footnotes[k]
        stripped_text = text.strip()
        if '\n' not in stripped_text:
            children = [{'type': 'paragraph', 'text': stripped_text}]
        else:
            lines = text.splitlines()
            second_line = ""
            for second_line in lines[1:]:
                if second_line:
                    break
            spaces = len(second_line) - len(second_line.lstrip())
            pattern = re.compile(r'^ {' + str(spaces) + r',}', flags=re.M)
            text = pattern.sub('', text)
            children = block.parse_text(text, state)
            if not isinstance(children, list):
                children = [children]

        return {
            'type': 'footnote_item',
            'children': children,
            'params': (k, refs),
        }

    def md_footnotes_hook(self, md, result, state):
        footnotes = state.get('footnotes')
        if not footnotes:
            return result

        children = []
        for k in state.get('def_footnotes'):
            refs = [i + 1 for i, j in enumerate(footnotes) if j == k]
            children.append(self.parse_footnote_item(md.block, k, refs, state))

        tokens = [{'type': 'footnotes', 'children': children}]
        output = md.block.render(tokens, md.inline, state)
        return result + output

    def render_html_footnote_ref(self, key, index, fn):
        i = str(index)
        html = '<sup class="footnote-ref" id="fnref-' + i + '">'
        return html + '<a href="#fn-' + str(i) + '">' + str(i) + '</a></sup>'

    def render_html_footnotes(self, text):
        return (
            '<hr/><section class="footnotes">\n<ol>\n'
            + text
            + '</ol>\n</section>\n'
        )

    def render_html_footnote_item(self, text, key, refs):
        if len(refs) == 1:
            back = (
                '<a href="#fnref-'
                + str(refs[0])
                + '" class="footnote"><i class="fas fa-long-arrow-alt-up"></i></a> '
            )
        else:
            ref_list = []
            for i, r in enumerate(refs):
                letter = self._letter_from_index(i + 1)
                ref_list.append(
                    f'<a href="#fnref-{r}" class="footnote">{letter}</a>'
                )
            back = (
                '<i class="fas fa-long-arrow-alt-up"></i> '
                + ', '.join(ref_list)
                + ' '
            )

        text = text.rstrip()
        if text.startswith('<p>'):
            text = '<p>' + back + text[3:]
        else:
            text = back + text
        return '<li id="fn-' + str(key) + '">' + text + '</li>\n'

    def __call__(self, md):
        md.inline.register_rule(
            'footnote',
            self.INLINE_FOOTNOTE_PATTERN,
            self.parse_inline_footnote,
        )
        index = md.inline.rules.index('std_link')
        if index != -1:
            md.inline.rules.insert(index, 'footnote')
        else:
            md.inline.rules.append('footnote')

        md.block.register_rule(
            'def_footnote', self.DEF_FOOTNOTE, self.parse_def_footnote
        )
        index = md.block.rules.index('def_link')
        if index != -1:
            md.block.rules.insert(index, 'def_footnote')
        else:
            md.block.rules.append('def_footnote')

        if md.renderer.NAME == 'html':
            md.renderer.register('footnote_ref', self.render_html_footnote_ref)
            md.renderer.register(
                'footnote_item', self.render_html_footnote_item
            )
            md.renderer.register('footnotes', self.render_html_footnotes)

        md.after_render_hooks.append(self.md_footnotes_hook)


class mistunePluginTaskLists:
    """
    Rewrote plugin_task_lists from mistune/plugins/task_lists.py
    """

    TASK_LIST_ITEM = re.compile(r'^(\[[ xX]\])\s+')

    def task_lists_hook(self, md, tokens, state):
        return self._rewrite_all_list_items(tokens)

    def render_ast_task_list_item(self, children, level, checked):
        return {
            'type': 'task_list_item',
            'children': children,
            'level': level,
            'checked': checked,
        }

    def render_html_task_list_item(self, text, level, checked):
        checkbox = '<input class="task-list-item-checkbox" ' 'type="checkbox" '
        if checked:
            checkbox += ' checked/>'
        else:
            checkbox += '/>'

        if text.startswith('<p>'):
            text = text.replace('<p>', '<p>' + checkbox, 1)
        else:
            text = checkbox + text

        return '<li class="task-list-item">' + text + '</li>\n'

    def __call__(self, md):
        md.before_render_hooks.append(self.task_lists_hook)

        if md.renderer.NAME == 'html':
            md.renderer.register(
                'task_list_item', self.render_html_task_list_item
            )
        elif md.renderer.NAME == 'ast':
            md.renderer.register(
                'task_list_item', self.render_ast_task_list_item
            )

    def _rewrite_all_list_items(self, tokens):
        for tok in tokens:
            if tok['type'] == 'list_item':
                self._rewrite_list_item(tok)
            if 'children' in tok.keys():
                self._rewrite_all_list_items(tok['children'])
        return tokens

    def _rewrite_list_item(self, item):
        children = item['children']
        if children:
            first_child = children[0]
            text = first_child.get('text', '')
            m = self.TASK_LIST_ITEM.match(text)
            if m:
                mark = m.group(1)
                first_child['text'] = text[m.end() :]

                params = item['params']
                if mark == '[ ]':
                    params = (params[0], False)
                else:
                    params = (params[0], True)

                item['type'] = 'task_list_item'
                item['params'] = params


class mistunePluginMark:
    #: mark syntax looks like: ``==word==``
    MARK_PATTERN = (
        r'==(?=[^\s=])(' r'(?:\\=|[^=])*' r'(?:' + ESCAPE_TEXT + r'|[^\s=]))=='
    )

    def parse_mark(self, inline, m, state):
        text = m.group(1)
        return 'mark', inline.render(text, state)

    def render_html_mark(self, text):
        return '<mark>' + text + '</mark>'

    def __call__(self, md):
        md.inline.register_rule('mark', self.MARK_PATTERN, self.parse_mark)

        index = md.inline.rules.index('codespan')
        if index != -1:
            md.inline.rules.insert(index + 1, 'mark')
        else:  # pragma: no cover
            md.inline.rules.append('mark')

        if md.renderer.NAME == 'html':
            md.renderer.register('mark', self.render_html_mark)


class mistunePluginFancyBlocks:
    """
    ::: info
    :::
    """

    FANCY_BLOCK = re.compile(
        r'( {0,3})(\:{3,}|~{3,})([^\:\n]*)\n'
        r'(?:|([\s\S]*?)\n)'
        r'(?: {0,3}\2[~\:]* *\n+|$)'
    )
    FANCY_BLOCK_HEADER = re.compile(r'^#{1,5}\s*(.*)\n+')

    def parse_fancy_block(self, block, m, state):
        # get text and the newline that has been eaten up
        text = m.group(4) or "" + "\n"
        family = m.group(3).strip().lower()

        # find (and remove) the header from the text block
        header = self.FANCY_BLOCK_HEADER.match(text)
        if header is not None:
            header = header.group(1)
            text = self.FANCY_BLOCK_HEADER.sub('', text, 1)

        # parse the text inside the block, remove headings from the rules
        # -- we dont wont them in the toc so these are handled extra
        rules = list(block.rules)
        rules.remove('axt_heading')
        rules.remove('setex_heading')

        children = block.parse(text, state, rules)
        if not isinstance(children, list):
            children = [children]

        return {
            "type": "fancy_block",
            "params": (family, header),
            "text": text,
            "children": children,
        }

    def render_html_fancy_block(self, text, family, header):
        if family in ["info", "blue"]:
            cls = "alert alert-primary"
        elif family in ["warning", "yellow"]:
            cls = "alert alert-secondary"
        elif family in ["danger", "red"]:
            cls = "alert alert-danger"
        elif family in ["success", "green"]:
            cls = "alert alert-success"
        elif family in ["none", "empty"]:
            cls = "alert"
        else:
            cls = "alert"
        if header is not None:
            header = f'<h4 class="alert-heading">{header}</h4>'
        else:
            header = ""
        text = text.strip()
        return (
            f'<div class="{cls} mb-20" role="alert">{header}\n{text}</div>\n'
        )

    def __call__(self, md):
        md.block.register_rule(
            'fancy_block', self.FANCY_BLOCK, self.parse_fancy_block
        )

        md.block.rules.append('fancy_block')

        if md.renderer.NAME == "html":
            md.renderer.register("fancy_block", self.render_html_fancy_block)


class mistunePluginSpoiler:
    SPOILER_LEADING = re.compile(r'^ *\>\!', flags=re.MULTILINE)
    SPOILER_BLOCK = re.compile(r'(?: {0,3}>![^\n]*(\n|$))+')

    def parse_spoiler_block(self, block, m, state):
        text = m.group(0)

        # we are searching for the complete bock, so we have to remove
        # the syntax >!
        text = self.SPOILER_LEADING.sub('', text)

        text = text.strip()

        children = block.parse(text, state)
        if not isinstance(children, list):
            children = [children]

        return {
            "type": "spoiler_block",
            "text": text,
            "children": children,
        }

    def render_html_spoiler_block(self, text):
        text = text.strip()
        if text.startswith('<p>'):
            text = text[3:]
        if text.endswith('</p>'):
            text = text[:-4]
        return f'<div class="spoiler">\n  <button class="spoiler-button" onclick="otterwiki.toggle_spoiler(this)"><i class="far fa-eye"></i></button>\n  <p>{text}</p>\n</div>\n\n'

    def __call__(self, md):
        md.block.register_rule(
            'spoiler_block', self.SPOILER_BLOCK, self.parse_spoiler_block
        )

        index = md.block.rules.index('block_quote')
        if index != -1:
            md.block.rules.insert(index, 'spoiler_block')
        else:
            md.block.rules.append('spoiler_block')

        if md.renderer.NAME == "html":
            md.renderer.register(
                "spoiler_block", self.render_html_spoiler_block
            )


class mistunePluginFold:
    FOLD_LEADING = re.compile(r'^ *\>\|', flags=re.MULTILINE)
    FOLD_BLOCK = re.compile(r'(?: {0,3}>\|[^\n]*(\n|$))+')

    FOLD_BLOCK_HEADER = re.compile(r'^#{1,5}\s*(.*)\n+')

    def parse_fold_block(self, block, m, state):
        text = m.group(0)

        # we are searching for the complete bock, so we have to remove
        # the syntax >|
        text = self.FOLD_LEADING.sub('', text).strip()

        # find (and remove) the header from the text block
        header = self.FOLD_BLOCK_HEADER.match(text)
        if header is not None:
            header = header.group(1)
            text = self.FOLD_BLOCK_HEADER.sub('', text, 1)

        # clean up trailing spaces
        text = "\n".join([x.rstrip() for x in text.strip().splitlines()])

        children = block.parse(text, state)
        if not isinstance(children, list):
            children = [children]

        return {
            "type": "fold_block",
            "text": text,
            "children": children,
            "params": (header,),
        }

    def render_html_fold_block(self, text, header=None):
        text = text.strip()
        if text.startswith('<p>'):
            text = text[3:]
        if text.endswith('</p>'):
            text = text[:-4]
        if header is None:
            header = "..."
        return f'''<details class="collapse-panel">
<summary class="collapse-header">
{header}
</summary>
<div class="collapse-content"><p>{text}</p></div></details>'''

    def __call__(self, md):
        md.block.register_rule(
            'fold_block', self.FOLD_BLOCK, self.parse_fold_block
        )

        index = md.block.rules.index('block_quote')
        if index != -1:
            md.block.rules.insert(index, 'fold_block')
        else:
            md.block.rules.append('fold_block')

        if md.renderer.NAME == "html":
            md.renderer.register("fold_block", self.render_html_fold_block)


class mistunePluginMath:
    # too aggressive
    # MATH_BLOCK = re.compile(r'(\${1,2})((?:\\.|[\s\S])*)\1')
    # MATH_BLOCK = re.compile(r'\${1,2}[^]*?[^\\]\${1,2}')
    MATH_BLOCK = re.compile(r'(\${2})((?:\\.|.)*)\${2}')
    MATH_INLINE_PATTERN = (
        r'\$(?=[^\s\$])(' r'(?:\\\$|[^\$])*' r'(?:' + ESCAPE_TEXT + r'|[^\s\$]))\$'
    )
    def parse_block(self, block, m, state):
        text = m.group(2)
        return {
            "type": "math_block",
            "text": text,
        }

    def render_html_block(self, text):
        return f'''\n\\[{text}\\]\n'''

    def parse_inline(self, inline, m, state):
        text = m.group(1)
        return 'math_inline', text

    def render_html_inline(self, text):
        return '\\(' + text + '\\)'

    def __call__(self, md):
        md.block.register_rule(
            'math_block', self.MATH_BLOCK, self.parse_block
        )
        md.inline.register_rule('math_inline', self.MATH_INLINE_PATTERN, self.parse_inline)

        md.block.rules.append('math_block')
        md.inline.rules.append('math_inline')

        if md.renderer.NAME == "html":
            md.renderer.register("math_block", self.render_html_block)
            md.renderer.register('math_inline', self.render_html_inline)


plugin_task_lists = mistunePluginTaskLists()
plugin_footnotes = mistunePluginFootnotes()
plugin_mark = mistunePluginMark()
plugin_fancy_blocks = mistunePluginFancyBlocks()
plugin_spoiler = mistunePluginSpoiler()
plugin_fold = mistunePluginFold()
plugin_math = mistunePluginMath()

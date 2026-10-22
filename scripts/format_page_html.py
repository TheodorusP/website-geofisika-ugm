"""Indent page HTML without splitting mixed inline text or rewriting entities."""
from html.parser import HTMLParser


class Element:
    def __init__(self, tag='', opening=''):
        self.tag, self.opening, self.children = tag, opening, []


class PageParser(HTMLParser):
    void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = Element()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Element(tag, self.get_starttag_text())
        self.stack[-1].children.append(node)
        if tag not in self.void:
            self.stack.append(node)

    def handle_endtag(self, tag):
        assert self.stack[-1].tag == tag, tag
        self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_entityref(self, name):
        self.handle_data('&' + name + ';')

    def handle_charref(self, name):
        self.handle_data('&#' + name + ';')

    def handle_decl(self, decl):
        self.handle_data('<!' + decl + '>')

    def handle_comment(self, data):
        self.handle_data('<!--' + data + '-->')


def format_html(source):
    parser = PageParser()
    parser.feed(source)
    assert len(parser.stack) == 1
    inline = {'a', 'b', 'strong', 'em', 'i', 'span', 'small', 'br', 'img',
              'code', 'sup', 'sub', 'abbr'}

    def raw(node):
        if isinstance(node, str):
            return node
        return node.opening + ''.join(raw(c) for c in node.children) + (
            '' if node.tag in parser.void else '</' + node.tag + '>')

    def render(node, depth):
        indent = '  ' * depth
        if isinstance(node, str):
            return indent + node.strip() if node.strip() else ''
        children = [c for c in node.children if not isinstance(c, str) or c.strip()]
        containers = {'html', 'head', 'body', 'main', 'section', 'div', 'nav',
                      'ol', 'ul', 'details', 'header', 'footer'}
        if node.tag in parser.void or (node.tag not in containers and all(
                isinstance(c, str) or c.tag in inline for c in children)):
            return indent + raw(node).strip()
        lines = [indent + node.opening]
        lines.extend(render(c, depth + 1) for c in children)
        lines.append(indent + '</' + node.tag + '>')
        return '\n'.join(line for line in lines if line)

    return '\n'.join(render(c, 0) for c in parser.root.children
                     if not isinstance(c, str) or c.strip()) + '\n'

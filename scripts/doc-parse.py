#!/usr/bin/env python3
"""NIRVANA doc-parser: HTML -> clean markdown-ish text (stdlib only, no deps).
Usage: doc-parse.py <in.html> <out.md>"""
import html.parser, re, sys

class MD(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.skip = 0
        self.pre = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'nav', 'footer', 'header'):
            self.skip += 1
        elif tag == 'pre':
            self.pre += 1
            self.out.append('\n```\n')
        elif tag in ('h1',): self.out.append('\n# ')
        elif tag in ('h2',): self.out.append('\n## ')
        elif tag in ('h3',): self.out.append('\n### ')
        elif tag in ('h4',): self.out.append('\n#### ')
        elif tag in ('p', 'div', 'li', 'tr', 'section', 'table'): self.out.append('\n')
        elif tag == 'br': self.out.append('\n')
        elif tag == 'td': self.out.append(' | ')
        elif tag in ('code',) and not self.pre: self.out.append('`')
        elif tag == 'img':
            src = a.get('src', '')
            self.out.append(f'[IMG:{src}]')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer', 'header'):
            self.skip = max(0, self.skip - 1)
        elif tag == 'pre':
            self.pre = max(0, self.pre - 1)
            self.out.append('\n```\n')
        elif tag in ('code',) and not self.pre:
            self.out.append('`')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'p', 'li', 'tr'):
            self.out.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

def convert(path):
    p = MD()
    p.feed(open(path, encoding='utf-8', errors='replace').read())
    text = ''.join(p.out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    return text

if __name__ == '__main__':
    out = convert(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        f.write(out)
    print('parsed %d chars -> %s' % (len(out), sys.argv[2]))

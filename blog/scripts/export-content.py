#!/usr/bin/env python3
"""Export published Hugo article bodies to Markdown. Stdlib only; run after Hugo.

The catalog, not a source-directory scan, determines the publication boundary.
Tables, glossary definitions, code, Mermaid source and appended references survive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)
    def find(self, predicate):
        if predicate(self): return self
        for child in self.children:
            if isinstance(child, Node):
                found = child.find(predicate)
                if found is not None: return found
        return None

class Document(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        # HTML allows omitted closing tags; close peers at their nearest scope.
        peers = {'li': ({'li'}, {'ul','ol'}), 'td': ({'td','th'}, {'tr'}),
                 'th': ({'td','th'}, {'tr'}), 'tr': ({'tr'}, {'table','tbody','thead'})}
        if tag in peers:
            close, boundary = peers[tag]
            for i in range(len(self.stack)-1,0,-1):
                if self.stack[i].tag in close:
                    del self.stack[i:]; break
                if self.stack[i].tag in boundary: break
        if tag in {'p','div','section','h1','h2','h3','h4','ul','ol','table','pre'} and self.stack[-1].tag == 'p':
            self.stack.pop()
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID: self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID: self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break
    def handle_data(self, text): self.stack[-1].children.append(text)

def markdown(node, url):
    if isinstance(node, str): return re.sub(r'\s+', ' ', node)
    tag, attrs = node.tag, node.attrs
    classes = attrs.get('class','').split()
    if tag in {'script','style','nav'} or 'data-export-exclude' in attrs: return ''
    if tag == 'button' and 'abbr-trigger' not in classes: return ''
    if tag == 'a' and ('hextra-heading-anchor' in classes or attrs.get('aria-label','').startswith('Permalink')): return ''
    if tag == 'pre':
        code = node.find(lambda n:n.tag=='code')
        source = code.text() if code else node.text()
        language = 'mermaid' if 'mermaid' in classes else ''
        if code:
            language = code.attrs.get('data-lang','')
            for cls in code.attrs.get('class','').split():
                if cls.startswith('language-'): language = cls[9:]
        fence = '`' * max(3,1+max((len(m) for m in re.findall(r'`+',source)),default=0))
        return f'\n\n{fence}{language}\n{source}{'' if source.endswith(chr(10)) else chr(10)}{fence}\n\n'
    if tag == 'table':
        rows=[]
        def collect(n):
            if not isinstance(n,Node): return
            if n.tag=='tr': rows.append([markdown(c,url).strip().replace('|','\\|').replace('\n','<br>') for c in n.children if isinstance(c,Node) and c.tag in {'th','td'}])
            else:
                for c in n.children: collect(c)
        collect(node)
        if not rows:return ''
        width=max(map(len,rows));rows=[r+['']*(width-len(r)) for r in rows]
        lines=['| '+' | '.join(r)+' |' for r in rows]
        lines.insert(1,'| '+' | '.join(['---']*width)+' |')
        return '\n\n'+'\n'.join(lines)+'\n\n'
    text=''.join(markdown(c,url) for c in node.children)
    if re.fullmatch('h[1-6]',tag):
        title=text.strip()
        if attrs.get('id'):title=f'[{title}]({url}#{attrs["id"]})'
        return '\n\n'+'#'*int(tag[1])+' '+title+'\n\n'
    if tag=='a' and attrs.get('href'):return f'[{text.strip()}]({urljoin(url,attrs["href"])})'
    if tag=='img':return f'![{attrs.get("alt", "")}]({urljoin(url,attrs.get("src", ""))})'
    if tag=='code':
        fence='`' * (1+max((len(m) for m in re.findall(r'`+',node.text())),default=0))
        return fence+' '+node.text()+' '+fence
    if tag in {'strong','b'}:return '**'+text.strip()+'**'
    if tag in {'em','i'}:return '*'+text.strip()+'*'
    if tag=='abbr':return text+(f' ({attrs["title"]})' if attrs.get('title') else '')
    if 'abbr-panel' in classes:return ' ('+text.strip()+') '
    if 'abbr-name' in classes:return text+': '
    if tag in {'ul','ol'}:
        items=[]
        for i,c in enumerate(c for c in node.children if isinstance(c,Node) and c.tag=='li'):
            marker=f'{i+1}. ' if tag=='ol' else '- '
            value=''.join(markdown(k,url) for k in c.children).strip()
            items.append(marker+value.replace('\n','\n'+' '*len(marker)))
        return '\n\n'+'\n'.join(items)+'\n\n'
    if tag=='blockquote':return '\n\n'+'\n'.join('> '+l for l in text.strip().splitlines())+'\n\n'
    if tag=='br':return '\n'
    if tag=='hr':return '\n\n---\n\n'
    if tag in {'p','div','section','article','details','figure','figcaption'}:return '\n\n'+text.strip()+'\n\n'
    return text

def export(public):
    public=Path(public).resolve()
    catalog_path=public/'content-index.json'
    catalog=json.loads(catalog_path.read_text())
    base_path=urlparse(catalog['site']).path.rstrip('/')
    outputs=[]
    for article in catalog['articles']:
        path=unquote(urlparse(article['url']).path)
        if base_path and not path.startswith(base_path+'/'):raise ValueError(f'Article outside site: {path}')
        directory=(public/path[len(base_path):].strip('/')).resolve()
        if not directory.is_relative_to(public):raise ValueError('Export escapes public directory')
        document=Document((directory/'index.html').read_text())
        body=document.root.find(lambda n:'data-article-body' in n.attrs)
        if body is None:body=document.root.find(lambda n:n.tag=='main' and n.attrs.get('id')=='content')
        if body is None:raise ValueError(f'No article body: {article["url"]}')
        text=markdown(body,article['url'])
        # Do not normalize generated Markdown globally: whitespace inside fenced
        # code is source data, including blank lines and indentation.
        text=text.strip()
        def unresolved(n):
            if isinstance(n,str):return bool(re.search(r'\{\{[<%]',n))
            return n.tag not in {'pre','code'} and any(unresolved(c) for c in n.children)
        if unresolved(body):raise ValueError(f'Unresolved shortcode outside code in {article["url"]}')
        header=f'# {article["title"]}\n\nSource: {article["url"]}\nPublished: {article["published"]}\nUpdated: {article["updated"]}\n'
        if article.get('last_verified'):header+=f'Last verified: {article["last_verified"]}\n'
        result=header+'\n'+text+'\n'
        outputs.append((directory/'index.md',result))
        article['content_sha256']=hashlib.sha256(result.encode()).hexdigest()
    for path,result in outputs:path.write_text(result)
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    print(f'Exported {len(outputs)} published pages to Markdown')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('public',type=Path)
    export(parser.parse_args().public)

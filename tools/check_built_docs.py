#!/usr/bin/env python3
"""Check rendered current docs, sidebar, search data, and local links after Jekyll."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import check_docs


class PageHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.navigation: set[str] = set()
        self.ids: set[str] = set()
        self.in_navigation = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'nav' and attrs.get('id') == 'site-nav':
            self.in_navigation = True
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
            if self.in_navigation:
                self.navigation.add(unquote(urlsplit(attrs['href']).path))
        if tag == 'link' and attrs.get('rel') == 'stylesheet' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'script' and attrs.get('src'):
            self.links.append(attrs['src'])

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.in_navigation = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site_dir', type=Path, help='Jekyll output directory')
    args = parser.parse_args()
    output = args.site_dir.resolve()
    errors: list[str] = []
    pages = check_docs.load_pages(errors)
    base_url = 'https://iapyeh.github.io/sshscript'
    base_path = '/sshscript'
    expected_nav = {base_path + page.url for page in pages if page.visible}
    html_cache: dict[Path, PageHTML] = {}

    def read_html(path):
        if path not in html_cache:
            html = PageHTML()
            html.feed(path.read_text(encoding='utf-8'))
            html_cache[path] = html
        return html_cache[path]

    for relative in ('index.html', '404.html', 'v3a/index.html',
                     'assets/css/just-the-docs-default.css'):
        if not (output / relative).is_file():
            errors.append(f'missing build artifact: {relative}')

    links = 0
    for page in pages:
        path = output / page.url.lstrip('/') / 'index.html'
        if not path.is_file():
            errors.append(f'missing rendered page: {page.url}')
            continue
        html = read_html(path)
        rendered = path.read_text(encoding='utf-8')
        if f'SSHScript {check_docs.CURRENT_VERSION} documentation.' not in rendered:
            errors.append(f'{page.url}: footer version does not match current release')
        for required in ('href="https://pypi.org/project/sshscript/"',
                         'href="https://github.com/iapyeh/sshscript/releases/latest"'):
            if required not in rendered:
                errors.append(f'{page.url}: missing current release entry: {required}')
        if '<title>' in rendered and 'SSHScript v3.1 Documentation</title>' in rendered:
            errors.append(f'{page.url}: stale site title')
        if 'main-content' not in html.ids:
            errors.append(f'{page.url}: missing theme layout')
        if html.navigation != expected_nav:
            errors.append(f'{page.url}: sidebar differs from the {len(expected_nav)} visible source pages; '
                          f'missing={sorted(expected_nav - html.navigation)}, '
                          f'extra={sorted(html.navigation - expected_nav)}')
        for link in html.links:
            url = urlsplit(urljoin(base_url + page.url, link))
            if url.netloc != 'iapyeh.github.io' or not url.path.startswith(base_path + '/'):
                continue
            target = output / unquote(url.path[len(base_path) + 1:])
            if target.is_dir() or url.path.endswith('/'):
                target = target / 'index.html'
            if not target.is_file():
                errors.append(f'{page.url}: broken local link or asset: {link}')
                continue
            links += 1
            if url.fragment and target.suffix == '.html' and unquote(url.fragment) not in read_html(target).ids:
                errors.append(f'{page.url}: missing anchor: {link}')

    search_path = output / 'assets/js/search-data.json'
    try:
        search = json.loads(search_path.read_text(encoding='utf-8'))
        if not isinstance(search, dict) or not search:
            raise ValueError('search index is empty or not an object')
        search_urls = {unquote(urlsplit(record['url']).path) for record in search.values()}
        expected_search = {base_path + page.url for page in pages
                           if page.metadata.get('search_exclude') is not True}
        if search_urls != expected_search:
            errors.append(f'search pages differ from source: missing={sorted(expected_search - search_urls)}, '
                          f'extra={sorted(search_urls - expected_search)}')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'invalid search index: {exc}')
        search = {}

    # Historical archives contain untranslated source assets; this contract
    # applies to the maintained v3a site only.
    if any((output / 'v3a').rglob('*.zh-tw*')):
        errors.append('unpublished v3a translations were included in the build')

    if errors:
        for error in sorted(set(errors)):
            print('ERROR:', error)
        return 1
    print(f'Validated {len(pages)} generated pages, {len(expected_nav)} sidebar entries, '
          f'{len(search)} search records, and {links} internal links/assets/anchors.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

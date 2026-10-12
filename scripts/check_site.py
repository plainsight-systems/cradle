#!/usr/bin/env python3
"""Check generated local links, anchors, assets and publication boundaries."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit

from content import PublicationError


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.errors = []
        self.canonical = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if key := attrs.get("id"):
            if key in self.ids:
                self.errors.append(f"duplicate id {key}")
            self.ids.add(key)
        if tag == "img" and not attrs.get("alt"):
            self.errors.append("image has no alternative text")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = bool(attrs.get("href"))
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])
        for candidate in attrs.get("srcset", "").split(","):
            if candidate.strip():
                self.links.append(candidate.split()[0])


def check(output, base_url, preview=False):
    output = Path(output).resolve()
    base = urlsplit(base_url)
    pages = {}
    errors = []
    for path in output.rglob("*.html"):
        text = path.read_text()
        relative = path.relative_to(output).as_posix()
        page = Page(text)
        pages[path] = page
        errors.extend(f"{relative}: {e}" for e in page.errors)
        if not page.canonical:
            errors.append(f"{relative}: no canonical URL")
        if re.search(r"/Users/|/home/|file://|CLAUDE\.local", text):
            errors.append(f"{relative}: local working context leaked")
        if not preview and ('name="robots" content="noindex' in text or 'name=robots content="noindex' in text):
            errors.append(f"{relative}: preview content in production")
    if not (output / "index.html").is_file():
        errors.append("Missing homepage")
    if not preview and (output / "preview").exists():
        errors.append("Preview route in production")
    def resolve(link, current):
        absolute = urlsplit(urljoin(current, link))
        if absolute.scheme not in {"http", "https"} or absolute.netloc != base.netloc:
            return None, ""
        if not absolute.path.startswith(base.path):
            errors.append(f"Link escapes deployment subpath: {link}")
            return None, ""
        target = (output / unquote(absolute.path[len(base.path):])).resolve()
        if not target.is_relative_to(output):
            errors.append(f"Link escapes output: {link}")
            return None, ""
        if target.is_dir():
            target /= "index.html"
        if not target.is_file():
            errors.append(f"Missing local destination: {link} (from {current})")
        return target, unquote(absolute.fragment)
    for path, page in pages.items():
        relative = path.relative_to(output).as_posix()
        current = urljoin(base_url, relative.removesuffix("index.html"))
        for link in page.links:
            target, fragment = resolve(link, current)
            if target in pages and fragment and fragment not in pages[target].ids:
                errors.append(f"{relative}: missing anchor in {link}")
    for path in output.rglob("*.css"):
        current = urljoin(base_url, path.relative_to(output).as_posix())
        for link in re.findall(r"url\(['\"]?([^)'\"]+)['\"]?\)", path.read_text()):
            resolve(link, current)
    if errors:
        raise PublicationError("Site checks failed:\n" + "\n".join(sorted(set(errors))))
    print(f"Checked {len(pages)} HTML pages: links, anchors, assets and publication boundaries pass.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        check(args.output, args.base_url, args.preview)
    except (PublicationError, OSError) as exc:
        sys.exit(str(exc))

#!/usr/bin/env python3
"""Build or preview Cradle without exposing working material to Hugo."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

from content import (ROOT, PublicationError, articles, check_release, check_hugo_version,
                     document, no_symlinks, page_metadata, rendered_body)


def stage_content(destination, preview=False, root=ROOT):
    shutil.copytree(root / "web/content", destination, dirs_exist_ok=True)
    available = [a for a in articles(root) if preview or a.public]
    for article in available:
        if not preview:
            check_release(article, root)
        target = destination / "lessons" / article.folder.name
        target.mkdir(parents=True)
        meta = page_metadata(article)
        meta["canonicalURL"] = article.canonical
        meta["weight"] = meta["lesson"]
        (target / "index.md").write_text(document(meta, rendered_body(article, available)), encoding="utf-8")
        for name, data in article.assets.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if preview:
        target = destination / "preview"
        target.mkdir()
        shutil.copyfile(root / "scripts/fixtures/article-preview.md", target / "index.md")
    return len(available)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "serve"])
    parser.add_argument("--base-url", help="Required for build; include the Pages subpath and trailing slash")
    parser.add_argument("--preview", action="store_true", help="Include drafts, future articles, and /preview/; writes dist-preview/")
    parser.add_argument("--port", type=int, default=1313)
    args = parser.parse_args()
    if args.command == "build" and not args.base_url:
        parser.error("build requires --base-url (serve uses localhost)")
    base = args.base_url or f"http://localhost:{args.port}/"
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or not base.endswith("/"):
        parser.error("--base-url must be an absolute HTTP(S) URL ending with /, without query or fragment")
    version = subprocess.check_output(["hugo", "version"], text=True)
    check_hugo_version(version)
    output = ROOT / ("dist-preview" if args.preview else "dist")
    no_symlinks(output)
    with tempfile.TemporaryDirectory(prefix="cradle-site-") as temp:
        stage = Path(temp)
        count = stage_content(stage / "content", args.preview)
        overlay = stage / "build.json"
        overlay.write_text(json.dumps({"params": {"preview": args.preview}}))
        command = ["hugo"]
        if args.command == "serve":
            command += ["server", "--bind", "127.0.0.1", "--port", str(args.port), "--disableFastRender"]
        command += ["--source", str(ROOT / "web"), "--config", f"hugo.toml,{overlay}",
                    "--contentDir", str(stage / "content"), "--baseURL", base,
                    "--destination", str(output), "--cleanDestinationDir", "--panicOnWarning"]
        if args.preview:
            command += ["--buildDrafts", "--buildFuture"]
        if args.command == "build":
            command += ["--minify"]
        print(f"Cradle: {count} article(s); {'preview' if args.preview else 'production'}", flush=True)
        if args.command == "serve":
            print("Article sources are staged at startup. Restart after editing articles/.", flush=True)
        subprocess.run(command, check=True, env={**os.environ, "HUGO_ENVIRONMENT": "production"})
        if args.command == "build":
            from check_site import check
            check(output, base, args.preview)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except (PublicationError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"site: {exc}")

#!/usr/bin/env python3
"""Export one approved article to a personal-site checkout. Never commit or deploy."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from content import (ROOT, SERIES, PublicationError, articles, check_release, digest,
                     document, git, no_symlinks, page_metadata, rendered_body,
                     repository_url, tree_hashes)
from render_math import render_math


def export(article_name, site, dry_run=False, root=ROOT):
    available = articles(root)
    article = next((a for a in available if a.folder.name == article_name), None)
    if article is None:
        raise PublicationError(f"No article named {article_name!r} in articles/")
    if not article.public:
        raise PublicationError("Only non-draft articles dated today or earlier can be exported")
    check_release(article, root)
    site = Path(site).absolute()
    no_symlinks(site)
    if not (site / "hugo.yaml").is_file() or not (site / "content/writing").is_dir():
        raise PublicationError("--site must identify the personal Hugo site with content/writing/ and hugo.yaml")
    slug = article.meta["personal_slug"]
    target = site / "content/writing" / slug
    record = site / "data/cradle-exports" / f"{slug}.json"
    no_symlinks(target)
    no_symlinks(record)
    # The personal site already has flat articles, so check both Hugo representations.
    for suffix in (".md", ".html"):
        if target.with_suffix(suffix).exists() or target.with_suffix(suffix).is_symlink():
            raise PublicationError(f"A personal-site page already occupies slug {slug}")
    if target.exists():
        if not record.is_file():
            raise PublicationError(f"Destination {slug} already exists and is not owned by this exporter")
        previous = json.loads(record.read_text())
        if previous.get("source_article") != f"articles/{article_name}/index.md":
            raise PublicationError("Export record belongs to a different source article")
        if tree_hashes(target) != previous.get("files"):
            raise PublicationError("Destination has changed since export. Reconcile its edits with the source before replacing it.")
    elif record.exists():
        raise PublicationError("Exported bundle is missing but its record remains. Reconcile the destination before exporting again.")
    revision = git(root, "rev-parse", "HEAD")
    source_files = [f"articles/{article_name}/index.md", *[f"articles/{article_name}/{n}" for n in article.assets]]
    tracked = set(git(root, "ls-files", "--", *source_files).splitlines())
    dirty = tracked != set(source_files) or bool(git(root, "status", "--porcelain", "--", *source_files))
    if dirty and not dry_run:
        raise PublicationError("Commit the article and its selected images before export so its source revision is reproducible (use --dry-run to inspect)")
    meta = page_metadata(article)
    meta.update({"type": "application", "series": [SERIES], "part": meta["lesson"],
                 "canonicalURL": article.canonical, "cradle_source": {
                     "repository": repository_url(root), "revision": revision,
                     "article": f"articles/{article_name}/index.md"}})
    repo = repository_url(root)
    start = article.meta["start_tag"]
    finish = article.meta["end_tag"]
    snapshots = (f"[Starting code]({repo}/tree/{start})" if start else "Start with an empty program")
    snapshots += f" · [Completed code]({repo}/tree/{finish})\n\n"
    body = snapshots + rendered_body(article, [a for a in available if a.public], personal=True)
    if article.meta.get("math"):
        body = render_math(body)
        # The generated MathML needs no destination-side KaTeX script or CSS.
        meta["math"] = False
    files = {"index.md": document(meta, body).encode(), **article.assets}
    hashes = {name: digest(data) for name, data in files.items()}
    manifest = {"format": 1, "source_article": f"articles/{article_name}/index.md",
                "revision": revision, "files": hashes}
    if dry_run:
        print(f"Would export {article_name} to content/writing/{slug}/")
        print(f"Source: {revision}{' + uncommitted article changes' if dirty else ''}")
        print("Files: " + ", ".join(sorted(files)))
        return files
    if target.exists() and tree_hashes(target) == hashes:
        print(f"Unchanged: {slug}")
        return files
    # Stage on the same filesystem and retain a rollback copy until both writes succeed.
    target.parent.mkdir(parents=True, exist_ok=True)
    record.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cradle-export-", dir=site) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        for name, data in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        new_record = Path(temp) / "record.json"
        new_record.write_text(json.dumps(manifest, indent=2) + "\n")
        backup = Path(temp) / "previous"
        if target.exists():
            target.rename(backup)
        try:
            stage.rename(target)
            new_record.replace(record)
        except OSError:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                backup.rename(target)
            raise
    print(f"Exported {slug}. Review and commit the article bundle and data/cradle-exports/{slug}.json in the personal site.")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", help="Article folder name, for example 01-the-cradle")
    parser.add_argument("--site", required=True, type=Path, help="Explicit path to the personal-site checkout")
    parser.add_argument("--dry-run", action="store_true", help="Validate and list the planned export without writing")
    args = parser.parse_args()
    export(args.article, args.site, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (PublicationError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"publish-article: {exc}")

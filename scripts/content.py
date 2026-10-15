"""Shared, deliberately small publication contract. Python 3.11+, no packages."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERIES = "Let's Build a Transformer!"
HUGO_VERSION = "0.154.2"
FIELDS = {"title", "description", "lesson", "date", "draft", "start_tag", "end_tag",
          "personal_slug", "publish_assets", "tags", "math"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
TAG = re.compile(r"lesson-[0-9]{2}(?:\.[0-9]+)?\Z")


class PublicationError(Exception):
    pass


def check_hugo_version(version):
    # Official binaries include a Git SHA; Homebrew's build omits it.
    if not re.match(rf"hugo v{re.escape(HUGO_VERSION)}(?:-[0-9a-f]{{7,40}})?(?:\+|\s|$)", version):
        raise PublicationError(f"Use Hugo {HUGO_VERSION}; found {version.strip()}")


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise PublicationError(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def no_symlinks(path):
    """Check parents too: resolving first would erase evidence of a symlink."""
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PublicationError(f"Symlinks are not publication inputs or destinations: {path}")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree_hashes(folder):
    no_symlinks(folder)
    if not folder.is_dir():
        raise PublicationError(f"Expected a directory: {folder}")
    result = {}
    for path in sorted(folder.rglob("*")):
        no_symlinks(path)
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = digest(path.read_bytes())
        elif not path.is_dir():
            raise PublicationError(f"Not a regular publication file: {path}")
    return result


def document(meta, body):
    # JSON is a native Hugo front-matter format; no lossy YAML serializer needed.
    return json.dumps(meta, ensure_ascii=False, indent=2, default=str) + "\n\n" + body


@dataclass
class Article:
    folder: Path
    meta: dict
    body: str
    assets: dict

    @property
    def public(self):
        return not self.meta["draft"] and self.meta["date"] <= datetime.now(timezone.utc).date()

    @property
    def canonical(self):
        return f"https://cradle.plainsight-systems.com/lessons/{self.folder.name}/"

    @property
    def personal_url(self):
        return f"https://andrewphunter.com/writing/{self.meta['personal_slug']}/"


def read_article(folder, max_lesson=18):
    no_symlinks(folder)
    source = folder / "index.md"
    no_symlinks(source)
    raw = source.read_text(encoding="utf-8")
    match = re.match(r"\A\+\+\+\r?\n(.*?)\r?\n\+\+\+\r?\n(.*)\Z", raw, re.S)
    if not match:
        raise PublicationError(f"{source}: use +++ TOML front matter (see articles/README.md)")
    meta = tomllib.loads(match[1])
    if extra := meta.keys() - FIELDS:
        raise PublicationError(f"{source}: unsupported metadata: {', '.join(sorted(extra))}")
    for field in ("title", "description", "personal_slug"):
        if not isinstance(meta.get(field), str) or not meta[field].strip():
            raise PublicationError(f"{source}: {field} must be a nonempty string")
    if not SLUG.fullmatch(meta["personal_slug"]):
        raise PublicationError(f"{source}: personal_slug must be lowercase words joined by hyphens")
    number = meta.get("lesson")
    if type(number) is not int or not 0 <= number <= max_lesson:
        raise PublicationError(f"{source}: lesson must be between 0 (prologue) and {max_lesson}")
    if not re.fullmatch(rf"{number:02d}-[a-z0-9]+(?:-[a-z0-9]+)*", folder.name):
        raise PublicationError(f"{source}: folder must start with lesson number {number:02d}-")
    if type(meta.get("draft")) is not bool:
        raise PublicationError(f"{source}: draft must explicitly be true or false")
    if type(meta.get("date")) is not date:
        raise PublicationError(f"{source}: date must be an unquoted TOML date, YYYY-MM-DD")
    for field in ("start_tag", "end_tag"):
        value = meta.get(field, "")
        if not isinstance(value, str) or (value and not TAG.fullmatch(value)):
            raise PublicationError(f"{source}: invalid {field}")
        meta[field] = value
    if not meta["draft"]:
        for field, expected in (("end_tag", number), ("start_tag", number - 1)):
            if expected >= 0 and not re.fullmatch(rf"lesson-{expected:02d}(?:\.[0-9]+)?", meta[field]):
                raise PublicationError(f"{source}: {field} must identify lesson {expected:02d}")
        if number == 0 and meta["start_tag"]:
            raise PublicationError(f"{source}: the prologue starts from an empty program")
    if "math" in meta and type(meta["math"]) is not bool:
        raise PublicationError(f"{source}: math must be true or false")
    if not isinstance(meta.get("tags", []), list) or any(not isinstance(t, str) for t in meta.get("tags", [])):
        raise PublicationError(f"{source}: tags must be an array of strings")
    names = meta.get("publish_assets", [])
    if not isinstance(names, list) or any(not isinstance(p, str) for p in names):
        raise PublicationError(f"{source}: publish_assets must be an array of paths")
    if len(names) != len(set(names)):
        raise PublicationError(f"{source}: duplicate asset")
    assets = {}
    for name in names:
        rel = PurePosixPath(name)
        if (len(rel.parts) < 2 or rel.parts[0] != "images" or rel.as_posix() != name
                or any(p in {".", ".."} or p.startswith(".") for p in rel.parts)
                or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                or rel.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".avif"}):
            raise PublicationError(f"{source}: invalid image asset {name!r}")
        path = folder / name
        no_symlinks(path)
        if not path.is_file():
            raise PublicationError(f"{source}: missing image {name}")
        assets[name] = path.read_bytes()
    body = match[2].strip() + "\n"
    if re.search(r"\{\{[<%]", body):
        raise PublicationError(f"{source}: Hugo shortcodes are not portable between the two sites")
    # Keep relative links meaningful in both destinations. Includes reference links.
    pattern = r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"\n]*")?\)|^\[(?!\^)[^\]]+\]:\s*(\S+)'
    for link in re.finditer(pattern, body, re.M):
        value = link[1] or link[2]
        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http", "mailto", "lesson"} or value.startswith("#"):
            continue
        if parsed.path not in assets:
            raise PublicationError(f"{source}: local link {value!r} is not a selected image; use lesson:NN for article links")
    return Article(folder, meta, body, assets)


def articles(root=ROOT):
    result = [read_article(p.parent) for p in sorted((root / "articles").glob("*/index.md"))]
    for key in ("lesson", "personal_slug"):
        values = [a.meta[key] for a in result]
        if len(values) != len(set(values)):
            raise PublicationError(f"Duplicate article {key}")
    return result


def repository_url(root=ROOT):
    with (root / "web/hugo.toml").open("rb") as stream:
        url = tomllib.load(stream)["params"].get("repository", "")
    if url and not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url):
        raise PublicationError("web/hugo.toml params.repository must be an HTTPS GitHub repository URL without a trailing slash")
    return url


def check_release(article, root=ROOT):
    if not repository_url(root):
        raise PublicationError("Set params.repository in web/hugo.toml before publishing lessons")
    for field in ("start_tag", "end_tag"):
        if tag := article.meta[field]:
            git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")


def rendered_body(article, available, personal=False):
    """Portable links: [title](lesson:02#heading), resolved for each destination."""
    def destination(number, fragment):
        number = int(number)
        target = next((a for a in available if a.meta["lesson"] == number), None)
        if target is None:
            raise PublicationError(f"{article.folder.name}: link points to an unavailable lesson {number}")
        base = target.personal_url if personal else f"../{target.folder.name}/"
        return base + (fragment or "")
    body = re.sub(r"\]\(lesson:([0-9]+)(#[^\s)]*)?\)",
                  lambda m: f"]({destination(m[1], m[2])})", article.body)
    return re.sub(r"^(\[(?!\^)[^\]]+\]:\s*)lesson:([0-9]+)(#[^\s]*)?",
                  lambda m: m[1] + destination(m[2], m[3]), body, flags=re.M)


def page_metadata(article):
    return {k: v for k, v in article.meta.items() if k not in {"publish_assets", "personal_slug"}}

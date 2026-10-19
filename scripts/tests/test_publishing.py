"""Exercise real Git snapshots, filesystem conflicts, and Hugo-rendered output."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import ROOT, PublicationError, articles, git, read_article, tree_hashes, check_hugo_version
from publish_article import export
from check_site import check
from render_math import render_math

spec = importlib.util.spec_from_file_location("cradle_site", ROOT / "scripts/site.py")
site_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_module)


class PublishingTests(unittest.TestCase):
    def test_hugo_version_formats_keep_exact_release_pin(self):
        for version in ("hugo v0.154.2+extended+withdeploy darwin/arm64",
                        "hugo v0.154.2-abcdef123456+extended linux/amd64",
                        "hugo v0.154.2 linux/amd64"):
            check_hugo_version(version)
        for version in ("hugo v0.154.20+extended", "hugo v0.155.0+extended",
                        "hugo v0.154.2-rc1+extended", "hugo v0.154.2garbage"):
            with self.assertRaises(PublicationError):
                check_hugo_version(version)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "source"
        self.site = Path(self.temp.name).resolve() / "personal"
        (self.root / "web/content").mkdir(parents=True)
        (self.root / "web/hugo.toml").write_text('[params]\nrepository = "https://github.com/example/cradle"\n')
        (self.site / "content/writing").mkdir(parents=True)
        (self.site / "hugo.yaml").write_text('baseURL: https://andrewphunter.com/\n')
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "tests@example.invalid")
        git(self.root, "config", "user.name", "Publication tests")
        self.folder = self.write_article()
        self.commit()
        git(self.root, "tag", "lesson-00")
        git(self.root, "tag", "lesson-01")
        self.target = self.site / "content/writing/cradle-01-test"
        self.record = self.site / "data/cradle-exports/cradle-01-test.json"

    def write_article(self, number=1, draft=False, day="2020-01-01", images=True, body=None):
        folder = self.root / f"articles/{number:02d}-test"
        folder.mkdir(parents=True, exist_ok=True)
        if images:
            (folder / "images").mkdir(exist_ok=True)
            (folder / "images/figure.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>')
        start = f"lesson-{number-1:02d}" if number > 0 else ""
        meta = f'''+++
title = "Lesson {number}"
description = "A publication test."
lesson = {number}
date = {day}
draft = {str(draft).lower()}
start_tag = "{start}"
end_tag = "lesson-{number:02d}"
personal_slug = "cradle-{number:02d}-test"
publish_assets = {json.dumps(['images/figure.svg'] if images else [])}
+++
'''
        text = body if body is not None else "## A checked result\n\nArticle body.\n\n" + ("![A test circle](images/figure.svg)\n" if images else "")
        (folder / "index.md").write_text(meta + text)
        (folder / "notes.md").write_text("PRIVATE WORKING NOTES")
        (folder / "images/unselected.svg").write_text("PRIVATE IMAGE") if images else None
        return folder

    def commit(self):
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "Test publication input")

    def run_export(self, dry_run=False):
        with redirect_stdout(io.StringIO()):
            return export("01-test", self.site, dry_run, self.root)

    def test_prologue_tags_and_lesson_one_start(self):
        prologue = self.write_article(number=0, images=False)
        self.assertEqual(read_article(prologue).meta["end_tag"], "lesson-00")
        for folder, old, new in (
            (prologue, 'end_tag = "lesson-00"', 'end_tag = ""'),
            (prologue, 'start_tag = ""', 'start_tag = "lesson-01"'),
            (self.folder, 'start_tag = "lesson-00"', 'start_tag = ""'),
        ):
            source = folder / "index.md"
            original = source.read_text()
            source.write_text(original.replace(old, new))
            with self.assertRaises(PublicationError):
                read_article(folder)
            source.write_text(original)

    def test_prologue_export_and_portable_links(self):
        self.write_article(number=0, images=False, body="[Next](lesson:01)")
        self.write_article(body="[Setup](lesson:00)")
        self.commit()
        with redirect_stdout(io.StringIO()):
            result = export("00-test", self.site, root=self.root)
        text = result["index.md"].decode()
        self.assertIn('"part": 0', text)
        self.assertIn("https://github.com/example/cradle/tree/lesson-00", text)
        self.assertIn("https://andrewphunter.com/writing/cradle-01-test/", text)
        text = self.run_export()["index.md"].decode()
        self.assertIn("https://andrewphunter.com/writing/cradle-00-test/", text)

    def test_allowlist_provenance_and_idempotence(self):
        self.run_export()
        self.assertEqual(set(tree_hashes(self.target)), {"index.md", "images/figure.svg"})
        doc = (self.target / "index.md").read_text()
        self.assertIn(git(self.root, "rev-parse", "HEAD"), doc)
        self.assertIn('"part": 1', doc)
        self.assertIn('"canonicalURL": "https://cradle.plainsight-systems.com/lessons/01-test/"', doc)
        self.assertNotIn(str(self.root), doc)
        before = self.target.stat().st_mtime_ns
        self.run_export()
        self.assertEqual(before, self.target.stat().st_mtime_ns)

    def test_dry_run_writes_nothing_even_with_uncommitted_source(self):
        with (self.folder / "index.md").open("a") as f:
            f.write("\nNew source content.\n")
        before = tree_hashes(self.site)
        self.run_export(True)
        self.assertEqual(before, tree_hashes(self.site))
        with self.assertRaisesRegex(PublicationError, "Commit the article"):
            self.run_export()

    def test_destination_edit_is_preserved(self):
        self.run_export()
        (self.target / "index.md").write_text("A destination edit to preserve")
        before = tree_hashes(self.site)
        with self.assertRaisesRegex(PublicationError, "Destination has changed"):
            self.run_export()
        self.assertEqual(before, tree_hashes(self.site))

    def test_destination_extra_file_is_preserved(self):
        self.run_export()
        (self.target / "personal-note.txt").write_text("Keep me")
        with self.assertRaisesRegex(PublicationError, "Destination has changed"):
            self.run_export()
        self.assertTrue((self.target / "personal-note.txt").is_file())

    def test_foreign_bundle_and_flat_slug_collisions(self):
        self.target.mkdir()
        with self.assertRaisesRegex(PublicationError, "not owned"):
            self.run_export()
        self.target.rmdir()
        self.target.with_suffix(".md").write_text("Existing article")
        with self.assertRaisesRegex(PublicationError, "occupies slug"):
            self.run_export()

    def test_source_update_prunes_only_previous_exported_assets(self):
        self.run_export()
        self.write_article(images=False)
        self.commit()
        self.run_export()
        self.assertEqual(set(tree_hashes(self.target)), {"index.md"})

    def test_drafts_and_future_articles_cannot_export(self):
        for options in ({"draft": True}, {"day": "2099-01-01"}):
            self.write_article(**options)
            with self.assertRaisesRegex(PublicationError, "non-draft"):
                self.run_export(True)

    def test_missing_release_tag_cannot_publish(self):
        git(self.root, "tag", "-d", "lesson-01")
        with self.assertRaises(PublicationError):
            self.run_export(True)
        self.assertFalse(self.target.exists())

    def test_source_symlink_and_traversal_rejected(self):
        image = self.folder / "images/figure.svg"
        image.unlink()
        image.symlink_to(self.folder / "notes.md")
        with self.assertRaisesRegex(PublicationError, "Symlinks"):
            self.run_export(True)
        image.unlink()
        image.write_text("restored")
        source = self.folder / "index.md"
        source.write_text(source.read_text().replace("images/figure.svg", "images/../../notes.svg"))
        with self.assertRaisesRegex(PublicationError, "invalid image"):
            read_article(self.folder)

    def test_symlinked_destination_parent_rejected(self):
        real = self.site / "real-writing"
        (self.site / "content/writing").rename(real)
        (self.site / "content/writing").symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(PublicationError, "Symlinks"):
            self.run_export()

    def test_failed_manifest_write_restores_previous_bundle(self):
        self.run_export()
        before = tree_hashes(self.site)
        self.write_article(body="Revised source")
        self.commit()
        with patch.object(Path, "replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                self.run_export()
        self.assertEqual(before, tree_hashes(self.site))

    def test_duplicate_number_and_unavailable_lesson_link(self):
        copy = self.root / "articles/01-copy"
        shutil.copytree(self.folder, copy)
        with self.assertRaisesRegex(PublicationError, "Duplicate article lesson"):
            articles(self.root)
        shutil.rmtree(copy)
        self.write_article(body="[Not yet published](lesson:02)")
        with self.assertRaisesRegex(PublicationError, "unavailable lesson"):
            self.run_export(True)

    def test_unselected_image_reference_rejected(self):
        self.write_article(body="![Hidden](images/unselected.svg)")
        with self.assertRaisesRegex(PublicationError, "not a selected image"):
            self.run_export(True)

    def test_portable_lesson_links(self):
        self.write_article(number=2)
        git(self.root, "tag", "lesson-02")
        self.write_article(body="[Next](lesson:02#a-checked-result)\n\n[Next again][two]\n\n[two]: lesson:02\n")
        self.commit()
        files = self.run_export()
        # A future lesson gets a project canonical without redirecting blog navigation.
        with redirect_stdout(io.StringIO()):
            later = export("02-test", self.site, root=self.root)
        self.assertIn('"canonicalURL": "https://cradle.plainsight-systems.com/lessons/02-test/"', later["index.md"].decode())
        self.assertIn("https://andrewphunter.com/writing/cradle-02-test/#a-checked-result", files["index.md"].decode())
        staged = Path(self.temp.name) / "links"
        site_module.stage_content(staged, root=self.root)
        self.assertIn("../02-test/#a-checked-result", (staged / "lessons/01-test/index.md").read_text())

    @unittest.skipUnless(shutil.which("hugo"), "Hugo required for math export")
    def test_formula_export_preserves_code_and_renders_equations(self):
        literal = "```text\n\\[x_i\\]\n```\n\n`\\(x_i\\)`"
        body = "Inline \\(x_i\\).\n\n\\[x_i = \\frac{1}{n}\\]\n\n" + literal
        result = render_math(body)
        self.assertEqual(result.count("<math"), 2)
        self.assertIn(literal, result)
        self.assertIn("<msub>", result)

    @unittest.skipUnless(shutil.which("hugo"), "Hugo required for rendering integration")
    def test_hugo_render_publication_boundaries_and_subpath(self):
        self.write_article(number=0, images=False)
        self.write_article(number=2, draft=True)
        self.write_article(number=3, day="2099-01-01")
        content = Path(self.temp.name) / "content"
        site_module.stage_content(content, root=self.root)
        self.assertTrue((content / "lessons/01-test/index.md").exists())
        self.assertFalse((content / "lessons/02-test").exists())
        self.assertFalse((content / "lessons/03-test").exists())
        self.assertFalse((content / "lessons/01-test/notes.md").exists())
        # Include actual landing/about/section pages in the isolated staged content.
        shutil.copytree(ROOT / "web/content", content, dirs_exist_ok=True)
        output = Path(self.temp.name) / "output"
        subprocess.run(["hugo", "--source", str(ROOT / "web"), "--contentDir", str(content),
                        "--destination", str(output), "--baseURL", "https://example.org/cradle/",
                        "--panicOnWarning"], check=True, capture_output=True)
        with redirect_stdout(io.StringIO()):
            check(output, "https://example.org/cradle/")
        html = (output / "lessons/01-test/index.html").read_text()
        self.assertIn('<link rel="canonical" href="https://cradle.plainsight-systems.com/lessons/01-test/"', html)
        self.assertIn('<meta property="og:url" content="https://cradle.plainsight-systems.com/lessons/01-test/"', html)
        self.assertIn('href="/cradle/lessons/01-test/"', (output / "index.html").read_text())
        prologue = (output / "lessons/00-test/index.html").read_text()
        self.assertIn("/ Prologue", prologue)
        self.assertNotIn("/ Lesson 00", prologue)
        self.assertIn('href="/cradle/lessons/01-test/"', prologue)
        self.assertIn('href="/cradle/lessons/00-test/"', html)
        for file in ("index.html", "lessons/index.html"):
            index = (output / file).read_text()
            self.assertIn("1 of 18 lessons published", index)
            self.assertLess(index.index('href="/cradle/lessons/00-test/"'),
                            index.index('class="lesson-list"'))
        all_html = "".join(p.read_text() for p in output.rglob("*.html"))
        self.assertNotIn("PRIVATE", all_html)
        self.assertFalse((output / "preview").exists())
        feed = ET.parse(output / "lessons/index.xml")
        items = feed.findall("./channel/item")
        self.assertEqual(len(items), 2)
        self.assertEqual({item.findtext("title") for item in items}, {"Lesson 0", "Lesson 1"})
        self.assertFalse((output / "about/index.xml").exists())
        self.assertIn('https://example.org/cradle/lessons/index.xml', html)
        for item in items:
            self.assertTrue(item.findtext("link").startswith("https://example.org/cradle/lessons/"))
            canonical = item.findtext("link").replace("https://example.org/cradle/", "https://cradle.plainsight-systems.com/")
            self.assertEqual(item.findtext("guid"), canonical)


    @unittest.skipUnless(shutil.which("hugo"), "Hugo required for rendering integration")
    def test_series_status_ignores_drafts_and_future_even_in_preview(self):
        self.write_article(number=0, draft=True)
        self.write_article(number=2, draft=True)
        self.write_article(number=3, day="2099-01-01")
        # Latest must consider the full sequence, including later lessons.
        self.write_article(number=5, day="2021-02-03")
        fixture = self.root / "scripts/fixtures"
        fixture.mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts/fixtures/article-preview.md", fixture / "article-preview.md")
        content = Path(self.temp.name) / "preview-content"
        site_module.stage_content(content, preview=True, root=self.root)
        shutil.copytree(ROOT / "web/content", content, dirs_exist_ok=True)
        output = Path(self.temp.name) / "preview-output"
        subprocess.run(["hugo", "--source", str(ROOT / "web"), "--contentDir", str(content),
                        "--destination", str(output), "--baseURL", "https://example.org/cradle/",
                        "--buildDrafts", "--buildFuture", "--panicOnWarning"], check=True, capture_output=True)
        for file in ("index.html", "lessons/index.html"):
            html = (output / file).read_text()
            self.assertIn("2 of 18 lessons published", html)
            self.assertIn('href="/cradle/lessons/05-test/">Latest: Lesson 5', html)
            self.assertIn('datetime="2020-01-01">1 Jan 2020</time>', html)
            self.assertIn("Read lesson", html)
            self.assertNotIn('href="/cradle/lessons/00-test/"', html)
            self.assertNotIn('href="/cradle/lessons/02-test/"', html)
            self.assertNotIn('href="/cradle/lessons/03-test/"', html)
            self.assertNotIn('>Draft<', html)
        series = (output / "lessons/index.html").read_text()
        self.assertEqual(series.count('class="lesson-published"'), 2)
        self.assertEqual(series.count('class="lesson-planned"'), 16)
        feed = ET.parse(output / "lessons/index.xml")
        items = feed.findall("./channel/item")
        self.assertEqual([item.findtext("title") for item in items], ["Lesson 5", "Lesson 1"])
        self.assertNotIn("PRIVATE", (output / "lessons/index.xml").read_text())
        self.assertNotIn("/preview/", (output / "lessons/index.xml").read_text())
        # With no published content, every row remains planned and Latest disappears.
        for path in (content / "lessons").glob("*-test"):
            shutil.rmtree(path)
        subprocess.run(["hugo", "--source", str(ROOT / "web"), "--contentDir", str(content),
                        "--destination", str(output), "--baseURL", "https://example.org/cradle/",
                        "--cleanDestinationDir", "--panicOnWarning"], check=True, capture_output=True)
        series = (output / "lessons/index.html").read_text()
        self.assertIn("0 of 18 lessons published", series)
        self.assertEqual(series.count('class="lesson-planned"'), 18)
        self.assertNotIn('Latest:', series)
        self.assertEqual(ET.parse(output / 'lessons/index.xml').findall('./channel/item'), [])


if __name__ == "__main__":
    unittest.main()

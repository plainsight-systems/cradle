# Project site

Hugo presentation for Cradle's GitHub Pages site, following the approved workshop illustration and
Plainsight typography, navy framing, and ivory reading pages.

## Local preview

Install **Hugo 0.154.2** and **Python 3.11 or newer**, then run from the repository root:

```sh
python3 scripts/site.py serve --preview
```

Open `http://localhost:1313/` for the homepage, `/lessons/` for the dedicated series index, and `/preview/` for
the sample article layout. The published prologue is at `/lessons/00-getting-the-cradle-ready/`. Omit `--preview` to see only public content. Templates, styles, and sequence data
reload automatically; restart the server after editing article sources or files in `web/content/`, which are
staged at startup.

## Site files

- `content/`: the project overview and other site-specific pages.
- `layouts/`: page templates, including article and series navigation.
- `assets/`: site styling. The shared artwork is mounted from `docs/assets/` at build time.
- `data/lessons.json`: the planned sequence, with a short outcome for each lesson.
- `static/fonts/`: self-hosted IBM Plex fonts and their SIL Open Font License.
- `hugo.toml`: site settings and the public repository URL once it exists.

Paths in this list are relative to `web/`; other paths in this README are relative to the repository root.

## Series and article content

The homepage shows a separate setup prologue and previews the first four lessons and links to `/lessons/`, which shows the complete 18-lesson
planned sequence, from the first GPU kernel to performance work on the finished engine. Edit titles and outcomes in `web/data/lessons.json`. Planned entries
do not need placeholder article files.

The lesson index derives publication status from the articles: non-draft pages whose publication date has
arrived are marked Published, dated, and linked, with a Read lesson link. All other entries remain Planned.
Both indexes show the publication count; Latest points to the most recently dated published article and is
omitted when no articles have been published. The count and Latest link always consider the full series,
including lessons beyond the homepage preview.
Drafts and future articles do not count as published, including in local previews. No separate status field
needs to be maintained in the sequence data. The prologue uses `lesson = 0`, appears before the numbered
roadmap, and is excluded from the 18-lesson publication count. Its planned text lives in `web/data/prologue.json`.
It can be the Latest article once published.

Article text and images live in `articles/`. Build through `scripts/site.py`: it stages selected content before
calling Hugo, so working material never becomes a page resource. A direct `hugo` invocation omits the shared
article pipeline and is not a release build. See [article authoring](../articles/README.md) for the metadata,
image allowlist, and portable links used by both publication destinations.

The setup prologue is published; no numbered lessons have been authored. The `/preview/` fixture exercises
prose, math, code, and tables. It lives in `scripts/fixtures/`, outside Hugo's normal content tree, and is never
a published lesson. Preview builds include draft pages, but the index still treats their lessons as Planned.

## Building and publishing

The complete published-lesson RSS feed is `/lessons/index.xml`, advertised in
the HTML head. It includes the prologue and all published lessons without a
recent-item limit. The same draft/date boundary applies even in preview builds;
About, the roadmap's unpublished entries, and the preview fixture never enter
the feed. Only title, description, publication date and URLs are emitted.

RSS reading links point to the Cradle edition; the GUID is the existing
personal-edition URL, retained as a stable feed identity independently of the
HTML canonical URL. Plainsight Systems uses that identity to avoid
listing a syndicated lesson twice. Its combined writing index refreshes this
feed automatically, so publishing a lesson requires no matching hub edit.

```sh
python3 scripts/site.py build --base-url https://example.org/cradle/
```

Replace the example URL with the actual destination, including its project subpath and trailing slash.
Production output goes to ignored `dist/`; explicit preview builds go to ignored `dist-preview/`. The build
checks links, anchors, assets, and publication boundaries. Never deploy preview output.

GitHub Pages deploys the production artifact through `.github/workflows/pages.yml`. The repository's Pages
source must be set to GitHub Actions. Set `params.repository` in `web/hugo.toml` before publishing lessons so
code snapshot links can resolve; published lessons require locally available release tags.

The personal site receives separate exports from the same article sources. Both editions declare the
Cradle lesson URL as canonical, including Open Graph metadata. The personal site owns its presentation
and deployment. See [commands and publishing](../scripts/README.md) for export,
destination-edit protection, testing, and deployment setup.

## Presentation and licensing

Navigation, the mobile contents disclosure, math, and reading work without JavaScript. Hugo renders equations
as MathML using its [embedded math renderer](https://gohugo.io/functions/transform/tomath/). Images retain their
aspect ratios, long code and tables scroll within the article, and reduced motion is respected. The artwork
comes from `docs/assets/cradle-readme.png`; responsive WebP versions are generated at build time.

Site code and configuration use Apache 2.0; prose and original artwork use CC BY 4.0. The Plex fonts retain
their SIL Open Font License. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE) for scope and attribution.

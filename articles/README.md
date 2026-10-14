# Articles

This is the authoritative source for "Let's Build a Transformer!". Each installment gets a numbered folder with
`index.md` and its images. The setup prologue is published in `00-getting-the-cradle-ready/`; lesson 1 is published in `01-the-cradle/`.

Use TOML front matter, with an explicit draft flag and publication date:

```toml
+++
title = "The cradle"
description = "Run our first C# kernel on the GPU."
lesson = 1
date = 2026-10-12
draft = true
start_tag = "lesson-00"
end_tag = "lesson-01"
personal_slug = "cradle-01-the-cradle"
publish_assets = []
tags = ["C#", "GPU", "Transformers"]
math = false
+++
```

The date above illustrates the format; choose the actual publication date. No article is created by this example.
Use `lesson = 0` and folder `00-getting-the-cradle-ready` for the prologue. It has an empty
`start_tag` and ends at `lesson-00`. It appears before the 18 numbered lessons and does not count toward their
publication total. Name subsequent folders `01-the-cradle`, `02-buffers-and-shapes`, and so on. Titles and dates may change while drafting;
keep published folder names and `personal_slug` stable. The planned index is in `web/data/lessons.json`; setup text is in `web/data/prologue.json`.

Lesson 1 starts from `lesson-00`. Its article explains the backend metadata, device selection, and kernel-build test as part of the lesson; the shared build scripts are already in the starting snapshot. Every numbered lesson requires the previous lesson's tag in `start_tag`. The
completed tag must match the lesson number. Correction tags such as `lesson-03.1` are accepted. Production builds
and exports verify these tags exist locally; publish the tags with the code when releasing an article.

## Portable content

Write ordinary Markdown, with fenced code blocks and a language identifier. Avoid site-specific Hugo shortcodes.
Headings should begin at `##`; the page template supplies the title. Use descriptive image alt text.

Store images inside the article's `images/` folder, explicitly list them in `publish_assets`, and reference them
with relative Markdown links such as `![Buffer layout](images/buffers.svg)`. Only selected PNG, JPEG, WebP, SVG,
GIF, and AVIF files can leave the article folder. Files such as notes and unselected images are never copied.
Symlinks, private dotfiles, and parent-directory traversal are rejected.

Link to another installment using `[Buffers and shapes](lesson:02)` or `[Indexing](lesson:02#indexing)`. Use `lesson:00` to link to the prologue.
The publishing commands resolve these for each destination and reject links to unpublished lessons in production.
External HTTPS links and same-page anchors also work. Avoid absolute project-site paths in the shared article.

The Cradle site renders `\( ... \)` inline and `\[ ... \]` or `$$ ... $$` display equations to MathML at build time.
Set `math = true` on articles with formulas. The exporter renders those spans to MathML too, preserving the
surrounding Markdown. This avoids depending on the personal site's Markdown delimiter handling or client-side
math renderer. Use fenced code blocks for literal formula examples; indented code blocks are not supported by
the formula exporter.

## Publishing

Full articles publish to both andrewphunter.com and Cradle's GitHub Pages site. The personal article URL is the
canonical URL, derived from `personal_slug`. Publish the personal edition before, or alongside, the project-site
edition so that canonical destination exists. Sources remain here; each destination owns its presentation and
deployment. See [the publishing commands](../scripts/README.md).

Drafts and future-dated articles appear only in explicit local preview builds. Changing a draft to public does
not export it to the personal site automatically. The example article at `/preview/` is a site fixture, not an
installment, and never enters a production build or export.

Keep private notes, reviews and editorial planning outside the publishable repository.

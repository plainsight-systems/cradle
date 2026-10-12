"""Render formula spans for destinations whose Markdown parser consumes TeX delimiters."""

import json
from pathlib import Path
import re
import subprocess
import tempfile

from content import HUGO_VERSION, PublicationError

# Fences and inline code win before formula delimiters. Code samples stay literal.
TOKENS = re.compile(
    r"(?P<fence>^(?P<ticks>`{3,}|~{3,})[^\n]*\n.*?^(?P=ticks)[ \t]*$)"
    r"|(?P<code>(?P<backticks>`+)(?!`).*?(?P=backticks)(?!`))"
    r"|(?P<display>\\\[(?P<bracket>.*?)\\\]|\$\$(?P<dollar>.*?)\$\$)"
    r"|(?P<inline>\\\((?P<paren>.*?)\\\))",
    re.M | re.S,
)


def render_math(body):
    matches = [m for m in TOKENS.finditer(body) if m.group("display") or m.group("inline")]
    if not matches:
        return body
    version = subprocess.check_output(["hugo", "version"], text=True)
    if not re.match(rf"hugo v{re.escape(HUGO_VERSION)}(?:\+| )", version):
        raise PublicationError(f"Formula export requires Hugo {HUGO_VERSION}")
    formulas = [{"tex": next(m[k] for k in ("bracket", "dollar", "paren") if m[k] is not None),
                 "block": m["display"] is not None} for m in matches]
    with tempfile.TemporaryDirectory(prefix="cradle-math-") as temp:
        root = Path(temp)
        (root / "data").mkdir()
        (root / "layouts").mkdir()
        (root / "hugo.toml").write_text('disableKinds = ["taxonomy", "term", "RSS", "sitemap"]\n[outputs]\nhome = ["JSON"]\n')
        (root / "data/formulas.json").write_text(json.dumps(formulas))
        (root / "layouts/index.json").write_text(
            '{{ $result := slice }}{{ range site.Data.formulas }}'
            '{{ $result = $result | append (string (transform.ToMath .tex (dict "displayMode" .block "output" "mathml"))) }}'
            '{{ end }}{{ $result | jsonify | safeJS }}')
        result = subprocess.run(["hugo", "--source", str(root)], capture_output=True, text=True)
        if result.returncode:
            raise PublicationError(f"Unable to render article formulas: {result.stderr.strip()}")
        rendered = json.loads((root / "public/index.json").read_text())
    parts = []
    cursor = 0
    for match, formula in zip(matches, rendered, strict=True):
        parts.append(body[cursor:match.start()])
        # Numeric entities preserve text inside MathML through another Markdown pass,
        # including the TeX annotation, without accidental backslash/emphasis parsing.
        formula = re.sub(r"(?<=>)[^<]+(?=<)", lambda m: "".join(f"&#{ord(c)};" for c in m[0]), formula)
        if match["display"]:
            formula = f'\n\n<div class="cradle-equation">\n{formula}\n</div>\n\n'
        parts.append(formula)
        cursor = match.end()
    parts.append(body[cursor:])
    return "".join(parts)

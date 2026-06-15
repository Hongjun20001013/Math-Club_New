import re
from typing import Any, Optional

from tikz_svg import replace_tikz_with_svg_html


def _extract_braced_content(text: str, start_idx: int):
    """
    Extract {...} content with nested brace support.
    Returns (content, next_index_after_closing_brace) or (None, start_idx) on failure.
    """
    if start_idx >= len(text) or text[start_idx] != "{":
        return None, start_idx

    depth = 0
    i = start_idx
    content_start = start_idx + 1
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[content_start:i], i + 1
        i += 1

    return None, start_idx


def _extract_choiceboxes(block: str):
    """
    Parse \\choicebox{A}{...} blocks while preserving nested braces inside choice text.
    """
    choices_map = {}
    marker = r"\choicebox"
    i = 0
    while True:
        idx = block.find(marker, i)
        if idx == -1:
            break

        j = idx + len(marker)
        while j < len(block) and block[j].isspace():
            j += 1

        letter, j = _extract_braced_content(block, j)
        if letter is None:
            i = idx + len(marker)
            continue

        while j < len(block) and block[j].isspace():
            j += 1

        content, j = _extract_braced_content(block, j)
        if content is None:
            i = idx + len(marker)
            continue

        letter = letter.strip().upper()
        if letter in {"A", "B", "C", "D"}:
            choices_map[letter] = content

        i = j

    return choices_map


def _contains_table_ampersand(text: str) -> bool:
    """Detect LaTeX/table column separators, ignoring &#...; currency entities."""
    scratch = re.sub(r"&#\d+;", "", text)
    scratch = re.sub(r"&(?:amp|lt|gt|quot|apos|nbsp);", "", scratch, flags=re.I)
    return "&" in scratch


def _convert_align_blocks_to_display_math(text: str) -> str:
    """Turn amsmath align blocks into \\[ ... \\] so MathJax renders them."""
    def repl(m: re.Match[str]) -> str:
        body = m.group(1).strip()
        return f"\\[\n{body}\n\\]"

    return re.sub(
        r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}",
        repl,
        text,
        flags=re.S,
    )


def _normalize_arc_notation(text: str) -> str:
    """Map publisher arc macros to MathJax-safe \\overset{\\frown}{...}."""
    text = re.sub(r"\\wideparen\{([^{}]+)\}", r"\\overset{\\frown}{\1}", text)
    text = re.sub(r"\\overarc\{([^{}]+)\}", r"\\overset{\\frown}{\1}", text)
    return text


def clean_math(text: str) -> str:
    """
    Normalize mixed LaTeX math delimiters for MathJax:
    - $$...$$  -> \\[...\\]
    - $...$    -> \\(...\\)  (only unescaped dollars)
    - \\$      -> $
    """
    text_vault: list[str] = []

    def _shield_text_block(match: re.Match[str]) -> str:
        idx = len(text_vault)
        text_vault.append(match.group(0))
        return f"%%CMTEXT{idx}%%"

    # Keep \\text{...} literal so $...$ inside labels (e.g. underbrace) is not broken.
    text = re.sub(
        r"\\text\{((?:[^{}]|\{[^{}]*\})*)\}",
        _shield_text_block,
        text,
    )
    # Protect escaped currency dollars first so they are never parsed as math delimiters.
    text = text.replace(r"\$", "&#36;")
    # Display math first to avoid being consumed by inline conversion.
    text = re.sub(r"(?<!\\)\$\$(.*?)(?<!\\)\$\$", r"\\[\1\\]", text, flags=re.S)
    # Inline math, skipping escaped currency dollars such as \$5.
    # Use \displaystyle for more "math-like" rendering (clearer fractions/radicals).
    text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", r"\\(\\displaystyle \1\\)", text, flags=re.S)
    for idx, block in enumerate(text_vault):
        text = text.replace(f"%%CMTEXT{idx}%%", block)
    return text


def _convert_latex_lists(text: str) -> str:
    """
    Turn \\begin{itemize} / \\begin{enumerate} blocks into HTML lists so they
    are not shown as raw LaTeX. Math inside items stays as \\( ... \\) for MathJax.
    """

    def itemize_repl(match: Any) -> str:
        body = match.group(1).strip()
        parts = re.split(r"\\item\s*", body)
        lis = []
        for chunk in parts:
            chunk = chunk.strip()
            if not chunk:
                continue
            mlab = re.match(r"^\[([^\]]*)\]\s*(.*)$", chunk, re.S)
            if mlab:
                marker, inner = mlab.group(1), mlab.group(2).strip()
                lis.append(
                    '<li class="stem-li-labeled">'
                    f'<span class="stem-li-marker">{marker}</span> '
                    f'<span class="stem-li-body">{inner}</span>'
                    "</li>"
                )
            else:
                lis.append(f"<li>{chunk}</li>")
        return '<ul class="stem-itemize">' + "".join(lis) + "</ul>"

    def enumerate_repl(match: Any) -> str:
        body = match.group(1).strip()
        parts = re.split(r"\\item\s*", body)
        lis = []
        for chunk in parts:
            chunk = chunk.strip()
            if not chunk:
                continue
            mlab = re.match(r"^\[([^\]]*)\]\s*(.*)$", chunk, re.S)
            if mlab:
                marker, inner = mlab.group(1), mlab.group(2).strip()
                lis.append(
                    '<li class="stem-li-labeled">'
                    f'<span class="stem-li-marker">{marker}</span> '
                    f'<span class="stem-li-body">{inner}</span>'
                    "</li>"
                )
            else:
                lis.append(f"<li>{chunk}</li>")
        return '<ol class="stem-enumerate">' + "".join(lis) + "</ol>"

    # Convert innermost list environments first so nested itemize/enumerate parse correctly.
    inner_itemize = re.compile(
        r"\\begin\{itemize\}((?:[^\\]|\\(?!begin\{itemize\}))*?)\\end\{itemize\}",
        re.S,
    )
    while inner_itemize.search(text):
        text = inner_itemize.sub(itemize_repl, text, count=1)
    inner_enumerate = re.compile(
        r"\\begin\{enumerate\}(?:\[[^\]]*\])?"
        r"((?:[^\\]|\\(?!begin\{enumerate\}))*?)\\end\{enumerate\}",
        re.S,
    )
    while inner_enumerate.search(text):
        text = inner_enumerate.sub(enumerate_repl, text, count=1)
    return text


def strip_document_noise(text: str) -> str:
    """
    Remove publisher headers, PDF page markers, and other boilerplate lines
    that sometimes appear when content is copied from PDFs or master docs.
    """
    lines_out = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", line):
            continue
        if re.match(r"^Novel Prep SAT", line, re.I):
            continue
        if re.match(r"^Jack Zeng\s*$", line, re.I):
            continue
        lines_out.append(raw.rstrip())
    return "\n".join(lines_out)


def _clean_table_cell(cell: str) -> str:
    """Strip LaTeX text wrappers from array/tabular cells before HTML output."""
    cell = cell.strip()
    for _ in range(8):
        updated = re.sub(
            r"\\(?:text|textbf|mathrm|textit|emph)\{([^{}]*)\}",
            r"\1",
            cell,
        )
        if updated == cell:
            break
        cell = updated
    cell = cell.replace("--", "–")
    cell = cell.replace(r"\%", "%")
    cell = cell.replace("{,}", ",")
    # Percent signs must survive clean_latex_junk comment stripping in HTML tables.
    cell = cell.replace("%", "&#37;")
    return cell.strip()


def _parse_table_cell(cell: str) -> tuple[int, str]:
    """Return (colspan, cleaned cell HTML) for a tabular cell."""
    cell = cell.strip()
    m = re.match(r"\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*)\}\s*$", cell, re.S)
    if m:
        return int(m.group(1)), _clean_table_cell(m.group(2))
    return 1, _clean_table_cell(cell)


def _array_body_to_html_table(body: str) -> str:
    """Turn LaTeX array/tabular body (rows split by \\\\, cols by &) into an HTML table."""
    body = body.strip()
    rows_raw = re.split(r"\\\\", body)
    rows: list[list[tuple[int, str]]] = []
    for raw in rows_raw:
        r = raw.strip()
        if not r:
            continue
        if re.fullmatch(r"\\hline\s*", r):
            continue
        r = re.sub(r"^\\hline\s*", "", r)
        r = re.sub(r"\s*\\hline\s*$", "", r).strip()
        if not r:
            continue
        rows.append([_parse_table_cell(c) for c in r.split("&")])
    if not rows:
        return ""
    parts = [
        '<div class="stem-table-wrap"><table class="stem-table">',
        "<thead><tr>",
    ]
    for span, c in rows[0]:
        if span > 1:
            parts.append(f'<th colspan="{span}">{c}</th>')
        else:
            parts.append(f"<th>{c}</th>")
    parts.extend(["</tr></thead>", "<tbody>"])
    for row in rows[1:]:
        parts.append("<tr>")
        for span, c in row:
            if span > 1:
                parts.append(f'<td colspan="{span}">{c}</td>')
            else:
                parts.append(f"<td>{c}</td>")
        parts.append("</tr>")
    parts.extend(["</tbody></table></div>"])
    return "".join(parts)


def latex_array_and_tabular_to_html(text: str) -> str:
    """Convert array/tabular environments to HTML before other cleanup (avoids stray & for MathJax)."""
    text = re.sub(
        r"\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}",
        lambda m: _array_body_to_html_table(m.group(1)),
        text,
        flags=re.S,
    )
    text = re.sub(
        r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}",
        lambda m: _array_body_to_html_table(m.group(1)),
        text,
        flags=re.S,
    )
    text = re.sub(
        r"\\\[\s*(<div class=\"stem-table-wrap\">.*?</div>)\s*\\\]",
        r"\1",
        text,
        flags=re.S,
    )
    return text


_AMSMATH_ENV_NAMES = (
    "aligned",
    "alignedat",
    "gathered",
    "cases",
    "split",
    "align*",
    "align",
    "gather*",
    "gather",
    "multline*",
    "multline",
)


def _shield_amsmath_environments(text: str) -> tuple[str, list[str]]:
    """
    Temporarily remove amsmath blocks so global \\\\ -> newline does not strip
    row breaks MathJax needs inside aligned / align / cases / etc.
    """
    vault: list[str] = []
    for env in _AMSMATH_ENV_NAMES:
        pat = re.compile(
            rf"\\begin\{{{re.escape(env)}\}}.*?\\end\{{{re.escape(env)}\}}",
            re.DOTALL,
        )
        while True:
            m = pat.search(text)
            if not m:
                break
            vault.append(m.group(0))
            text = pat.sub(f"<<<AMSMATH_{len(vault) - 1}>>>", text, count=1)
    return text, vault


def _unshield_amsmath(text: str, vault: list[str]) -> str:
    for i, chunk in enumerate(vault):
        text = text.replace(f"<<<AMSMATH_{i}>>>", chunk)
    return text


def clean_latex_junk(text: str) -> str:
    """
    清理你模板里的无用 latex 指令
    """
    # TeX comments: unescaped % through end of line (e.g. \choicebox{A}{% newline)
    def _strip_tex_comments(s: str) -> str:
        table_vault: list[str] = []

        def _vault_tables(text: str) -> str:
            pat = re.compile(r'<div class="stem-table-wrap">.*?</div>', re.S)

            def repl(m: re.Match[str]) -> str:
                table_vault.append(m.group(0))
                return f"<<<HTML_TABLE_{len(table_vault) - 1}>>>"

            return pat.sub(repl, text)

        s = _vault_tables(s)
        out: list[str] = []
        for ln in s.splitlines():
            out.append(re.sub(r"(?<!\\)%.*$", "", ln).rstrip())
        s = "\n".join(out)
        for i, chunk in enumerate(table_vault):
            s = s.replace(f"<<<HTML_TABLE_{i}>>>", chunk)
        return s

    text = _strip_tex_comments(text)
    text, _amsmath_vault = _shield_amsmath_environments(text)
    text = re.sub(r"\\newpage\s*", "", text)
    text = re.sub(r"\\pagebreak\s*", "", text)
    text = re.sub(r"\\cleardoublepage\s*", "", text)
    text = re.sub(r"\\vspace\{.*?\}", "", text, flags=re.S)
    # \hspace / \hspace* outside \(...\) is left as raw text; MathJax won't render it.
    text = re.sub(r"\\hspace\*?\s*\{[^}]*\}", "  ", text)
    text = re.sub(r"\\noindent", "", text)
    text = re.sub(r"\\renewcommand\{.*?\}\{.*?\}", "", text, flags=re.S)
    text = re.sub(r"\\begin\{center\}", "", text)
    text = re.sub(r"\\end\{center\}", "", text)
    text = re.sub(r"\\hline", "", text)
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", text)
    # Do not strip \\text{} here — it breaks MathJax inside \\(...\\) (e.g. ^\\circ\\text{C}, \\text{cm}).
    # Table cells are normalized earlier in _clean_table_cell().
    # Turn LaTeX table line breaks into readable line breaks (not inside amsmath).
    text = re.sub(r"\\\\", "\n", text)
    text = _unshield_amsmath(text, _amsmath_vault)
    text = _convert_align_blocks_to_display_math(text)
    # Normalize thousands separator style from 350{,}000 -> 350,000
    text = text.replace("{,}", ",")
    text = text.replace(r"\%", "%")
    text = strip_document_noise(text)
    text = _normalize_arc_notation(text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _pipe_lines_to_table_html(text: str) -> Optional[str]:
    """
    Convert pipe-separated lines into an HTML table when possible.
    Returns None when the content does not look tabular.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    separator = None
    if sum(1 for line in lines if "|" in line) >= 2:
        separator = "|"
    elif sum(1 for line in lines if _contains_table_ampersand(line)) >= 2:
        separator = "&"
    if separator is None:
        return None

    pipe_lines = [line for line in lines if separator in line]
    rows = []
    for row_line in pipe_lines:
        cells = [c.strip() for c in row_line.split(separator)]
        if len(cells) >= 2:
            rows.append(cells)
    if len(rows) < 2:
        return None

    html_parts = ['<div class="stem-table-wrap"><table class="stem-table">']
    html_parts.append("<thead><tr>")
    for cell in rows[0]:
        html_parts.append(f"<th>{cell}</th>")
    html_parts.append("</tr></thead><tbody>")
    for row in rows[1:]:
        html_parts.append("<tr>")
        for cell in row:
            html_parts.append(f"<td>{cell}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table></div>")
    return "\n".join(html_parts)


def _format_stem_html(text: str) -> str:
    """
    Convert cleaned stem text into readable HTML:
    - consecutive pipe-separated lines => table
    - normal lines => paragraph blocks
    """
    lines = [line.strip() for line in text.split("\n")]
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        # Pre-rendered list HTML (from _convert_latex_lists): do not wrap in <p>.
        stripped = line.strip()
        if stripped.startswith("<ul ") or stripped.startswith("<ol "):
            html_parts.append(line)
            i += 1
            continue

        if stripped.startswith("<div "):
            html_parts.append(line)
            i += 1
            continue

        # Preserve display-math blocks so MathJax can parse them as a unit.
        if line == r"\[":
            block_lines = [line]
            i += 1
            while i < len(lines):
                block_lines.append(lines[i].strip())
                if lines[i].strip() == r"\]":
                    i += 1
                    break
                i += 1
            html_parts.append(f"<div class=\"stem-math-block\">{chr(10).join(block_lines)}</div>")
            continue

        if "|" in line:
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                current = lines[i].strip()
                if current:
                    table_lines.append(current)
                i += 1

            # Treat 2+ rows as tabular data.
            if len(table_lines) >= 2:
                rows = []
                for row_line in table_lines:
                    cells = [c.strip() for c in row_line.split("|")]
                    rows.append(cells)

                html_parts.append('<div class="stem-table-wrap"><table class="stem-table">')
                header = rows[0]
                html_parts.append("<thead><tr>")
                for cell in header:
                    html_parts.append(f"<th>{cell}</th>")
                html_parts.append("</tr></thead>")
                html_parts.append("<tbody>")
                for row in rows[1:]:
                    html_parts.append("<tr>")
                    for cell in row:
                        html_parts.append(f"<td>{cell}</td>")
                    html_parts.append("</tr>")
                html_parts.append("</tbody></table></div>")
                continue

            # Single pipe line: keep as paragraph fallback.
            html_parts.append(f"<p>{table_lines[0]}</p>")
            continue

        if _contains_table_ampersand(line):
            table_lines = []
            while i < len(lines) and _contains_table_ampersand(lines[i]):
                current = lines[i].strip()
                if current:
                    table_lines.append(current)
                i += 1
            if len(table_lines) >= 2:
                rows = []
                for row_line in table_lines:
                    cells = [c.strip() for c in row_line.split("&")]
                    rows.append(cells)

                html_parts.append('<div class="stem-table-wrap"><table class="stem-table">')
                header = rows[0]
                html_parts.append("<thead><tr>")
                for cell in header:
                    html_parts.append(f"<th>{cell}</th>")
                html_parts.append("</tr></thead>")
                html_parts.append("<tbody>")
                for row in rows[1:]:
                    html_parts.append("<tr>")
                    for cell in row:
                        html_parts.append(f"<td>{cell}</td>")
                    html_parts.append("</tr>")
                html_parts.append("</tbody></table></div>")
                continue
            html_parts.append(f"<p>{table_lines[0]}</p>")
            continue

        html_parts.append(f"<p>{line}</p>")
        i += 1

    return "\n".join(html_parts)


def _replace_includegraphics_static_prefix(text: str, prefix: str) -> str:
    """Turn \\includegraphics{file} into <img> under a static URL prefix (e.g. Unit 3 figures)."""
    base = prefix.rstrip("/")
    # Hard drills and Unit 4 geometry share compact figure sizing (see .stem-figure-img--hard).
    img_class = (
        "stem-figure-img stem-figure-img--hard"
        if "/hard" in base or "/unit4" in base
        else "stem-figure-img"
    )

    def repl(m: Any) -> str:
        fname = m.group(1).strip()
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", fname)
        if not safe:
            return ""
        return (
            f'<img class="{img_class}" src="{base}/{safe}" '
            'alt="" loading="lazy" />'
        )

    return re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", repl, text)


def parse_tex_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    norm = path.replace("\\", "/")
    if "Unit_3_PS" in norm or "/problem_solving/" in norm:
        content = _replace_includegraphics_static_prefix(content, "/static/unit3/")
    if "Unit_4_Geometry" in norm or "/geometry/" in norm:
        content = _replace_includegraphics_static_prefix(content, "/static/unit4/")
    if "/hard/" in norm:
        content = _replace_includegraphics_static_prefix(content, "/static/hard/")

    questions = []

    # Split on markforreview; blocks[0] is preamble before the first question.
    blocks = content.split(r"\noindent\markforreview")

    for block in blocks[1:]:
        if not block.strip():
            continue

        # ------------------ Stem ------------------
        stem_part = block.split(r"\choicebox")[0]
        stem_part = latex_array_and_tabular_to_html(stem_part)
        stem_part = replace_tikz_with_svg_html(stem_part)
        stem_part = clean_latex_junk(stem_part)
        stem_part = _convert_latex_lists(stem_part)
        stem_part = clean_math(stem_part)
        stem_part = _mathjax_safe_lt_in_tex_math(stem_part)
        stem_part = _format_stem_html(stem_part)

        # ------------------ Choices ------------------
        choices = ["", "", "", ""]  # A B C D slots
        raw_choices = _extract_choiceboxes(block)

        for letter, content in raw_choices.items():
            idx = ord(letter) - ord("A")
            if idx < 0 or idx > 3:
                continue
            content = latex_array_and_tabular_to_html(content)
            content = replace_tikz_with_svg_html(content)
            content = clean_latex_junk(content)
            content = _convert_latex_lists(content)
            table_html = _pipe_lines_to_table_html(content)
            if table_html:
                content = table_html
            else:
                content = clean_math(content)
            content = _mathjax_safe_lt_in_tex_math(content)
            choices[idx] = content

        letters_present = {L for L in "ABCD" if raw_choices.get(L)}
        is_mcq = letters_present == set("ABCD") and all(choices)

        if is_mcq:
            questions.append(
                {
                    "stem": stem_part,
                    "choices": choices,
                    "question_kind": "mcq",
                }
            )
        else:
            questions.append(
                {
                    "stem": stem_part,
                    "choices": [],
                    "question_kind": "free_response",
                }
            )

    return questions


_PLACEMENT_GRAPH_NAME = re.compile(
    r"\\newcommand\{\\(graph(?:line|para|rad|abs|circle)[A-E])\}\s*\{"
)


def _collect_placement_graph_macro_bodies(tex: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _PLACEMENT_GRAPH_NAME.finditer(tex):
        name = m.group(1)
        brace_at = m.end() - 1
        body, _ = _extract_braced_content(tex, brace_at)
        if body:
            out[name] = body
    return out


def _expand_placement_graph_macros(text: str, macros: dict[str, str]) -> str:
    for name, body in macros.items():
        text = text.replace("\\" + name, body)
    return text


def _replace_includegraphics_with_img(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        fname = m.group(1).strip()
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", fname)
        if not safe:
            return ""
        # Q64 diagram: vector SVG (browser-safe) replaces raster placeholder name in TeX.
        if safe == "1.png":
            safe = "1.svg"
        return (
            f'<img class="stem-figure-img" src="/static/placement/{safe}" '
            'alt="" loading="lazy" />'
        )

    return re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", repl, text)


def _strip_needspace(text: str) -> str:
    return re.sub(r"\\needspace\*?\s*\{[^}]*\}", "", text)


def _placement_part_meta(n: int) -> tuple[str, str]:
    """1-based question index → (section code, English title)."""
    if n <= 15:
        return "I", "Part I — Foundations and Algebra Skills"
    if n <= 30:
        return "II", "Part II — Exponents, Rational Expressions, and Functions"
    if n <= 45:
        return "III", "Part III — Graphs, Geometry, and Radical Functions"
    if n <= 60:
        return "IV", "Part IV — Functions, Trigonometry, and Precalculus"
    return "V", "Part V — Geometry, Solid Geometry, and Advanced Readiness"


def _find_balanced_mc_args(block: str, mc_start: int) -> Optional[tuple[list[str], int]]:
    """
    After ``\\mc``, read five braced groups (supports nested ``{...}``).
    Returns (args, index_after_fifth_group).
    """
    j = mc_start + len(r"\mc")
    args: list[str] = []
    for _ in range(5):
        while j < len(block) and block[j].isspace():
            j += 1
        arg, j = _extract_braced_content(block, j)
        if arg is None:
            return None
        args.append(arg)
    return args, j


def _split_enumerate_choice_body(body: str) -> list[str]:
    parts = re.split(r"\\item\s*", body.strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_placement_choices(block: str) -> Optional[tuple[str, list[str]]]:
    """
    From a single-question TeX chunk (after ``\\circnum``), return (raw_stem, raw_choice_texs).
    Discards trailing part headers / page breaks after the choice block.
    """
    block = _strip_needspace(block)
    mc_m = re.search(r"\\mc(?![A-Za-z])", block)
    en_m = re.search(r"\\begin\{enumerate\}", block)

    use_mc = False
    use_en = False
    if mc_m and en_m:
        use_mc = mc_m.start() <= en_m.start()
        use_en = not use_mc
    elif mc_m:
        use_mc = True
    elif en_m:
        use_en = True
    else:
        return None

    if use_mc:
        start = mc_m.start()
        parsed = _find_balanced_mc_args(block, start)
        if not parsed:
            return None
        args, end = parsed
        stem_raw = block[:start].strip()
        return stem_raw, list(args)

    start = en_m.start()
    em = re.search(
        r"\\begin\{enumerate\}(?:\[[^\]]*\])?(.*?)\\end\{enumerate\}",
        block[start:],
        flags=re.S,
    )
    if not em:
        return None
    body = em.group(1)
    end_local = em.end() + start
    items = _split_enumerate_choice_body(body)
    if len(items) != 5:
        return None
    stem_raw = block[:start].strip()
    return stem_raw, items


def _mathjax_safe_lt_in_tex_math(s: str) -> str:
    """
    Inside ``\\(...\\)`` and ``\\[...\\]``, bare ``<`` is parsed as an HTML tag opener in the browser.
    Replace with TeX ``\\lt`` (MathJax) while preserving ``<=`` / ``>=``.
    """
    parts: list[str] = []
    i = 0
    n = len(s)

    def _fix_inner(inner: str) -> str:
        if "<div" in inner or "<svg" in inner or "<table" in inner:
            return inner
        inner = inner.replace("<=", "§LE§").replace(">=", "§GE§")
        inner = inner.replace("<", r"\lt ")
        inner = re.sub(r"(?<!\\)%", r"\\%", inner)
        return inner.replace("§LE§", "<=").replace("§GE§", ">=")

    while i < n:
        if s.startswith("\\(", i):
            j = s.find("\\)", i + 2)
            if j == -1:
                parts.append(s[i:])
                break
            inner = _fix_inner(s[i + 2 : j])
            parts.append("\\(" + inner + "\\)")
            i = j + 2
            continue
        if s.startswith("\\[", i):
            j = s.find("\\]", i + 2)
            if j == -1:
                parts.append(s[i:])
                break
            inner = _fix_inner(s[i + 2 : j])
            parts.append("\\[" + inner + "\\]")
            i = j + 2
            continue
        j_open = s.find("\\(", i + 1)
        j_br = s.find("\\[", i + 1)
        j = n
        if j_open != -1:
            j = min(j, j_open)
        if j_br != -1:
            j = min(j, j_br)
        parts.append(s[i:j])
        i = j
    return "".join(parts)


def _unwrap_display_math_brackets_around_figure_html(text: str) -> str:
    r"""
    TeX often wraps ``\begin{tikzpicture}...\end{tikzpicture}`` in ``\[ ... \]``.
    After TikZ becomes HTML, those delimiters are not math: strip the wrapper so
    ``\[`` / ``\]`` do not appear on the page or inside ``stem-math-block``.
    """
    return re.sub(
        r"\\\[\s*((?:<div class=\"stem-figure-wrap[^\"]*\"[\s\S]*?</div>\s*)+)\\\]",
        r"\1",
        text,
        flags=re.S,
    )


def _strip_leading_tex_control_space(s: str) -> str:
    """Remove TeX control-space (``\\ ``) after ``\\circnum`` so MathJax does not show a stray backslash."""
    t = s.lstrip()
    while True:
        if not t.startswith("\\"):
            break
        m = re.match(r"^\\\s+", t)
        if not m:
            break
        t = t[m.end() :]
    return t


def _format_placement_choice_html(raw: str) -> str:
    raw = _strip_needspace(raw)
    raw = _strip_leading_tex_control_space(raw)
    raw = latex_array_and_tabular_to_html(raw)
    raw = replace_tikz_with_svg_html(raw)
    raw = clean_latex_junk(raw)
    raw = _convert_latex_lists(raw)
    table_html = _pipe_lines_to_table_html(raw)
    if table_html:
        raw = table_html
    else:
        raw = clean_math(raw)
    raw = _mathjax_safe_lt_in_tex_math(raw)
    return raw


def _format_placement_stem_html(raw: str) -> str:
    raw = _strip_needspace(raw)
    raw = _strip_leading_tex_control_space(raw)
    raw = latex_array_and_tabular_to_html(raw)
    raw = replace_tikz_with_svg_html(raw)
    raw = _unwrap_display_math_brackets_around_figure_html(raw)
    raw = clean_latex_junk(raw)
    raw = _convert_latex_lists(raw)
    raw = clean_math(raw)
    raw = _mathjax_safe_lt_in_tex_math(raw)
    return _format_stem_html(raw)


def parse_placement_answer_key(tex: str) -> dict[int, str]:
    """
    Parse ``n. L`` entries (L is A–E) from the Answer Key ``array`` block.
    """
    out: dict[int, str] = {}
    # TeX uses ``.\ `` (control space) between number and letter in the key table.
    for m in re.finditer(r"(\d+)\.(?:\\\s+|\s+)([A-E])\b", tex):
        n = int(m.group(1))
        if 1 <= n <= 70:
            out[n] = m.group(2).upper()
    return out


def parse_placement_tex_file(path: str):
    """
    Parse Novel Prep ``Placement_Test.tex`` style items: ``\\circnum{n}`` stem,
    then ``\\mc{a}{b}{c}{d}{e}`` or a five-item ``enumerate`` (graph options).
    Only questions 1–70 are returned; answer grid / teacher pages are ignored.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    doc_i = content.find(r"\begin{document}")
    body = content[doc_i:] if doc_i != -1 else content
    macros = _collect_placement_graph_macro_bodies(content)

    circ = list(re.finditer(r"\\circnum\{(\d+)\}", body))
    by_num: dict[int, tuple[int, int]] = {}
    for idx, m in enumerate(circ):
        n = int(m.group(1))
        if n < 1 or n > 70:
            continue
        start = m.end()
        end = circ[idx + 1].start() if idx + 1 < len(circ) else len(body)
        by_num[n] = (start, end)

    questions: list[dict[str, Any]] = []
    for n in range(1, 71):
        span = by_num.get(n)
        if not span:
            continue
        chunk = body[span[0] : span[1]]
        chunk = _expand_placement_graph_macros(chunk, macros)
        extracted = _extract_placement_choices(chunk)
        if not extracted:
            continue
        stem_raw, choice_raws = extracted
        stem_raw = _replace_includegraphics_with_img(stem_raw)
        stem_html = _format_placement_stem_html(stem_raw)
        choices_html = [_format_placement_choice_html(c) for c in choice_raws]
        sec, title_en = _placement_part_meta(n)
        questions.append(
            {
                "stem": stem_html,
                "choices": choices_html,
                "question_kind": "mcq5",
                "display_number": n,
                "knowledge_section": sec,
                "knowledge_section_title_en": title_en,
                "knowledge_section_title_zh": title_en,
            }
        )

    return questions

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
                let_m = re.match(r"^([A-D])\.\s*(.*)$", chunk, re.S)
                if let_m:
                    lis.append(
                        '<li class="stem-li-labeled">'
                        f'<span class="stem-li-marker">{let_m.group(1)}</span> '
                        f'<span class="stem-li-body">{let_m.group(2).strip()}</span>'
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
                let_m = re.match(r"^([A-D])\.\s*(.*)$", chunk, re.S)
                if let_m:
                    lis.append(
                        '<li class="stem-li-labeled">'
                        f'<span class="stem-li-marker">{let_m.group(1)}</span> '
                        f'<span class="stem-li-body">{let_m.group(2).strip()}</span>'
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


def _cell_needs_math_delimiters(cell: str) -> bool:
    """Detect plain-text LaTeX math in tabular/array cells (e.g. 2x^2 + 7x + 9)."""
    if not cell or re.search(r"\\\(|\\\[|\$", cell):
        return False
    if re.search(r"\\(?:overline|underline|phantom|frac)\b", cell):
        return True
    if re.search(r"\^[0-9{]", cell):
        return True
    if re.search(r"[0-9]*[a-zA-Z]\s*[-+*/]\s*[0-9a-zA-Z]", cell):
        return True
    return False


def _expand_dollar_math_segments(cell: str) -> str:
    """Turn `$p\\%$ of $x$` style cells into inline math plus prose."""
    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"\$(.+?)\$", cell):
        if m.start() > pos:
            prose = cell[pos : m.start()].strip()
            if prose:
                parts.append(prose.replace("%", "&#37;"))
        inner = m.group(1).strip()
        inner = inner.replace(r"\%", "%").replace("%", r"\%")
        parts.append(f"\\(\\displaystyle {inner}\\)")
        pos = m.end()
    if pos < len(cell):
        tail = cell[pos:].strip()
        if tail:
            parts.append(tail.replace("%", "&#37;"))
    return " ".join(parts)


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
    cell = re.sub(r"\\(?:~| )", " ", cell)
    cell = cell.replace("---", "—")
    cell = cell.replace("--", "–")
    cell = cell.replace("{,}", ",")
    if re.search(r"\$.+?\$", cell):
        return _expand_dollar_math_segments(cell)
    cell = cell.replace(r"\%", "%")
    cell = re.sub(
        r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
        r"\\(\\frac{\1}{\2}\\)",
        cell,
    )
    cell = re.sub(r"\\frac(\d)(\d)", r"\\(\\frac{\1}{\2}\\)", cell)
    cell = re.sub(r"\\;\s*", " ", cell)
    # Percent signs must survive clean_latex_junk comment stripping in HTML tables.
    cell = cell.replace("%", "&#37;")
    # Normalize $...$ once so clean_latex_junk does not nest MATHSEG vaults inside \(...\).
    m_dollar = re.fullmatch(r"\$(.+)\$", cell.strip(), flags=re.S)
    if m_dollar:
        inner = m_dollar.group(1).strip().replace("%", r"\%")
        cell = f"\\(\\displaystyle {inner}\\)"
    elif _cell_needs_math_delimiters(cell):
        cell = f"\\({cell}\\)"
    return cell.strip()


def _parse_table_cell(cell: str) -> tuple[int, str]:
    """Return (colspan, cleaned cell HTML) for a tabular cell."""
    cell = cell.strip()
    cell = re.sub(r"\\(?:rowcolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?\{[^}]*\}\s*", "", cell)
    m = re.match(r"\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*)\}\s*$", cell, re.S)
    if m:
        return int(m.group(1)), _clean_table_cell(m.group(2))
    return 1, _clean_table_cell(cell)


def _array_body_to_html_table(body: str) -> str:
    """Turn LaTeX array/tabular body (rows split by \\\\, cols by &) into an HTML table."""
    body = body.strip()
    body = re.sub(r"\\\\\[[^\]]*\]", r"\\\\", body)
    rows_raw = re.split(r"\\\\", body)
    rows: list[list[tuple[int, str]]] = []
    for raw in rows_raw:
        r = raw.strip()
        if not r:
            continue
        if re.fullmatch(r"\\(?:hline|toprule|midrule|bottomrule|addlinespace)\s*", r):
            continue
        r = re.sub(r"\\(?:rowcolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?\{[^}]*\}\s*", "", r)
        r = re.sub(r"^\\(?:hline|toprule|midrule|bottomrule)\s*", "", r)
        r = re.sub(r"\s*\\(?:hline|toprule|midrule|bottomrule)\s*$", "", r).strip()
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


def _tabularx_body_to_html(body: str) -> str:
    """Two-column tabularx (text & figure) → side-by-side layout; fallback to table."""
    body = body.strip()
    if "&" not in body:
        return _array_body_to_html_table(body)
    left, right = [part.strip() for part in body.split("&", 1)]
    if not left or not right:
        return _array_body_to_html_table(body)
    left_html = _clean_table_cell(left)
    return (
        '<div class="stem-figure-row stem-figure-row--stacked">'
        f'<div class="stem-figure-row__text">{left_html}</div>'
        f'<div class="stem-figure-row__fig">{right}</div>'
        "</div>"
    )


def _replace_tabularx_blocks(text: str) -> str:
    """Parse ``tabularx`` with nested-brace column specs (e.g. ``{@{}X r@{}}``)."""
    marker = r"\begin{tabularx}"
    out: list[str] = []
    last = 0
    while True:
        start = text.find(marker, last)
        if start == -1:
            out.append(text[last:])
            break
        out.append(text[last:start])
        i = start + len(marker)
        ok = True
        for _ in range(2):
            while i < len(text) and text[i].isspace():
                i += 1
            _arg, i = _extract_braced_content(text, i)
            if _arg is None:
                ok = False
                break
        end_tag = r"\end{tabularx}"
        end = text.find(end_tag, i) if ok else -1
        if end == -1:
            out.append(text[start:])
            break
        body = text[i:end].strip()
        out.append(_tabularx_body_to_html(body))
        last = end + len(end_tag)
    return "".join(out)


def _replace_latex_env_blocks(text: str, env: str, convert_body) -> str:
    """Replace \\begin{env}{...}...\\end{env} using balanced-brace column specs."""
    begin = rf"\begin{{{env}}}"
    end = rf"\end{{{env}}}"
    out: list[str] = []
    last = 0
    while True:
        idx = text.find(begin, last)
        if idx == -1:
            out.append(text[last:])
            break
        out.append(text[last:idx])
        pos = idx + len(begin)
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == "{":
            spec, pos = _extract_braced_content(text, pos)
            if spec is None:
                out.append(text[idx : idx + len(begin)])
                last = idx + len(begin)
                continue
        end_idx = text.find(end, pos)
        if end_idx == -1:
            out.append(text[idx:])
            break
        body = text[pos:end_idx]
        out.append(convert_body(body))
        last = end_idx + len(end)
    return "".join(out)


def latex_array_and_tabular_to_html(text: str) -> str:
    """Convert array/tabular environments to HTML before other cleanup (avoids stray & for MathJax)."""
    text = _replace_latex_env_blocks(text, "array", _array_body_to_html_table)
    text = _replace_latex_env_blocks(text, "tabular", _array_body_to_html_table)
    text = _replace_tabularx_blocks(text)
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


def _shield_math_delimited_segments(text: str) -> tuple[str, list[str]]:
    """Preserve ``$...$``, ``\\(...\\)``, and display math while normalizing row breaks."""
    vault: list[str] = []
    patterns = [
        r"(?<!\\)\$\$(?:(?!\$\$).)+?(?<!\\)\$\$",
        r"(?<!\\)\$(?:(?!\$).)+?(?<!\\)\$",
        r"\\\[(?:[^\]]|\\\])+?\\\]",
        r"\\\((?:[^)]|\\\))+?\\\)",
    ]
    for pat in patterns:
        while True:
            m = re.search(pat, text, flags=re.S)
            if not m:
                break
            vault.append(m.group(0))
            text = text[: m.start()] + f"<<<MATHSEG{len(vault) - 1}>>>" + text[m.end() :]
    return text, vault


def _unshield_math_delimited_segments(text: str, vault: list[str]) -> str:
    for i in range(len(vault) - 1, -1, -1):
        text = text.replace(f"<<<MATHSEG{i}>>>", vault[i])
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
    text, _mathseg_vault = _shield_math_delimited_segments(text)
    text = re.sub(r"\\newpage\s*", "", text)
    text = re.sub(r"\\pagebreak\s*", "", text)
    text = re.sub(r"\\cleardoublepage\s*", "", text)
    text = re.sub(r"\\vspace\{.*?\}", "", text, flags=re.S)
    text = re.sub(r"\\vspace\*?\{[^}]*\}", "", text)
    text = re.sub(r"\\hfill\b\s*", " ", text)
    text = re.sub(r"\\hfil\b\s*", " ", text)
    # \hspace / \hspace* outside \(...\) is left as raw text; MathJax won't render it.
    text = re.sub(r"\\hspace\*?\s*\{[^}]*\}", "  ", text)
    text = re.sub(r"\\noindent", "", text)
    text = re.sub(r"\\renewcommand\{.*?\}\{.*?\}", "", text, flags=re.S)
    text = re.sub(r"\\begin\{center\}", "", text)
    text = re.sub(r"\\end\{center\}", "", text)
    text = re.sub(r"\\begin\{multicols\}\{[^}]*\}", "", text)
    text = re.sub(r"\\end\{multicols\}", "", text)
    text = re.sub(r"\\hline", "", text)
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", text)
    # Do not strip \\text{} here — it breaks MathJax inside \\(...\\) (e.g. ^\\circ\\text{C}, \\text{cm}).
    # Table cells are normalized earlier in _clean_table_cell().
    # Turn LaTeX table line breaks into readable line breaks (not inside amsmath).
    text = re.sub(r"\\\\", "\n", text)
    text = _unshield_math_delimited_segments(text, _mathseg_vault)
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


PLACEMENT_MAX_QUESTIONS = 85


def _convert_array_in_display_math(text: str) -> str:
    """Turn ``\\begin{array}`` blocks inside ``\\[...\\]`` into HTML tables."""

    def repl_block(m: re.Match[str]) -> str:
        inner = m.group(1)
        if r"\begin{array}" not in inner and r"\begin{tabular}" not in inner:
            return m.group(0)
        converted = latex_array_and_tabular_to_html(inner)
        return converted if converted != inner else m.group(0)

    return re.sub(r"\\\[(.*?)\\\]", repl_block, text, flags=re.S)


def _normalize_placement_question_markers(body: str) -> str:
    """Support hybrid-gate ``\\q{n}`` and ``\\item[\\circnum{n}]`` markers."""
    cut = body.find(r"\section*{Student Answer Grid}")
    if cut != -1:
        body = body[:cut]
    body = re.sub(
        r"\\item\[\s*\\circnum\{(\d+)\}\s*\]",
        r"\\circnum{\1}",
        body,
    )
    body = re.sub(r"\\q\{(\d+)\}", r"\\circnum{\1}", body)
    return body


def _expand_placement_inline_diagram_macros(text: str) -> str:
    """Inline hybrid-gate diagram macros (e.g. circle chord figure for Q27)."""
    if r"\circleChordDiagram" not in text:
        return text
    chord_svg = (
        '<div class="stem-figure-wrap" role="img" aria-label="Circle with chords">'
        '<svg viewBox="0 0 220 220" width="220" height="220" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="110" cy="110" r="96" fill="none" stroke="#1f1f26" stroke-width="2.2"/>'
        '<line x1="28" y="94" x2="192" y="94" stroke="#1f1f26" stroke-width="2"/>'
        '<line x1="58" y="36" x2="58" y="184" stroke="#1f1f26" stroke-width="2"/>'
        '<line x1="28" y="94" x2="58" y="36" stroke="#1f1f26" stroke-width="2"/>'
        '<line x1="58" y="36" x2="192" y="94" stroke="#1f1f26" stroke-width="2"/>'
        '<text x="8" y="100" font-size="14" font-weight="600">A</text>'
        '<text x="44" y="28" font-size="14" font-weight="600">B</text>'
        '<text x="198" y="100" font-size="14" font-weight="600">C</text>'
        '<text x="44" y="206" font-size="14" font-weight="600">E</text>'
        '<text x="72" y="118" font-size="14" font-weight="600">D</text>'
        "</svg></div>"
    )
    text = text.replace(r"\circleChordDiagram", chord_svg)
    return text


def _placement_part_meta(n: int) -> tuple[str, str]:
    """1-based question index → (gate code, English title)."""
    if n <= 16:
        return "1", "Gate 1 — Algebra I Readiness"
    if n <= 37:
        return "2", "Gate 2 — Geometry Readiness"
    if n <= 53:
        return "3", "Gate 3 — Algebra II Readiness"
    if n <= 69:
        return "4", "Gate 4 — Precalculus Readiness"
    return "5", "Gate 5 — Calculus Readiness"


def _find_balanced_mc_args(block: str, mc_start: int) -> Optional[tuple[list[str], int]]:
    """
    After ``\\mc``, read four or five braced groups (supports nested ``{...}``).
    Returns (args, index_after_last_group).
    """
    j = mc_start + len(r"\mc")
    args: list[str] = []
    while len(args) < 5:
        while j < len(block) and block[j].isspace():
            j += 1
        if j >= len(block) or block[j] != "{":
            break
        arg, j = _extract_braced_content(block, j)
        if arg is None:
            break
        args.append(arg)
    if len(args) not in (4, 5):
        return None
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
    if len(items) not in (4, 5):
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
        if "MATHSEG" in inner:
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
        r"\\\[\s*((?:<div class=\"(?:stem-figure-wrap|placement-vertical-op|placement-longdiv)[^\"]*\"[\s\S]*?</div>\s*)+)\\\]",
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
    raw = _strip_math_delimiters_around_html(raw)
    raw = replace_tikz_with_svg_html(raw)
    raw = clean_latex_junk(raw)
    raw = _convert_latex_lists(raw)
    table_html = _pipe_lines_to_table_html(raw)
    if table_html:
        raw = table_html
    elif "stem-table-wrap" in raw:
        return raw
    else:
        raw = clean_math(raw)
    raw = _mathjax_safe_lt_in_tex_math(raw)
    return raw


def _inject_placement_geometry_svgs(text: str) -> str:
    """Inline SVG for Enhanced Math II graphing diagrams that lack generic TikZ matchers."""
    if "112^" in text or r"112^\circ" in text:
        parallel_svg = (
            '<div class="stem-figure-wrap" role="img" aria-label="Parallel lines with transversal">'
            '<svg viewBox="0 0 320 180" width="320" height="180" xmlns="http://www.w3.org/2000/svg">'
            '<line x1="20" y1="50" x2="300" y2="50" stroke="#1f1f26" stroke-width="2"/>'
            '<text x="305" y="54" font-size="14">ℓ</text>'
            '<line x1="20" y1="130" x2="300" y2="130" stroke="#1f1f26" stroke-width="2"/>'
            '<text x="305" y="134" font-size="14">m</text>'
            '<line x1="60" y1="160" x2="250" y2="20" stroke="#1f1f26" stroke-width="2"/>'
            '<text x="145" y="42" font-size="13">112°</text>'
            '<text x="52" y="118" font-size="13">(3x+7)°</text>'
            '</svg></div>'
        )
        text = re.sub(
            r"\\begin\{center\}.*?\\end\{center\}",
            parallel_svg,
            text,
            flags=re.S,
        )
        text = re.sub(
            r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}",
            parallel_svg,
            text,
            flags=re.S,
        )
    if "3x+5" in text and "5x-9" in text:
        circle_svg = (
            '<div class="stem-figure-wrap" role="img" aria-label="Circle with tangent segments">'
            '<svg viewBox="0 0 280 200" width="280" height="200" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="90" cy="100" r="55" fill="none" stroke="#1f1f26" stroke-width="2"/>'
            '<text x="78" y="104" font-size="13">O</text>'
            '<line x1="135" y1="62" x2="230" y2="100" stroke="#1f1f26" stroke-width="2"/>'
            '<line x1="135" y1="138" x2="230" y2="100" stroke="#1f1f26" stroke-width="2"/>'
            '<text x="142" y="58" font-size="12">T</text>'
            '<text x="142" y="152" font-size="12">S</text>'
            '<text x="236" y="104" font-size="12">P</text>'
            '<text x="175" y="72" font-size="11">3x+5</text>'
            '<text x="175" y="132" font-size="11">5x-9</text>'
            '</svg></div>'
        )
        text = re.sub(
            r"\\begin\{center\}.*?\\end\{center\}",
            circle_svg,
            text,
            flags=re.S,
        )
        text = re.sub(
            r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}",
            circle_svg,
            text,
            flags=re.S,
        )
    return text


def _normalize_placement_currency(text: str) -> str:
    """No-op: ``clean_math`` already turns ``\\$`` into HTML entities for MathJax."""
    return text


def _format_placement_stem_html(raw: str) -> str:
    raw = _strip_needspace(raw)
    raw = _strip_leading_tex_control_space(raw)
    raw = re.sub(r"\\sectiontag\{[^{}]*\}", "", raw)
    raw = re.sub(r"\\hfill\b\s*", " ", raw)
    raw = re.sub(r"\\hfil\b\s*", " ", raw)
    raw = _expand_placement_inline_diagram_macros(raw)
    raw = latex_array_and_tabular_to_html(raw)
    raw = _convert_array_in_display_math(raw)
    raw = _normalize_placement_currency(raw)
    raw = _inject_placement_geometry_svgs(raw)
    raw = replace_tikz_with_svg_html(raw)
    raw = _unwrap_display_math_brackets_around_figure_html(raw)
    raw = clean_latex_junk(raw)
    raw = _convert_latex_lists(raw)
    html_vault: list[str] = []

    def _vault_html_block(m: re.Match[str]) -> str:
        html_vault.append(m.group(0))
        return f"<<<HTMLBLOCK{len(html_vault) - 1}>>>"

    raw = re.sub(
        r'<div class="(?:placement-vertical-op|placement-longdiv|stem-figure-wrap|stem-figure-row|stem-table-wrap)[^"]*"[^>]*>.*?</div>',
        _vault_html_block,
        raw,
        flags=re.S,
    )
    raw = clean_math(raw)
    for i, block in enumerate(html_vault):
        raw = raw.replace(f"<<<HTMLBLOCK{i}>>>", block)
    raw = _mathjax_safe_lt_in_tex_math(raw)
    return _format_stem_html(raw)


def parse_placement_answer_key(tex: str) -> dict[int, str]:
    """
    Parse answer letters (A–E) from the Answer Key section.
    Supports legacy ``n. L`` array rows and hybrid-gate enumerate lists.
    """
    out: dict[int, str] = {}
    key_m = re.search(
        r"\\section\*\{Answer Key\}(.*?)\\end\{document\}",
        tex,
        flags=re.S,
    )
    if key_m:
        block = key_m.group(1)
        for i, letter in enumerate(
            re.findall(r"\\item\s+([A-E])\b", block),
            start=1,
        ):
            if 1 <= i <= PLACEMENT_MAX_QUESTIONS:
                out[i] = letter.upper()
        if out:
            return out
    for m in re.finditer(r"(\d+)\.(?:\\\s+|\s+)([A-E])\b", tex):
        n = int(m.group(1))
        if 1 <= n <= PLACEMENT_MAX_QUESTIONS:
            out[n] = m.group(2).upper()
    return out


def _placement_gate_span(n: int) -> tuple[int, int]:
    """1-based question index → (first, last) inclusive for its gate."""
    if n <= 16:
        return 1, 16
    if n <= 37:
        return 17, 37
    if n <= 53:
        return 38, 53
    if n <= 69:
        return 54, 69
    return 70, PLACEMENT_MAX_QUESTIONS


def parse_placement_tex_file(path: str):
    """
    Parse Novel Prep upper-school placement items: ``\\circnum{n}`` / ``\\q{n}`` stem,
    then ``\\mc{a}{b}{c}{d}{e}`` or a five-item ``enumerate`` (graph options).
    Returns questions 1–PLACEMENT_MAX_QUESTIONS; teacher pages are ignored.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    doc_i = content.find(r"\begin{document}")
    body = content[doc_i:] if doc_i != -1 else content
    body = _normalize_placement_question_markers(body)
    macros = _collect_placement_graph_macro_bodies(content)

    circ = list(re.finditer(r"\\circnum\{(\d+)\}", body))
    by_num: dict[int, tuple[int, int]] = {}
    for idx, m in enumerate(circ):
        n = int(m.group(1))
        if n < 1 or n > PLACEMENT_MAX_QUESTIONS:
            continue
        start = m.end()
        end = circ[idx + 1].start() if idx + 1 < len(circ) else len(body)
        by_num[n] = (start, end)

    questions: list[dict[str, Any]] = []
    for n in range(1, PLACEMENT_MAX_QUESTIONS + 1):
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
        gate_lo, gate_hi = _placement_gate_span(n)
        questions.append(
            {
                "stem": stem_html,
                "choices": choices_html,
                "question_kind": "mcq5" if len(choice_raws) == 5 else "mcq",
                "display_number": n,
                "placement_section": f"gate_{sec}",
                "placement_section_title": title_en.split("—", 1)[-1].strip() or title_en,
                "placement_section_index": n - gate_lo + 1,
                "placement_section_total": gate_hi - gate_lo + 1,
                "placement_global_index": n,
                "placement_global_total": PLACEMENT_MAX_QUESTIONS,
                "knowledge_section": sec,
                "knowledge_section_title_en": title_en,
                "knowledge_section_title_zh": title_en,
            }
        )

    return questions


def _enhanced_math_placement_part_meta(n: int) -> tuple[str, str]:
    """Enhanced Math I placement: 50 MCQ in Parts A / B / C."""
    if n <= 10:
        return "A", "Part A — Core Readiness"
    if n <= 30:
        return "B", "Part B — Math I Mastery"
    return "C", "Part C — Enhanced Math I Readiness"


def _enhanced_math2_placement_part_meta(n: int) -> tuple[str, str]:
    """Enhanced Math II placement: 55 MCQ in Parts A / B."""
    if n <= 28:
        return "A", "Part A — Math II Readiness"
    return "B", "Part B — Enhanced Math II Readiness"


def _parse_braced_args(s: str, start: int, count: int) -> tuple[list[str], int]:
    """Read ``count`` consecutive ``{...}`` arguments starting at ``start``."""
    args: list[str] = []
    i = start
    for _ in range(count):
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s) or s[i] != "{":
            break
        depth = 0
        j = i
        while j < len(s):
            ch = s[j]
            if ch == "\\" and j + 1 < len(s):
                j += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    args.append(s[i + 1 : j])
                    i = j + 1
                    break
            j += 1
        else:
            break
    return args, i


def _expand_choices_macros(text: str) -> str:
    """Expand ``\\choices`` / ``\\choicesTwo`` into a flat A–D ``enumerate``."""
    pattern = re.compile(r"\\choices(?:Two)?")
    out: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        out.append(text[last : m.start()])
        args, end = _parse_braced_args(text, m.end(), 4)
        if len(args) == 4:
            enum = (
                r"\begin{enumerate}[label=(\Alph*)]"
                + "\n"
                + "\n".join(rf"\item {a}" for a in args)
                + "\n"
                + r"\end{enumerate}"
            )
            out.append(enum)
            last = end
        else:
            out.append(m.group(0))
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def _extract_enhanced_math_mcq_block(block: str) -> Optional[tuple[str, list[str]]]:
    """Parse stem + four choices from enumerate and/or ``\\choices`` macros."""
    expanded = _expand_choices_macros(block)
    return _extract_four_choice_enumerate(expanded)


ENHANCED_MATH_PLACEMENT_PROFILES: dict[str, dict[str, Any]] = {
    "math_1": {
        "max_mcq": 50,
        "graph_section": r"\section*{Graphing Questions}",
        "part_meta_fn": _enhanced_math_placement_part_meta,
    },
    "math_2": {
        "max_mcq": 55,
        "graph_section": r"\section*{Graphing and Constructed Response}",
        "part_meta_fn": _enhanced_math2_placement_part_meta,
    },
}


MIDDLE_LEVEL_FIGURE_META: dict[str, tuple[str, int]] = {
    "rectmixed": ("Shaded rectangles", 240),
    "quarterSquare": ("Square with one quarter shaded", 120),
    "rectangleSixFour": ("6 inch by 4 inch rectangle", 200),
    "numberLineTwoEightSix": ("Number line near 286", 320),
    "rulerST": ("Ruler from R to T", 360),
    "rectRuler": ("Rectangle on ruler", 260),
    "segmentABC": ("Segment A-B-C", 300),
    "lShapeArea": ("L-shaped polygon", 340),
    "pentagonSquare": ("Square and pentagon", 200),
    "triPrism": ("Triangular prism", 300),
    "similarTriangles": ("Similar triangles", 240),
    "trapezoidSolid": ("Trapezoidal prism", 220),
    "baseSolid": ("Composite solid base", 280),
}


def _middle_level_figure_img(name: str) -> str:
    alt, max_w = MIDDLE_LEVEL_FIGURE_META[name]
    return (
        f'<div class="stem-figure-wrap stem-figure-wrap--middle" role="img" aria-label="{alt}">'
        f'<img class="stem-figure-img stem-figure-img--placement-middle" '
        f'src="/static/placement_middle/{name}.png" alt="{alt}" loading="lazy" '
        f'data-ml-figure="{name}" style="max-width:{max_w}px" />'
        f"</div>"
    )


MIDDLE_LEVEL_DIAGRAM_HTML: dict[str, str] = {
    name: _middle_level_figure_img(name) for name in MIDDLE_LEVEL_FIGURE_META
}
MIDDLE_LEVEL_DIAGRAM_HTML["longdiv"] = ""  # expanded via parameterized macro below


# lo, hi, section code, student-facing band label, full part title
MIDDLE_LEVEL_PARTS: list[tuple[int, int, str, str, str]] = [
    (1, 20, "I", "Math 5 readiness", "Part I — Math 5/4 Readiness"),
    (21, 40, "II", "Math 6 readiness", "Part II — Math 6/5 Readiness"),
    (41, 60, "III", "Math 7 readiness", "Part III — Math 7/6 Readiness"),
    (61, 80, "IV", "Math 8 readiness", "Part IV — Math 8/7 Readiness"),
    (81, 100, "V", "Algebra 1/2 readiness", "Part V — Algebra 1/2 Readiness"),
]


def _middle_level_part_for_qnum(n: int) -> tuple[int, int, str, str, str]:
    for part in MIDDLE_LEVEL_PARTS:
        lo, hi, code, short, title = part
        if lo <= n <= hi:
            return part
    return MIDDLE_LEVEL_PARTS[0]


def _split_top_level_enumerate_items(chunk: str) -> list[str]:
    """Return body of each top-level ``\\item`` inside the first outer ``enumerate``."""
    bi = chunk.find(r"\begin{enumerate}")
    if bi < 0:
        return []
    body = chunk[bi:]
    items: list[str] = []
    i = 0
    depth = 0
    cur_start: int | None = None
    begin = r"\begin{enumerate}"
    end = r"\end{enumerate}"
    item_tok = r"\item"
    while i < len(body):
        if body.startswith(begin, i):
            depth += 1
            i += len(begin)
            if i < len(body) and body[i] == "[":
                j = body.find("]", i)
                i = j + 1 if j != -1 else i
            continue
        if body.startswith(end, i):
            if depth == 1 and cur_start is not None:
                items.append(body[cur_start:i].strip())
                cur_start = None
            depth -= 1
            i += len(end)
            continue
        if depth == 1 and body.startswith(item_tok, i):
            nxt = i + len(item_tok)
            if nxt >= len(body) or not body[nxt].isalpha():
                if cur_start is not None:
                    items.append(body[cur_start:i].strip())
                cur_start = nxt
            i = nxt
            continue
        i += 1
    return items


def _strip_math_delimiters_around_html(text: str) -> str:
    """Remove stray $ / \\(...\\) wrappers after array→HTML conversion."""
    text = re.sub(
        r'(?<!\\)\$\s*(<div class="stem-table-wrap">.*?</div>)\s*(?<!\\)\$',
        r"\1",
        text,
        flags=re.S,
    )
    text = re.sub(
        r'\\\(\s*\\displaystyle\s*(<div class="stem-table-wrap">.*?</div>)\s*\\\)',
        r"\1",
        text,
        flags=re.S,
    )
    return text


def _expand_enhanced_math_placement_macros(text: str) -> str:
    """Inline ``\\grid``, work space, and blank lines from Enhanced Math I placement TeX."""
    grid_block = r"""
\begin{center}
\begin{tikzpicture}[scale=0.43]
\draw[step=1cm,gray!35,very thin] (-8,-8) grid (8,8);
\draw[->,thick] (-8.3,0)--(8.3,0) node[right] {$x$};
\draw[->,thick] (0,-8.3)--(0,8.3) node[above] {$y$};
\foreach \x in {-8,-6,-4,-2,2,4,6,8} \draw (\x,0.15)--(\x,-0.15) node[below] {\scriptsize \x};
\foreach \y in {-8,-6,-4,-2,2,4,6,8} \draw (0.15,\y)--(-0.15,\y) node[left] {\scriptsize \y};
\end{tikzpicture}
\end{center}
""".strip()
    text = text.replace(r"\grid", grid_block)
    text = re.sub(
        r"\\longwork\s*",
        '<div class="placement-work-space placement-work-space--long" role="note"><span class="placement-work-label">Space for work on paper</span></div>',
        text,
    )
    text = re.sub(
        r"\\work\{[^}]*\}",
        '<div class="placement-work-space" role="note"><span class="placement-work-label">Work space</span></div>',
        text,
    )
    text = re.sub(
        r"\\work\s*",
        '<div class="placement-work-space" role="note"><span class="placement-work-label">Work space</span></div>',
        text,
    )
    text = re.sub(
        r"\\blankline\{[^}]*\}",
        '<span class="placement-blank-line" aria-hidden="true"></span>',
        text,
    )
    text = re.sub(r"\\newpage\s*", "", text)
    return text


def _enhanced_math_section_slice(body: str, section_title: str, next_section: str | None) -> str:
    start = body.find(section_title)
    if start < 0:
        return ""
    if next_section:
        end = body.find(next_section, start + len(section_title))
        if end < 0:
            end = len(body)
        return body[start:end]
    return body[start:]


def _extract_four_choice_enumerate(block: str) -> Optional[tuple[str, list[str]]]:
    """Parse stem + four A–D choices from ``enumerate[label=(\\Alph*)]``."""
    em_matches = list(
        re.finditer(
            r"\\begin\{enumerate\}\[label=\(\\Alph\*\)\](.*?)\\end\{enumerate\}",
            block,
            flags=re.S,
        )
    )
    if not em_matches:
        return None
    em = em_matches[-1]
    choice_body = em.group(1)
    parts = re.split(r"\\item\s+", choice_body.strip())
    choices = [p.strip() for p in parts if p.strip()]
    if len(choices) != 4:
        return None
    stem = block[: em_matches[0].start()].strip()
    stem = re.sub(r"\\begin\{multicols\}\{[^}]*\}", "", stem)
    stem = re.sub(r"\\end\{multicols\}", "", stem)
    return stem, choices


def parse_enhanced_math_placement_answer_key(tex: str) -> dict[int, str]:
    """Parse tabular MC answer key (Q row + Ans row) used by Enhanced Math I placement."""
    out: dict[int, str] = {}
    for block in re.finditer(
        r"Q\s*&\s*([\d&\s]+)\\.*?Ans\s*&\s*([A-D&\s]+)\\",
        tex,
        flags=re.S,
    ):
        qs = [int(x) for x in re.findall(r"\d+", block.group(1))]
        ans = re.findall(r"[A-D]", block.group(2))
        for q, letter in zip(qs, ans):
            if q >= 1:
                out[q] = letter.upper()
    return out


def parse_enhanced_math_placement_tex_file(path: str, *, profile: str = "math_1"):
    """
    Parse Enhanced Math placement TeX (Math I or Math II): MCQ + graphing + free response.
    """
    cfg = ENHANCED_MATH_PLACEMENT_PROFILES.get(profile, ENHANCED_MATH_PLACEMENT_PROFILES["math_1"])
    max_mcq = int(cfg["max_mcq"])
    graph_section = str(cfg["graph_section"])
    part_meta_fn = cfg["part_meta_fn"]

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    doc_i = content.find(r"\begin{document}")
    body = content[doc_i:] if doc_i != -1 else content
    mc_start = body.find(r"\section*{Multiple Choice Questions}")
    graph_start = body.find(graph_section)
    fr_start = body.find(r"\section*{Free Response Questions}")
    teacher_start = body.find(r"\section*{Teacher Scoring Guide}")
    if mc_start < 0 or graph_start < 0 or fr_start < 0:
        return []

    mc_block = body[mc_start:graph_start]
    raw_items = _split_top_level_enumerate_items(mc_block)
    questions: list[dict[str, Any]] = []
    mc_count = 0
    for raw_item in raw_items:
        if mc_count >= max_mcq:
            break
        extracted = _extract_enhanced_math_mcq_block(raw_item)
        if not extracted:
            continue
        mc_count += 1
        stem_raw, choice_raws = extracted
        stem_raw = _replace_includegraphics_with_img(stem_raw)
        stem_html = _format_placement_stem_html(stem_raw)
        choices_html = [_format_placement_choice_html(c) for c in choice_raws]
        sec, title_en = part_meta_fn(mc_count)
        questions.append(
            {
                "stem": stem_html,
                "choices": choices_html,
                "question_kind": "mcq",
                "display_number": mc_count,
                "placement_section": "mcq",
                "placement_section_title": "Multiple choice",
                "placement_section_index": mc_count,
                "placement_section_total": max_mcq,
                "knowledge_section": sec,
                "knowledge_section_title_en": title_en,
                "knowledge_section_title_zh": title_en,
            }
        )

    graph_block = body[graph_start:fr_start]
    graph_items = _split_top_level_enumerate_items(graph_block)
    graph_total = len(graph_items)
    for i, raw_item in enumerate(graph_items, 1):
        stem_raw = _expand_enhanced_math_placement_macros(raw_item.strip())
        stem_raw = _replace_includegraphics_with_img(stem_raw)
        stem_html = _format_placement_stem_html(stem_raw)
        questions.append(
            {
                "stem": stem_html,
                "choices": [],
                "question_kind": "constructed_response",
                "display_number": i,
                "placement_section": "graphing",
                "placement_section_title": "Graphing — show your work",
                "placement_section_index": i,
                "placement_section_total": graph_total,
                "knowledge_section": "G",
                "knowledge_section_title_en": "Graphing",
                "knowledge_section_title_zh": "Graphing",
            }
        )

    fr_block = body[fr_start:teacher_start if teacher_start > 0 else len(body)]
    fr_items = _split_top_level_enumerate_items(fr_block)
    fr_total = len(fr_items)
    for i, raw_item in enumerate(fr_items, 1):
        stem_raw = _expand_enhanced_math_placement_macros(raw_item.strip())
        stem_raw = _replace_includegraphics_with_img(stem_raw)
        stem_html = _format_placement_stem_html(stem_raw)
        questions.append(
            {
                "stem": stem_html,
                "choices": [],
                "question_kind": "constructed_response",
                "display_number": i,
                "placement_section": "free_response",
                "placement_section_title": "Free response — modeling & reasoning",
                "placement_section_index": i,
                "placement_section_total": fr_total,
                "knowledge_section": "FR",
                "knowledge_section_title_en": "Free response",
                "knowledge_section_title_zh": "Free response",
            }
        )
    return questions


def _extract_middle_level_macros(tex: str) -> dict[str, str]:
    """Pull ``\\newcommand`` bodies from the middle-level placement preamble."""
    doc_i = tex.find(r"\begin{document}")
    preamble = tex[:doc_i] if doc_i != -1 else tex
    macros: dict[str, str] = {}
    for m in re.finditer(
        r"\\newcommand\{\\([A-Za-z]+)\}(?:\[[^\]]*\])?\{",
        preamble,
    ):
        name = m.group(1)
        inner, _ = _extract_braced_content(preamble, m.end() - 1)
        if inner is not None:
            macros[name] = inner
    return macros


def _vertical_mul_html(a: str, b: str) -> str:
    a = a.strip().replace(r"\$", "$")
    b = b.strip().replace(r"\$", "$")
    return (
        '<div class="placement-vertical-op placement-vertical-op--mul" role="math" aria-label="multiplication">'
        f'<div class="placement-vertical-op__row">{a}</div>'
        f'<div class="placement-vertical-op__row placement-vertical-op__row--op">× {b}</div>'
        '<div class="placement-vertical-op__rule" aria-hidden="true"></div>'
        '</div>'
    )


def _vertical_add_html(a: str, b: str, total: str) -> str:
    a = a.strip().replace(r"\$", "$")
    b = b.strip().replace(r"\$", "$")
    total = total.strip().replace(r"\$", "$")
    rows = [
        f'<div class="placement-vertical-op__row">{a}</div>',
        f'<div class="placement-vertical-op__row">{b}</div>',
        '<div class="placement-vertical-op__rule" aria-hidden="true"></div>',
    ]
    if total:
        rows.append(f'<div class="placement-vertical-op__row">{total}</div>')
    return (
        '<div class="placement-vertical-op placement-vertical-op--add" role="math" aria-label="addition">'
        + "".join(rows)
        + "</div>"
    )


def _vertical_sub_html(a: str, b: str, total: str) -> str:
    a = a.strip().replace(r"\$", "$")
    b = b.strip().replace(r"\$", "$")
    total = total.strip().replace(r"\$", "$")
    rows = [
        f'<div class="placement-vertical-op__row">{a}</div>',
        f'<div class="placement-vertical-op__row">{b}</div>',
        '<div class="placement-vertical-op__rule" aria-hidden="true"></div>',
    ]
    if total:
        rows.append(f'<div class="placement-vertical-op__row">{total}</div>')
    return (
        '<div class="placement-vertical-op placement-vertical-op--sub" role="math" aria-label="subtraction">'
        + "".join(rows)
        + "</div>"
    )


def _normalize_vertical_array_cell(cell: str) -> str:
    cell = cell.strip()
    cell = re.sub(r"\\hline\s*", "", cell).strip()
    cell = re.sub(r"\\text\{\\?\$\}", "$", cell)
    return cell.replace(r"\$", "$")


def _vertical_array_block_to_html(body: str) -> str | None:
    body = re.sub(r"\\\\\[[^\]]*\]", r"\\\\", body)
    rows: list[str] = []
    for raw in re.split(r"\\\\", body):
        cell = _normalize_vertical_array_cell(raw)
        if cell:
            rows.append(cell)
    if len(rows) < 2:
        return None
    first = rows[0]
    second = rows[1]
    third = rows[2] if len(rows) > 2 else ""
    if len(rows) >= 3 and rows[-1].startswith("+"):
        body_rows = "".join(
            f'<div class="placement-vertical-op__row">{row}</div>' for row in rows[:-1]
        )
        body_rows += f'<div class="placement-vertical-op__row">{rows[-1]}</div>'
        body_rows += '<div class="placement-vertical-op__rule" aria-hidden="true"></div>'
        return (
            '<div class="placement-vertical-op placement-vertical-op--add" role="math" aria-label="addition">'
            + body_rows
            + "</div>"
        )
    if second.startswith("+") or second.startswith(r"\+"):
        return _vertical_add_html(first, second, third)
    if second.startswith("-") or second.startswith(r"\-"):
        return _vertical_sub_html(first, second, third)
    if second.lstrip().startswith(r"\times") or "times" in second:
        parts = re.split(r"\\times", second, maxsplit=1)
        if len(parts) == 2:
            return _vertical_mul_html(first, parts[1].strip())
    return None


def _replace_vertical_array_blocks(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        html = _vertical_array_block_to_html(m.group(1))
        return html if html else m.group(0)

    text = re.sub(
        r"\\begin\{array\}\{r\}(.*?)\\end\{array\}",
        repl,
        text,
        flags=re.S,
    )
    return re.sub(
        r"\\\[\s*(<div class=\"placement-vertical-op[^]]*?</div>)\s*\\\]",
        r"\1",
        text,
        flags=re.S,
    )


def _replace_braced_macro_calls(
    text: str, name: str, arity: int, builder
) -> str:
    pat = re.compile(rf"\\{name}")
    out: list[str] = []
    last = 0
    for m in pat.finditer(text):
        out.append(text[last : m.start()])
        args, end = _parse_braced_args(text, m.end(), arity)
        if len(args) == arity:
            out.append(builder(*args))
            last = end
        else:
            out.append(m.group(0))
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def _expand_middle_level_item(item: str, macros: dict[str, str]) -> str:
    text = item
    text = re.sub(r"\\sectiontag\{[^}]*\}", "", text)
    text = re.sub(r"\\newpage\s*", "", text)
    text = re.sub(r"\\needspace\{[^}]*\}", "", text)
    text = re.sub(r"\\end\{enumerate\}\s*", "", text)
    text = re.sub(r"\\vspace\*?\{[^}]*\}", "", text)
    text = re.sub(r"\\hfill\b\s*", " ", text)
    text = re.sub(r"\\hfil\b\s*", " ", text)
    text = re.sub(r"\\frac\{\\blank\}\{([^}]+)\}", r"\\frac{\\phantom{00}}{\1}", text)
    text = re.sub(r"\\blank\b", r"\\underline{\\phantom{000}}", text)

    text = _replace_vertical_array_blocks(text)
    text = _replace_braced_macro_calls(text, "verticalmul", 2, _vertical_mul_html)
    text = _replace_braced_macro_calls(text, "verticaladd", 3, _vertical_add_html)
    text = _replace_braced_macro_calls(text, "verticalsub", 3, _vertical_sub_html)
    text = re.sub(
        r"\\\[\s*(<div class=\"(?:placement-vertical-op|stem-figure-wrap)[\s\S]*?</div>)\s*\\\]",
        r"\1",
        text,
        flags=re.S,
    )

    pat = re.compile(r"\\longdiv" + (r"\{([^{}]*)\}" * 2))
    while True:
        m = pat.search(text)
        if not m:
            break
        divisor, dividend = m.groups()
        safe_d, safe_n = re.sub(r"[^a-zA-Z0-9._-]", "", divisor), re.sub(r"[^a-zA-Z0-9._-]", "", dividend)
        repl = (
            f'<div class="stem-figure-wrap stem-figure-wrap--middle stem-figure-wrap--longdiv" role="img" '
            f'aria-label="long division">'
            f'<img class="stem-figure-img stem-figure-img--placement-middle stem-figure-img--longdiv" '
            f'src="/static/placement_middle/longdiv_{safe_d}_{safe_n}.png" alt="Long division" '
            f'loading="lazy" style="max-width:140px" />'
            f"</div>"
        )
        text = text[: m.start()] + repl + text[m.end() :]

    text = re.sub(
        r"\\work\{[^}]*\}",
        "",
        text,
    )

    for name, html in MIDDLE_LEVEL_DIAGRAM_HTML.items():
        if html:
            text = text.replace(f"\\{name}", html)

    skip = {
        "longdiv",
        "verticalmul",
        "verticaladd",
        "verticalsub",
        "qnum",
        "circnum",
        "diagramchip",
        "sectiontag",
        "ansline",
        "blank",
        "work",
        *MIDDLE_LEVEL_DIAGRAM_HTML.keys(),
    }
    for name in sorted((k for k in macros if k not in skip), key=len, reverse=True):
        text = text.replace(f"\\{name}", macros[name])

    text = re.sub(r"\\diagramchip\{[^}]*\}", "", text)
    text = _expand_enhanced_math_placement_macros(text)
    text = re.sub(r"\\vspace\*?\{[^}]*\}", "", text)
    text = re.sub(r"\\end\{enumerate\}\s*", "", text)
    return text.strip()


def _split_middle_level_qnum_items(tex_body: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"\\qnum\{(\d+)\}")
    matches = list(pattern.finditer(tex_body))
    items: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(tex_body)
        body = tex_body[start:end].strip()
        items.append((n, body))
    return items


def parse_middle_level_placement_tex_file(path: str, *, topic: str = "middle_level"):
    """
    Parse ``Placement_Middle_Level.tex`` — full 100-item middle-level placement (5 × 20 CR bands).
    """
    if topic != "middle_level":
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    doc_i = content.find(r"\begin{document}")
    body = content[doc_i:] if doc_i != -1 else content
    guide_start = body.find(r"\section*{Placement Guide}")
    chunk = body[:guide_start] if guide_start > 0 else body
    macros = _extract_middle_level_macros(content)
    raw_items = _split_middle_level_qnum_items(chunk)
    filtered = [(n, txt) for n, txt in raw_items if 1 <= n <= 100]
    global_total = len(filtered)
    questions: list[dict[str, Any]] = []
    for n, raw_item in filtered:
        lo, hi, sec_code, band_label, sec_title = _middle_level_part_for_qnum(n)
        part_index = n - lo + 1
        part_total = hi - lo + 1
        stem_raw = _expand_middle_level_item(raw_item, macros)
        stem_raw = _replace_includegraphics_with_img(stem_raw)
        stem_html = _format_placement_stem_html(stem_raw)
        questions.append(
            {
                "stem": stem_html,
                "choices": [],
                "question_kind": "free_response",
                "display_number": n,
                "placement_section": f"part_{sec_code.lower()}",
                "placement_section_title": band_label,
                "placement_section_index": part_index,
                "placement_section_total": part_total,
                "placement_global_index": n,
                "placement_global_total": global_total,
                "knowledge_section": sec_code,
                "knowledge_section_title_en": sec_title,
                "knowledge_section_title_zh": sec_title,
            }
        )
    return questions

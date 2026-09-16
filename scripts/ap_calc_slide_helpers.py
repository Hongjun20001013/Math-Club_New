"""HTML slide building blocks for AP Calculus course materials."""
from __future__ import annotations

FIG = "/static/ap_calc/figures"


def fig(path: str, caption: str = "", cls: str = "") -> str:
    cap = f'<figcaption class="ap-fig-cap">{caption}</figcaption>' if caption else ""
    return (
        f'<figure class="ap-fig {cls}">'
        f'<img src="{path}" alt="{caption or "Graph"}" loading="lazy"/>'
        f"{cap}</figure>"
    )


def big_idea(html: str) -> str:
    return (
        '<div class="ap-box ap-box--big-idea">'
        '<span class="ap-box-label">Big Idea</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def definition(title: str, html: str) -> str:
    return (
        '<div class="ap-box ap-box--definition">'
        f'<span class="ap-box-label">Definition · {title}</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def key_point(title: str, html: str) -> str:
    return (
        '<div class="ap-box ap-box--key">'
        f'<span class="ap-box-label">Key Point · {title}</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def checkpoint(html: str) -> str:
    return (
        '<div class="ap-box ap-box--checkpoint">'
        '<span class="ap-box-label">AP Checkpoint</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def warning(html: str) -> str:
    return (
        '<div class="ap-box ap-box--warning">'
        '<span class="ap-box-label">Common Mistake</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def role(label: str, title: str, lead: str) -> str:
    return (
        f'<div class="cm-slide-role cm-slide-role--lesson">'
        f'<span class="cm-slide-role-label">{label}</span>'
        f"<strong>{title}</strong><p>{lead}</p></div>"
    )


def math_block(tex: str) -> str:
    return f'<div class="stem-math-block cm-math-block ap-math-block">{tex}</div>'


def intro(unit: str, section: str, title: str, chips: list[tuple[str, str]]) -> str:
    chip_html = "".join(
        f'<button type="button" class="cm-intro-chip" data-cm-jump-section="{idx}">'
        f'<span class="cm-intro-chip-num">{num}</span>'
        f'<span class="cm-intro-chip-label">{label}</span></button>'
        for num, (idx, label) in enumerate(chips, 1)
    )
    return (
        '<div class="cm-intro-canvas ap-calc-intro">'
        '<div class="cm-intro-bg" aria-hidden="true">'
        '<span class="cm-intro-orb cm-intro-orb--1"></span>'
        '<span class="cm-intro-orb cm-intro-orb--2"></span>'
        '<span class="cm-intro-grid"></span></div>'
        '<div class="cm-intro-content">'
        '<span class="cm-intro-kicker">Novel Prep · AP Calculus AB / BC</span>'
        f'<p class="cm-intro-unit">Unit {unit} · Section {section}</p>'
        f'<h1 class="cm-intro-title">{title}</h1>'
        '<p class="cm-intro-lede">Professional lesson deck — definitions, graphs, worked examples, and packet-aligned AP practice.</p>'
        '<div class="cm-intro-meta">'
        '<span class="cm-intro-meta-item"><em>Representations</em>Graph · Table · Algebra · Words</span>'
        '<span class="cm-intro-meta-item"><em>Practice</em>Interactive MCQ + PDF packet</span>'
        "</div>"
        f'<div class="cm-intro-chips">{chip_html}</div>'
        '<p class="cm-intro-cta">Tap a section chip or press <strong>Next</strong> to begin.</p>'
        "</div></div>"
    )


def outline(unit: str, section: str, title: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><button type="button" class="cm-content-item" data-cm-jump-section="{idx}">'
        f'<span class="cm-content-num">{num:02d}</span>'
        f'<span class="cm-content-copy"><strong>{label}</strong>'
        f"<span>Jump to section</span></span>"
        f'<span class="cm-content-arrow" aria-hidden="true">→</span></button></li>'
        for num, (idx, label) in enumerate(items, 1)
    )
    return (
        '<div class="cm-content-canvas"><div class="cm-content-bg" aria-hidden="true">'
        '<span class="cm-content-orb cm-content-orb--1"></span>'
        '<span class="cm-content-orb cm-content-orb--2"></span>'
        '<span class="cm-content-grid"></span></div>'
        '<div class="cm-content-inner">'
        '<span class="cm-content-kicker">Lesson outline</span>'
        f'<p class="cm-content-unit">Unit {unit} · {section}</p>'
        f'<h2 class="cm-content-title">{title}</h2>'
        f'<p class="cm-content-lede">{len(items)} sections · full AP-style progression.</p>'
        f'<ol class="cm-content-list">{rows}</ol>'
        "</div></div>"
    )


def section_divider(num: str, title: str) -> str:
    return (
        f'<div class="cm-section-divider"><span class="cm-section-num">{num}</span>'
        f'<span class="cm-section-kicker">Up next</span>'
        f'<h3 class="cm-section-title">{title}</h3></div>'
    )


def mcq(stem: str, choices: list[str], correct: str, strategy: str = "") -> str:
    letters = "ABCD"
    grid = "".join(
        f'<button type="button" class="cm-mcq-choice" data-choice="{letters[i]}">'
        f'<span class="cm-mcq-letter">{letters[i]}</span>'
        f'<span class="cm-mcq-text">{c}</span></button>'
        for i, c in enumerate(choices[:4])
    )
    strat = (
        f'<div class="cm-strategy-chip"><span class="cm-strategy-chip-label">Strategy</span>'
        f"<p>{strategy}</p></div>"
        if strategy
        else ""
    )
    return (
        '<div class="cm-question-workspace"><div class="cm-question-stem">'
        f"{strat}"
        '<div class="cm-slide-role cm-slide-role--question">'
        '<span class="cm-slide-role-label">Question Practice</span>'
        "<strong>Try it first</strong>"
        "<p>Work on paper, then check your reasoning.</p></div>"
        f"{stem}</div>"
        '<div class="cm-question-interact">'
        f'<div class="cm-mcq-interactive" data-cm-mcq data-cm-correct="{correct}">'
        '<p class="cm-mcq-prompt">Choose your answer</p>'
        f'<div class="cm-mcq-grid">{grid}</div>'
        '<div class="cm-mcq-actions">'
        '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>'
        '<button type="button" class="cm-mcq-skip" data-cm-go-answer>View worked solution →</button>'
        "</div></div></div></div>"
    )


def answer(correct_line: str, solution_html: str) -> str:
    return (
        '<div class="cm-slide-role cm-slide-role--answer">'
        '<span class="cm-slide-role-label">Answer Review</span>'
        "<strong>Check and correct</strong>"
        "<p>Compare your work with the model solution.</p></div>"
        f"<p><strong>{correct_line}</strong></p>"
        '<div class="cm-try-banner" data-cm-try-banner>'
        '<div class="cm-try-banner-icon" aria-hidden="true">✦</div>'
        '<div class="cm-try-banner-copy"><strong>Your turn</strong>'
        "<span>Reveal only after you've written a full solution.</span></div>"
        '<button type="button" class="cm-reveal-btn" data-cm-reveal-solution>Show solution</button>'
        "</div>"
        '<p><strong>Solution:</strong></p>'
        f'<div class="cm-solution-panel cm-is-collapsed" data-cm-solution-panel>{solution_html}</div>'
    )


def practice_packet(section: str, title: str) -> str:
    return (
        '<div class="ap-calc-packet-card glass-panel np-glass">'
        '<p class="np-atelier-kicker">Practice packet</p>'
        f"<h2>{title}</h2>"
        "<p>Download the classroom worksheet and full solution key — every problem maps to this lesson.</p>"
        '<div class="ap-calc-packet-actions">'
        f'<a class="np-atelier-btn np-atelier-btn--primary" href="/ap/calc/practice/{section}/packet.pdf" target="_blank" rel="noopener">Open packet PDF</a>'
        f'<a class="np-atelier-btn np-atelier-btn--ghost" href="/ap/calc/practice/{section}/solutions.pdf" target="_blank" rel="noopener">Open solutions PDF</a>'
        "</div></div>"
    )


class SlideBuilder:
    def __init__(self, section: str):
        self.section = section
        self.slides: list[dict] = []
        self._idx = 1

    def add(self, title: str, html: str, kind: str = "lesson", **kw) -> int:
        idx = self._idx
        self.slides.append(
            {
                "index": idx,
                "title": title,
                "html": html,
                "kind": kind,
                "group": kw.get("group", "learn"),
                "section": kw.get("section", self.section),
                "study_tip": kw.get("study_tip", ""),
                **{k: v for k, v in kw.items() if k not in ("group", "section", "study_tip")},
            }
        )
        self._idx += 1
        return idx

"""Writing rubrics from Novel Prep English Diagnostic answer keys (20 points)."""

from __future__ import annotations

from typing import Any

# Score bands — same on G7-8 and G9-11 answer keys
WRITING_SCORE_BANDS: list[dict[str, Any]] = [
    {"range": "17–20", "title": "Strong", "summary": "Ready for accelerated / honors-style work."},
    {"range": "13–16", "title": "Solid", "summary": "Structure is there; detail, reflection, or rebuttal may be thin."},
    {"range": "9–12", "title": "Developing", "summary": "Ideas present but structure or evidence needs explicit teaching."},
    {"range": "0–8", "title": "Foundational", "summary": "Sentence- and paragraph-level support before full essays."},
]

_G7_8_OPTION_A = {
    "title": "Option A · Personal experience",
    "criteria": [
        {"id": "focus", "label": "Focus", "max_points": 4, "strong": "One clear event; the story has a clear point.", "partial": "Event is clear but the point is vague, or it covers too many events.", "weak": "No clear event; jumps between topics."},
        {"id": "development", "label": "Development", "max_points": 6, "strong": "Specific actions, feelings, sensory details, or dialogue that show the experience.", "partial": "Some details, but mostly tells instead of shows.", "weak": "A list of events with almost no detail."},
        {"id": "reflection", "label": "Reflection", "max_points": 4, "strong": "Explains clearly what was learned or how the writer changed.", "partial": "States a lesson in one general line.", "weak": "No reflection."},
        {"id": "organization", "label": "Organization", "max_points": 3, "strong": "Clear beginning, middle, end; time transitions.", "partial": "Mostly in order; some jumps.", "weak": "Hard to follow."},
        {"id": "language", "label": "Language & conventions", "max_points": 3, "strong": "Varied sentences, consistent past tense, few errors.", "partial": "Some errors or tense shifts; meaning clear.", "weak": "Frequent errors interfere with meaning."},
    ],
}

_G7_8_OPTION_B = {
    "title": "Option B · Argument",
    "criteria": [
        {"id": "claim", "label": "Claim", "max_points": 4, "strong": "Clear opinion that directly answers the question.", "partial": "Opinion is stated but general, or wavers.", "weak": "No clear opinion."},
        {"id": "reasons", "label": "Reasons & evidence", "max_points": 6, "strong": "Two or more reasons, each with a specific example that is explained.", "partial": "Reasons are relevant, but examples are general or not explained.", "weak": "Opinions only, with no examples."},
        {"id": "other_side", "label": "Other side", "max_points": 4, "strong": "States the other side fairly and explains why it is weaker.", "partial": "Mentions the other side with little or no response.", "weak": "Other side not mentioned."},
        {"id": "organization", "label": "Organization", "max_points": 3, "strong": "Introduction, body paragraphs, conclusion; clear transitions.", "partial": "Mostly organized; basic transitions.", "weak": "No paragraphs; hard to follow."},
        {"id": "language", "label": "Language & conventions", "max_points": 3, "strong": "Varied sentences, few errors.", "partial": "Some errors; meaning clear.", "weak": "Frequent errors interfere with meaning."},
    ],
}

_G9_11_ARGUMENT = {
    "title": "Argumentative essay",
    "criteria": [
        {"id": "claim", "label": "Claim & position", "max_points": 4, "strong": "Clear, arguable claim that directly answers the prompt.", "partial": "Position is stated but general, or wavers between sides.", "weak": "No clear position, or simply restates the prompt."},
        {"id": "reasons", "label": "Reasons & evidence", "max_points": 6, "strong": "Two or more reasons, each with a specific, relevant example explained and linked to the claim.", "partial": "Relevant reasons, but examples are general or not fully explained.", "weak": "Opinions with no real examples, or examples that do not support the claim."},
        {"id": "counter", "label": "Counterargument", "max_points": 4, "strong": "States the opposing view fairly and clearly explains why it is less convincing.", "partial": "Mentions the other side but the rebuttal is thin or missing.", "weak": "No counterargument."},
        {"id": "organization", "label": "Organization", "max_points": 3, "strong": "Intro with claim, focused body paragraphs, conclusion, purposeful transitions.", "partial": "Mostly organized; some paragraphs mix ideas or transitions are basic.", "weak": "Hard to follow; no paragraphing."},
        {"id": "language", "label": "Language & conventions", "max_points": 3, "strong": "Varied sentences, precise academic words, few errors.", "partial": "Some errors and repetition, but meaning is clear.", "weak": "Frequent errors that interfere with meaning."},
    ],
}


def writing_rubric_for(topic: str, option: str) -> dict[str, Any]:
    opt = (option or "").strip().upper()
    if topic == "english_g9_11":
        return dict(_G9_11_ARGUMENT)
    if opt == "B":
        return dict(_G7_8_OPTION_B)
    return dict(_G7_8_OPTION_A)


def writing_score_band(total: int) -> dict[str, str]:
    if total >= 17:
        return WRITING_SCORE_BANDS[0]
    if total >= 13:
        return WRITING_SCORE_BANDS[1]
    if total >= 9:
        return WRITING_SCORE_BANDS[2]
    return WRITING_SCORE_BANDS[3]

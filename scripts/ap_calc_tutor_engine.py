"""Contextual tutor hints, misconception taxonomy, and mastery helpers for AP Calc 1.1–1.3."""
from __future__ import annotations

from typing import Any

# ── Misconception taxonomy ─────────────────────────────────────────────────────

MISCONCEPTIONS: dict[str, dict[str, Any]] = {
    # 1.1
    "average-vs-instantaneous": {
        "lessonIds": ["1.1"],
        "studentFacingMessage": "You treated a finite interval average as if it were the instantaneous rate.",
        "level1Hint": "An average rate needs a time interval. Instantaneous rate is the limiting value as the interval shrinks.",
        "level2Hint": "Watch how Δs/h changes as h gets smaller — does it stabilize near one number?",
        "remediationSlideId": None,
    },
    "finite-interval-called-instantaneous": {
        "lessonIds": ["1.1"],
        "studentFacingMessage": "A secant on [a, a+h] is still an average over that interval.",
        "level1Hint": "Secant slope = average rate over the interval from a to a+h.",
        "level2Hint": "Only after h → 0 (with h ≠ 0) does the secant approach the tangent.",
        "remediationSlideId": None,
    },
    "substitute-h-zero-too-early": {
        "lessonIds": ["1.1"],
        "studentFacingMessage": "h = 0 gives 0/0 — undefined. Approach h → 0 with h ≠ 0.",
        "level1Hint": "h = 0 collapses the interval to a single point — no secant slope.",
        "level2Hint": "Use h = ±0.1, ±0.01, ±0.001 to see the pattern approaching the tangent.",
        "remediationSlideId": None,
    },
    "rise-run-reversed": {
        "lessonIds": ["1.1"],
        "studentFacingMessage": "Secant slope = rise Δs divided by run h, not the reverse.",
        "level1Hint": "Orange run is h (horizontal); blue rise is Δs (vertical).",
        "level2Hint": "Slope = Δs/h = (s(a+h)−s(a))/h.",
        "remediationSlideId": None,
    },
    "missing-units": {
        "lessonIds": ["1.1"],
        "studentFacingMessage": "Include units: meters per second, not just the number.",
        "level1Hint": "Δs is in meters; h is in seconds; rate is m/s.",
        "level2Hint": "Write your final answer with units: ___ m/s.",
        "remediationSlideId": None,
    },
    # 1.2
    "limit-equals-function-value": {
        "lessonIds": ["1.2", "1.3"],
        "studentFacingMessage": "The limit describes approach heights; f(c) is read from the filled point.",
        "level1Hint": "Trace both branches first — the limit comes from approach, not the dot.",
        "level2Hint": "Open circle = approach height L; filled dot = f(c). They can differ.",
        "remediationSlideId": None,
    },
    "approach-means-equality": {
        "lessonIds": ["1.2", "1.3"],
        "studentFacingMessage": "Near c is not the same as at c.",
        "level1Hint": "x → c means x approaches c but never equals c during tracing.",
        "level2Hint": "Keep the tracer on the branch, not on the target x = c.",
        "remediationSlideId": None,
    },
    "input-output-target-swapped": {
        "lessonIds": ["1.2", "1.3"],
        "studentFacingMessage": "x → c is the input target; L is the output height approached.",
        "level1Hint": "Move x toward c on the horizontal axis; watch y on the vertical axis.",
        "level2Hint": "L⁻ and L⁺ are y-values, not x-values.",
        "remediationSlideId": None,
    },
    "filled-point-determines-limit": {
        "lessonIds": ["1.2", "1.3"],
        "studentFacingMessage": "The filled dot shows f(c); branches determine the limit.",
        "level1Hint": "Ignore the filled dot until after you lock both one-sided limits.",
        "level2Hint": "Branches approach one height; the filled dot may sit elsewhere.",
        "remediationSlideId": None,
    },
    "notation-direction-error": {
        "lessonIds": ["1.2", "1.3"],
        "studentFacingMessage": "x → c⁻ means x stays less than c; x → c⁺ means x stays greater than c.",
        "level1Hint": "Minus (−) = left approach; plus (+) = right approach.",
        "level2Hint": "Read the superscript carefully — it is not part of the number c.",
        "remediationSlideId": None,
    },
    # 1.3
    "filled-point-first": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "You read f(c) before tracing both branches.",
        "level1Hint": "Temporarily ignore the filled dot — trace along x < c first.",
        "level2Hint": "Follow the left branch toward x = c and watch which y-height you approach.",
        "remediationSlideId": None,
    },
    "checks-left-only": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "You locked only the left side — complete the right trace too.",
        "level1Hint": "After locking L⁻, switch to the right tracer (x > c).",
        "level2Hint": "Both one-sided limits are needed before comparing.",
        "remediationSlideId": None,
    },
    "checks-right-only": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "You locked only the right side — complete the left trace too.",
        "level1Hint": "Start with the left tracer on x < c.",
        "level2Hint": "Lock L⁻ before moving to the right side.",
        "remediationSlideId": None,
    },
    "averages-unequal-one-sided-limits": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "Do not average L⁻ and L⁺ — they must match exactly for a two-sided limit.",
        "level1Hint": "Compare the two heights — are they the same number?",
        "level2Hint": "If L⁻ ≠ L⁺, the two-sided limit does not exist.",
        "remediationSlideId": None,
    },
    "tracer-at-target": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "The tracer cannot sit at x = c — limits describe approach, not the point itself.",
        "level1Hint": "Move closer to c but stay on the branch: try x = c − 0.01 or c + 0.01.",
        "level2Hint": "Use the preset buttons to approach c without reaching it.",
        "remediationSlideId": None,
    },
    "endpoint-needs-two-sides": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "At a domain endpoint, only the valid one-sided limit exists.",
        "level1Hint": "Check the domain — which directions of approach are allowed?",
        "level2Hint": "For √x at x = 0, only x → 0⁺ is in the domain.",
        "remediationSlideId": None,
    },
    "open-closed-point-confusion": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "Open circle = approach height; filled dot = function value.",
        "level1Hint": "The open circle marks the limit height; the filled dot marks f(c).",
        "level2Hint": "They can be at different y-coordinates on the same x = c.",
        "remediationSlideId": None,
    },
    "infinite-treated-as-finite": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "If |y| grows without bound, the finite limit does not exist.",
        "level1Hint": "Watch y as x approaches c — does it shoot upward or downward?",
        "level2Hint": "Unbounded behavior means no finite two-sided limit.",
        "remediationSlideId": None,
    },
    "DNE-without-reason": {
        "lessonIds": ["1.3"],
        "studentFacingMessage": "State why the limit DNE: unequal sides, unbounded, or oscillatory.",
        "level1Hint": "Compare L⁻ and L⁺ — do they agree?",
        "level2Hint": "Explain: the two-sided limit DNE because L⁻ ≠ L⁺ (or only one side exists).",
        "remediationSlideId": None,
    },
}

# ── Levelled hints per lesson (deterministic, no LLM) ──────────────────────────

TUTOR_HINT_LEVELS: dict[str, list[dict[str, str]]] = {
    "1.1": [
        {"type": "Observation hint", "text": "Watch how Δs and h change together as you move the slider."},
        {"type": "Strategy hint", "text": "Try h from the left (negative) and right (positive) — do both slopes approach the same number?"},
        {"type": "Representation hint", "text": "Secant slope = Δs/h = (s(a+h)−s(a))/h. At t=2 with s(t)=t²+1, slope = 4+h."},
        {"type": "Partial step", "text": "h=0.1 → slope 4.1; h=−0.1 → slope 3.9. Both approach 4."},
        {"type": "Full solution", "text": "Instantaneous rate at t=2 is 4 m/s. Left and right secant slopes agree → tangent slope 4."},
    ],
    "1.2": [
        {"type": "Observation hint", "text": "Trace from the left toward c, then from the right — watch the y-values on each branch."},
        {"type": "Strategy hint", "text": "Ignore the filled dot until you have locked both L⁻ and L⁺."},
        {"type": "Representation hint", "text": "Write L⁻ = lim_{x→c⁻} f(x) and L⁺ = lim_{x→c⁺} f(x) from your traces."},
        {"type": "Partial step", "text": "If L⁻ = L⁺ = L, then lim_{x→c} f(x) = L. f(c) may differ or be undefined."},
        {"type": "Full solution", "text": "Complete symbolic and verbal statements using your locked observations and f(c)."},
    ],
    "1.3": [
        {"type": "Observation hint", "text": "Temporarily ignore the filled dot — trace along x < c on the left branch only."},
        {"type": "Strategy hint", "text": "Watch which horizontal height the purple tracer approaches as x nears c from the left."},
        {"type": "Representation hint", "text": "Write your left observation as lim_{x→c⁻} f(x) = ___."},
        {"type": "Partial step", "text": "Lock L⁻ and L⁺, then compare. If they match, the two-sided limit exists."},
        {"type": "Full solution", "text": "State L⁻, L⁺, comparison, two-sided conclusion, and f(c) separately."},
    ],
}


def tracer_presets(target_x: float, domain_min: float | None = None) -> dict[str, list[float]]:
    c = target_x
    left = [c - 1, c - 0.5, c - 0.1, c - 0.01, c - 0.001]
    right = [c + 1, c + 0.5, c + 0.1, c + 0.01, c + 0.001]
    if domain_min is not None:
        left = [x for x in left if x >= domain_min]
    return {"left": left, "right": right}


def enrich_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Attach tracer presets and misconception tags to a graph case."""
    c = float(scenario["targetX"])
    domain_min = scenario.get("domainMin")
    scenario["allowedTracerValues"] = tracer_presets(c, domain_min)
    scenario.setdefault("misconceptionTags", [])
    return scenario


def contextual_hints_for_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Slide-specific hint sequences (lesson 1.2 #4 and 1.3 #5). No h = 0 outside 1.1."""
    slide_id = spec.get("slideId", "")
    if slide_id == "1.2-4":
        return {
            "sequence": [
                {"type": "Observation hint", "text": "Predict whether the left and right approach heights will agree."},
                {"type": "Strategy hint", "text": "Now approach x = 3 from the other side."},
                {"type": "Representation hint", "text": "Record the y-value the graph is approaching, not the value at x = 3."},
            ],
            "caseOverrides": {
                "case-b": {"type": "Case B", "text": "The limit is determined by nearby values; the filled point determines f(3)."},
                "case-d": {"type": "Case D", "text": "Compare L− and L+. A two-sided limit exists only when they agree."},
            },
        }
    if slide_id == "1.3-5":
        return {
            "sequence": [
                {"type": "Left branch", "text": "Follow the left branch toward x = 2. What height is it approaching?"},
                {"type": "Right branch", "text": "Now follow the right branch toward x = 2."},
                {"type": "Two-sided limit", "text": "If both sides approach 3, the two-sided limit is 3."},
                {"type": "Inspect f(c)", "text": "Only after finding the limit should you inspect the filled point."},
                {"type": "Open vs filled", "text": "The open circle describes the approached value; the filled point describes f(2)."},
            ],
        }
    return {}


def tutor_context_for_spec(spec: dict[str, Any]) -> dict[str, Any]:
    lesson_id = spec.get("lessonId", "")
    return {
        "lessonId": lesson_id,
        "slideId": spec.get("slideId", ""),
        "hintLevels": TUTOR_HINT_LEVELS.get(lesson_id, TUTOR_HINT_LEVELS["1.3"]),
        "contextualHints": contextual_hints_for_spec(spec),
        "misconceptions": {
            k: v for k, v in MISCONCEPTIONS.items()
            if lesson_id in v.get("lessonIds", [])
        },
    }


def mastery_from_lab_progress(lab_progress: dict[str, Any]) -> dict[str, int]:
    """Compute objective mastery components from lab interaction data."""
    objectives = lab_progress.get("objectives") or {}
    if not objectives:
        exposure = min(40, int(lab_progress.get("slidesViewed", 0) * 8))
        return {"exposure": exposure, "interaction": 0, "guided": 0, "independent": 0, "explanation": 0, "total": exposure}

    totals = []
    for obj in objectives.values():
        exp = min(10, int(obj.get("exposure", 0)))
        inter = min(20, int(obj.get("interaction", 0)))
        guided = min(20, int(obj.get("guidedSuccess", 0)))
        indep = min(30, int(obj.get("independentSuccess", 0)))
        explain = min(20, int(obj.get("explanationQuality", 0)))
        totals.append(exp + inter + guided + indep + explain)
    total = round(sum(totals) / len(totals)) if totals else 0
    return {"total": min(100, total)}


def learning_event_schema() -> dict[str, Any]:
    return {
        "userId": "integer",
        "courseId": "ap-calc",
        "unitId": "string",
        "lessonId": "string",
        "slideId": "string",
        "objectiveId": "string",
        "labId": "string",
        "caseId": "string",
        "eventType": "prediction_submitted|tracer_moved|left_observation_locked|right_observation_locked|comparison_submitted|function_value_submitted|explanation_submitted|hint_requested|answer_checked|mastery_updated",
        "graphState": "object",
        "prediction": "any",
        "answer": "any",
        "correct": "boolean",
        "attempts": "integer",
        "hintsUsed": "integer",
        "misconceptionTags": "string[]",
        "masteryBefore": "integer",
        "masteryAfter": "integer",
        "timestamp": "integer",
    }

"""Canonical Interactive Math Lab specifications for AP Calc 1.1–1.3.

Graph, table, formula, and AI context are generated from these specs —
never duplicated in lesson HTML or JS literals.
"""
from __future__ import annotations

import json
from typing import Any

SECANT_H_VALUES = [-1, -0.5, -0.1, -0.01, 0.01, 0.1, 0.5, 1]


def secant_lab_11() -> dict[str, Any]:
    return {
        "id": "secant-tangent-11",
        "lessonId": "1.1",
        "labType": "SecantTangentLab",
        "learningObjective": "Estimate instantaneous rate as secant slopes approach a tangent slope.",
        "functionDefinition": "t**2 + 1",
        "variable": "t",
        "domain": [0, 4.2],
        "targetX": 2,
        "movableX": None,
        "allowedValues": SECANT_H_VALUES,
        "excludedValues": [0],
        "tangent": {"slope": 4, "through": [2, 5]},
        "secant": {"baseX": 2},
        "tableColumns": ["h", "Δs", "Δs/h", "interval"],
        "annotations": {
            "riseLabel": "Δs",
            "runLabel": "h",
            "units": {"input": "s", "output": "m", "rate": "m/s"},
        },
        "whatToNotice": [
            "Left and right h values give average rates approaching 4 m/s.",
            "h = 0 is not allowed — no interval, no secant slope.",
            "The tangent slope 4 is the instantaneous rate at t = 2.",
        ],
        "misconceptionTags": [
            "average-vs-instantaneous",
            "finite-interval-called-instantaneous",
            "substitute-h-zero-too-early",
            "numerator-denominator-confusion",
            "missing-units",
        ],
        "predictPrompt": "As h → 0 from both sides, does the secant slope increase, decrease, or stabilize? What tangent slope do you predict?",
        "explainPrompt": "Why can we use h → 0 but not h = 0 in the difference quotient?",
    }


def limit_cases_lab_12() -> dict[str, Any]:
    cases = [
        {
            "id": "case-a",
            "label": "A",
            "title": "Limit exists and equals f(c)",
            "branches": [{"fn": "x + 2", "x0": 0.5, "x1": 5.5, "color": "#6c4eff"}],
            "openPoints": [],
            "closedPoints": [{"x": 3, "y": 5}],
            "targetX": 3,
            "leftLimit": 5,
            "rightLimit": 5,
            "twoSidedLimit": 5,
            "functionValue": 5,
            "symbolic": "\\lim_{x\\to 3} f(x) = 5,\\quad f(3)=5",
            "verbal": "As x approaches 3, outputs approach 5 and the filled point is also 5.",
            "whatToNotice": "Continuous at c: approach height matches the filled dot.",
        },
        {
            "id": "case-b",
            "label": "B",
            "title": "Limit exists but differs from f(c)",
            "branches": [{"fn": "x + 2", "x0": 0.5, "x1": 5.5, "color": "#6c4eff"}],
            "openPoints": [{"x": 3, "y": 5}],
            "closedPoints": [{"x": 3, "y": 10}],
            "targetX": 3,
            "leftLimit": 5,
            "rightLimit": 5,
            "twoSidedLimit": 5,
            "functionValue": 10,
            "symbolic": "\\lim_{x\\to 3} f(x) = 5,\\quad f(3)=10",
            "verbal": "Branches approach 5, but the filled point sits at 10.",
            "whatToNotice": "A limit can exist even when f(c) is different.",
        },
        {
            "id": "case-c",
            "label": "C",
            "title": "Limit exists but f(c) is undefined",
            "branches": [{"fn": "x + 2", "x0": 0.5, "x1": 5.5, "color": "#6c4eff"}],
            "openPoints": [{"x": 3, "y": 5}],
            "closedPoints": [],
            "targetX": 3,
            "leftLimit": 5,
            "rightLimit": 5,
            "twoSidedLimit": 5,
            "functionValue": None,
            "symbolic": "\\lim_{x\\to 3} f(x) = 5,\\quad f(3)\\text{ DNE}",
            "verbal": "Outputs approach 5, but there is no filled point at x = 3.",
            "whatToNotice": "An open circle shows the approach height; no value at c.",
        },
        {
            "id": "case-d",
            "label": "D",
            "title": "Two-sided limit does not exist",
            "branches": [
                {"fn": "x - 4", "x0": 0.5, "x1": 2.98, "color": "#2563eb"},
                {"fn": "x + 1", "x0": 3.02, "x1": 5.5, "color": "#ea580c"},
            ],
            "openPoints": [],
            "closedPoints": [{"x": 3, "y": 0}],
            "targetX": 3,
            "leftLimit": -1,
            "rightLimit": 4,
            "twoSidedLimit": None,
            "functionValue": 0,
            "symbolic": "\\lim_{x\\to 3} f(x)\\text{ DNE}",
            "verbal": "Left branch approaches −1; right branch approaches 4.",
            "whatToNotice": "Unequal one-sided limits ⇒ two-sided limit DNE.",
        },
    ]
    return {
        "id": "limit-cases-12",
        "lessonId": "1.2",
        "labType": "GraphCaseSwitcher",
        "learningObjective": "Distinguish limit behavior from function value in four contrast cases.",
        "cases": cases,
        "misconceptionTags": [
            "limit-equals-function-value",
            "swaps-input-output-targets",
            "approach-means-equality",
            "notation-direction-error",
        ],
        "predictPrompt": "Before tracing, predict: will the left and right approach heights agree?",
        "explainPrompt": "How is the limit different from f(c) in this case?",
    }


def tracer_lab_13() -> dict[str, Any]:
    scenarios = [
        {
            "id": "continuous",
            "title": "Continuous point",
            "branches": [{"fn": "0.5*x + 1", "x0": -0.5, "x1": 4.5, "color": "#6c4eff"}],
            "openPoints": [],
            "closedPoints": [{"x": 2, "y": 2}],
            "targetX": 2,
            "leftLimit": 2,
            "rightLimit": 2,
            "twoSidedLimit": 2,
            "functionValue": 2,
            "previewNote": "Continuous — limit equals f(c).",
        },
        {
            "id": "removable-hole",
            "title": "Removable hole (preview)",
            "branches": [{"fn": "x + 1", "x0": -0.5, "x1": 4.5, "color": "#6c4eff"}],
            "openPoints": [{"x": 2, "y": 3}],
            "closedPoints": [],
            "targetX": 2,
            "leftLimit": 3,
            "rightLimit": 3,
            "twoSidedLimit": 3,
            "functionValue": None,
            "previewNote": "Visual preview only — formal classification in §1.10.",
        },
        {
            "id": "hole-filled",
            "title": "Hole with different filled value",
            "branches": [
                {"fn": "x + 1", "x0": -0.5, "x1": 1.98, "color": "#2563eb"},
                {"fn": "-x + 5", "x0": 2.02, "x1": 4.5, "color": "#ea580c"},
            ],
            "openPoints": [{"x": 2, "y": 3}],
            "closedPoints": [{"x": 2, "y": 1.5}],
            "targetX": 2,
            "leftLimit": 3,
            "rightLimit": 3,
            "twoSidedLimit": 3,
            "functionValue": 1.5,
            "previewNote": "Limit comes from branches, not the filled dot.",
        },
        {
            "id": "jump",
            "title": "Jump (preview)",
            "branches": [
                {"fn": "x - 4", "x0": -0.5, "x1": 2.98, "color": "#2563eb"},
                {"fn": "x + 1", "x0": 3.02, "x1": 4.5, "color": "#ea580c"},
            ],
            "openPoints": [],
            "closedPoints": [{"x": 3, "y": 0}],
            "targetX": 3,
            "leftLimit": -1,
            "rightLimit": 4,
            "twoSidedLimit": None,
            "functionValue": 0,
            "previewNote": "Jump preview — formal types in §1.10.",
        },
        {
            "id": "endpoint",
            "title": "Endpoint / one-sided domain",
            "branches": [{"fn": "sqrt(x)", "x0": 0, "x1": 4.5, "color": "#6c4eff"}],
            "openPoints": [],
            "closedPoints": [{"x": 0, "y": 0}],
            "targetX": 0,
            "leftLimit": None,
            "rightLimit": 0,
            "twoSidedLimit": None,
            "functionValue": 0,
            "domainMin": 0,
            "previewNote": "Only x → 0⁺ is in the domain.",
        },
        {
            "id": "infinite",
            "title": "Infinite behavior (extension)",
            "branches": [{"fn": "1/(x-2)**2 + 1", "x0": 0.2, "x1": 1.85, "color": "#6c4eff"},
                         {"fn": "1/(x-2)**2 + 1", "x0": 2.15, "x1": 4.3, "color": "#ea580c"}],
            "openPoints": [],
            "closedPoints": [],
            "targetX": 2,
            "leftLimit": None,
            "rightLimit": None,
            "twoSidedLimit": None,
            "functionValue": None,
            "infinite": True,
            "previewNote": "Optional extension — |y| grows without bound near x = 2.",
        },
    ]
    return {
        "id": "one-sided-tracer-13",
        "lessonId": "1.3",
        "labType": "OneSidedLimitTracer",
        "learningObjective": "Estimate left-hand, right-hand, and two-sided limits from a graph.",
        "scenarios": scenarios,
        "misconceptionTags": [
            "filled-point-first",
            "checks-one-side-only",
            "averages-unequal-one-sided-limits",
            "endpoint-requires-two-sides",
            "infinite-limit-treated-as-finite",
            "open-closed-point-confusion",
        ],
        "predictPrompt": "Before tracing, predict whether L⁻ and L⁺ will match.",
        "explainPrompt": "Explain why the two-sided limit does or does not exist.",
    }


def spec_json(spec: dict[str, Any]) -> str:
    return json.dumps(spec, separators=(",", ":"))

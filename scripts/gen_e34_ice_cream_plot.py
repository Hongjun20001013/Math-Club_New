#!/usr/bin/env python3
"""Generate a crisp Ice Cream Sales scatterplot (E34.png) from SAT 3.4 bank data."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "course_materials" / "E34.png"

# Coordinates measured from the official SAT-style Ice Cream Sales scatterplot.
POINTS = [
    (11.9, 480),
    (14.2, 520),
    (15.2, 630),
    (16.4, 620),
    (17.2, 710),
    (18.1, 720),
    (18.5, 710),
    (19.4, 710),
    (22.1, 820),
    (22.6, 750),
    (23.4, 840),
    (25.1, 910),
]


def main() -> None:
    xs = [p[0] for p in POINTS]
    ys = [p[1] for p in POINTS]

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
        }
    )

    fig, ax = plt.subplots(figsize=(6.5, 4.0), dpi=200)

    ax.set_title("Ice Cream Sales")
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Sales (dollars)")

    ax.set_xlim(10, 26)
    ax.set_ylim(300, 1000)
    ax.set_xticks(np.arange(10, 27, 2))
    ax.set_yticks(np.arange(300, 1001, 100))

    ax.set_xticks(np.arange(10, 27, 1), minor=True)
    ax.set_yticks(np.arange(300, 1001, 50), minor=True)
    ax.grid(True, which="major", linewidth=0.8, color="#cccccc")
    ax.grid(True, which="minor", linewidth=0.4, color="#e6e6e6")

    ax.scatter(xs, ys, c="black", s=28, zorder=3)

    line_x = np.array([10, 26])
    line_y = 33 * line_x + 84
    ax.plot(line_x, line_y, color="black", linewidth=1.6, zorder=2)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

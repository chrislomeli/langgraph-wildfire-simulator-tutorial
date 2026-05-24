"""evals.framework.reporting — render a Report as a readable scorecard.

Pure formatting; no agent knowledge. Swap for a richer reporter (HTML, a
dashboard push) without touching the spine.
"""

from __future__ import annotations

from evals.framework.core import Report


def render_scorecard(report: Report) -> str:
    lines = [
        f"Run #{report.run_id} — {report.passed_cases}/{report.total_cases} cases passed "
        f"({report.pass_rate:.0%})",
        "",
        "Metrics:",
    ]
    if report.metrics:
        width = max(len(k) for k in report.metrics)
        for k in sorted(report.metrics):
            lines.append(f"  {k:<{width}} : {report.metrics[k]:.3f}")
    else:
        lines.append("  (none)")
    if report.regressions:
        lines.append("")
        lines.append("Regressions vs baseline:")
        lines.extend(f"  ! {r}" for r in report.regressions)
    return "\n".join(lines)

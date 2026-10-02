"""PRISMA 2020 flow-diagram counts and rendering."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PrismaFlow:
    identified_by_db: dict[str, int] = field(default_factory=dict)
    identified_other: int = 0
    duplicates_removed: int = 0
    automation_ineligible: int = 0
    other_removed: int = 0
    screened: int = 0
    excluded_screening: int = 0
    screening_reasons: dict[str, int] = field(default_factory=dict)
    sought: int = 0
    not_retrieved: int = 0
    assessed: int = 0
    excluded_eligibility: dict[str, int] = field(default_factory=dict)
    included_studies: int = 0
    included_reports: int = 0

    @property
    def identified(self) -> int:
        return sum(self.identified_by_db.values()) + self.identified_other

    def to_dict(self) -> dict:
        d = asdict(self)
        d["identified"] = self.identified
        return d

    def check(self) -> list[str]:
        """Arithmetic consistency checks; returns a list of problems (empty if OK)."""
        problems = []
        if self.identified - self.duplicates_removed - self.automation_ineligible - self.other_removed != self.screened:
            problems.append("identified - removed != screened")
        if self.screened - self.excluded_screening != self.sought:
            problems.append("screened - excluded != sought")
        if self.sought - self.not_retrieved != self.assessed:
            problems.append("sought - not retrieved != assessed")
        if self.assessed - sum(self.excluded_eligibility.values()) != self.included_reports:
            problems.append("assessed - excluded != included")
        return problems


def build_flow(records_by_db: dict[str, int], duplicates_removed: int, ta_decisions, not_retrieved: list[str],
               el_decisions, automation_ineligible: int = 0) -> PrismaFlow:
    ta_excl = [d for d in ta_decisions if not d.included]
    el_excl = [d for d in el_decisions if not d.included]
    included = sum(d.included for d in el_decisions)
    flow = PrismaFlow(
        identified_by_db=dict(records_by_db),
        duplicates_removed=duplicates_removed,
        automation_ineligible=automation_ineligible,
        screened=len(ta_decisions),
        excluded_screening=len(ta_excl),
        screening_reasons=dict(Counter(d.reason for d in ta_excl).most_common()),
        sought=len(ta_decisions) - len(ta_excl),
        not_retrieved=len(not_retrieved),
        assessed=len(el_decisions),
        excluded_eligibility=dict(Counter(d.reason for d in el_excl).most_common()),
        included_studies=included,
        included_reports=included,
    )
    return flow


def render_flow_diagram(flow: PrismaFlow, path: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(10, 11))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 110)
    ax.axis("off")

    def box(x, y, w, h, text, fc="#ffffff"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3", fc=fc, ec="#1f3864", lw=1.2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5, wrap=True)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#1f3864", lw=1.2))

    for label, y0, y1 in (("Identification", 84, 106), ("Screening", 20, 82), ("Included", 2, 18)):
        ax.add_patch(FancyBboxPatch((0, y0), 6, y1 - y0, boxstyle="round,pad=0.2", fc="#a9c4eb", ec="none"))
        ax.text(3, (y0 + y1) / 2, label, rotation=90, ha="center", va="center", fontsize=10, weight="bold")

    ax.text(52, 108.5, "Identification of studies via databases and registers", ha="center", fontsize=11,
            weight="bold")
    db_lines = "\n".join(f"  {db} (n = {n})" for db, n in flow.identified_by_db.items())
    box(9, 86, 40, 18, f"Records identified from:\nDatabases (n = {flow.identified})\n{db_lines}")
    box(56, 86, 40, 18, f"Records removed before screening:\n  Duplicate records (n = {flow.duplicates_removed})\n"
                        f"  Marked ineligible by automation\n  tools (n = {flow.automation_ineligible})\n"
                        f"  Removed for other reasons (n = {flow.other_removed})")
    box(9, 68, 40, 10, f"Records screened\n(n = {flow.screened})")
    reasons = "\n".join(f"  {r} (n = {n})" for r, n in list(flow.screening_reasons.items())[:6])
    box(56, 64, 40, 18, f"Records excluded (n = {flow.excluded_screening})\n{reasons}", "#f7f7f7")
    box(9, 50, 40, 10, f"Reports sought for retrieval\n(n = {flow.sought})")
    box(56, 50, 40, 10, f"Reports not retrieved\n(n = {flow.not_retrieved})", "#f7f7f7")
    box(9, 30, 40, 10, f"Reports assessed for eligibility\n(n = {flow.assessed})")
    el = "\n".join(f"  {r} (n = {n})" for r, n in list(flow.excluded_eligibility.items())[:6])
    box(56, 22, 40, 22, f"Reports excluded (n = {sum(flow.excluded_eligibility.values())}):\n{el}", "#f7f7f7")
    box(9, 4, 40, 12, f"Studies included in review\n(n = {flow.included_studies})\n"
                      f"Reports of included studies\n(n = {flow.included_reports})", "#e2efda")
    arrow(29, 86, 29, 78.6)
    arrow(49, 95, 55.4, 95)
    arrow(29, 68, 29, 60.6)
    arrow(49, 73, 55.4, 73)
    arrow(29, 50, 29, 40.6)
    arrow(49, 55, 55.4, 55)
    arrow(29, 30, 29, 16.6)
    arrow(49, 35, 55.4, 35)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path

"""Risk-of-bias matrices: Cochrane RoB 2 (randomised) and ROBINS-I (non-randomised).

``suggest_rob`` produces *provisional* judgements from reporting cues in the
text (randomisation method, allocation concealment, blinding, attrition,
pre-registration, confounding adjustment).  They are a starting point that a
reviewer must confirm; they are never presented as final.
"""

from __future__ import annotations

import re

from ureme.models import Record

ROB2_DOMAINS = [
    "D1 Randomisation process",
    "D2 Deviations from intended interventions",
    "D3 Missing outcome data",
    "D4 Measurement of the outcome",
    "D5 Selection of the reported result",
]
ROBINS_I_DOMAINS = [
    "D1 Confounding",
    "D2 Selection of participants",
    "D3 Classification of interventions",
    "D4 Deviations from intended interventions",
    "D5 Missing data",
    "D6 Measurement of outcomes",
    "D7 Selection of the reported result",
]
ROB2_LEVELS = ["Low", "Some concerns", "High"]
ROBINS_LEVELS = ["Low", "Moderate", "Serious", "Critical"]
NO_INFO = "No information"

_ALIASES = {
    "low": "Low", "l": "Low", "+": "Low",
    "some concerns": "Some concerns", "some": "Some concerns", "unclear": "Some concerns", "sc": "Some concerns",
    "?": "Some concerns", "moderate": "Moderate", "m": "Moderate",
    "high": "High", "h": "High", "-": "High", "serious": "Serious", "s": "Serious", "critical": "Critical",
    "c": "Critical", "ni": NO_INFO, "no information": NO_INFO,
}


def normalize_judgement(value: str, tool: str) -> str:
    j = _ALIASES.get((value or "").strip().lower(), (value or "").strip())
    if tool == "RoB2" and j in {"Moderate"}:
        return "Some concerns"
    if tool == "RoB2" and j in {"Serious", "Critical"}:
        return "High"
    if tool == "ROBINS-I" and j == "Some concerns":
        return "Moderate"
    if tool == "ROBINS-I" and j == "High":
        return "Serious"
    return j


def normalize_tool(tool: str, design: str = "") -> str:
    t = (tool or "").lower().replace(" ", "").replace("_", "-")
    if t in {"rob2", "rob-2"}:
        return "RoB2"
    if t in {"robins-i", "robinsi"}:
        return "ROBINS-I"
    return "RoB2" if design.upper() == "RCT" else "ROBINS-I"


def overall_judgement(tool: str, judgements: list[str]) -> str:
    """RoB 2: any High -> High; >=3 Some concerns -> High (substantial concern); any Some concerns -> Some
    concerns; else Low.  ROBINS-I: overall equals the most severe domain."""
    js = [normalize_judgement(j, tool) for j in judgements if j]
    if not js:
        return ""
    if tool == "RoB2":
        if "High" in js:
            return "High"
        n_sc = sum(j in ("Some concerns", NO_INFO) for j in js)
        if n_sc >= 3:
            return "High"
        return "Some concerns" if n_sc else "Low"
    order = {lvl: i for i, lvl in enumerate(ROBINS_LEVELS)}
    known = [j for j in js if j in order]
    if not known:
        return NO_INFO
    return max(known, key=lambda j: order[j])


def _has(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    s = max(0, m.start() - 80)
    return text[s : m.end() + 80].replace("\n", " ").strip()


def suggest_rob(rec: Record, design: str) -> dict:
    text = rec.best_text
    tool = "RoB2" if design == "RCT" else "ROBINS-I"
    dom: dict[str, dict] = {}

    def put(name: str, judgement: str, support: str | None, why: str) -> None:
        dom[name] = {"judgement": judgement, "support": support or "", "rationale": why}

    registered = _has(text, r"(NCT\d{8}|ISRCTN\d+|ACTRN\d+|ChiCTR|EudraCT|PROSPERO|pre-?registered|trial registration)")
    attrition = _has(text, r"(lost to follow-?up|drop-?outs?|withdr[ae]w|attrition)")
    itt = _has(text, r"(intention[- ]to[- ]treat|\bITT\b|modified intention)")
    imput = _has(text, r"(multiple imputation|imputed|complete[- ]case)")
    if tool == "RoB2":
        seq = _has(text, r"(computer[- ]generated|random number|block randomi[sz]ation|stratified randomi[sz]ation|"
                         r"permuted block|central(ised|ized)? randomi[sz]ation)")
        conceal = _has(text, r"(allocation conceal|sealed (opaque )?envelope|interactive (web|voice) response|"
                             r"central allocation)")
        put(ROB2_DOMAINS[0], "Low" if seq and conceal else ("Some concerns" if seq or conceal else NO_INFO),
            seq or conceal, "Random sequence and concealment both reported" if seq and conceal else
            "Randomisation/concealment incompletely reported")
        blind = _has(text, r"(double[- ]blind|triple[- ]blind|placebo[- ]controlled|masked|sham)")
        openl = _has(text, r"(open[- ]label|unblinded|non-blinded)")
        put(ROB2_DOMAINS[1], "Low" if blind and itt else ("Some concerns" if blind or itt else
                                                          ("Some concerns" if openl else NO_INFO)),
            blind or itt or openl, "Blinding/ITT analysis cues")
        put(ROB2_DOMAINS[2], "Low" if (itt or imput) else ("Some concerns" if attrition else NO_INFO),
            itt or imput or attrition, "Handling of missing outcome data")
        assessor = _has(text, r"(blinded (outcome )?assess|assessor[s]? (were )?blind|objective outcome|mortality|"
                              r"all-cause death|laboratory[- ]measured)")
        put(ROB2_DOMAINS[3], "Low" if assessor or blind else ("High" if openl and "self-report" in text.lower()
                                                               else "Some concerns"),
            assessor or blind or openl, "Outcome assessment blinding / objectivity")
        put(ROB2_DOMAINS[4], "Low" if registered else "Some concerns", registered,
            "Prospective registration found" if registered else "No registration/protocol reference found")
    else:
        adj = _has(text, r"(adjusted for|multivariable|multivariate|propensity score|inverse probability|"
                         r"matched|confounder)")
        put(ROBINS_I_DOMAINS[0], "Moderate" if adj else "Serious", adj,
            "Confounding addressed by adjustment" if adj else "No confounding control reported")
        put(ROBINS_I_DOMAINS[1], "Moderate" if _has(text, r"(consecutive|population-based|registry)") else NO_INFO,
            _has(text, r"(consecutive|population-based|registry)"), "Participant selection")
        put(ROBINS_I_DOMAINS[2], "Low" if _has(text, r"(prescription record|medical record|registry|defined as)")
            else NO_INFO, _has(text, r"(prescription record|medical record|registry|defined as)"),
            "Intervention classification")
        put(ROBINS_I_DOMAINS[3], NO_INFO, None, "Rarely assessable from abstracts")
        put(ROBINS_I_DOMAINS[4], "Low" if imput else ("Moderate" if attrition else NO_INFO), imput or attrition,
            "Missing data handling")
        put(ROBINS_I_DOMAINS[5], "Low" if _has(text, r"(blind|objective|mortality|laboratory)") else "Moderate",
            _has(text, r"(blind|objective|mortality|laboratory)"), "Outcome measurement")
        put(ROBINS_I_DOMAINS[6], "Low" if registered else "Moderate", registered, "Protocol/registration")
    overall = overall_judgement(tool, [d["judgement"] for d in dom.values()])
    return {"record_id": rec.record_id, "tool": tool, "domains": dom, "overall": overall, "provisional": True}


def rob_matrix(studies) -> dict:
    """Group StudyOutcome-like objects (with rob_tool/rob_domains/rob_overall) into tool-specific matrices."""
    out: dict[str, dict] = {}
    seen = set()
    for s in studies:
        if s.study_label in seen:
            continue
        seen.add(s.study_label)
        tool = normalize_tool(s.rob_tool, s.design)
        domains = ROB2_DOMAINS if tool == "RoB2" else ROBINS_I_DOMAINS
        js = {d: normalize_judgement(s.rob_domains.get(d, ""), tool) for d in domains}
        overall = normalize_judgement(s.rob_overall, tool) if s.rob_overall else overall_judgement(tool, list(js.values()))
        m = out.setdefault(tool, {"domains": domains, "rows": []})
        m["rows"].append({"study": s.study_label, "judgements": js, "overall": overall})
    return out


COLORS = {"Low": "#4caf50", "Some concerns": "#ffc107", "Moderate": "#ffc107", "High": "#e53935",
          "Serious": "#e53935", "Critical": "#7b1fa2", NO_INFO: "#bdbdbd", "": "#ffffff"}


def render_traffic_light(matrix: dict, path) -> object:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    domains = matrix["domains"] + ["Overall"]
    rows = matrix["rows"]
    fig, ax = plt.subplots(figsize=(1.2 * len(domains) + 2.5, 0.42 * len(rows) + 1.8))
    for i, r in enumerate(rows):
        vals = [r["judgements"].get(d, "") for d in matrix["domains"]] + [r["overall"]]
        for j, v in enumerate(vals):
            ax.scatter(j, i, s=260, color=COLORS.get(v, "#ffffff"), edgecolors="#333", linewidths=0.5)
    ax.set_xticks(range(len(domains)))
    ax.set_xticklabels([d.split(" ")[0] if d != "Overall" else "Overall" for d in domains])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["study"] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(-0.6, len(domains) - 0.4)
    ax.grid(False)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    levels = (ROB2_LEVELS if len(matrix["domains"]) == len(ROB2_DOMAINS) else ROBINS_LEVELS) + [NO_INFO]
    legend = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS[l], markeredgecolor="#333",
                         markersize=9, label=l) for l in levels]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path

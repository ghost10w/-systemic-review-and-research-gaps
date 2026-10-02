"""Turn ranked gaps into structured research proposals (PICO + FINER + hypotheses + methods).

All automatically derived fields can be overridden by the user (``pico_overrides``),
and every FINER score carries its rationale so it can be audited.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from statsmodels.stats.power import NormalIndPower, TTestIndPower

from ureme.gaps.detector import Gap
from ureme.gaps.lexicon import STOPWORDS
from ureme.models import Record

_POP_NOUNS = (r"patients|adults|children|adolescents|women|men|participants|individuals|infants|neonates|"
              r"survivors|smokers|students|older adults|elderly|veterans|workers|athletes|people|mothers|pregnant women")
_STOP_AFTER = r"(?:were|was|who|are|is|and|or|in|to|from|using|at|by|for|that|which|underwent|received|completed)"
_POP = re.compile(rf"\b((?:[A-Za-z\-]+\s){{0,3}}(?:{_POP_NOUNS})(?:\s+(?:with|after|undergoing|receiving|at risk of)"
                  rf"(?:\s+(?!{_STOP_AFTER}\b)[A-Za-z0-9\-]+){{1,4}})?)", re.I)
_LEAD_TRIM = set(STOPWORDS) | {"we", "enrolled", "recruited", "studied", "involving", "comprising", "eligible",
                                 "consecutive", "total", "were", "was", "assigned", "allocated", "included", "a", "an"}
_OUTCOME = re.compile(r"\b(?:primary|secondary)?\s*(?:outcomes?|end-?points?)\s+(?:was|were|included|was the|"
                      r"measures? (?:was|were))\s+([^.;:]{4,90})", re.I)
_OUTCOME_WORDS = ["mortality", "survival", "quality of life", "pain", "depression", "anxiety", "hospitalization",
                  "hospitalisation", "readmission", "recurrence", "remission", "adverse events", "function",
                  "cognitive function", "blood pressure", "hba1c", "weight", "incidence", "relapse", "symptom severity",
                  "length of stay", "complications", "response rate", "adherence"]
_VULNERABLE = re.compile(r"child|infant|neonat|pregnan|elderly|older adults|prisoner|cognitive impair|dementia|"
                         r"psychiatric", re.I)
_INVASIVE = re.compile(r"surgery|surgical|implant|radiation|chemotherap|transplant|invasive|placebo surgery|"
                       r"withhold", re.I)

DESIGNS = {
    "Methodological": ("pragmatic, multicentre, randomised controlled trial",
                       ["Prospectively registered protocol (ClinicalTrials.gov) and SPIRIT-compliant reporting",
                        "Adequately powered sample size (see power calculation) with concealed central randomisation",
                        "Blinded outcome assessment and pre-specified primary outcome; intention-to-treat analysis",
                        "Follow-up long enough to capture clinically meaningful outcomes; CONSORT reporting"]),
    "Population": ("multicentre prospective cohort with stratified recruitment of under-represented groups",
                   ["Purposive/stratified sampling targeting the under-represented population",
                    "Pre-specified subgroup and interaction analyses (sex, age, ethnicity, setting)",
                    "Validated, culturally adapted outcome measures; STROBE reporting",
                    "Consider an embedded pragmatic trial once effect plausibility is established"]),
    "Mechanistic": ("mechanistic study combining experimental and causal-inference approaches",
                    ["Biomarker or imaging sub-study nested in an existing cohort/trial",
                     "Formal mediation analysis (counterfactual framework) of the hypothesised pathway",
                     "Where suitable, Mendelian randomisation or dose-response analyses for causal inference",
                     "Pre-registered analysis plan and open data/code"]),
    "Knowledge/Evidence": ("systematic review and meta-analysis followed by a confirmatory study",
                           ["PROSPERO-registered systematic review and meta-analysis (PRISMA 2020) to quantify the gap",
                            "GRADE assessment of certainty to identify the decisive uncertainty",
                            "Confirmatory prospective study or trial designed around the identified uncertainty",
                            "Cost-effectiveness / implementation outcomes where relevant"]),
}


@dataclass
class Proposal:
    proposal_id: str
    gap_id: str
    category: str
    title: str
    pico: dict
    research_question: str
    hypothesis: str
    null_hypothesis: str
    rationale: str
    design: str
    methods: list[str]
    sample_size: dict
    finer: dict
    finer_total: float
    references: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _most_common(items: list[str], default: str) -> str:
    items = [re.sub(r"\s+", " ", i).strip(" ,.;").lower() for i in items if i and len(i.strip()) > 3]
    return Counter(items).most_common(1)[0][0] if items else default


def extract_population(records: list[Record], default: str) -> str:
    found = []
    for r in records:
        for m in _POP.finditer(r.abstract or ""):
            words = m.group(1).split()
            while len(words) > 1 and (words[0].lower() in _LEAD_TRIM or words[0].isdigit()):
                words.pop(0)
            phrase = " ".join(words)
            found.append(phrase)
    return _most_common(found, default)


def extract_outcome(records: list[Record], default: str) -> str:
    found = [m.group(1) for r in records for m in _OUTCOME.finditer(r.abstract or "")]
    if found:
        return _most_common(found, default)
    text = " ".join(r.text.lower() for r in records)
    counts = {w: text.count(w) for w in _OUTCOME_WORDS}
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] else default


def sample_size(category: str, effect_sizes=(0.3, 0.5), alpha: float = 0.05, power: float = 0.8) -> dict:
    """Per-arm N for a two-arm comparison of means (Cohen's d) and of proportions (Cohen's h)."""
    out = {"alpha": alpha, "power": power, "continuous": {}, "dichotomous": {}}
    for d in effect_sizes:
        out["continuous"][f"d={d}"] = math.ceil(TTestIndPower().solve_power(effect_size=d, alpha=alpha, power=power))
    for p1, p2 in ((0.30, 0.20), (0.20, 0.15)):
        h = abs(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)))
        out["dichotomous"][f"{int(p1 * 100)}% vs {int(p2 * 100)}%"] = math.ceil(
            NormalIndPower().solve_power(effect_size=h, alpha=alpha, power=power))
    out["note"] = ("Per-arm sample sizes for illustrative effect sizes; replace with estimates from pilot data or "
                   "the pooled effect of the systematic review. Inflate for expected attrition.")
    if category == "Mechanistic":
        out["note"] += " Mediation analyses typically need substantially larger samples than total-effect tests."
    return out


def score_finer(gap: Gap, recs: list[Record], all_records: list[Record], pico: dict, category: str) -> dict:
    feas_base = {"Knowledge/Evidence": 5, "Population": 4, "Methodological": 3, "Mechanistic": 3}[category]
    feas = min(5, feas_base + (1 if len(all_records) >= 20 else 0) - (1 if gap.n_records < 2 else 0))
    cites = [r.citation_count or 0 for r in recs]
    mean_c = sum(cites) / len(cites) if cites else 0
    interesting = min(5, 2 + round(math.log1p(mean_c) / 1.5) + (1 if gap.subtype == "conflicting evidence" else 0))
    theme_words = [w for w in gap.theme.lower().split() if len(w) > 3]
    addressing = sum(all(w in r.title.lower() for w in theme_words) for r in all_records) if theme_words else 0
    share = addressing / max(len(all_records), 1)
    novel = 5 if share < 0.02 else 4 if share < 0.05 else 3 if share < 0.15 else 2
    text = f"{pico['population']} {pico['intervention']}"
    ethical = 4 - (1 if _VULNERABLE.search(text) else 0) - (1 if _INVASIVE.search(text) else 0)
    years = [r.year for r in recs if r.year]
    relevant = min(5, 2 + min(2, gap.n_records // 2) + (1 if years and max(years) >= max(
        (r.year or 0) for r in all_records) - 1 else 0))
    rationale = {
        "Feasible": f"{category} design; {len(all_records)} related records provide groundwork; "
                    f"{gap.n_records} studies document the gap.",
        "Interesting": f"Mean citation count of source studies = {mean_c:.1f}"
                       + ("; resolving conflicting evidence is of high interest." if gap.subtype ==
                          "conflicting evidence" else "."),
        "Novel": f"{addressing} of {len(all_records)} retrieved records ({share:.0%}) mention the theme in the title.",
        "Ethical": "Involves a vulnerable population or invasive intervention - requires careful ethics review."
                   if ethical < 4 else "No obvious ethical red flags; standard IRB/ethics approval required.",
        "Relevant": f"Raised by {gap.n_records} studies, including recent publications ({max(years) if years else 'n/a'}).",
    }
    scores = {"Feasible": feas, "Interesting": interesting, "Novel": novel, "Ethical": max(1, ethical),
              "Relevant": relevant}
    return {k: {"score": v, "rationale": rationale[k]} for k, v in scores.items()}


def _hypotheses(category: str, p: dict, theme: str, subtype: str) -> tuple[str, str, str]:
    P, I, C, O = p["population"], p["intervention"], p["comparison"], p["outcome"]
    if category == "Mechanistic":
        q = f"Is the effect of {I} on {O} in {P} mediated by mechanisms involving {theme}?"
        h1 = (f"In {P}, the effect of {I} (vs {C}) on {O} is significantly mediated by mechanisms involving "
              f"{theme}.")
        h0 = f"In {P}, mechanisms involving {theme} do not mediate the effect of {I} on {O} (indirect effect = 0)."
    elif category == "Population":
        q = (f"Does the effect of {I} compared with {C} on {O} hold in {P}, including groups under-represented in "
             f"current evidence (gap: {theme})?")
        h1 = (f"In {P}, {I} compared with {C} improves {O}, and the effect differs across the population "
              f"characteristics flagged by the gap ({theme}).")
        h0 = (f"In {P}, there is no difference in {O} between {I} and {C}, and no effect modification across the "
              f"flagged population characteristics.")
    elif subtype == "conflicting evidence":
        q = f"Does {I} compared with {C} change {O} in {P}, given conflicting evidence regarding {theme}?"
        h1 = f"In an adequately powered study of {P}, {I} produces a clinically important difference in {O} vs {C}."
        h0 = f"In {P}, {I} produces no clinically important difference in {O} compared with {C}."
    else:
        q = f"In {P}, does {I} compared with {C} improve {O}?"
        h1 = f"In {P}, {I} results in a significant difference in {O} compared with {C} in a rigorously designed study that overcomes the documented limitation ('{theme}')."
        h0 = f"In {P}, there is no difference in {O} between {I} and {C}."
    return q, h1, h0


def generate_proposals(gaps: list[Gap], records: list[Record], query_terms: list[str], top_n: int = 5,
                       pico_overrides: dict | None = None) -> list[Proposal]:
    by_id = {r.record_id: r for r in records}
    overrides = {k: v for k, v in (pico_overrides or {}).items() if v}
    intervention_default = query_terms[0] if query_terms else "the intervention of interest"
    proposals = []
    for i, gap in enumerate(gaps[:top_n], start=1):
        recs = [by_id[rid] for rid in gap.record_ids if rid in by_id]
        base_population = extract_population(recs or records, "the target population")
        population = base_population
        if gap.category == "Population":
            population = f"{base_population}, prioritising groups under-represented in current evidence"
        pico = {
            "population": population,
            "intervention": intervention_default,
            "comparison": "usual care or placebo",
            "outcome": extract_outcome(recs or records, "the primary clinical outcome"),
        }
        pico.update(overrides)
        q, h1, h0 = _hypotheses(gap.category, pico, gap.theme, gap.subtype)
        design, methods = DESIGNS[gap.category]
        finer = score_finer(gap, recs, records, pico, gap.category)
        total = round(sum(v["score"] for v in finer.values()) / 5, 2)
        rationale = (f"{gap.description} Supporting statements were extracted from {len(recs)} recent publications "
                     f"({', '.join(sorted({str(r.year) for r in recs if r.year})) or 'n/a'}). Addressing this gap "
                     f"would strengthen the evidence base on {intervention_default} and inform practice and future "
                     f"guideline recommendations.")
        title_pop = overrides.get("population") or base_population
        focus = f", addressing {gap.theme}" if not gap.theme.endswith(" issues") else ""
        title = (f"{pico['intervention'].capitalize()} versus {pico['comparison'].split(',')[0]} for "
                 f"{pico['outcome']} in {title_pop}: a {design}{focus}")
        proposals.append(Proposal(
            proposal_id=f"P{i:02d}", gap_id=gap.gap_id, category=gap.category, title=title, pico=pico,
            research_question=q, hypothesis=h1, null_hypothesis=h0, rationale=rationale, design=design,
            methods=list(methods), sample_size=sample_size(gap.category), finer=finer, finer_total=total,
            references=[r.citation() for r in recs[:8]], reference_ids=[r.record_id for r in recs[:8]],
        ))
    proposals.sort(key=lambda p: -p.finer_total)
    for i, p in enumerate(proposals, start=1):  # number in ranked order
        p.proposal_id = f"P{i:02d}"
    return proposals

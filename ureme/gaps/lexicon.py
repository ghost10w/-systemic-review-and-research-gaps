"""Pattern lexicons for gap mining.  Extend these lists to tune recall for a field."""

GAP_MARKERS = [
    r"\blimitations?\b", r"\bfurther (research|studies|investigation|work|trials?) (is|are) (needed|required|warranted)",
    r"\bfuture (research|studies|trials|work|investigations?)\b", r"\bremains? (unclear|unknown|uncertain|elusive|"
    r"poorly understood|to be (determined|elucidated|established))", r"\b(little|less) is known\b",
    r"\bnot (yet )?(been )?(well )?(established|studied|investigated|explored|examined|elucidated|understood)",
    r"\b(lack|paucity|scarcity|dearth|absence) of\b", r"\bknowledge gap", r"\bevidence gap", r"\bgaps? in\b",
    r"\b(warrant|warrants|warranted)\b", r"\b(inconsistent|conflicting|contradictory|mixed|equivocal) "
    r"(results|findings|evidence|data)", r"\bunanswered\b", r"\bunderexplored|under-explored|understudied|"
    r"under-studied|underrepresented|under-represented", r"\bshould be (interpreted with caution|confirmed|validated)",
    r"\bneeds? (to be )?(confirm|validat|replicat)", r"\bno (previous |prior )?(studies|trials|data) (have|has)",
    r"\b(is|are) (still )?(lacking|limited|scarce|sparse)\b", r"\b(larger|well-designed|adequately powered|"
    r"long-term|prospective) (studies|trials|cohorts?) (are|is) (needed|required|warranted)",
]

CATEGORY_LEXICON = {
    "Methodological": [
        r"small sample", r"sample size", r"underpowered|under-powered|statistical power", r"retrospective",
        r"cross-sectional design", r"observational (design|nature)", r"single[- ]cent(er|re)", r"selection bias",
        r"confound", r"short(er)? follow-?up", r"follow-?up (was|period) (short|limited)", r"self-report",
        r"recall bias", r"lack of (a )?control group", r"non-?randomi[sz]ed", r"open[- ]label", r"heterogene",
        r"measurement", r"standardi[sz]ed (protocol|definition|outcome)", r"risk of bias", r"methodolog",
        r"randomi[sz]ed (controlled )?trials? (are|is) (needed|required|warranted)", r"well-designed",
        r"adequately powered", r"blinding|unblinded",
    ],
    "Population": [
        r"generali[sz]ab", r"external validity", r"children|paediatric|pediatric|adolescen", r"older adults|elderly",
        r"\bwomen\b|female|sex differences|gender", r"ethnic|racial|race\b|minorit", r"low- and middle-income|"
        r"\blmic|developing countries|low-income", r"underrepresented|under-represented|diverse population",
        r"comorbid", r"pregnan", r"rural", r"specific population|other populations|different populations",
        r"socioeconomic", r"non-western|asian|african|latin",
    ],
    "Mechanistic": [
        r"mechanism", r"pathway", r"pathophysiolog", r"mediat", r"molecular", r"biological basis|biologic",
        r"causal|causality", r"signal(l)?ing", r"inflammat", r"genetic|genomic|epigenetic", r"biomarker",
        r"how .* (works?|affects?|influences?)", r"underlying", r"neurobiolog|neural", r"microbio",
        r"dose[- ]response", r"mode of action",
    ],
    "Knowledge/Evidence": [
        r"little is known", r"remains? (unclear|unknown|uncertain)", r"no (previous|prior) stud", r"limited evidence",
        r"evidence (is|remains) (limited|scarce|lacking|insufficient)", r"conflicting|inconsistent|contradictory",
        r"knowledge gap|evidence gap", r"not been (investigated|studied|explored)", r"long-term (effects|outcomes)",
        r"cost-effectiveness", r"comparative effectiveness", r"implementation", r"real-world",
    ],
}

POSITIVE_FINDING = [
    r"significantly (improv|reduc|increas|decreas|lower|higher|associat|enhanc|attenuat|prevent)",
    r"(was|were) (significantly |independently )?associated with (an? )?(increased|decreased|higher|lower|reduced|"
    r"greater|improved)", r"\beffective (in|for|at)\b", r"\bbeneficial\b", r"\bsuperior to\b",
    r"\bresulted in (a )?(significant|marked)", r"\bsignificant (improvement|reduction|increase|decrease|benefit|"
    r"effect|association)",
]
NULL_FINDING = [
    r"\bno (statistically )?significant (difference|effect|association|improvement|change|benefit|reduction)",
    r"\b(was|were|is|are) not (significantly )?(associated|different|effective|improved)",
    r"\bdid not (significantly )?(differ|improve|reduce|increase|change|affect|decrease|show)",
    r"\bno (difference|effect|association|benefit)\b", r"\bnon-?significant\b", r"\bfailed to (show|demonstrate)",
    r"\bcomparable (between|to|with)\b", r"\bnot superior\b",
]

STOPWORDS = set("""
a about above after again against all also although am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how however i if in into is it its itself just less may might
more most much must my no nor not of off on once only or other our ours out over own same she should so some
such than that the their theirs them themselves then there these they this those through to too under until
up upon very was we were what when where which while who whom why will with would you your yet study studies
studied research results result findings finding future further need needed needs required warranted limitation
limitations limited remains remain unclear unknown known little lack evidence data investigation investigations
present current trial trials patients participants however therefore thus well use used using based including
include included among within whether well-designed larger long-term warrant warrants confirm confirmed among
investigate investigated explore explored examined examine understanding understood elucidate elucidated
important potential possible possibly could various several one two three first second effect effects
significant significantly analysis analyses showed show shown suggest suggests suggested associated association
outcomes outcome group groups compared controlled randomized randomised clinical paper report reports reported
whereas mostly mainly especially particular particularly given terms term address addressed addressing
caution interpreted interpretation role roles aspect aspects factor factors small sample size sizes design designs due owing because generalizability
""".split())

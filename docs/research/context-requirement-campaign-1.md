# ICAB context-requirement campaign 1

Research-quality write-up of the first campaign run under
[`context-requirement-protocol.md`](context-requirement-protocol.md),
using `icab.tasks.experiment_design`/`icab.tasks.context_conditions`/
`icab.benchmark.context_experiment` (commit `3bbef33`) against ICAB's
real Docker infrastructure and NIST RChat. All numbers below are read
directly off persisted `ExperimentRecord`s under `results/raw/` — none
invented. Every quantitative claim cites the `run_id`(s) it rests on.

## 1. Experimental question

> What context does an industrial AI agent actually need to complete a
> specific ISA-95-level industrial use case, and which architectures
> can reliably expose it?

## 2. Experimental design

### Cohort (Phase 3)

Five use cases, chosen for genuinely different context requirements and
including both previously-difficult cases named in the task:

| Use case | ISA-95 level | Required | Candidate | Why selected |
|---|---|---|---|---|
| `eq-abnormal-behavior-diagnosis` | Equipment | C4, C3 | C4, C3, C5, C7 | Explicitly named as currently difficult (no tested condition met `pass_threshold=1.0` as of the prior milestone); diagnosis task type, temporal+relational requirement |
| `eq-value-and-relationship-combination` | Equipment | C5, C3 | C5, C3, C2 | Second Equipment use case with a MEANINGFULLY DIFFERENT requirement (operational+relational, not temporal+relational); already had partial real evidence to build repetition on |
| `pc-equipment-composition-discovery` | Process Cell | C1, C2 | C1, C2, C3 | Explicitly named as currently difficult; QA task type (not diagnosis), semantic+hierarchy requirement — architecturally distinct from every other cohort member (uns/opcua, not historian/knowledge_graph) |
| `pc-cross-unit-diagnosis` | Process Cell | C4, C3 | C4, C3, C5 | Second Process Cell use case, diagnosis type (parallels `eq-abnormal-behavior-diagnosis` one level up the ISA-95 hierarchy — same required dimensions, different level, useful cross-level comparison); had ZERO prior data |
| `area-process-cell-composition` | Area | C2, C3 | C2, C3, C1 | The only ISA-95 level besides Equipment/Process Cell with any real use case; carries the known `knowledge_graph`-only discoverability challenge explicitly called out in the task |

Not selected, and not fabricated to pad the cohort: `area-site-membership-identification`
(Area, 0 data, would duplicate the single-architecture structural
constraint already studied via `area-process-cell-composition`) and the
remaining 9 Equipment/Process Cell use cases (selected two per level was
the stated minimum; adding more without a specific new question would
not have added scientific value this campaign, per the explicit
instruction not to over-expand scope).

### Tasks, scenarios, architectures (Phase 4 reference conditions)

| Use case | Task | Scenario | Task's `available_architectures` | Realizable maximum | Within `candidate_context`? |
|---|---|---|---|---|---|
| `eq-abnormal-behavior-diagnosis` | `d2cooling-diagnosis-heat-transfer-category` | `d2_reactor_cooling_deviation` (fault `idv_17`) | historian, knowledge_graph | `C2+C3+C4+C5+C6+C7` | **No** — C2, C6 exceed `{C3,C4,C5,C7}` |
| `eq-value-and-relationship-combination` | `d2ctx-investigation-combine-value-and-relationship` | `d2_reactor_context_combination` | historian, knowledge_graph | `C2+C3+C4+C5+C6+C7` | **No** — C4, C6, C7 exceed `{C2,C3,C5}` |
| `pc-equipment-composition-discovery` | `d4plant-qa-discover-equipment` | `d4_plant_wide_investigation` | uns, opcua | `C1+C2+C5` | **No** — C5 exceeds `{C1,C2,C3}`; **also** C3 (in candidate) is UNREACHABLE by this task's own architectures at all |
| `pc-cross-unit-diagnosis` | `d4plant-diagnosis-reactor-vs-downstream` | `d4_plant_wide_investigation` | historian, knowledge_graph | `C2+C3+C4+C5+C6+C7` | **No** — C2, C6, C7 exceed `{C3,C4,C5}` |
| `area-process-cell-composition` | `area-investigation-process-cell-composition` | `d2_reactor_context_combination` | knowledge_graph | `C2+C3+C6` | **No** — C6 exceeds `{C1,C2,C3}` |

**Observed finding, all five cohort members:** the task's own
architecture-realizable maximum context ALWAYS exceeds the use case's
own declared `candidate_context` in this dataset — every architecture
that supplies a use case's required dimension(s) also supplies at least
one dimension the use case's own design never asked for. This is
consistent with, and now independently reproduced beyond, the single
architecture-realizability finding from the prior milestone (only 13/127
combinations realizable in isolation). It means "give the agent the
richest available context" and "give the agent exactly what this use
case needs" are two different, genuinely competing experimental
conditions in this system, not the same thing under a different name.

### Design strategies actually executed (Phases 5-7)

Per use case (see `docs/research/context-requirement-protocol.md` for
the general rule): the reference/full-realizable condition (Phase 4,
run with use-case scoping disabled since it exceeds `candidate_context`
by construction), a single-dimension sweep restricted to dimensions
within `candidate_context` (Phase 5, `--allow-overshoot` since almost
nothing resolves EXACT — see the 13/127 finding), and 1-3 pairwise/
ablation conditions targeting the use case's own `required_context` pair
plus one or two others (Phase 6/7). Agent fixed at `llm` (NIST RChat,
temperature 0.0), `max_steps=12`, throughout every new run in this
campaign.

### Repetition (Phase 8)

Every condition that already had `n=1` going into this campaign was
repeated at a second, distinct seed (seed 2) wherever the campaign
touched it. `pc-cross-unit-diagnosis` (a brand-new use case this
campaign) and the single-dimension conditions were run once (`n=1`)
given the campaign's budget — reported honestly as `tentative_small_n`,
not treated as a stable estimate.

### Success predicate (Phase 9)

Unchanged `GroundedInvestigationEvaluator` + each use case's own,
already-declared `EvaluationCriteria.binding_scores` at the explicit
default `pass_threshold=1.0` — see the protocol document. No threshold
was lowered for this campaign.

## 3. Coverage (report these numbers plainly, per instruction)

```
127 theoretical non-empty context combinations (2^7 - 1)
 13 realizable in isolation by ICAB's 6 real architectures
  6 distinct combinations actually executed in tep-v2, all-time
     (C1+C2, C2+C5, C1+C2+C5, C4+C5+C7, C2+C3+C6, C2+C3+C4+C5+C6+C7)
 33 individual runs across the 5-use-case cohort this campaign analyzes
     (18 new this campaign + 15 carried over from the prior milestone)
 33/33 completed without an orchestration-level failure (0 crashes)
  3/33 individually met EVERY one of their use case's binding scores at pass_threshold=1.0
  1/15 tested (use case, condition) pairs across the cohort met the threshold ON A CONDITION-MEAN basis
     (eq-value-and-relationship-combination's C2+C3+C4+C5+C6+C7, n=2)
```

None of the 127/13/6 numbers changed from the prior milestone's own
report except the executed count (was implicitly smaller before this
campaign) — this campaign did not attempt, and does not claim to have
attempted, anywhere near the full realizable set, let alone the full
127-combination space.

## 4. Results by use case

### `eq-abnormal-behavior-diagnosis` (13 runs, `tentative`→`repeated_empirical_result`)

Tested: `C2+C3+C6` (n=2), `C4+C5+C7` (n=6), `C2+C3+C4+C5+C6+C7` (n=5).

**Necessity** (metric `required_evidence_score`): every candidate
dimension shows a positive delta with evidence on both sides —
C3 delta=+0.71 (n_with=7, n_without=6), C4/C5/C7 delta=+0.45 each
(n_with=11, n_without=2). C3's delta is markedly larger than C4/C5/C7's,
despite C4 being one of this use case's own two `required_context`
dimensions — **tentative interpretation**, not yet a strong finding
given the small `n_without` for C4/C5/C7 (only 2 runs on the "without"
side, both `C2+C3+C6`).

**Sufficiency:** NO tested condition meets `pass_threshold=1.0` —
`candidate_minimum_sufficient_contexts: []`. Even the full
architecture-realizable `C2+C3+C4+C5+C6+C7` (n=5) reaches
`required_evidence_score=1.0`, `relationship_score=1.0`,
`grounding_score=1.0` but only `conclusion_correctness_score=0.25`
(run_ids: `v2ctx-equipment-ablation-C3+C5-historian+knowledge_graph-seed1-rep1`,
`v2study-uc1-a-C3+C4-historian+knowledge_graph-seed1-rep1`,
`v2study-uc1-b-...-seed1-rep1`, `v2study-uc1-b-...-seed2-rep1`,
`v2study-uc1-c-C3+C4-...-seed2-rep1`). Inspecting one of these runs
directly (`v2study-uc1-b-...-seed1-rep1`): the agent's conclusion
correctly cited the affected measurement's live value
(`urn:icab:measurement:reactor_cooling_water_outlet_temperature_meas`
at 95.10 degC) and correctly named the implicated equipment
(`urn:icab:equipment:reactor`, `affected_assets_mentioned` = True), but
`root_cause_identified=False` and `affected_assets_mentioned` was False
for the measurement id itself — the evaluator's heuristic requires the
conclusion to name a specific root-cause category AND cite the exact
measurement canonical id together; this run's prose ("suggesting a
cooling system process issue") was evidentially grounded but not phrased
in the form the deterministic check matches. **This is a genuine, cited
limitation of the evaluator's causal-conclusion heuristic
(`EvaluationCriteria.known_limitations`, unchanged, pre-existing since
M8/M13-C)** as much as it is evidence about the agent's reasoning — see
Section 9.

**Failure/discoverability:** all 8 single/narrower-architecture runs
land at `discovered_identifier` (efficiency_failure — every one
terminated via `step_budget_exceeded` at exactly 12 tool calls, verified
directly on `v2study-uc1-a-C4-historian-seed1-rep1`); all 5
full-context runs reach `grounded_in_conclusion` but classify as
`reasoning_failure`.

### `eq-value-and-relationship-combination` (6 runs, `repeated_empirical_result`)

Tested: `C2+C3+C6` (n=2), `C4+C5+C7` (n=2), `C2+C3+C4+C5+C6+C7` (n=2).

**Sufficiency: FOUND.** `C2+C3+C4+C5+C6+C7` (n=2) meets every binding
score (`required_evidence_score=1.0`, `relationship_score=1.0`,
`grounding_score=1.0`) at BOTH seeds
(`v2-necessity-demo-combined-...-seed1-rep1`,
`v2study-uc2-a-C2+C3+C4+C5+C6+C7-...-seed2-rep1`) — the only
condition-level success in this entire campaign. `candidate_minimum_sufficient_contexts: ["C2+C3+C4+C5+C6+C7"]`
— reported as the (sole) candidate MSC **among tested conditions**; the
smaller `C3+C5`/`C2+C3` etc. were never tested for this task (both
architectures together were the only route to `relationship_score=1.0`
in the data collected), so this is explicitly NOT a claim that a smaller
combination is insufficient, only that none was tested.

**Necessity:** C5 delta=+1.0 (n_with=4, n_without=2, clean). C3 and C2
BOTH show a delta of **-0.5** (mean_with=0.5, mean_without=1.0) —
**counter to intuition, and a confound, not a finding**: the "without
C3" side is entirely `C4+C5+C7` (historian alone), which happens to
score `required_evidence_score=1.0` for THIS task's specific ground
truth, while the "with C3" side pools `C2+C3+C6` (kg alone, scores 0.0)
and the full combo (scores 1.0). With only 3 distinct combinations
tested, per-dimension with/without partitioning is confounded by which
OTHER dimensions happen to travel with C3 in this architecture's
overshoot pattern — flagged explicitly rather than read as "C3 hurts."

### `pc-equipment-composition-discovery` (7 runs, `repeated_empirical_result`, agent-mixed)

Tested: `C1+C2` (n=3, 2 `llm` + 1 `scenario_aware`), `C2+C5` (n=2, 1
`llm` + 1 `scenario_aware`), `C1+C2+C5` (n=2, both `llm`).

**Sufficiency:** NO condition meets threshold — `canonical_id_score`
is the binding blocker throughout, and shows a striking, non-monotonic
pattern: `C1+C2`=0.31 (pooled), `C2+C5`=0.96 (pooled), `C1+C2+C5`
(both architectures together)=**0.0** — MORE context (adding the second
architecture) produced a WORSE canonical-id score than either single
architecture alone, on both seeds
(`v2study-uc3-a-C1+C2+C5-opcua+uns-seed1-rep1`,
`...-seed2-rep1`). This directly illustrates the task's explicit warning
against assuming "more context is automatically better": combining
`uns` and `opcua` together appears to have confused the agent's
canonical-id citation format rather than improving it — a genuine,
observed finding, though `n=2` at this specific combination is thin.

**Agent-mixing caveat (methodological, not a substantive finding):**
splitting by agent type changes the picture for `C1+C2`: the 2 `llm`
runs both score `canonical_id_score=0.0`
(`v2ctx-processcell-ablation-C1+C2-uns-seed1-rep1`,
`v2ctx-processcell-ablation-C1-uns-seed1-rep1`), while the 1
`scenario_aware` (deterministic baseline) run scores 0.92
(`v2-process-cell-smoke-...-uns-seed1-rep1`). The pooled 0.31 figure
above is a real mean over what was actually run, but an LLM-only
reading is more relevant to "does the LLM AGENT need this context," and
it shows the LLM alone never exceeded 1.0 canonical_id_score at ANY
tested combination for this task.

### `pc-cross-unit-diagnosis` (4 runs, `tentative_small_n`, brand-new use case)

Tested: `C2+C3+C6` (n=1), `C4+C5+C7` (n=1), `C2+C3+C4+C5+C6+C7` (n=2).

Same qualitative pattern as `eq-abnormal-behavior-diagnosis` one ISA-95
level up: `required_evidence_score`/`relationship_score` both reach 1.0
at full context, `conclusion_correctness_score` caps at 0.25
(`v2study-uc4-a-C3+C4-...-seed1-rep1`,
`v2study-uc4-b-C2+C3+C4+C5+C6+C7-...-seed1-rep1`). Necessity deltas
(C4=+0.83, C5=+0.83, C3=+0.17, all `n_without=1`) are consistent in
DIRECTION with `eq-abnormal-behavior-diagnosis` but rest on single
observations per side — reported as an early, cross-level-consistent
signal, not a confirmed result.

### `area-process-cell-composition` (3 runs, `tentative_small_n`)

Only ONE combination was ever reachable at all —`C2+C3+C6`, always via
`knowledge_graph` alone, regardless of which target (`C2`, `C3`, or
`C2+C3`) was requested, because this task declares exactly one
architecture (see the protocol's Step 1 note: this is the single
clearest real illustration in the whole dataset of the "task's
realizable space is a subset of one point" case). All 3 runs, across
BOTH tested seeds, score `required_evidence_score=0.0`,
`relationship_score=0.0`, `completeness_score=0.0` — a perfectly
consistent, 3-for-3, cross-seed failure
(`v2-area-smoke-...-knowledge_graph-seed1-rep1`,
`v2ctx-area-targeted-C2+C3-knowledge_graph-seed1-rep1`,
`v2study-uc5-a-C2+C3-knowledge_graph-seed2-rep1`). All 3 classify at
discoverability stage `discovered_identifier` — the agent acquired a
string that LOOKED like a candidate identifier
(e.g. `Reaction_Area_Cell_1`, `ReactionArea`) but never one that matched
the real canonical id, and never advanced past this stage. See Section 8.

## 5. Context necessity (cross-use-case synthesis)

Both diagnosis-type use cases in the cohort (`eq-abnormal-behavior-diagnosis`,
`pc-cross-unit-diagnosis`) show their declared `required_context`
dimensions (C3, C4) with a clearly positive necessity delta on
`required_evidence_score`, consistent across two different ISA-95
levels using the same context dimensions. **C3 was necessary under the
tested conditions** for both; **C4 was necessary under the tested
conditions** for both. Neither claim extends to "universally necessary"
— both rest on a single architecture pairing (historian + knowledge_graph)
and a single scenario/task per use case.

## 6. Context sufficiency

Only ONE (use case, condition) pair in the entire cohort met its
declared `pass_threshold=1.0`: `eq-value-and-relationship-combination`
at `C2+C3+C4+C5+C6+C7`. Every other tested condition for every other
cohort use case — including every tested FULL-context condition —
failed on at least one binding score, most often
`conclusion_correctness_score` (diagnosis use cases) or
`canonical_id_score` (`pc-equipment-composition-discovery`). This is the
single most important honest result of this campaign: **giving the
agent MORE context did not reliably make these use cases succeed** —
context sufficiency, evidence retrieval, and grounding were frequently
achieved (`required_evidence_score`/`grounding_score` = 1.0 at full
context in 3 of 4 non-Area use cases), while the REMAINING blocker was
either the evaluator's strict conclusion-correctness heuristic or (for
`pc-equipment-composition-discovery`) representation confusion from
combining two architectures.

## 7. Candidate MSC

| Use case | Candidate MSC(s) among tested | n | Note |
|---|---|---|---|
| `eq-abnormal-behavior-diagnosis` | none | — | No tested condition sufficient |
| `eq-value-and-relationship-combination` | `C2+C3+C4+C5+C6+C7` | 2 | Sole candidate — smaller combinations untested for this task |
| `pc-equipment-composition-discovery` | none | — | No tested condition sufficient |
| `pc-cross-unit-diagnosis` | none | — | No tested condition sufficient |
| `area-process-cell-composition` | none | — | Only one condition reachable at all, and it failed 3/3 |

No two INCOMPARABLE candidates were both sufficient in this campaign's
data (the partial-order logic in `icab.analysis.sufficiency
._minimal_sufficient_conditions` was exercised and is unit-tested for
that case — see Section 12 — but this specific dataset never produced
the situation).

## 8. Architecture exposure and discoverability

Separating REQUIREMENT from REPRESENTATION from ARCHITECTURE (Phase 13):
this campaign's required dimensions were C3 (Relational) and C4/C5
(Temporal/Operational) across most of the cohort. The representation
each architecture used was unchanged from the prior milestone
(`icab.analysis.representation.ARCHITECTURE_REPRESENTATION_LABELS`):
`knowledge_graph` exposes C3 as a typed relationship edge,
`historian` exposes C4/C5 as a time-series value. The conclusion is
deliberately NOT "knowledge_graph is required" — it is "relational
context (C3) showed a positive necessity delta, and `knowledge_graph`
was the only architecture in this cohort's tasks that could expose it
at all" (`CONTEXT_DIMENSION_ARCHITECTURES[C3] = {knowledge_graph, i3x}`,
and no cohort task declared `i3x` available).

**Discoverability, the Area case (Phase 14):** the `knowledge_graph`-only
Area task failed identically 3 times across 2 distinct seeds, always
stalling at `discovered_identifier` — the architecture connection itself
is verified healthy (`icab.architecture_health`, unchanged, still 7/7
PASS as of this campaign's Phase 1 check), so this is NOT an
architecture-connectivity failure. It is a genuine DISCOVERY-stage
failure: the agent has no way, using only `knowledge_graph`'s
relationship-query tools, to translate a plain-language reference ("the
Reaction Area") into the Area entity's real canonical id
(`urn:icab:area:reaction`) without a semantic/browsing layer (`uns`/
`i3x`) that this task does not grant. This is now a 3-for-3, 2-seed,
cross-campaign REPRODUCED empirical observation, not a one-off.

## 9. Failure analysis

Aggregated over the cohort's 33 runs (`icab.analysis.failure_taxonomy`):

| Category | n | Where |
|---|---|---|
| `efficiency_failure` | 15 | Every single/narrow-architecture run that ran out of its 12-step budget before completing discovery+retrieval |
| `reasoning_failure` | 7 | Full-context diagnosis runs where evidence/grounding hit 1.0 but `conclusion_correctness_score` did not |
| `representation_failure` | 6 | Every `pc-equipment-composition-discovery` run where `canonical_id_score < 1.0` |
| `none` (succeeded) | 3 | 2x `eq-value-and-relationship-combination` full-context, 1x `pc-equipment-composition-discovery` `C2+C5` (LLM) |
| `context_not_integrated` | 1 | One `eq-value-and-relationship-combination` historian-alone run where relationship evidence was never confirmed despite other evidence being available |
| `context_not_retrieved` | 1 | One `pc-cross-unit-diagnosis` historian-alone run |

No run in this cohort classified as `architecture_connectivity_failure`
or `context_not_discoverable` (the STRICTER "zero context acquired at
all" case) — every failure involved the agent acquiring SOME context,
just not enough, or not correctly interpreted/cited. Nothing was
`unresolved` — every one of the 33 runs' existing signals were
sufficient for the two taxonomies to classify it.

**Important, explicitly-flagged caveat:** `efficiency_failure` here
means "ran out of a 12-step budget," not "this context condition is
architecturally impossible to complete." A larger budget was not tested
in this campaign and might change some of these 15 outcomes — this is
recorded as an open question (Section 10), not resolved.

## 10. Limitations

- Only the conditions actually tested (Section 3's numbers) support any
  conclusion above — 127 theoretical, 13 realizable, 6 distinct
  combinations executed across a 33-run cohort. Nothing about an
  untested condition, including untested SUBSETS of a tested one, is
  claimed.
- TEP data limits ISA-95 coverage: this campaign's cohort spans
  Equipment/Process Cell/Area only, matching the framework's own honest
  0-use-case Enterprise/Site/Work Center coverage (unchanged, not
  revisited this campaign).
- Architecture-realizable combinations remain a small subset of the
  127-space (13/127), and this campaign executed only 6 of those 13 —
  further campaigns could extend coverage, e.g. `mqtt`-only (C5 exact)
  or `opcua`-only (`C2+C5` exact) conditions were not tested for the
  diagnosis-type use cases.
- LLM stochasticity: most conditions in this cohort rest on `n=1` or
  `n=2` — `sample_size_label` marks these `tentative_small_n` or
  `single_observation` throughout; only `eq-abnormal-behavior-diagnosis`
  and `eq-value-and-relationship-combination` reach
  `repeated_empirical_result` (n>=5 usable runs), and even there,
  individual CONDITIONS within them are often `n=2`.
- The `conclusion_correctness_score` heuristic (`root_cause_identified`
  + `affected_assets_mentioned` exact-match) is a known, pre-existing
  evaluator limitation (`EvaluationCriteria.known_limitations`,
  unchanged since M8/M13-C) — Section 4's `eq-abnormal-behavior-diagnosis`
  finding shows a concrete case where it likely under-credits a
  correctly-grounded answer phrased differently than the heuristic
  expects. This campaign did not modify the evaluator (out of scope,
  per instruction) — it is flagged as an interpretive caveat on every
  `reasoning_failure` classification above.
- `pc-equipment-composition-discovery`'s pooled statistics mix `llm` and
  `scenario_aware` (deterministic baseline) agent records — both are
  `RunValidity.VALID` under the existing convention, but they are
  different agents; Section 4 reports both the pooled and LLM-only
  reading explicitly rather than picking one silently.
- Candidate MSC is explicitly "among tested conditions" throughout (see
  the protocol document) — never global minimality.

## 11. Scientific claims, separated (Phase 17 audit)

**Observed findings** (directly supported by the cited `run_id`s above):

- Every cohort task's architecture-realizable maximum context exceeds
  its own use case's declared `candidate_context` (5/5 use cases).
- `eq-value-and-relationship-combination`'s full realizable context
  (`C2+C3+C4+C5+C6+C7`) met its use case's success criteria at both
  tested seeds; no other tested condition, for any cohort use case,
  did.
- Combining `uns`+`opcua` for `pc-equipment-composition-discovery`
  produced a WORSE `canonical_id_score` (0.0, both seeds) than either
  architecture alone (0.31/0.96 pooled) — more context did not help,
  and plausibly actively hurt, for this specific task.
- The Area `knowledge_graph`-only discoverability failure reproduced
  identically across 3 runs and 2 distinct seeds.
- For both diagnosis-type use cases, `required_evidence_score`/
  `relationship_score`/`grounding_score` reached 1.0 at full context
  while `conclusion_correctness_score` stayed at 0.25 in every case.

**Tentative interpretations** (plausible, but resting on small `n` or
partial confounds — stated as such above, not claims):

- C3 (Relational) showing a larger necessity delta than C4/C5/C7 for
  `eq-abnormal-behavior-diagnosis`.
- The negative necessity delta for C2/C3 in
  `eq-value-and-relationship-combination` reflects an with/without
  confound (which OTHER dimensions travel alongside C3 in this
  architecture's overshoot pattern), not that C3 is actually harmful.
- The `pc-cross-unit-diagnosis` necessity pattern echoing
  `eq-abnormal-behavior-diagnosis`'s (both `n_without=1`).

**Claims that remain unsupported by this campaign** (explicitly NOT
made, though a reader could be tempted to make them):

- That C3/C4 are UNIVERSALLY necessary for diagnosis-type use cases —
  only two, architecturally-identical (historian+knowledge_graph)
  tasks were tested.
- That `knowledge_graph` is "required" for relational reasoning in
  general — only that it was the sole architecture in this cohort
  capable of exposing C3 at all; `i3x` (also `C3`-capable) was never
  tested here.
- That a smaller-than-full-context combination is insufficient for any
  cohort use case — only that it was never tested.
- That the Area discoverability failure is unfixable — only that it
  reproduced 3/3 times under `knowledge_graph` alone at a 12-step
  budget; `uns`/`i3x`-assisted discovery was not tested for this task
  (this task declares `knowledge_graph` as its only architecture).
- That a longer step budget would or would not change any
  `efficiency_failure` outcome — not tested.
- That all 127, or even all 13 realizable, combinations were tested —
  6 were.

## 12. Tests added this campaign

`icab.analysis.sufficiency` gained partial-order-correct MSC
determination (`candidate_minimum_sufficient_contexts`, replacing a
single arbitrary tie-break) plus `run_ids` traceability on every tested
condition, propagated through `icab.analysis.matrix`/`.reports`. See
`tests/unit/analysis/test_necessity_and_sufficiency.py`
(`TestPartialOrderMultipleCandidates`, 4 new tests: two equal-cardinality
sufficient conditions both reported, two different-cardinality
incomparable conditions both reported, a dominated superset excluded,
an empty candidate list when nothing is sufficient) and
`tests/unit/analysis/test_matrix_and_reports.py` (2 new tests verifying
the new fields propagate end-to-end). Full suite (unit + integration):
unchanged pass count from the prior milestone plus these 6 new tests,
all green — see the commit this campaign is recorded under for the
exact number.

## 13. Reproducing this campaign

```powershell
# Dry run any condition first (no infrastructure needed)
uv run python scripts/icab_v2_cli.py resolve-conditions --task d2cooling-diagnosis-heat-transfer-category --design single

# The exact 6 campaign invocations run for this report (see run_ids cited above for their outputs):
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d2cooling-diagnosis-heat-transfer-category --design targeted --targets "C4,C7,C3+C4,C4+C5,C4+C7" --allow-overshoot --agent llm --seeds 1 --max-steps 12 --name v2study-uc1-a
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d2cooling-diagnosis-heat-transfer-category --design targeted --targets "C2+C3+C4+C5+C6+C7" --usecases-dir "" --agent llm --seeds 1,2 --max-steps 12 --name v2study-uc1-b
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d2cooling-diagnosis-heat-transfer-category --design targeted --targets "C3+C4" --allow-overshoot --agent llm --seeds 2 --max-steps 12 --name v2study-uc1-c
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d2ctx-investigation-combine-value-and-relationship --design targeted --targets "C4+C5+C7,C2+C3+C6,C2+C3+C4+C5+C6+C7" --usecases-dir "" --agent llm --seeds 2 --max-steps 12 --name v2study-uc2-a
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d4plant-qa-discover-equipment --design targeted --targets "C1+C2+C5" --usecases-dir "" --agent llm --seeds 1,2 --max-steps 12 --name v2study-uc3-a
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d4plant-diagnosis-reactor-vs-downstream --design targeted --targets "C3,C4,C3+C4" --allow-overshoot --agent llm --seeds 1 --max-steps 12 --name v2study-uc4-a
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d4plant-diagnosis-reactor-vs-downstream --design targeted --targets "C2+C3+C4+C5+C6+C7" --usecases-dir "" --agent llm --seeds 1 --max-steps 12 --name v2study-uc4-b
uv run python scripts/run_context_experiment.py --suite tep-v2 --task area-investigation-process-cell-composition --design targeted --targets "C2+C3" --allow-overshoot --agent llm --seeds 2 --max-steps 12 --name v2study-uc5-a

# Analysis (reads the persisted results/ above -- no new LLM calls)
uv run python scripts/icab_v2_cli.py analyze-sufficiency --use-case eq-abnormal-behavior-diagnosis
uv run python scripts/icab_v2_cli.py analyze-necessity --use-case eq-value-and-relationship-combination
uv run python scripts/icab_v2_cli.py matrix-context-requirement
uv run python scripts/icab_v2_cli.py matrix-failure-mode
```

Every run's `configuration_hash`, `generation_id`, `git_commit`,
`icab_version`, and seed are persisted on its own
`results/raw/<run_id>.json` — the `run_id`s cited throughout this
document are the complete index into that evidence.

## Appendix: Tables A-E (Phase 15)

Machine-readable JSON for each table is generated by the commands below
into `results/reports/` (gitignored, regenerable, not committed — see
"results/ policy" in `docs/benchmark/specification-v2.md`); the
human-readable rendering follows.

```
uv run python scripts/icab_v2_cli.py matrix-context-requirement > results/reports/campaign1-table-a.json
uv run python scripts/icab_v2_cli.py matrix-candidate-msc        > results/reports/campaign1-table-b.json
uv run python scripts/icab_v2_cli.py matrix-architecture-context > results/reports/campaign1-table-d.json
uv run python scripts/icab_v2_cli.py matrix-failure-mode         > results/reports/campaign1-table-e.json
```

### Table A — Context Requirement Matrix (cohort)

| Use case | C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|---|
| `eq-abnormal-behavior-diagnosis` | not_applicable | not_applicable | **required** | **required** | beneficial | not_applicable | beneficial |
| `eq-value-and-relationship-combination` | not_applicable | **sufficient** | **sufficient** | not_applicable | **sufficient** | not_applicable | not_applicable |
| `pc-equipment-composition-discovery` | **required** | **required** | not_demonstrated | not_applicable | not_applicable | not_applicable | not_applicable |
| `pc-cross-unit-diagnosis` | not_applicable | not_applicable | **required** | **required** | beneficial | not_applicable | not_applicable |
| `area-process-cell-composition` | not_demonstrated | **required** | **required** | not_applicable | not_applicable | not_applicable | not_applicable |

Every non-`not_applicable`/`not_demonstrated` cell is traceable to the
same use case's necessity/sufficiency report in Section 4 (`sufficient`
cells trace to Section 7's Table B; `required`/`beneficial` cells trace
to Section 5's necessity deltas).

### Table B — Candidate MSC

| use_case | ISA-95 level | candidate MSC | dimensions | architecture | repetitions | success rate (this condition) | supporting experiment IDs |
|---|---|---|---|---|---|---|---|
| `eq-abnormal-behavior-diagnosis` | equipment | *(none)* | — | — | — | 0/3 tested conditions | — |
| `eq-value-and-relationship-combination` | equipment | `C2+C3+C4+C5+C6+C7` | C2,C3,C4,C5,C6,C7 | historian+knowledge_graph | 2 | 2/2 | `v2-necessity-demo-combined-...-seed1-rep1`, `v2study-uc2-a-C2+C3+C4+C5+C6+C7-...-seed2-rep1` |
| `pc-equipment-composition-discovery` | process_cell | *(none)* | — | — | — | 0/3 tested conditions | — |
| `pc-cross-unit-diagnosis` | process_cell | *(none)* | — | — | — | 0/3 tested conditions | — |
| `area-process-cell-composition` | area | *(none)* | — | — | — | 0/1 tested condition | — |

### Table C — Context Combination Performance

| use_case | combination | architecture(s) | n | mean req_evidence | mean grounding | mean completeness | mean tool_calls | mean latency_ms |
|---|---|---|---|---|---|---|---|---|
| `area-process-cell-composition` | C2+C3+C6 | knowledge_graph | 3 | 0.00 | 1.00 | 0.00 | 11.3 | 4234 |
| `eq-abnormal-behavior-diagnosis` | C2+C3+C4+C5+C6+C7 | historian+knowledge_graph | 5 | 1.00 | 1.00 | 1.00 | 6.8 | 2545 |
| `eq-abnormal-behavior-diagnosis` | C2+C3+C6 | knowledge_graph | 2 | 0.00 | 1.00 | 0.00 | 11.0 | 4230 |
| `eq-abnormal-behavior-diagnosis` | C4+C5+C7 | historian | 6 | 0.00 | 1.00 | 0.00 | 11.7 | 4395 |
| `eq-value-and-relationship-combination` | C2+C3+C4+C5+C6+C7 | historian+knowledge_graph | 2 | 1.00 | 1.00 | 1.00 | 2.0 | 695 |
| `eq-value-and-relationship-combination` | C2+C3+C6 | knowledge_graph | 2 | 0.00 | 1.00 | 0.00 | 11.0 | 3663 |
| `eq-value-and-relationship-combination` | C4+C5+C7 | historian | 2 | 1.00 | 1.00 | 0.50 | 6.5 | 2222 |
| `pc-cross-unit-diagnosis` | C2+C3+C4+C5+C6+C7 | historian+knowledge_graph | 2 | 1.00 | 1.00 | 1.00 | 19.0 | 6730 |
| `pc-cross-unit-diagnosis` | C2+C3+C6 | knowledge_graph | 1 | 0.00 | 1.00 | 0.00 | 12.0 | 3967 |
| `pc-cross-unit-diagnosis` | C4+C5+C7 | historian | 1 | 0.50 | 1.00 | 0.50 | 20.0 | 7247 |
| `pc-equipment-composition-discovery` | C1+C2 | uns | 3 | 1.00 | 1.00 | 1.00 | 5.0 | 1664 |
| `pc-equipment-composition-discovery` | C1+C2+C5 | opcua+uns | 2 | 1.00 | 1.00 | 1.00 | 1.0 | 336 |
| `pc-equipment-composition-discovery` | C2+C5 | opcua | 2 | 1.00 | 1.00 | 1.00 | 7.0 | 2340 |

**Efficiency observation (not assumed beforehand, per instruction):**
for both diagnosis-type use cases where full context succeeded at
retrieving evidence, it did so with FEWER mean tool calls and LOWER mean
latency than the single-architecture conditions that failed to retrieve
it — e.g. `eq-abnormal-behavior-diagnosis` full context: 6.8 calls/2545ms
vs. single-architecture: 11.0-11.7 calls/4230-4395ms (all pinned at or
near the 12-step budget). `eq-value-and-relationship-combination`'s full
context succeeded in just 2.0 calls/695ms. This directly contradicts a
naive "more context costs more to use" assumption — here, the RIGHT
context let the agent stop searching sooner, while insufficient context
caused it to exhaust its budget searching for evidence it could never
find. The one exception: `pc-cross-unit-diagnosis`'s full context (19.0
calls) did not show the same efficiency gain over its single-architecture
conditions (12.0/20.0 calls) — `n=1-2` per condition here, not treated
as a stable contrast.

### Table D — Architecture x Context (all tep-v2 records, not cohort-scoped)

| architecture | claims to expose | n single-architecture runs | mean conclusion_correctness | mean grounding |
|---|---|---|---|---|
| `historian` | C4, C5, C7 | 9 | 0.39 | 1.00 |
| `knowledge_graph` | C2, C3, C6 | 8 | 0.31 | 1.00 |
| `opcua` | C2, C5 | 2 | 1.00 | 1.00 |
| `uns` | C1, C2 | 3 | 1.00 | 1.00 |

`i3x` and `mqtt` claim to expose context per
`CONTEXT_DIMENSION_ARCHITECTURES` but were never run alone by any tep-v2
task in this dataset — absent from this table, not scored as zero.

### Table E — Failure Modes (cohort, per run)

| use_case | combination | seed | discoverability stage | failure category | experiment ID |
|---|---|---|---|---|---|
| area-process-cell-composition | C2+C3+C6 | 1 | discovered_identifier | efficiency_failure | `v2-area-smoke-area-investigation-process-cell-composition-knowledge_graph-seed1-rep1` |
| area-process-cell-composition | C2+C3+C6 | 2 | discovered_identifier | efficiency_failure | `v2study-uc5-a-C2+C3-knowledge_graph-seed2-rep1` |
| area-process-cell-composition | C2+C3+C6 | 1 | discovered_identifier | efficiency_failure | `v2ctx-area-targeted-C2+C3-knowledge_graph-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C4+C5+C7 | 1 | discovered_identifier | efficiency_failure | `v2-fault-investigation-demo-d2cooling-diagnosis-heat-transfer-category-historian-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C2+C3+C6 | 1 | discovered_identifier | efficiency_failure | `v2-fault-investigation-demo-d2cooling-diagnosis-heat-transfer-category-knowledge_graph-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C2+C3+C6 | 1 | discovered_identifier | efficiency_failure | `v2ctx-equipment-ablation-C3-knowledge_graph-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C4+C5+C7 | 1 | discovered_identifier | efficiency_failure | `v2ctx-equipment-ablation-C5-historian-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C2+C3+C4+C5+C6+C7 | 1 | grounded_in_conclusion | reasoning_failure | `v2ctx-equipment-ablation-C3+C5-historian+knowledge_graph-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C4+C5+C7 | 1 | discovered_identifier | efficiency_failure | `v2study-uc1-a-C4-historian-seed1-rep1`, `v2study-uc1-a-C7-historian-seed1-rep1`, `v2study-uc1-a-C4+C5-historian-seed1-rep1`, `v2study-uc1-a-C4+C7-historian-seed1-rep1` |
| eq-abnormal-behavior-diagnosis | C2+C3+C4+C5+C6+C7 | 1, 2 | grounded_in_conclusion | reasoning_failure | `v2study-uc1-a-C3+C4-...-seed1-rep1`, `v2study-uc1-b-...-seed1-rep1`, `v2study-uc1-b-...-seed2-rep1`, `v2study-uc1-c-C3+C4-...-seed2-rep1` |
| eq-value-and-relationship-combination | C2+C3+C4+C5+C6+C7 | 1, 2 | grounded_in_conclusion | none (success) | `v2-necessity-demo-combined-...-seed1-rep1`, `v2study-uc2-a-C2+C3+C4+C5+C6+C7-...-seed2-rep1` |
| eq-value-and-relationship-combination | C4+C5+C7 | 1 | grounded_in_conclusion | efficiency_failure | `v2-necessity-demo-split-...-historian-seed1-rep1` |
| eq-value-and-relationship-combination | C4+C5+C7 | 2 | grounded_in_conclusion | context_not_integrated | `v2study-uc2-a-C4+C5+C7-historian-seed2-rep1` |
| eq-value-and-relationship-combination | C2+C3+C6 | 1, 2 | discovered_identifier | efficiency_failure | `v2-necessity-demo-split-...-knowledge_graph-seed1-rep1`, `v2study-uc2-a-C2+C3+C6-...-seed2-rep1` |
| pc-cross-unit-diagnosis | C2+C3+C6 | 1 | discovered_identifier | efficiency_failure | `v2study-uc4-a-C3-knowledge_graph-seed1-rep1` |
| pc-cross-unit-diagnosis | C4+C5+C7 | 1 | discovered_identifier | context_not_retrieved | `v2study-uc4-a-C4-historian-seed1-rep1` |
| pc-cross-unit-diagnosis | C2+C3+C4+C5+C6+C7 | 1 | grounded_in_conclusion | reasoning_failure | `v2study-uc4-a-C3+C4-...-seed1-rep1`, `v2study-uc4-b-C2+C3+C4+C5+C6+C7-...-seed1-rep1` |
| pc-equipment-composition-discovery | C2+C5 | 1 | retrieved_value | representation_failure | `v2-process-cell-smoke-...-opcua-seed1-rep1` |
| pc-equipment-composition-discovery | C1+C2 | 1 | retrieved_value | representation_failure | `v2-process-cell-smoke-...-uns-seed1-rep1` |
| pc-equipment-composition-discovery | C1+C2 | 1 | retrieved_value | representation_failure | `v2ctx-processcell-ablation-C1+C2-uns-seed1-rep1`, `v2ctx-processcell-ablation-C1-uns-seed1-rep1` |
| pc-equipment-composition-discovery | C2+C5 | 1 | grounded_in_conclusion | none (success) | `v2ctx-processcell-ablation-C2-opcua-seed1-rep1` |
| pc-equipment-composition-discovery | C1+C2+C5 | 1, 2 | retrieved_value | representation_failure | `v2study-uc3-a-C1+C2+C5-opcua+uns-seed1-rep1`, `v2study-uc3-a-C1+C2+C5-opcua+uns-seed2-rep1` |

No row in this cohort is `unresolved` — every one of the 33 runs
classified cleanly under the existing failure taxonomy and
discoverability stages.

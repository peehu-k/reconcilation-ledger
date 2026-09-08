# Architecture

## Design goals

1. The model proposes; deterministic code decides. The extractor only returns
   candidate facts (and optionally rephrases an already-decided explanation).
   Comparison, normalisation, and every corroborate / contradict / reconcile verdict
   are pure Python with an explicit rule trace.
2. No unverifiable fact in the ledger. Every stored fact's quote is re-found in the
   freshly parsed source; failures are quarantined, not asserted.
3. Runs locally and offline. Local parsing, a local model or the bundled replay data,
   SQLite, static HTML. No paid service, no mandatory key.
4. Prefer `unresolved` to a guess. Low confidence, unverifiable evidence, or ambiguous
   metadata goes to the review queue, never to a fabricated answer.
5. Generalise. Nothing is keyed to a company, a metric, a filename, or a page.

## Module map

```
rlx/
  config.py              thresholds, paths, provider selection (.env optional)
  cli.py                 rlx init|ingest|ingest-dir|reconcile|stats|serve|reset
  pipeline.py            orchestration: ingest → extract → normalize → store → reconcile
                         (idempotent, resumable, incremental, degrades gracefully)

  ingest/
    parse.py             PyMuPDF → pages + typed blocks + bbox + structural_confidence
    registry.py          content-hash, published-date resolution, primary-entity guess
    chunk.py             blocks → ≤~1200-token chunks (never cross a page)
    jobs.py              per-document resumable job cursor

  extract/               -- the only model-facing code --
    schema.py            Pydantic RawFactList + JSON Schema for constrained decoding
    prompts.py           versioned extraction / repair prompts
    quote_guard.py       exact / ws-normalized / fuzzy re-verification of every quote
    extractor.py         call + 1 repair + per-fact guard; returns kept + rejected
    jsonio.py            tolerant JSON extraction (fences, trailing commas, smart quotes)
    providers/           ollama (default) · gemini (opt-in) · replay (offline) · null

  normalize/             -- pure, deterministic, exhaustively unit-tested --
    text.py              whitespace / control-char / accent / superscript handling
    footnotes.py         strip glued "(1)" / "(1,2)" markers, protect "(452)" negatives
    sign.py              accounting negatives: "(452)", "Rs. (452 Cr)", "(6.3%)"
    units.py             value+unit → (value_num, currency, unit_canonical, scale)
    periods.py           "FY24" / "2024-25" / "FY2024/25" / "Q4 FY24" / "as on 3 Jan 2025"
                         / "April-December 2024" / "CY2024"  → one canonical string
    vintage.py           estimate_status (first_advance...actual...projection) + as_of_date
    entities.py          entity_key: legal-suffix strip, pronoun→primary entity
    attributes.py        attribute_key: lexical + small seed lexicon (NOT an ontology)
    flags.py             basis_flags / scope_flags from qualifier text
    sanity.py            sign_suspect / implausible_percent / low_structural / ...
    pipeline.py          RawFact + DocContext → canonical Fact (+ content_hash)

  match/
    blocking.py          candidate pairs within (entity_key, attribute_key), O(k²)
    registry.py          link near-duplicate keys (rapidfuzz; optional embeddings)
    embeddings.py        guarded bge-small; degrades to "no signal" if absent

  reconcile/             -- pure, deterministic --
    compare.py           EQUAL / DIFFERENT / INCOMPARABLE (numeric-aware, PIN-aware)
    rules.py             the ordered cascade (see below)
    confidence.py        relation_confidence scoring
    cascade.py           compare → run cascade → bucket + rule_trace + explanation

  adjudicate/
    adjudicator.py       narrow: rephrase a decided explanation; template fallback

  api/
    app.py               FastAPI: upload + JSON + HTML views
    report.py            selects and shapes rows for the templates (4-case picker)
    templates/           base + report + facts + relations + unresolved (inline CSS)

  store/
    migrations.sql       SQLite schema (WAL)
    db.py  models.py  queries.py
```

## Data model (SQLite)

`documents` (content_sha256 unique = idempotency key; published_date + its source) ·
`pages` · `blocks` (kind, bbox, structural_confidence) ·
`raw_facts` (verbatim model output + quote_match) ·
`facts` (canonical: entity_key, attribute_key, value_num/value_text, currency,
unit_canonical, period_canonical, as_of_date, estimate_status, basis_flags,
scope_flags, attributed_to, extraction_confidence, sanity_flags, content_hash unique) ·
`relations` (fact_a, fact_b, bucket, rule_code, rule_trace, explanation,
relation_confidence; unique(fact_a,fact_b)) ·
`entity_registry` / `attribute_registry` (emergent, append-only, aliases logged) ·
`ingest_jobs` (stage, cursor, status - resumable) ·
`rejected_facts` (quote_not_found) · `extraction_errors` (malformed output) ·
`embeddings` (cache).

`content_hash` deliberately excludes `source_page`: the same figure repeated on many
pages of one document is one fact.

## The reconcile cascade

`reconcile(a, b)`:
1. `compare(a, b)` → `EQUAL` (→ corroborated, if cross-doc/page) / `INCOMPARABLE`
   (→ unresolved) / `DIFFERENT` (→ run cascade).
   Numeric comparison only when both facts have a `value_num` **and** a compatible
   quantity unit; identifiers/addresses/names compare as normalized strings, PIN-aware.
2. Ordered rules, first match wins, each appended to `rule_trace`:
   `ROUNDING → UNIT_SCALE → PERIOD → TEMPORAL_STATUS → ESTIMATE_VINTAGE → SCOPE →
   BASIS → IDENTIFIER_REVISION → ATTRIBUTION`.
3. No rule applies → `contradiction` if `min(extraction_confidence) is above the threshold` and no sanity
   flag; else `unresolved`.

`ESTIMATE_VINTAGE` (signature) fires for numeric facts of the same period whose
`estimate_status` maturities differ (first_advance < second_advance < provisional <
revised < actual) **or** whose `as_of_date`s differ by ≥ 45 days - the number matured
between publications.

## Reliability specifics

| risk | mitigation |
|---|---|
| model hallucinates a quote | quote guard → `rejected_facts`, never promoted |
| model invents a table value | low `structural_confidence` on deck/table blocks → low `extraction_confidence` → sanity + threshold routing |
| "Loss ... 2,491.86" read as +positive | `sign_suspect` sanity flag → unresolved |
| crore vs million ×10 error | deterministic `units.py`, unit-tested |
| FY24 ≡ 2023-24 ≡ FY2023/24 | deterministic `periods.py`, unit-tested |
| "the Company" ambiguity | resolved to `documents.primary_entity_key` |
| relayed figure ("per the IMF") counted as agreement | `attributed_to` + `ATTRIBUTION` rule |
| model unreachable mid-run | job → `paused_llm`, partial facts kept, `rlx ingest` resumes |
| malformed model output | `extraction_errors` row, chunk skipped, run completes |
| re-upload / re-run | content-hash no-op; `content_hash` unique; `relations` unique |
| new PDF | only its chunks are extracted; only pairs touching new facts are built |

## Deliberately out of scope

Graph database; vector DB service; layout-ML/OCR; multi-agent orchestration;
fine-tuning; bounding-box image highlighting (designed-for, not shipped).

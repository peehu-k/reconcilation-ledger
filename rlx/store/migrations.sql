-- Reconciliation Ledger schema. SQLite, single file, WAL mode.
-- Every row that matters carries provenance (pipeline_version / model / created_at).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    content_sha256 TEXT UNIQUE NOT NULL,          -- idempotency key
    title TEXT,
    source_path TEXT,
    page_count INTEGER,
    published_date TEXT,                          -- explicit > "Dated .." on cover > PDF CreationDate > NULL
    published_date_source TEXT,                   -- how we got it (for the report's honesty note)
    primary_entity_key TEXT,                      -- resolves "the Company" / "your Company"
    primary_entity_display TEXT,
    pipeline_version TEXT,
    model_name TEXT,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,                     -- 1-based PDF order
    printed_label TEXT,                           -- printed page number if detected
    text TEXT NOT NULL,
    width REAL, height REAL,
    PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    idx INTEGER NOT NULL,                         -- order on page
    kind TEXT,                                    -- paragraph|heading|list|table_region|slide_textbox
    text TEXT NOT NULL,
    bbox TEXT,                                    -- json [x0,y0,x1,y1]
    char_start INTEGER,                           -- offset into pages.text
    char_end INTEGER,
    structural_confidence REAL NOT NULL DEFAULT 0.9
);
CREATE INDEX IF NOT EXISTS ix_blocks_doc ON blocks(doc_id, page_no);

CREATE TABLE IF NOT EXISTS raw_facts (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_id INTEGER REFERENCES blocks(id) ON DELETE CASCADE,
    page_no INTEGER,
    fact_kind TEXT,
    entity_text TEXT,
    attribute_label TEXT,
    value_text TEXT,
    unit_text TEXT,
    period_text TEXT,
    as_of_text TEXT,
    estimate_status_text TEXT,
    basis_text TEXT,
    scope_text TEXT,
    attributed_to_text TEXT,
    quote TEXT NOT NULL,
    llm_self_confidence REAL,
    quote_match TEXT,                             -- exact|fuzzy|FAIL
    quote_char_start INTEGER,
    quote_char_end INTEGER,
    prompt_version TEXT,
    model_name TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_rawfacts_doc ON raw_facts(doc_id);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    raw_fact_id INTEGER REFERENCES raw_facts(id) ON DELETE CASCADE,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER,
    fact_kind TEXT,
    entity_key TEXT,
    entity_display TEXT,
    attribute_key TEXT,
    attribute_display TEXT,
    value_num REAL,                               -- NULL for non-numeric
    value_text TEXT,
    currency TEXT,                                -- INR|USD|... or NULL
    unit_canonical TEXT,                          -- currency_amount|ratio|count|tonnes|number|null
    scale_applied REAL,
    period_canonical TEXT,
    as_of_date TEXT,
    estimate_status TEXT,
    basis_flags TEXT,                             -- json list
    scope_flags TEXT,                             -- json list
    attributed_to TEXT,
    quote TEXT,
    quote_match TEXT,
    source_page INTEGER,
    printed_label TEXT,
    extraction_confidence REAL,
    sanity_flags TEXT,                            -- json list
    content_hash TEXT UNIQUE,
    pipeline_version TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_facts_block ON facts(entity_key, attribute_key);
CREATE INDEX IF NOT EXISTS ix_facts_doc ON facts(doc_id);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY,
    fact_a INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    fact_b INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    entity_key TEXT,
    attribute_key TEXT,
    bucket TEXT NOT NULL,                         -- corroborated|contradiction|reconciled|unresolved
    rule_code TEXT,                               -- EXACT|ROUNDING|UNIT_SCALE|PERIOD|ESTIMATE_VINTAGE|SCOPE|BASIS|ATTRIBUTION|NONE|...
    rule_trace TEXT,                              -- json list of every step tried
    explanation TEXT,
    explanation_source TEXT,                      -- template|llm
    relation_confidence REAL,
    pipeline_version TEXT,
    created_at TEXT,
    UNIQUE (fact_a, fact_b)
);
CREATE INDEX IF NOT EXISTS ix_relations_bucket ON relations(bucket);

CREATE TABLE IF NOT EXISTS entity_registry (
    entity_key TEXT PRIMARY KEY,
    canonical_display TEXT,
    aliases TEXT,                                 -- json list
    decided_by TEXT,                             -- seed|pronoun|fuzzy|llm
    score REAL,
    first_seen_doc INTEGER,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS attribute_registry (
    attribute_key TEXT PRIMARY KEY,
    canonical_display TEXT,
    aliases TEXT,
    unit_hint TEXT,
    decided_by TEXT,
    score REAL,
    first_seen_doc INTEGER,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage TEXT,                                   -- registered|parsed|extracting|extracted|reconciled|done|paused_llm|error
    cursor INTEGER DEFAULT 0,                     -- chunk index processed so far
    total INTEGER DEFAULT 0,
    status TEXT,
    error TEXT,
    provider TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS rejected_facts (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    block_id INTEGER,
    page_no INTEGER,
    reason TEXT,                                  -- quote_not_found|schema_invalid|sanity
    payload TEXT,                                 -- json of the proposed fact
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS extraction_errors (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    block_id INTEGER,
    page_no INTEGER,
    error TEXT,
    raw_output TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS embeddings (
    key TEXT PRIMARY KEY,                         -- sha1(text)
    vec BLOB
);

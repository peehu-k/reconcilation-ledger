"""End-to-end pipeline over the six real starter PDFs using the offline replay
provider. Covers Milestone-3 checklist items: four cases, re-verifiable evidence,
idempotency, incremental add, resumability, malformed extraction, LLM unavailable.

The six PDFs are parsed once per test *class* (module-scoped fixture) - PyMuPDF
parsing of the 100-page filings dominates runtime.
"""
import pytest

import conftest
from rlx.config import CONFIG
from rlx.store.db import get_conn, reset_db

PDFS = conftest.starter_pdfs()
pytestmark = pytest.mark.skipif(not PDFS, reason="starter PDFs not present in this environment")


def _by_name(frag):
    return next(p for p in PDFS if frag in p.name)


def _ingest(path, provider="replay", **kw):
    from rlx.pipeline import ingest_document
    return ingest_document(path, provider_name=provider, **kw)


# --------------------------------------------------------------------- shared ledger

@pytest.fixture(scope="module")
def full_ledger(tmp_path_factory):
    dbp = tmp_path_factory.mktemp("it") / "full.db"
    old = CONFIG.db_path
    CONFIG.db_path = dbp
    reset_db(dbp)
    reports = [_ingest(p) for p in PDFS]
    yield dbp, reports
    CONFIG.db_path = old


@pytest.fixture()
def scratch_db(tmp_path):
    dbp = tmp_path / "s.db"
    old = CONFIG.db_path
    CONFIG.db_path = dbp
    reset_db(dbp)
    yield dbp
    CONFIG.db_path = old


# --------------------------------------------------------------------- four cases

def test_four_cases_present(full_ledger):
    dbp, _ = full_ledger
    conn = get_conn(dbp)
    from rlx.api.report import overview, unresolved_items
    ov = overview(conn)
    assert ov["cases"]["corroboration"], "no corroboration case"
    assert ov["cases"]["contradiction"], "no contradiction case"
    assert any(ov["cases"][k] for k in
               ("reconciled_vintage", "reconciled_period", "reconciled_temporal", "reconciled_basis")), \
        "no reconciled case"
    u = unresolved_items(conn)
    assert u["rejected"] or u["errors"] or u["flagged"], "no extraction-failure evidence"
    rules = {r["rule_code"] for r in conn.execute("SELECT rule_code FROM relations WHERE bucket='reconciled'")}
    assert "ESTIMATE_VINTAGE" in rules, "signature vintage reconciliation did not fire"


def test_every_fact_has_reverifiable_evidence(full_ledger):
    dbp, _ = full_ledger
    conn = get_conn(dbp)
    rows = conn.execute("SELECT quote, quote_match FROM facts").fetchall()
    assert rows and all(r["quote"] and r["quote_match"] in ("exact", "fuzzy") for r in rows)
    assert conn.execute("SELECT COUNT(*) FROM facts WHERE quote_match='FAIL'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM rejected_facts WHERE reason='quote_not_found'").fetchone()[0] >= 1


def test_no_false_corroboration_across_currencies_or_kinds(full_ledger):
    dbp, _ = full_ledger
    conn = get_conn(dbp)
    for r in conn.execute("""SELECT fa.currency ca, fb.currency cb, fa.unit_canonical ua, fb.unit_canonical ub
                             FROM relations rel JOIN facts fa ON fa.id=rel.fact_a JOIN facts fb ON fb.id=rel.fact_b
                             WHERE rel.bucket='corroborated'"""):
        if r["ca"] and r["cb"]:
            assert r["ca"] == r["cb"], "corroborated across different currencies"
        assert not ({r["ua"], r["ub"]} == {"ratio", "currency_amount"}), "corroborated ratio vs amount"


def test_reconcile_rebuild_is_deterministic(full_ledger):
    dbp, _ = full_ledger
    conn = get_conn(dbp)
    before = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    from rlx.pipeline import reconcile_all
    reconcile_all(conn)
    after = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    assert before == after > 0


# --------------------------------------------------------------------- idempotency

def test_reupload_is_noop(scratch_db):
    p = _by_name("earnings")
    r1 = _ingest(p)
    n1 = get_conn(scratch_db).execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    r2 = _ingest(p)
    n2 = get_conn(scratch_db).execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    assert r1.doc_id == r2.doc_id and r2.status == "exists" and n1 == n2 > 0


# --------------------------------------------------------------------- incremental

def test_incremental_add_leaves_existing_relations_untouched(scratch_db):
    _ingest(_by_name("rbi"))
    _ingest(_by_name("imf"))
    conn = get_conn(scratch_db)
    snap = {(r["fact_a"], r["fact_b"], r["bucket"], r["rule_code"])
            for r in conn.execute("SELECT fact_a,fact_b,bucket,rule_code FROM relations")}
    assert snap, "expected relations from the first two macro docs"
    _ingest(_by_name("economic-survey"))
    conn = get_conn(scratch_db)
    after = {(r["fact_a"], r["fact_b"], r["bucket"], r["rule_code"])
             for r in conn.execute("SELECT fact_a,fact_b,bucket,rule_code FROM relations")}
    assert snap.issubset(after) and len(after) > len(snap)


# --------------------------------------------------------------------- resumability

class _FlakyProvider:
    name = "flaky"

    def __init__(self, ok=3):
        from rlx.extract.providers.replay import ReplayProvider
        self._inner, self._n, self._ok, self._blown = ReplayProvider(), 0, ok, False

    def available(self):
        return True

    def complete_json(self, system, user, *, schema=None, repair_system=None):
        from rlx.extract.providers import LLMUnavailable
        self._n += 1
        if self._n > self._ok and not self._blown:
            self._blown = True
            raise LLMUnavailable("simulated outage")
        return self._inner.complete_json(system, user, schema=schema, repair_system=repair_system)


def test_pause_on_llm_outage_then_resume(scratch_db, monkeypatch):
    from rlx.extract.providers import get_provider as real_get
    flaky = _FlakyProvider(ok=3)
    monkeypatch.setattr("rlx.pipeline.get_provider",
                        lambda name=None: flaky if name == "flaky" else real_get("replay"))
    p = _by_name("earnings")
    r1 = _ingest(p, provider="flaky")
    assert r1.status == "paused_llm"
    conn = get_conn(scratch_db)
    partial = conn.execute("SELECT COUNT(*) FROM facts WHERE doc_id=?", (r1.doc_id,)).fetchone()[0]
    assert conn.execute("SELECT status FROM ingest_jobs WHERE doc_id=?", (r1.doc_id,)).fetchone()["status"] == "paused_llm"

    r2 = _ingest(p, provider="replay-final")
    conn = get_conn(scratch_db)
    final = conn.execute("SELECT COUNT(*) FROM facts WHERE doc_id=?", (r2.doc_id,)).fetchone()[0]
    assert r2.doc_id == r1.doc_id
    assert conn.execute("SELECT status FROM ingest_jobs WHERE doc_id=?", (r2.doc_id,)).fetchone()["status"] == "done"
    assert final >= partial


# --------------------------------------------------------------------- degradation

def test_llm_completely_unavailable_still_parses(scratch_db, monkeypatch):
    from rlx.extract.providers import LLMUnavailable

    class _Dead:
        name = "dead"
        def available(self): return False
        def complete_json(self, *a, **k): raise LLMUnavailable("down")

    monkeypatch.setattr("rlx.pipeline.get_provider", lambda name=None: _Dead())
    r = _ingest(_by_name("earnings"), provider="dead")
    conn = get_conn(scratch_db)
    assert conn.execute("SELECT COUNT(*) FROM pages WHERE doc_id=?", (r.doc_id,)).fetchone()[0] > 0
    from rlx.api.report import overview
    assert overview(conn)["counts"]["documents"] == 1


def test_malformed_extraction_is_logged_not_fatal(scratch_db, monkeypatch):
    class _Junk:
        name = "junk"
        def available(self): return True
        def complete_json(self, *a, **k): raise ValueError("not JSON at all")

    monkeypatch.setattr("rlx.pipeline.get_provider", lambda name=None: _Junk())
    r = _ingest(_by_name("earnings"), provider="junk")
    conn = get_conn(scratch_db)
    assert r.status == "done"
    assert conn.execute("SELECT COUNT(*) FROM extraction_errors WHERE doc_id=?", (r.doc_id,)).fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM facts WHERE doc_id=?", (r.doc_id,)).fetchone()[0] == 0

"""Non-shape-invariant metrics through the persistence layer.

ast_hash is identifier/literal-blind, so the observation_artifacts row
represents a SHAPE. Metrics that read identifier text
(identifier_quality, trivial_delegation_ratio via delegation_kind) must
be recomputed per occurrence on BOTH persistence paths — never served
from the shape-keyed metrics_json cache. Regression tests for the
ast_hash-identity bug (PR #9's storage-layer half):

- rename all identifiers (shape unchanged) → second run must yield fresh
  values while the dormant shortcut still fires for shape metrics
- shape-identical twins in one file → each scores from its own identifiers
- metrics_json never contains non-shape-invariant metric ids
"""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.persistence import run_pipeline_with_persistence
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.storage.sqlite_store import SQLAlchemyObservationStore

BAD_NAMES_SOURCE = """def f(a, b):
    x = 0
    for q in a:
        x = x + q
    return x * b
"""

# Same AST shape as BAD_NAMES_SOURCE; every identifier meaningful.
GOOD_NAMES_SOURCE = """def compute_invoice_total(invoice_line_items, tax_rate):
    running_total = 0
    for line_item in invoice_line_items:
        running_total = running_total + line_item
    return running_total * tax_rate
"""

# `f(x)` passes the parameter straight through → RETURN_PASSTHROUGH.
DELEGATING_SOURCE = """def alpha(x):
    return f(x)
"""

# Same shape, but `w` is not a parameter → DelegationKind.NONE.
NON_DELEGATING_SOURCE = """def alpha(x):
    return f(w)
"""

CONFIG = InstinctConfig(scope="personal", suppress=[])


def _run(
    sample: Path, store: SQLAlchemyObservationStore, cwd: Path
) -> dict[tuple[str, str], object]:
    """Drain one persisted run; return {(artifact_name, metric_id): value}."""
    rows, _ = run_pipeline_with_persistence(sample, CONFIG, store, cwd=cwd)
    return {(artifact.name, m.metric_id): m.value for artifact, m in rows}


def test_identifier_quality_fresh_after_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renaming every identifier keeps the shape (dormant shortcut fires)
    but identifier_quality must reflect the NEW names, not run 1's cache."""
    from savviety_instinct.analyze import CYCLOMATIC_METRIC

    call_count = 0
    original = CYCLOMATIC_METRIC.compute

    def counting_compute(artifact, context):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return original(artifact, context)

    monkeypatch.setattr(CYCLOMATIC_METRIC, "compute", counting_compute)

    sample = tmp_path / "sample.py"
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")

    sample.write_text(BAD_NAMES_SOURCE)
    first = _run(sample, store, tmp_path)
    assert first[("f", "identifier_quality")] == pytest.approx(0.0)
    calls_first = call_count
    assert calls_first == 1

    sample.write_text(GOOD_NAMES_SOURCE)
    second = _run(sample, store, tmp_path)
    assert second[("compute_invoice_total", "identifier_quality")] == pytest.approx(1.0), (
        "identifier_quality served stale from the shape-keyed cache after a rename"
    )
    assert call_count == calls_first, (
        "dormant shortcut should still fire for shape-invariant metrics on run 2"
    )


def test_shape_twins_score_independently_through_persistence(tmp_path: Path) -> None:
    """Two shape-identical functions in one file share an artifact row but
    must each yield identifier_quality from their own identifiers (the
    second twin exercises the within-run shortcut path)."""
    sample = tmp_path / "sample.py"
    sample.write_text(GOOD_NAMES_SOURCE + "\n\n" + BAD_NAMES_SOURCE)
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")

    values = _run(sample, store, tmp_path)
    assert values[("compute_invoice_total", "identifier_quality")] == pytest.approx(1.0)
    assert values[("f", "identifier_quality")] == pytest.approx(0.0)


def test_trivial_delegation_fresh_after_identifier_change(tmp_path: Path) -> None:
    """delegation_kind matches argument identifiers against parameter names,
    which ast_hash omits — the module keeps its shape but the ratio changes."""
    sample = tmp_path / "sample.py"
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")

    sample.write_text(DELEGATING_SOURCE)
    first = _run(sample, store, tmp_path)
    assert first[(str(sample), "trivial_delegation_ratio")] == pytest.approx(1.0)

    sample.write_text(NON_DELEGATING_SOURCE)
    second = _run(sample, store, tmp_path)
    assert second[(str(sample), "trivial_delegation_ratio")] == pytest.approx(0.0), (
        "trivial_delegation_ratio served stale from the shape-keyed cache"
    )


def test_metrics_json_excludes_non_shape_invariant(tmp_path: Path) -> None:
    """The artifact row is keyed on shape; per-occurrence metric values must
    never be persisted into its metrics_json."""
    import json

    from sqlalchemy import create_engine, text

    sample = tmp_path / "sample.py"
    sample.write_text(GOOD_NAMES_SOURCE)
    db = tmp_path / "instinct.db"
    _run(sample, SQLAlchemyObservationStore(db), tmp_path)

    engine = create_engine(f"sqlite:///{db}")
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT metrics_json FROM observation_artifacts")).fetchall()
    finally:
        engine.dispose()

    assert rows, "expected persisted artifact rows"
    for (raw,) in rows:
        cached_ids = set(json.loads(raw))
        assert "identifier_quality" not in cached_ids
        assert "trivial_delegation_ratio" not in cached_ids
        assert cached_ids, "shape-invariant metrics should still be cached"

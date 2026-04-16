"""Initial schema — arch §4.1.

Creates all MVP tables plus forward-compat reservations:
- `llm_verdicts` (R2 hook, empty in MVP per §12)
- `patterns`, `pattern_evidence` (R3 hooks, empty in MVP per §11 / §12)

`repo_fingerprint` columns on `runs` and `observation_artifacts` per D10
enable the R2+ Postgres warehouse aggregation. `context_hash` on
`run_observations` is a dedicated column per D6.

Revision ID: 001
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_fingerprint", sa.Text, nullable=False),
        sa.Column("repo_fingerprint_source", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("commit_sha", sa.Text, nullable=True),
        sa.Column("branch", sa.Text, nullable=True),
        sa.Column("config_hash", sa.Text, nullable=False),
        sa.Column("tool_version", sa.Text, nullable=False),
        sa.Column("metric_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_runs_fingerprint", "runs", ["repo_fingerprint"])

    op.create_table(
        "observation_artifacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_fingerprint", sa.Text, nullable=False),
        sa.Column("ast_hash", sa.Text, nullable=False),
        sa.Column("language", sa.Text, nullable=False),
        sa.Column("artifact_kind", sa.Text, nullable=False),
        sa.Column("ast_serialized", sa.LargeBinary, nullable=True),
        sa.Column("metrics_json", sa.Text, nullable=False),
        sa.Column("metric_version", sa.Text, nullable=False),
        sa.Column(
            "first_seen_run_id",
            sa.Integer,
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_run_id",
            sa.Integer,
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("stability_tier", sa.Text, nullable=False),
        sa.UniqueConstraint("ast_hash", "language", "metric_version"),
    )
    op.create_index("idx_artifacts_ast_hash", "observation_artifacts", ["ast_hash"])
    op.create_index("idx_artifacts_stability", "observation_artifacts", ["stability_tier"])
    op.create_index("idx_artifacts_fingerprint", "observation_artifacts", ["repo_fingerprint"])

    op.create_table(
        "run_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=False),
        sa.Column("symbol_name", sa.Text, nullable=False),
        sa.Column("enclosing_scope", sa.Text, nullable=True),
        sa.Column("context_hash", sa.Text, nullable=False),
    )
    op.create_index("idx_run_obs_run", "run_observations", ["run_id"])
    op.create_index("idx_run_obs_artifact", "run_observations", ["artifact_id"])
    op.create_index("idx_run_obs_file", "run_observations", ["file_path"])
    op.create_index("idx_run_obs_context", "run_observations", ["context_hash"])

    op.create_table(
        "rankings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_observation_id",
            sa.Integer,
            sa.ForeignKey("run_observations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attention_priority", sa.Float, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("contributing_metrics_json", sa.Text, nullable=False),
    )
    op.create_index("idx_rankings_run", "rankings", ["run_id", "rank"])

    op.create_table(
        "run_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("axis", sa.Text, nullable=False),
        sa.Column("p50", sa.Float, nullable=True),
        sa.Column("p90", sa.Float, nullable=True),
        sa.Column("p95", sa.Float, nullable=True),
        sa.Column("p99", sa.Float, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
    )

    op.create_table(
        "llm_verdicts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column("context_hash", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("prompt_hash", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("artifact_id", "context_hash", "model_id", "prompt_hash"),
    )

    op.create_table(
        "patterns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pattern_id", sa.Text, nullable=False, unique=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("structural_sig", sa.Text, nullable=True),
        sa.Column("lifecycle_state", sa.Text, nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "pattern_evidence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pattern_id", sa.Integer, sa.ForeignKey("patterns.id"), nullable=False),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("relation", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_pattern_evidence_pattern", "pattern_evidence", ["pattern_id"])
    op.create_index("idx_pattern_evidence_artifact", "pattern_evidence", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("idx_pattern_evidence_artifact", table_name="pattern_evidence")
    op.drop_index("idx_pattern_evidence_pattern", table_name="pattern_evidence")
    op.drop_table("pattern_evidence")
    op.drop_table("patterns")
    op.drop_table("llm_verdicts")
    op.drop_table("run_profiles")
    op.drop_index("idx_rankings_run", table_name="rankings")
    op.drop_table("rankings")
    op.drop_index("idx_run_obs_context", table_name="run_observations")
    op.drop_index("idx_run_obs_file", table_name="run_observations")
    op.drop_index("idx_run_obs_artifact", table_name="run_observations")
    op.drop_index("idx_run_obs_run", table_name="run_observations")
    op.drop_table("run_observations")
    op.drop_index("idx_artifacts_fingerprint", table_name="observation_artifacts")
    op.drop_index("idx_artifacts_stability", table_name="observation_artifacts")
    op.drop_index("idx_artifacts_ast_hash", table_name="observation_artifacts")
    op.drop_table("observation_artifacts")
    op.drop_index("idx_runs_fingerprint", table_name="runs")
    op.drop_table("runs")

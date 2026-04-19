"""Shared test helpers.

Private convention: underscore prefix signals "tests only, not project API".
"""

from __future__ import annotations

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.core.types import ArtifactKind


def expected_row_count(n_functions: int, n_modules: int = 0) -> int:
    """Compute the number of (artifact, metric_value) tuples the pipeline yields.

    Derives from METRICS_REGISTRY so tests don't hard-code metric counts.
    Row count = n_functions × |function metrics| + n_modules × |module metrics|.
    """
    fn_metrics = sum(1 for m in METRICS_REGISTRY if ArtifactKind.FUNCTION in m.applies_to)
    mod_metrics = sum(1 for m in METRICS_REGISTRY if ArtifactKind.MODULE in m.applies_to)
    return n_functions * fn_metrics + n_modules * mod_metrics

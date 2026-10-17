#!/usr/bin/env python3
"""Generate every vector file and vectors/SHA256SUMS.

One module per protocol chapter under scripts/vectors/. The scenarios are chosen by hand (edges, transitions); the
expected values come from the small reference computations in those modules. The Go tests of this repository
recompute the expectations independently, so a slip in either one shows up. Run from the repository root:
python3 -I scripts/gen-vectors.py (-I keeps the working directory off the import path; the modules are loaded from
scripts/vectors explicitly).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vectors"))

import ch02_config  # noqa: E402
import ch03_errors  # noqa: E402
import ch04_calls  # noqa: E402
import ch05_database  # noqa: E402
import ch06_events  # noqa: E402
import ch07_work  # noqa: E402
import ch08_authz  # noqa: E402
import ch08_canonical  # noqa: E402
import ch08_identity  # noqa: E402
import ch09_list  # noqa: E402
from common import VEC, sums  # noqa: E402

if __name__ == "__main__":
    VEC.mkdir(exist_ok=True)
    ch03_errors.errors()
    ch04_calls.outbound_timeout()
    ch04_calls.retry_decision_vectors()
    ch04_calls.retry_budget_vectors()
    ch04_calls.circuit_breaker_vectors()
    ch02_config.config_parse_vectors()
    ch04_calls.call_outcomes_vectors()
    ch06_events.partition_vectors()
    ch06_events.envelope_vectors()
    ch07_work.cron_vectors()
    ch05_database.db_errors_vectors()
    ch05_database.migration_lint_vectors()
    ch08_canonical.canonical_vectors()
    ch08_authz.segment_eval_vectors()
    ch08_identity.jwt_vectors()
    ch09_list.search_vectors()
    ch09_list.pages_vectors()
    ch09_list.projection_vectors()
    sums()
    print("\n".join(sorted(p.name for p in VEC.iterdir())))

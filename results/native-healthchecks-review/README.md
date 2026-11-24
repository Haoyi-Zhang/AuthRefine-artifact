# Independent native Healthchecks review

The retained review passed the complete 120-case physical-record checks, the
720 profile/2,400 component decoding checks, 114 fresh native replay checks,
seven concrete observation controls and all 37 first-failure positions.

From the artifact directory, rerun without writing files:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_native_healthchecks.py --results results/native-healthchecks

To save another review, choose a new directory outside the scientific records:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_native_healthchecks.py --results results/native-healthchecks --output results/native-healthchecks-review-reproduction

Existing output directories are rejected. No native application execution is
performed by this audit. The full procedure, closed findings and interpretation
of the replaced-Project control are in ../../proofs/native-healthchecks-review.md.

- summary.json gives the closure counts and the supported claim.
- source-review.json records the checked original/control source relationship.
- native-review.json records the full grid, physical snapshots and identity cases.
- profile-review.json records each caller/observation result and fresh replays.
- observation-controls.json retains the original blind-spot controls, metadata
  controls, 37 event positions and the positive CORS-order control.

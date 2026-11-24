"""Compare frozen native metadata observations to the earlier independent IR.

The IR has no SQL executor, Pydantic runtime or full get_all response. Those
extra native observations are kept separate from paired equality claims.
"""
from __future__ import annotations
from pathlib import Path
import sys

from .source import SOURCE, registry_model


def compare(fixtures, observations):
    # Import only after the native output file has been frozen by run.py.
    code = Path(__file__).resolve().parents[1] / "code"
    sys.path.insert(0, str(code))
    from secret_metadata_profile import observe
    registry = registry_model(observations.get("orm_version", "1.16.0"))
    if observations.get("registry_source", registry) != registry:
        raise ValueError("Native registry source binding differs")
    metadata_registry = registry["predicate_mode"] == "secrecy-metadata"
    profiles = {p["id"]: p for p in fixtures["profiles"]}
    rows = []
    for direct in observations["selection_observations"]:
        profile = profiles[direct["profile"]]
        requested = direct["requested_fields"]
        reference = observe(
            (SOURCE / profile["consumer"] / "piccolo_api/crud/endpoints.py").read_bytes(),
            (SOURCE / profile["producer"] / "piccolo_api/session_auth/tables.py").read_bytes(),
            None if requested is None else tuple(requested), direct["exclude_secrets_override"],
            corrected_registry=metadata_registry,
            filter_boundary_repair=profile["owned_filter_boundary_repair"])
        native = {"query_fields": direct["query"]["projected_fields"],
                  "filter_fields": direct["filter_fields"],
                  "registry_fields": direct["registry_fields"],
                  "token_metadata_secret": direct["token_metadata_secret"]}
        rows.append({"profile": direct["profile"], "context": direct["context"],
                     "native": native, "interpreter": reference, "agree": native == reference})
    if not all(row["agree"] for row in rows):
        raise ValueError("Native and interpreted metadata observations differ")
    return {"registry_source": registry,
            "registry_interpretation": "Source predicate selects Secret-subclass membership or literal secrecy metadata in the separate DataRecord interpreter.",
            "paired_fields": ["query_fields", "filter_fields", "registry_fields", "token_metadata_secret"],
            "paired_observations": len(rows), "disagreements": 0,
            "native_only": ["SQL execution and exceptions", "query rows", "Pydantic schema", "complete get_all JSON response", "filter requests"],
            "rows": rows}

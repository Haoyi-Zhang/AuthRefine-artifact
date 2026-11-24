"""Declared native-study inputs and source identities, without evaluators."""
CONTRACT = {
    "clock": "2020-01-01T00:00:00",
    "caller": "predeclared complete word; all earlier observations remain in force across reconstruction",
    "family": "all fixed bijections from named rows to credential labels; no supplied anchors",
    "observations": {
        "projected": ["authorization decision", "presence of every named row"],
        "selected-row": ["authorization decision", "presence of every named row", "selected row identity on lookup"],
    },
    "raw_record_scope": "Full row contents and tokens validate execution; they are not additional candidate-comparison observations.",
    "restore_complete": "Harness reconstructs every original row and credential, preserving the candidate and the entire comparison history.",
    "reset_initial": "Harness reconstructs exactly the supplied initial subset; initially absent rows remain absent.",
    "cost": "Each production lookup/removal costs one request; fixture reconstruction is counted separately. Initial fixture preparation is outside residual cost.",
}
SOURCE = "source_study/source/h19/after/piccolo_api/session_auth/tables.py"
METHODS = ["SessionsBase.get_user_id", "SessionsBase.remove_session"]

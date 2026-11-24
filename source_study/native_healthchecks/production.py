"""Production caller-profile checks of injectively encoded native observations.

The executable caller-state cap is respected by consecutive blocks of at most
15 captured events. The application is never reset at a block boundary: all
values are drawn from the same collected full prefix. A single routing configuration
is held across blocks. Conjunction of block results is exact equality of all
declared finite vectors; the first failing block determines the first failing
prefix in the complete, prefix-closed caller word.
"""
import json
import math
from pathlib import Path
import sys

from . import contracts, outcomes


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def artifact_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "src/protocol_profile.py").is_file(): return parent
    override = __import__("os").environ.get("AUTHREFINE_ARTIFACT")
    if override and (Path(override) / "src/protocol_profile.py").is_file(): return Path(override)
    raise ValueError("AuthRefine production source is unavailable")


def component(expected, actual):
    from language import normalize
    values = sorted({canonical(value) for value in expected + actual})
    codes = {value: index + 1 for index, value in enumerate(values)}
    width = max(1, math.ceil(math.log2(len(values) + 1)))
    if len(expected) > 15 or width > 7: raise ValueError("production observation envelope exceeded")
    fields = ["outcome_bit_" + str(i) for i in range(width)]
    names = ["event_" + str(i).zfill(2) for i in range(len(expected))]
    policy = dict(principals=names, resources=["outcome"], actions=["capture"], roles=[], members=[], aliases=[],
                  state=[[name, False] for name in fields], rules=[])
    for name, value in zip(names, expected, strict=True):
        code = codes[canonical(value)]
        policy["rules"].append(dict(decision="allow", guard=[dict(field="principal", name=name, negated=False)],
                                    updates=[dict(name=field, value=bool(code & (1 << bit))) for bit, field in enumerate(fields)]))
    policy = normalize(policy)
    alphabet = [[name, "outcome", "capture"] for name in names]
    size = len(names)
    machine = dict(state_names=fields, alphabet=alphabet, observations=[0] + [codes[canonical(value)] for value in actual], initial=0,
                   transitions=[[(["allow", q + 1] if q == i else None) for i in range(size)] for q in range(size + 1)])
    caller = dict(initial=0, transitions=[[(q + 1 if q == i else None) for i in range(size)] for q in range(size + 1)])
    return dict(policy=policy, machine=machine, caller=caller, codebook=[None] + [json.loads(value) for value in values],
                capture_is_access_grant=False)


def diagnose(case, caller_name, mode):
    # Admission checks all 37 operations and every concrete boundary first,
    # including later blocks; no incomplete native prefix can be accepted.
    contracts.check_case(case)
    root = artifact_root()
    if str(root / "src") not in sys.path: sys.path.insert(0, str(root / "src"))
    from protocol_profile import protocol_binding_profile
    from protocol_grouped import support_indexed_protocol_profile
    references, observed = (outcomes.project(values[:contracts.CALLERS[caller_name]], mode) for values in outcomes.vectors(case))
    components, first = [], None
    for start in range(0, len(references), 15):
        inputs = component(references[start:start + 15], observed[start:start + 15])
        methods = {}
        for name, function in (("protocol-scan", protocol_binding_profile), ("protocol-grouped", support_indexed_protocol_profile)):
            result = function(inputs["policy"], inputs["machine"], inputs["caller"], family=[{}])
            profile = result["profiles"][0]
            expected_first = next((i + 1 for i, (left, right) in enumerate(zip(references[start:start + 15], observed[start:start + 15], strict=True)) if not contracts.typed_equal(left, right)), None)
            if profile["equivalent"] != (expected_first is None) or profile["length"] != expected_first:
                raise ValueError("production caller profile differs from independent finite-word equality")
            methods[name] = result
        if first is None and not methods["protocol-scan"]["profiles"][0]["equivalent"]:
            first = start + methods["protocol-scan"]["profiles"][0]["length"]
        components.append(dict(start=start, inputs=inputs, methods=methods,
            application_boundary_before=case["initial"] if start == 0 else case["records"][start - 1]["after"],
            application_boundary_continuity_checked=True))
    oracle = outcomes.independent_profile(case, caller_name, mode)
    if oracle["length"] != first: raise ValueError("block composition lost the globally fixed configuration")
    return {**oracle, "components": components,
            "method_scope": "Two production fixed-configuration caller-profile algorithms. Four concrete credential-routing configurations have separately executed targets; this is not one common-target correspondence-family profile."}

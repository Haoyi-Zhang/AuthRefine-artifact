"""Exact root-branch encodings of the bounded native request language."""
import math
from pathlib import Path
import sys

from . import specification as spec


def core_imports():
    artifact = Path(__file__).resolve().parents[2]
    if str(artifact / "src") not in sys.path:
        sys.path.insert(0, str(artifact / "src"))
    from language import normalize
    from protocol_profile import protocol_binding_profile
    from protocol_grouped import support_indexed_protocol_profile
    return normalize, (("protocol-scan", protocol_binding_profile),
                       ("protocol-grouped", support_indexed_protocol_profile))


def branch(expected, actual, first):
    normalize, _ = core_imports()
    paths = [()] + [word for word in spec.words()[1:] if word[0] == first]
    internal = [word for word in paths if len(word) < spec.DEPTH]
    names = {word: "history_" + str(index).zfill(2) for index, word in enumerate(internal)}
    values = sorted({spec.canonical(value) for word in paths[1:] for value in (expected[word], actual[word])})
    codes = {value: index + 1 for index, value in enumerate(values)}
    width = max(1, math.ceil(math.log2(len(values) + 1)))
    if len(paths) != 14 or len(internal) != 5 or len(values) > 26 or width > 5:
        raise ValueError("root-branch encoding exceeds its proved envelope")
    fields = ["outcome_bit_" + str(index) for index in range(width)]
    policy = dict(principals=sorted(names.values()), resources=list(spec.SYMBOLS), actions=["capture"],
                  roles=[], members=[], aliases=[], state=[[field, False] for field in fields], rules=[])
    for word in paths[1:]:
        code = codes[spec.canonical(expected[word])]
        policy["rules"].append(dict(decision="allow",
            guard=[dict(field="principal", name=names[word[:-1]], negated=False),
                   dict(field="resource", name=word[-1], negated=False)],
            updates=[dict(name=field, value=bool(code & (1 << bit))) for bit, field in enumerate(fields)]))
    policy = normalize(policy)
    alphabet = [[principal, symbol, "capture"] for principal in policy["principals"] for symbol in policy["resources"]]
    positions = {tuple(request): index for index, request in enumerate(alphabet)}
    target_position = {word: index for index, word in enumerate(paths)}
    caller_position = {word: index for index, word in enumerate(internal)}
    sink = len(internal)
    transitions = [[None] * len(alphabet) for _ in paths]
    caller_rows = [[None] * len(alphabet) for _ in range(sink + 1)]
    for word in paths[1:]:
        request = positions[(names[word[:-1]], word[-1], "capture")]
        transitions[target_position[word[:-1]]][request] = ["allow", target_position[word]]
        caller_rows[caller_position[word[:-1]]][request] = caller_position[word] if word in caller_position else sink
    machine = dict(state_names=fields, alphabet=alphabet, observations=[0] + [codes[spec.canonical(actual[word])] for word in paths[1:]],
                   initial=0, transitions=transitions)
    caller = dict(initial=0, transitions=caller_rows)
    ast_nodes = sum(1 + len(rule["guard"]) + len(rule["updates"]) for rule in policy["rules"])
    result = dict(first_operation=first, policy=policy, machine=machine, caller=caller,
                  codebook=[None] + [__import__("json").loads(value) for value in values],
                  target_histories=[list(word) for word in paths],
                  caller_histories=[list(word) for word in internal] + [None],
                  history_principals={spec.name(word): name for word, name in names.items()},
                  bounds=dict(target_states=len(paths), caller_states=len(caller_rows), state_bits=width,
                              ast_nodes=ast_nodes, reference_rules=len(policy["rules"]),
                              rich_codes=len(values), enabled_edges=len(paths) - 1),
                  capture_is_access_grant=False, physical_histories_merged=False)
    if ast_nodes > 104:
        raise ValueError("root-branch AST bound differs")
    verify_language(result)
    return result


def verify_language(component):
    """Independent traversal verifies the history-label erasure bijection."""
    machine, caller = component["machine"], component["caller"]
    found = set()
    queue = [(machine["initial"], caller["initial"], ())]
    seen = set()
    while queue:
        q, t, word = queue.pop()
        if (q, t) in seen:
            raise ValueError("branch unexpectedly merges histories or contains a cycle")
        seen.add((q, t))
        if component["target_histories"][q] != list(word):
            raise ValueError("core event erasure lost its physical history")
        found.add(word)
        for index, next_t in enumerate(caller["transitions"][t]):
            if next_t is None:
                continue
            edge = machine["transitions"][q][index]
            if edge is None:
                raise ValueError("caller enables an absent native edge")
            principal, symbol, action = machine["alphabet"][index]
            if action != "capture" or principal != component["history_principals"][spec.name(word)]:
                raise ValueError("history-labelled event was admitted at the wrong prefix")
            queue.append((edge[1], next_t, (*word, symbol)))
    expected = {()} | {word for word in spec.words()[1:] if word[0] == component["first_operation"]}
    if found != expected or len(found) != 14:
        raise ValueError("root branch is not its complete prefix language")
    return found


def decode(component, indices):
    q, t, word = component["machine"]["initial"], component["caller"]["initial"], []
    for index in indices:
        next_t = component["caller"]["transitions"][t][index]
        edge = component["machine"]["transitions"][q][index]
        if next_t is None or edge is None:
            raise ValueError("production witness leaves its native language")
        word.append(component["machine"]["alphabet"][index][1])
        q, t = edge[1], next_t
        if component["target_histories"][q] != word:
            raise ValueError("production witness decodes to the wrong native history")
    return word


def diagnose(case):
    rows = spec.admit(case)
    _, methods = core_imports()
    results = []
    for mode in ("complete", "http_status"):
        expected = {word: spec.project(spec.reference_observation(case, word), mode) for word in rows}
        actual = {word: spec.project(spec.actual_observation(row), mode) for word, row in rows.items()}
        components, union, first_words = [], set(), []
        for first in spec.SYMBOLS:
            inputs = branch(expected, actual, first)
            union |= verify_language(inputs)
            differences = [word for word in rows if word[0] == first and not spec.typed_equal(expected[word], actual[word])]
            first_word = min(differences, key=lambda word: (len(word), word)) if differences else None
            checked = {}
            for method, function in methods:
                result = function(inputs["policy"], inputs["machine"], inputs["caller"], family=[{}])
                profile = result["profiles"][0]
                decoded = None if profile["equivalent"] else decode(inputs, profile["indices"])
                if not spec.typed_equal(decoded, None if first_word is None else list(first_word)):
                    raise ValueError("production result differs from independent branch first difference")
                checked[method] = result
            if first_word is not None:
                first_words.append(first_word)
            components.append(dict(inputs=inputs, methods=checked))
        if union != set(spec.words()):
            raise ValueError("branch union does not equal the complete bounded request language")
        independent = spec.independent_profile(case, mode)
        first = min(first_words, key=lambda word: (len(word), word)) if first_words else None
        if not spec.typed_equal(independent["shortest_word"], None if first is None else list(first)):
            raise ValueError("branch composition lost bounded global shortestness")
        results.append(dict(**independent, components=components,
                            complete_bounded_language=True, language_words=len(union),
                            singleton_configuration=True, shared_correspondence_family=False))
    return results


def bound_probe():
    """Exercise the production admission boundary with all outcomes distinct."""
    _, methods = core_imports()
    expected = {word: {"reference": list(word)} for word in spec.words()[1:]}
    actual = {word: {"actual": list(word)} for word in spec.words()[1:]}
    components, union = [], set()
    for first in spec.SYMBOLS:
        inputs = branch(expected, actual, first)
        union |= verify_language(inputs)
        for _, function in methods:
            result = function(inputs["policy"], inputs["machine"], inputs["caller"], family=[{}])
            if result["shortest_failure"] != 1:
                raise ValueError("worst-case bound probe did not execute the production checker")
        components.append(inputs["bounds"])
    if union != set(spec.words()):
        raise ValueError("bound probe language coverage differs")
    return dict(native_execution=False, purpose="production schema and language bounds before acquisition",
                full_tree_nodes=40, full_tree_edges=39, branches=components, union_words=len(union),
                production_methods_checked=2)

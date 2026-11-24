#!/usr/bin/env python3
"""Bounded command-line entry point for complete fixed-binding diagnosis.

This complements policy.py's uniform-verdict ``diagnose`` command. A completed
profile is written atomically, without overwriting its destination. Invalid or
inconclusive inputs leave no profile file. Semantic differences are completed
diagnostic results and therefore exit successfully with their full family rows.
"""
from __future__ import annotations

import argparse
import json

from checker import Rejected, ensure, load
from extensions import DEFAULT_FAMILY_LIMIT, DEFAULT_WORK_BUDGET, binding_profile
from family_diagnosis import support_indexed_profile
from language import PolicyError, read_policy
from policy import output
from protocol_profile import protocol_binding_profile
from protocol_grouped import support_indexed_protocol_profile
from symbolic_family import symbolic_family_profile


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Rejected(message)


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("policy", help="canonical policy JSON or .cnl sentence file")
    parser.add_argument("machine", help="bounded target-machine JSON")
    parser.add_argument("output", help="new JSON output path; never overwritten")
    parser.add_argument("--engine", choices=("indexed", "scan", "protocol", "protocol-indexed",
                                             "symbolic", "symbolic-cudd", "protocol-symbolic",
                                             "protocol-symbolic-cudd"), default="indexed")
    parser.add_argument("--family", help="JSON array of complete legal bindings; otherwise use Cartesian declarations")
    parser.add_argument("--protocol", help="caller protocol JSON, required for protocol engines")
    parser.add_argument("--budget", type=int, default=DEFAULT_WORK_BUDGET,
                        help="engine-specific abstract work envelope")
    parser.add_argument("--family-limit", type=int, default=DEFAULT_FAMILY_LIMIT,
                        help="maximum family inputs, including duplicates")
    parser.add_argument("--node-limit", type=int, help="decision-diagram node cap, symbolic engines only")
    parser.add_argument("--symbolic-operations", type=int,
                        help="backend conditional-operation cap, symbolic engines only")
    try:
        args = parser.parse_args(argv)
        with_protocol = args.engine.startswith("protocol")
        is_symbolic = "symbolic" in args.engine
        ensure(with_protocol == (args.protocol is not None),
               "--protocol is required for protocol engines and is not accepted by total-table engines")
        ensure(is_symbolic or (args.node_limit is None and args.symbolic_operations is None),
               "diagram limits require a symbolic engine")
        policy = read_policy(args.policy)
        machine = load(args.machine)
        family = load(args.family) if args.family is not None else None
        if args.family is not None:
            ensure(isinstance(family, list), "--family must contain a JSON array of complete bindings")
        options = {"family": family, "budget": args.budget, "family_limit": args.family_limit}
        if is_symbolic:
            symbolic_options = {"backend": "cudd" if args.engine.endswith("cudd") else "finite-domain"}
            if args.node_limit is not None:
                symbolic_options["node_limit"] = args.node_limit
            if args.symbolic_operations is not None:
                symbolic_options["operation_limit"] = args.symbolic_operations
            result = symbolic_family_profile(policy, machine,
                                             protocol=load(args.protocol) if with_protocol else None,
                                             **options, **symbolic_options)
        elif with_protocol:
            method = (support_indexed_protocol_profile if args.engine == "protocol-indexed"
                      else protocol_binding_profile)
            result = method(policy, machine, load(args.protocol), **options)
        else:
            method = support_indexed_profile if args.engine == "indexed" else binding_profile
            result = method(policy, machine, **options)
        output(args.output, {"engine": args.engine, **result})
        print(json.dumps({"completed": True, "engine": args.engine,
                          "classification": result["classification"],
                          "bindings": result["bindings"]}))
        return 0
    except (PolicyError, Rejected, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError) as error:
        inconclusive = ((isinstance(error, PolicyError) and error.category == "LIMIT")
                        or (isinstance(error, Rejected) and error.kind == "inconclusive"))
        print(json.dumps({"completed": False, "kind": "inconclusive" if inconclusive else "invalid",
                          "reason": str(error)}))
        return 2 if inconclusive else 1


if __name__ == "__main__":
    raise SystemExit(main())

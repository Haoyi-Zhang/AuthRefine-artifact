"""Strict, deterministic JSON and exclusive evidence-file creation."""
import gzip
import json
import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, names, label):
    require(type(value) is dict and set(value) == set(names), label + ": exact fields required")


def integer(value, label, low=0, high=None):
    require(type(value) is int and value >= low and (high is None or value <= high),
            label + ": integer outside permitted range")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def same(left, right):
    return encoded(left) == encoded(right)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _float(value):
    result = float(value)
    require(math.isfinite(result), "nonfinite JSON float")
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def read(path):
    raw = path.read_bytes()
    return decode(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def read_lines(path):
    raw = gzip.decompress(path.read_bytes())
    require(raw.endswith(b"\n"), "native record stream has no final line delimiter")
    return [decode(line) for line in raw.splitlines()]


def write(path, value):
    raw = encoded(value)
    with path.open("xb") as stream:
        stream.write(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw + b"\n")

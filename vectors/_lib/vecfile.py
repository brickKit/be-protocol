"""Shared writer for be-protocol vector files.

Every generator builds a list of cases and calls write_file(). The layout of a
file is described in vectors/README.md and vectors/case-file.schema.json.
Only the standard library is used, so any Python >= 3.11 regenerates the
vectors without installing anything.
"""

import json
import os
import re

PROTOCOL = "1.0"
_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+\.[a-z0-9][a-z0-9-]*$")


class CaseList:
    def __init__(self, area, topic):
        self.area = area
        self.topic = topic
        self.cases = []
        self._ids = set()

    def add(self, slug, description, op, inp, expected=None, error=None, refs=None):
        cid = f"{self.area}.{self.topic}.{slug}"
        if not _ID_RE.fullmatch(cid):
            raise ValueError(f"bad case id {cid!r}")
        if cid in self._ids:
            raise ValueError(f"duplicate case id {cid!r}")
        if (expected is None) == (error is None):
            raise ValueError(f"{cid}: exactly one of expected / error")
        self._ids.add(cid)
        case = {"id": cid, "description": description, "op": op, "input": inp}
        if refs:
            case["refs"] = refs
        if error is not None:
            if isinstance(error, str):
                error = {"reason": error}
            case["expected_error"] = error
        else:
            case["expected"] = expected
        self.cases.append(case)
        return case


def write_file(path, area, topic, generator, cases, notes=None):
    doc = {
        "area": area,
        "topic": topic,
        "protocol": PROTOCOL,
        "generated_by": generator,
        "note": "Generated file: do not edit by hand; change the generator and re-run it (make -C vectors gen).",
    }
    if notes:
        doc["notes"] = notes
    doc["cases"] = cases.cases if isinstance(cases, CaseList) else cases
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return len(doc["cases"])


def area_dir(file_of_generator):
    """The area directory (parent of gen/) of a generator file."""
    return os.path.dirname(os.path.dirname(os.path.abspath(file_of_generator)))

import json
from pathlib import Path

import pytest

from gpsvet import Fix, detect

VECTORS = sorted((Path(__file__).parents[2] / "spec" / "vectors").glob("*.json"))


def load(path):
    doc = json.loads(path.read_text())
    fixes = [Fix(*row[:7], cn0=tuple(row[7]) if row[7] else None) for row in doc["fixes"]]
    return doc, fixes


@pytest.mark.parametrize("path", VECTORS, ids=lambda p: p.stem)
def test_vector(path):
    doc, fixes = load(path)
    rep = detect(fixes, doc["profile"])
    exp = doc["expected"]
    assert rep.spoofed == exp["spoofed"]
    assert rep.scores == pytest.approx(exp["scores"], abs=1e-6)
    got = sorted([f.index, f.check, f.severity] for f in rep.flags)
    assert [g[:2] for g in got] == [e[:2] for e in exp["flags"]]
    assert [g[2] for g in got] == pytest.approx([e[2] for e in exp["flags"]], abs=1e-6)


def test_vectors_exist():
    assert len(VECTORS) >= 15

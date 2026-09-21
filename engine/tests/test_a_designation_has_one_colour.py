"""En beteckning, en färg - även när bladet skriver ut dimensionen på ett ställe och utelämnar den på ett annat.

Ett rör som byter färg mitt i sin egen sträckning läses som två rör. Det hände så fort samma namn förekom både
med och utan dimension: identitetsnyckeln bär `|DN?` för det ena och `|DN22` för det andra, och färgen hashades
på hela nyckeln. Färgen hör till namnet. Dimensionen står i tabellens egen kolumn.

Paletten är produktens, inte motorns, så provet kör den där den bor: källan transpileras med den esbuild som
redan följer med frontenden och körs i node. Saknas något av det hoppas provet över i stället för att ljuga.
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PALETTE = os.path.join(ROOT, "frontend", "src", "palette.ts")
ESBUILD = os.path.join(ROOT, "frontend", "node_modules", ".bin", "esbuild")


def _colours(keys: list[str]) -> dict[str, str]:
    if not (shutil.which("node") and os.path.isfile(ESBUILD) and os.path.isfile(PALETTE)):
        pytest.skip("node eller frontendens esbuild finns inte här")
    js = subprocess.run([ESBUILD, PALETTE, "--format=cjs"], capture_output=True, text=True, check=True).stdout
    prog = js + "\nconsole.log(JSON.stringify(Object.fromEntries(%s.map((k) => [k, module.exports.identityColor(k)]))));" % json.dumps(keys)
    return json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout)


def test_the_same_designation_is_one_colour_with_and_without_a_dimension():
    c = _colours(["KV31|DN15", "KV31|DN?", "KV31", "VS1-S13|DN22", "VS1-S13|DN?"])
    assert c["KV31|DN15"] == c["KV31|DN?"] == c["KV31"], c
    assert c["VS1-S13|DN22"] == c["VS1-S13|DN?"], c


def test_two_different_designations_are_told_apart():
    c = _colours(["S01-P3|DN75", "S01-P5|DN75", "KV1|DN15", "VV1|DN15"])
    assert c["S01-P3|DN75"] != c["S01-P5|DN75"], c
    assert c["KV1|DN15"] != c["VV1|DN15"], c


def test_the_colour_does_not_move_between_runs_of_the_same_sheet():
    # samma nyckel två gånger ger samma svar: färgen är en funktion av namnet, inte av ordningen den frågades i
    a = _colours(["VS21-S13-F50|DN15"])
    b = _colours(["KV1|DN?", "VS21-S13-F50|DN15"])
    assert a["VS21-S13-F50|DN15"] == b["VS21-S13-F50|DN15"]

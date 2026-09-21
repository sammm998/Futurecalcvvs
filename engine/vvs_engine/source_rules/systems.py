"""System conventions copied losslessly from swedish-vvs-drawings/data.

Do not infer a twin from a system missing from the supplied table. This table
permits pairing; the drawing must still provide actual parallel geometry.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def systems():
    data=json.loads((Path(__file__).with_name('data')/'system_designations.json').read_text())
    return {entry['code']:entry for entry in data['entries']}

def system_code(system):
    value = re.sub(r'\d+$','',(system or '').strip())
    # VVCi is a distinct supplied code; uppercasing it loses its table entry.
    return next((code for code in systems() if code.casefold() == value.casefold()), value.upper())

def line_count(system):
    return systems().get(system_code(system),{}).get('line_count')

def permits_unlabelled_twin(system):
    return line_count(system)==2

def is_gravity(system):
    # Swedish assign_label.py and PipeStudio associate.py: S*/D*, except SL.
    code=system_code(system)
    return code.startswith(('S','D')) and code!='SL'

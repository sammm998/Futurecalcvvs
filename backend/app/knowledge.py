"""Complete supplied VVS definitions and PipeStudio reference documents.

Source text stays inert. Local drawing evidence governs engine decisions;
import completeness is separate from runtime rule coverage.
"""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def vocabulary():
    return json.loads((Path(__file__).with_name('data')/'swedish-vvs-knowledge.json').read_text(encoding='utf-8'))

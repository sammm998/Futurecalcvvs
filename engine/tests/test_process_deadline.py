import sys
from pathlib import Path
import pytest


def test_even_a_single_page_has_an_enforced_process_deadline(synthetic_pdf,tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
    from app.analysis_worker import analyze_isolated
    from vvs_engine.cli import AnalysisTookTooLong
    with pytest.raises(AnalysisTookTooLong,match='tidsgränsen'):
        analyze_isolated(synthetic_pdf,str(tmp_path/'out'),deadline_s=.01,
                         determinism=False,review=False,second_reader=False)
    assert not (tmp_path/'out/summary.json').exists()

from vvs_engine.profile.styles import identify, library, distance
from vvs_engine.pdf.extract import extract_document


def test_reference_aliases_are_not_independent_styles(synthetic_pdf):
    report=identify(extract_document(synthetic_pdf).pages[0])
    assert report['reference_count']==14
    assert report['canonical_style_count']==11
    assert report['applied_to_quantities'] is False
    assert report['state']=='UNKNOWN', 'A tiny synthetic drawing does not prove a known style'


def test_same_profile_has_zero_distance_when_all_features_exist():
    lib,_=library()
    p=lib['styles'][0]['profile']
    assert distance(p,p)==0


def test_unknown_style_uses_local_measurements_without_borrowing_nearest_rules(monkeypatch):
    from vvs_engine.source_rules.styles import resolve
    import vvs_engine.profile.styles as classifier
    evidence={'state':'UNKNOWN','nearest':{'style_id':'style-1','distance':.4},
              'candidates':[{'style_id':'style-1'}], 'measured':{'width_ladder':[.42,1.17]}}
    monkeypatch.setattr(classifier,'identify',lambda page:evidence)
    profile,report=resolve(object())
    assert profile['rules']==[]
    assert profile['observed_features']==evidence['measured']
    assert report['id'] is None
    assert report['policy']=='general_rules_with_local_evidence'

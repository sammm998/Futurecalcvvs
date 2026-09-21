from vvs_engine.source_rules.coverage import report


def test_import_does_not_claim_full_semantic_or_accuracy_verification():
    r=report()
    assert len(r['tables'])==24
    assert not r['import_equals_implementation']
    assert not r['unattended_takeoff_verified']
    assert all(not t['whole_table_implemented'] for t in r['tables'])
    assert all(not rule['accuracy_verified'] for rule in r['rules'])
    states={rule['source_rule']:rule['state'] for rule in r['rules']}
    assert states['document_rules/as_built_duty']=='REFERENCE_ONLY'
    assert states['document_rules/precedence_drawing_vs_spec']=='EXECUTABLE'

from vvs_engine.source_rules.swedish import tables, lookup, label_facts, vertical_notation, specification_conflict


def test_all_supplied_code_fields_are_available_without_losing_collisions():
    from vvs_engine.source_rules.systems import system_code, line_count
    assert len(tables()) == 24
    for name, table in tables().items():
        for entry in table.get('entries', []):
            for key in ('code', 'sensor_code', 'instrument_code'):
                if key in entry:
                    assert {'table': name, 'entry': entry} in lookup(entry[key])['meanings']
    assert lookup('DB')['state'] == 'AMBIGUOUS'
    assert lookup('NONEXISTENT')['state'] == 'UNKNOWN'
    assert lookup('DB', {'DB': {'meaning': 'local'}})['meanings'] == [{'meaning': 'local'}]
    assert system_code('VVCi1')=='VVCi'
    assert line_count('VVCi1') == next(e['line_count'] for e in tables()['system_designations']['entries'] if e['code']=='VVCi')


def test_vertical_rules_preserve_all_four_meanings_without_inventing_height():
    for over, under in [(False,False),(True,False),(False,True),(True,True)]:
        r = vertical_notation(over, under, is_vertical=True)
        assert r['penetrates_slab_above'] == (not over)
        assert r['penetrates_slab_below'] == (not under)
        assert r['length_m'] is None
    assert vertical_notation(False,False,is_vertical=False)['state'] == 'NOT_APPLICABLE'


def test_pressure_height_and_material_codes_do_not_invent_flow_or_specifications():
    d = {'system':'SL','middle':['S13'],'dimension':22,'raw':'SL1-S13-22/W'}
    r = label_facts({'designations':[d]})['designations'][0]
    assert not r['level_can_indicate_flow']
    assert r['material'] is None and r['insulation_specification'] is None
    assert r['unresolved_middle_fields'] == ['S13']


def test_specification_precedence_requires_applicable_contract_and_keeps_conflict():
    assert specification_conflict('copper','steel')['value'] is None
    r = specification_conflict('copper','steel',contract_type='utförandeentreprenad')
    assert r['value']=='steel' and r['review_required'] and r['state']=='CONFLICT'
    assert specification_conflict(None,'steel')['state']=='MISSING_INPUT'


def test_printed_suffix_separators_and_venting_names_survive_native_adapter():
    from dataclasses import asdict
    from vvs_engine.source_rules.pipestudio.vvs import parse_designation
    from vvs_engine.source_rules.swedish import designation_text
    for text in ['VV01-X7-25-F60','KV01-X7-20-W40','S01-P5-110L','VS1-S13-22/W']:
        assert designation_text(asdict(parse_designation(text))) == text

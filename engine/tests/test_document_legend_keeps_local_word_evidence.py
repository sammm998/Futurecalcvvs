from vvs_engine.semantics.legend import DrawingLegend, LegendEntry, learn_roles


def entry(role='unused', origin='usage'):
    return LegendEntry('AV1', 'Avstängningsventil', '', (10,10,100,20), role, origin)


def test_document_legend_keeps_a_component_identified_by_its_own_description():
    document = DrawingLegend(own=False, entries=[entry()])
    sheet = DrawingLegend(own=True, entries=[entry('component', 'the_list_says_so')])
    learn_roles(document, sheet)
    assert document.entries[0].role == 'component'
    assert document.entries[0].role_from == 'the_list_says_so'


def test_a_borrowed_description_is_not_republished_as_local_evidence():
    document = DrawingLegend(own=False, entries=[entry()])
    sheet = DrawingLegend(own=False, entries=[entry('component', 'the_list_says_so')])
    learn_roles(document, sheet)
    assert document.entries[0].role == 'unused'


def test_inherited_roles_cannot_vote_for_themselves():
    document = DrawingLegend(own=False, entries=[entry()])
    sheet = DrawingLegend(own=True, entries=[entry('system', 'other_sheet')])
    learn_roles(document, sheet)
    assert document.entries[0].role == 'unused'

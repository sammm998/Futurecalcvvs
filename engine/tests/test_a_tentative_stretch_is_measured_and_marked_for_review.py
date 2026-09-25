"""A stretch the native reading names only tentatively is measured, and marked for review where no second reading agrees.

The viewer showed such stretches as "Obekräftad utbredning": one designation, known, but bound with low
confidence, and the stretch was left out of the quantity until someone redrew it. Where the host engine,
reading its own leaders and contacts, confirms that same designation, two readings agree and the piece is
confirmed outright. Otherwise it is measured on its one designation and marked: the pipe says it needs review,
and the quantity row reports how many of its metres rest on such a reading. Two competing designations stay
unresolved.
"""
from types import SimpleNamespace

from vvs_engine.measure.measure import aggregate
from vvs_engine.pipes.ownership import PrimState, identity_from_text
from vvs_engine.source_rules.native_assignment import project

from test_what_the_native_graph_names_nothing_on_keeps_the_host_reading import _graphs, _native, _result


def _low():
    r = _result()
    r['combined']['result']['bindings'][0]['confidence'] = 'low'
    return r


def _host_says(text, dim):
    def reading(graphs):
        ident = identity_from_text(text, dim, text.split('-')[0], None)
        return SimpleNamespace(prim_states={'f': {0: PrimState(state='CONFIRMED', identity=ident, reason='host')}})
    return reading


def test_the_host_reading_the_same_name_confirms_it_outright():
    ownership, report = project(_graphs(), _native(), _low(), 0, {}, _host_says('KV1-X7-40', 40))
    st = ownership.prim_states['f'][0]
    assert st.state == 'CONFIRMED' and st.identity.display == 'KV1-X7-40' and not st.tentative
    assert report['host_confirmed_primitives'] == 1 and report['tentative_primitives'] == 0
    assert not any(p.needs_review for p in ownership.pipes)


def test_without_a_second_reading_it_is_measured_and_marked():
    ownership, report = project(_graphs(), _native(), _low(), 0, {})
    st = ownership.prim_states['f'][0]
    assert st.state == 'CONFIRMED' and st.identity.display == 'KV1-X7-40' and st.tentative
    assert report['tentative_primitives'] == 1
    pipe = next(p for p in ownership.pipes if p.identity.display == 'KV1-X7-40')
    assert pipe.needs_review


def test_a_different_host_name_keeps_the_native_name_marked():
    ownership, _ = project(_graphs(), _native(), _low(), 0, {}, _host_says('KV1-X7-16', 16))
    st = ownership.prim_states['f'][0]
    assert st.state == 'CONFIRMED' and st.identity.display == 'KV1-X7-40' and st.tentative


def test_the_quantity_row_says_how_much_rests_on_a_tentative_reading():
    ownership, _ = project(_graphs(), _native(), _low(), 0, {})
    pipe = next(p for p in ownership.pipes if p.identity.display == 'KV1-X7-40')
    m = SimpleNamespace(pipe=pipe, twin_of=None, horizontal_m=2.0, horizontal_pdf_units=100.0, hatched_m=0.0,
                        state='CONFIRMED', vertical_m=None)
    row = aggregate([m], {}, 0.02)[0]
    assert row['confirmed_horizontal_m'] == 2.0 and row['review_m'] == 2.0

"""A stretch the native reading names only tentatively is confirmed when the host reads the same name on it.

The viewer showed such stretches as "Obekräftad utbredning": one designation, known, but bound with low
confidence, so the stretch was not measured. The host engine reads the sheet with its own leaders and contacts;
where it independently confirmed that same designation on the piece, two readings agree and the piece is
measured. Where the host names something else, or nothing, the piece stays unconfirmed - on the reference
sheets those tentative names were wrong about half the time.
"""
from types import SimpleNamespace

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


def test_the_host_reading_the_same_name_confirms_it():
    ownership, report = project(_graphs(), _native(), _low(), 0, {}, _host_says('KV1-X7-40', 40))
    st = ownership.prim_states['f'][0]
    assert st.state == 'CONFIRMED' and st.identity.display == 'KV1-X7-40'
    assert report['host_confirmed_primitives'] == 1


def test_a_different_host_name_leaves_it_unconfirmed():
    ownership, report = project(_graphs(), _native(), _low(), 0, {}, _host_says('KV1-X7-16', 16))
    assert ownership.prim_states['f'][0].state == 'AMBIGUOUS'
    assert report['host_confirmed_primitives'] == 0


def test_without_the_host_it_stays_unconfirmed():
    ownership, _ = project(_graphs(), _native(), _low(), 0, {})
    assert ownership.prim_states['f'][0].state == 'AMBIGUOUS'

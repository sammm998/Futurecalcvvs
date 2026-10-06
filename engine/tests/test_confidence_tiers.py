"""Every measured pipe says how sure the reading is of it: sure, inferred, or to be reviewed."""
from vvs_engine.pipes.confidence import tier


def test_a_label_of_its_own_is_sure():
    assert tier(['pipestudio_native_assignment']) == 'sure'
    assert tier(['pipestudio_native_assignment_confirmed_by_host_reading']) == 'sure'


def test_a_name_run_on_from_named_pipe_is_inferred():
    assert tier(['continues_the_connected_pipe']) == 'inferred'
    assert tier(['pipestudio_native_assignment', 'gravity_walk_lower_invert']) == 'inferred'
    assert tier(['host_reading_where_the_native_graph_named_nothing']) == 'inferred'


def test_a_tentative_name_or_a_flag_is_for_review():
    assert tier(['pipestudio_native_assignment'], needs_review=True) == 'review'
    assert tier(['model_completeness']) == 'review'
    assert tier(['pipestudio_native_assignment'], flags=['dimension_change_without_fitting']) == 'review'

"""Optional covering and DN line breaks do not change a legend code's role."""
from types import SimpleNamespace

from vvs_engine.semantics.legend import DrawingLegend, LegendEntry, assign_roles


def test_system_material_pattern_is_shared_across_covering_and_dimension_layout():
    legend = DrawingLegend(entries=[
        LegendEntry(c, '', '', (0, 0, 10, 10))
        for c in ['KV1', 'VV1', 'RAD2', 'AV201', 'X7', 'S13']
    ])
    def label(head, text, pattern, dn, source):
        return SimpleNamespace(text=text, system_token=head, pattern=pattern,
                               dn=dn, dn_source=source, bbox=(100, 100, 200, 110))
    rows = [label('KV1', 'KV1-X7', 'A9-A9', 16, 'row'),
            label('VV1', 'VV1-X7-16', 'A9-A9-9', 16, 'inline'),
            label('RAD2', 'RAD2-S13/W', 'A9-A9/A', 35, 'row'),
            label('AV201', 'AV201-22', 'A9-9', 22, 'inline')]
    assign_roles(legend, rows)
    assert {'KV1', 'VV1', 'RAD2'} <= legend.systems()
    assert 'AV201' not in legend.systems()
    assert legend.names_a_pipe(rows[2])


def test_repeated_unlisted_numbered_variant_uses_its_own_labels():
    legend = DrawingLegend(entries=[LegendEntry(c, '', '', (0, 0, 10, 10))
                                   for c in ['RAD1', 'RAD2', 'S13', 'AV201']])
    def label(head, material, number):
        return SimpleNamespace(did=f'{head}-{number}', text=f'{head}-{material}-35/W',
                               system_token=head, pattern='A9-A9-9/A', dn=35, dn_source='inline',
                               bbox=(100, 100+number*20, 200, 110+number*20))
    rows = [label('RAD1', 'S13', 1), label('RAD2', 'S13', 2),
            label('RAD3', 'S13', 3), label('RAD3', 'S13', 4),
            label('RAD4', 'S13', 5), label('RAD5', 'UNKNOWN', 6), label('RAD5', 'UNKNOWN', 7),
            label('ROOM1', 'S13', 8), label('ROOM1', 'S13', 9)]
    assign_roles(legend, rows)
    assert legend.usage_systems == {'RAD3': ['RAD3-3', 'RAD3-4']}
    assert legend.names_a_pipe(rows[2])
    assert not legend.names_a_pipe(rows[4])
    assert not legend.names_a_pipe(rows[7])
    # The original legend remains original; no description or geometry is invented.
    assert 'RAD3' not in legend.by_code
    assign_roles(legend, rows[:2])
    assert not legend.usage_systems


def test_sheet_artifacts_keep_local_system_evidence_when_showing_the_set_legend(synthetic_pdf):
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.pipeline import analyze_page
    from vvs_engine.output.artifacts import sheet_reading
    from vvs_engine.semantics.legend import adopt

    doc = extract_document(synthetic_pdf)
    pa = analyze_page(doc.pages[0])
    pa.legend.usage_systems = {"RAD3": ["local-label-1", "local-label-2"]}
    shared = DrawingLegend(entries=[LegendEntry("RAD1", "Värme", "", (0, 0, 10, 10))],
                           usage_systems={"RAD9": ["other-sheet-1", "other-sheet-2"]})
    result = sheet_reading(pa, doc, doc_legend=shared)["drawing-legend.json"]
    assert result["usage_systems"] == pa.legend.usage_systems
    assert not adopt(pa.legend).usage_systems

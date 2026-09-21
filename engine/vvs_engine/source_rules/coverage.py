"""Trace imported source material separately from executable takeoff policies.

Unit-test coverage is not drawing accuracy or verification of site documents.
This catalogue deliberately leaves unsupported procedures unimplemented.
"""
import hashlib
import json
from pathlib import Path
from .swedish import DATA

POLICIES = {
    'pipe_marking_rules/label_format': ('adapter.parse_source_designation', 'test_pipestudio_source_flow.py'),
    'pipe_marking_rules/label_repetition': ('systems.permits_unlabelled_twin', 'test_source_circuit_contacts.py'),
    'pipe_marking_rules/index_meaning': ('swedish.label_facts', 'test_swedish_runtime.py'),
    'pipe_marking_rules/properties_from_beskrivning': ('swedish.label_facts', 'test_swedish_runtime.py'),
    'pipe_marking_rules/single_line_representation': ('pipestudio.assemble', 'test_native_detection_bridge.py'),
    'pipe_marking_rules/section_convention': ('native_assignment.project', 'test_native_detection_bridge.py'),
    'document_rules/precedence_drawing_vs_spec': ('swedish.specification_conflict', 'test_swedish_runtime.py'),
}


def report():
    tables=[];rules=[]
    for path in sorted(DATA.glob('*.json')):
        d=json.loads(path.read_text());entries=d.get('entries',[])
        code_count=sum(any(k in e for k in ('code','sensor_code','instrument_code')) for e in entries)
        tables.append({'table':path.stem,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'imported':True,'lookup_entries':code_count,'whole_table_implemented':False})
        for e in entries:
            if 'id' not in e:continue
            key=path.stem+'/'+e['id'];implementation=POLICIES.get(key)
            rules.append({'source_rule':key,'state':'EXECUTABLE' if implementation else 'REFERENCE_ONLY',
                          'implementation':implementation[0] if implementation else None,
                          'related_test_file':implementation[1] if implementation else None,
                          'semantic_coverage_complete':False,
                          'accuracy_verified':False})
    return {'tables':tables,'rules':rules,'import_equals_implementation':False,
            'site_and_contract_requirements_verified':False,'unattended_takeoff_verified':False}

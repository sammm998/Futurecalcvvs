"""Geometry admission keeps short, explicitly named systems in the graph.

Admission is not ownership: the original source assignment engines still decide
which label binds each stretch. No system is admitted from its layer alone.
"""
def has_pipe_run(description, matching_label_contacts=0, annotation_width=None):
    if description.longest_chain < 25:
        return False
    if matching_label_contacts >= 1 and annotation_width is not None and description.width > annotation_width + 1e-6:
        return True
    return description.kind != 'sparse' and description.total_length >= 60

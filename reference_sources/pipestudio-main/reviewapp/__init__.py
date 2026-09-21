"""Review & annotation application for the pipe segmentation pipeline.

Modular by design:

    models.py       object models (Pipe, LabelBox, JoinPoint, Document)
    pipeline.py     the only bridge to pipe_seg / pipe_types
    assignment.py   re-runnable label assignment on the edited document
    session.py      document ownership, persistence, exports
    server.py       HTTP server + JSON API
    static/         front end (ES modules)

Nothing in the CV pipeline imports this package, so it can be removed without
affecting pipe_seg.py or pipe_types.py.
"""

__all__ = ["serve"]

from .server import serve

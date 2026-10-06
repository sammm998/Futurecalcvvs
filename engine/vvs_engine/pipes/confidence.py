"""How sure the reading is of a measured pipe: sure, inferred, or to be reviewed.

The takeoff counts every metre it can name, and says how it came by each name, so the reader knows how much of a
figure to check:

  sure      a label's own leader names it, as the drawing's own reading found it (and, where a second reading
            looked, that one agreed);
  inferred  named by the drawing's logic rather than a label of its own: run on from named pipe it joins, read
            by the host where the drawing's own reading named nothing, sized by the walk along a gravity run,
            and the like;
  review    measured on the best reading there is, but marked for the reader: a tentative name, a name a
            model gave in its second look, or a pipe a consistency check flagged.
"""
from __future__ import annotations

SURE, INFERRED, REVIEW = "sure", "inferred", "review"
TIERS = (SURE, INFERRED, REVIEW)

# reasons that mean a label's own evidence named the run
_SURE = {"pipestudio_native_assignment", "pipestudio_native_assignment_confirmed_by_host_reading"}
# reasons that always ask the reader to look
_REVIEW = {"model_completeness", "pipestudio_tentative_best_reading"}


def tier(evidence, needs_review: bool = False, flags=()) -> str:
    """The tier of one measured pipe from the reasons it was named by."""
    reasons = set(evidence or ())
    if needs_review or flags or reasons & _REVIEW:
        return REVIEW
    if reasons and reasons <= _SURE:
        return SURE
    return INFERRED

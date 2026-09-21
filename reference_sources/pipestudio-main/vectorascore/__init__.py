"""Stage-wise vector pipeline: extract -> profile -> detect -> labels -> bucket -> assemble -> associate -> fable binding -> review.

Every stage is a pure function over the previous stage's JSON; coordinates are
page points in the DISPLAYED (de-rotated) frame, y down, matching the rendered
background at ``scale`` px/pt.
"""

"""Cross-capability kernels.

Modules here are used by more than one capability and belong to none of them.
Keeping them under `shared/` distinguishes a genuine shared kernel from a
capability's own logic that merely has not been absorbed yet -- the distinction
S8 of the architecture review is really about.

Measured before moving (2026-07-30):

* `profile/`   -- used by fitness, research, user, planning, graph and vfs.
                 Notably NOT fitness-specific, which is why the review's
                 suggestion to absorb it into `capabilities/fitness/` was not
                 followed: research and planning would then import from inside
                 another capability's folder.
* `grounding/` -- used by fitness (3 files) and research (2).
"""

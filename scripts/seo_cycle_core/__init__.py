"""Shared helpers for seo-cycle command-line scripts.

T-089 round 3: importing `spend_guard` here, not leaving it to each client
to remember, is deliberate. The gate it installs (`PAID_HOSTS` +
`armed_spend()`, see `spend_guard.py`) only exists in a process that has
imported it — a process problem the independent review named directly
(round-2 finding R2-1). Every existing paid client already imports
something else from this package (config, usage_ledger, ads helpers) for
reasons that have nothing to do with money — importing `spend_guard` here
means the gate activates as a side effect of that, not as a separate step a
client author has to know to take. This does not cover a script that
imports NOTHING from `seo_cycle_core` at all; that residual gap and its
compensating control (a static check, not a runtime one) are documented in
`spend_guard.py`'s own module docstring."""

from . import spend_guard as _spend_guard  # noqa: F401

"""Skip tests whose premise is a file-permission denial when running as root.

root ignores the mode bits these tests rely on (`chmod 000`, read-only
directories), so under root the "unreadable"/"unwritable" fixture is in fact
readable/writable and the assertion fails for a reason that says nothing
about the code under test. CI runners are non-root, so the tests still run
there; containers and VPS deployments that run as root skip them honestly
instead of reporting 6 false failures.
"""

from __future__ import annotations

import os
import unittest

RUNNING_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

skip_if_root = unittest.skipIf(
    RUNNING_AS_ROOT,
    "root обходит права файлов — тест на отказ доступа здесь не воспроизводится",
)

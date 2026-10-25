"""Imports every module's table models so Alembic and tests see the full metadata.

Each phase adds its module here, e.g. ``import app.modules.identity.models``.
"""

import app.modules.candidacies.models
import app.modules.geography.models
import app.modules.identity.models
import app.modules.people.models  # noqa: F401

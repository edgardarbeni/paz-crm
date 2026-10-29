"""Imports every installed module's table models so Alembic and tests see the full metadata.
Modules declare their models in `module.py` (`app.core.modules`)."""

from app.core.modules import import_models

import_models()

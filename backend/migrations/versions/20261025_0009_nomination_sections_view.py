"""candidacies: view nomination_sections (sections covered by each nomination, by level)

Used by the geographic-scope rules (D-34): a nomination is readable when it shares at least
one section with the user's scope and editable when all of its sections are in scope.
UNION ALL per level so each branch uses the matching index on geography.sections.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25
"""

from collections.abc import Sequence

from alembic import op

from migrations.helpers import app_role, execute_script, if_role_exists

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    execute_script(
        """
        CREATE VIEW candidacies.nomination_sections AS
          SELECT n.id AS nomination_id, s.id AS section_id
          FROM candidacies.nominations n
          JOIN geography.sections s ON s.municipality_id = n.municipality_id AND s.is_active
          WHERE n.geographic_level = 'municipality'
        UNION ALL
          SELECT n.id, s.id FROM candidacies.nominations n
          JOIN geography.sections s ON s.local_district_id = n.local_district_id AND s.is_active
          WHERE n.geographic_level = 'local_district'
        UNION ALL
          SELECT n.id, s.id FROM candidacies.nominations n
          JOIN geography.sections s ON s.federal_district_id = n.federal_district_id AND s.is_active
          WHERE n.geographic_level = 'federal_district'
        UNION ALL
          SELECT n.id, s.id FROM candidacies.nominations n
          JOIN geography.sections s ON s.state_id = n.state_id AND s.is_active
          WHERE n.geographic_level = 'state'
        UNION ALL
          SELECT n.id, s.id FROM candidacies.nominations n
          JOIN geography.states st ON st.electoral_region_id = n.electoral_region_id
          JOIN geography.sections s ON s.state_id = st.id AND s.is_active
          WHERE n.geographic_level = 'electoral_region'
        UNION ALL
          SELECT n.id, s.id FROM candidacies.nominations n
          JOIN candidacies.electoral_processes p ON p.id = n.process_id
          JOIN geography.sections s ON s.framework_id = p.framework_id AND s.is_active
          WHERE n.geographic_level = 'national';
        """
    )
    role = app_role()
    op.execute(if_role_exists(role, f"GRANT SELECT ON candidacies.nomination_sections TO {role};"))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS candidacies.nomination_sections")

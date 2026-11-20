from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audit_events') as batch:
        batch.alter_column('target_id', existing_type=sa.String(36), type_=sa.String(64))


def downgrade():
    with op.batch_alter_table('audit_events') as batch:
        batch.alter_column('target_id', existing_type=sa.String(64), type_=sa.String(36))

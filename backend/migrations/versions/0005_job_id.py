from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('calls', sa.Column('job_id', sa.String(36), nullable=True))


def downgrade():
    op.drop_column('calls', 'job_id')

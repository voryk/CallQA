from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    tables = sa.inspect(connection).get_table_names()
    if 'calls' not in tables:
        op.create_table(
            'calls',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('original_name', sa.String(255), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('size_bytes', sa.Integer, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
    columns = {c['name'] for c in sa.inspect(connection).get_columns('calls')}
    additions = [
        sa.Column('storage_name', sa.String(64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('transcript', sa.Text, nullable=True),
        sa.Column('segments', sa.JSON, nullable=True),
        sa.Column('language', sa.String(20), nullable=True),
        sa.Column('error', sa.String(500), nullable=True),
        sa.Column('operator_id', sa.String(64), nullable=True),
        sa.Column('assessment', sa.JSON, nullable=True),
        sa.Column('assessment_status', sa.String(20), nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column('calls', column)


def downgrade():
    op.drop_table('calls')

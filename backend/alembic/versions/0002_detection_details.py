"""store YOLO detection metadata"""
from alembic import op
import sqlalchemy as sa

revision = "0002_detection_details"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("predictions", sa.Column("detection_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("predictions", sa.Column("boxes_json", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("predictions", "boxes_json")
    op.drop_column("predictions", "detection_count")

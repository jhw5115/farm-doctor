"""initial inspection schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("inspection_batches", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("status", sa.String(24), nullable=False), sa.Column("total_count", sa.Integer(), nullable=False), sa.Column("completed_count", sa.Integer(), nullable=False), sa.Column("failed_count", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_inspection_batches_created_at", "inspection_batches", ["created_at"]); op.create_index("ix_inspection_batches_status", "inspection_batches", ["status"])
    op.create_table("inspection_images", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("inspection_batches.id", ondelete="CASCADE"), nullable=False), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("content_type", sa.String(100), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("object_key", sa.String(512), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("object_key"))
    op.create_index("ix_inspection_images_batch_id", "inspection_images", ["batch_id"]); op.create_index("ix_inspection_images_status", "inspection_images", ["status"])
    op.create_table("predictions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("image_id", sa.Integer(), sa.ForeignKey("inspection_images.id", ondelete="CASCADE"), nullable=False), sa.Column("class_code", sa.String(64), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("model_version", sa.String(128), nullable=False), sa.Column("predicted_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("image_id"))
    op.create_index("ix_predictions_class_code", "predictions", ["class_code"])
    op.create_table("model_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version", sa.String(128), nullable=False), sa.Column("model_path", sa.String(512), nullable=False), sa.Column("class_names", sa.Text(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("version"))

def downgrade():
    op.drop_table("model_versions"); op.drop_table("predictions"); op.drop_table("inspection_images"); op.drop_table("inspection_batches")

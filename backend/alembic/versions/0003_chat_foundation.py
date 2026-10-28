"""add chatbot persistence and knowledge document metadata"""

from alembic import op
import sqlalchemy as sa

revision = "0003_chat_foundation"
down_revision = "0002_detection_details"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_token", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_sessions_client_token", "chat_sessions", ["client_token"])
    op.create_index("ix_chat_sessions_created_at", "chat_sessions", ["created_at"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("file_key", sa.String(length=512), nullable=True),
        sa.Column("external_file_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_documents_is_active", "knowledge_documents", ["is_active"])


def downgrade():
    op.drop_table("knowledge_documents")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")

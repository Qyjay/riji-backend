"""add plaza and avatar tables

Revision ID: 831ee9e5cb90
Revises: a1c4f7d8e9b2
Create Date: 2026-04-14 18:09:14.606008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '831ee9e5cb90'
down_revision: Union[str, None] = 'a1c4f7d8e9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 广场帖子表 ──
    op.create_table(
        'plaza_posts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('images', sa.Text(), server_default='[]'),
        sa.Column('location', sa.String(), server_default=''),
        sa.Column('tags', sa.Text(), server_default='[]'),
        sa.Column('likes', sa.Integer(), server_default='0'),
        sa.Column('comments', sa.Integer(), server_default='0'),
        sa.Column('agent_responses', sa.Integer(), server_default='0'),
        sa.Column('is_from_agent', sa.Boolean(), server_default='0'),
        sa.Column('allow_agent_reply', sa.Boolean(), server_default='1'),
        sa.Column('school_only', sa.Boolean(), server_default='0'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_plaza_posts_type', 'plaza_posts', ['type'])
    op.create_index('ix_plaza_posts_user_id', 'plaza_posts', ['user_id'])

    # ── 帖子评论表 ──
    op.create_table(
        'plaza_comments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('post_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_agent', sa.Boolean(), server_default='0'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['post_id'], ['plaza_posts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_plaza_comments_post_id', 'plaza_comments', ['post_id'])

    # ── 点赞记录表 ──
    op.create_table(
        'post_likes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('post_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['post_id'], ['plaza_posts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),
    )

    # ── 分身记忆库表 ──
    op.create_table(
        'avatar_memories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), server_default='manual'),
        sa.Column('source_ref', sa.String(), server_default=''),
        sa.Column('confidence', sa.Float(), server_default='1.0'),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('is_pinned', sa.Boolean(), server_default='0'),
        sa.Column('need_type', sa.String(), nullable=True),
        sa.Column('urgency', sa.String(), nullable=True),
        sa.Column('expiry', sa.BigInteger(), nullable=True),
        sa.Column('match_status', sa.String(), nullable=True),
        sa.Column('tags', sa.Text(), server_default='[]'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_avatar_memories_user_category', 'avatar_memories', ['user_id', 'category'])

    # ── 分身状态表 ──
    op.create_table(
        'avatar_status',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('browsed_count', sa.Integer(), server_default='0'),
        sa.Column('matched_count', sa.Integer(), server_default='0'),
        sa.Column('chatting_count', sa.Integer(), server_default='0'),
        sa.Column('last_active_at', sa.BigInteger(), server_default='0'),
        sa.Column('enabled_channels', sa.Text(), server_default='["buddy","help","share","dating"]'),
        sa.Column('enabled_actions', sa.Text(), server_default='["browse","match","comment"]'),
        sa.Column('match_range', sa.Text(), server_default='{"school":"","distanceKm":10}'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id'),
    )

    # ── 分身推荐匹配表 ──
    op.create_table(
        'avatar_matches',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('post_id', sa.String(), nullable=False),
        sa.Column('match_score', sa.Integer(), server_default='0'),
        sa.Column('match_reasons', sa.Text(), server_default='[]'),
        sa.Column('agent_conversation', sa.Text(), server_default='[]'),
        sa.Column('status', sa.String(), server_default='new'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['post_id'], ['plaza_posts.id']),
    )
    op.create_index('ix_avatar_matches_user_id', 'avatar_matches', ['user_id'])
    op.create_index('ix_avatar_matches_status', 'avatar_matches', ['status'])

    # ── 分身侧写表 ──
    op.create_table(
        'avatar_profiles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('summary', sa.Text(), server_default=''),
        sa.Column('diary_count', sa.Integer(), server_default='0'),
        sa.Column('chat_count', sa.Integer(), server_default='0'),
        sa.Column('generated_at', sa.BigInteger(), server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('avatar_profiles')
    op.drop_index('ix_avatar_matches_status', 'avatar_matches')
    op.drop_index('ix_avatar_matches_user_id', 'avatar_matches')
    op.drop_table('avatar_matches')
    op.drop_table('avatar_status')
    op.drop_index('ix_avatar_memories_user_category', 'avatar_memories')
    op.drop_table('avatar_memories')
    op.drop_table('post_likes')
    op.drop_index('ix_plaza_comments_post_id', 'plaza_comments')
    op.drop_table('plaza_comments')
    op.drop_index('ix_plaza_posts_user_id', 'plaza_posts')
    op.drop_index('ix_plaza_posts_type', 'plaza_posts')
    op.drop_table('plaza_posts')

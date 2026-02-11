"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('subjects', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('name_ar', sa.String(128), unique=True), sa.Column('code', sa.String(32), unique=True), sa.Column('pdf_path', sa.String(255)), sa.Column('content_version', sa.Integer(), nullable=False, server_default='1'), sa.Column('created_at', sa.DateTime()))
    op.create_table('toc_items', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id')), sa.Column('parent_id', sa.Integer(), sa.ForeignKey('toc_items.id'), nullable=True), sa.Column('title', sa.String(512)), sa.Column('level', sa.Integer()), sa.Column('order_index', sa.Integer()), sa.Column('start_pdf_page', sa.Integer(), nullable=True), sa.Column('end_pdf_page', sa.Integer(), nullable=True), sa.Column('printed_page_start', sa.Integer(), nullable=True))
    op.create_table('chunks', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id')), sa.Column('toc_item_id', sa.Integer(), sa.ForeignKey('toc_items.id'), nullable=True), sa.Column('pdf_page_index', sa.Integer()), sa.Column('printed_page_number', sa.Integer(), nullable=True), sa.Column('content', sa.Text()))
    op.create_table('lesson_embeddings', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id')), sa.Column('toc_item_id', sa.Integer(), sa.ForeignKey('toc_items.id')), sa.Column('summary', sa.Text()), sa.Column('embedding', Vector(1536)))
    op.create_table('users', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('telegram_id', sa.Integer(), unique=True), sa.Column('username', sa.String(64), nullable=True), sa.Column('grade', sa.String(128), nullable=True), sa.Column('created_at', sa.DateTime()))
    op.create_table('user_sessions', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')), sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=True), sa.Column('toc_item_id', sa.Integer(), sa.ForeignKey('toc_items.id'), nullable=True), sa.Column('selected_range_start', sa.Integer(), nullable=True), sa.Column('selected_range_end', sa.Integer(), nullable=True))
    op.create_table('coupons', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('code', sa.String(64), unique=True), sa.Column('kind', sa.String(32)), sa.Column('subject_code', sa.String(32), nullable=True), sa.Column('is_used', sa.Boolean(), server_default=sa.text('false')), sa.Column('expires_at', sa.DateTime(), nullable=True))
    op.create_table('redemptions', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('coupon_id', sa.Integer(), sa.ForeignKey('coupons.id')), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')), sa.Column('redeemed_at', sa.DateTime()))
    op.create_table('subscriptions', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), unique=True), sa.Column('active', sa.Boolean(), server_default=sa.text('true')))
    op.create_table('subject_unlocks', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')), sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id')), sa.UniqueConstraint('user_id', 'subject_id', name='uq_user_subject_unlock'))
    op.create_table('event_logs', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True), sa.Column('event_type', sa.String(64)), sa.Column('payload', sa.Text()), sa.Column('created_at', sa.DateTime()))
    op.create_table('rate_limit_buckets', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer()), sa.Column('bucket', sa.String(32)), sa.Column('window_start', sa.DateTime()), sa.Column('count', sa.Integer()))
    op.create_table('cache_entries', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('cache_key', sa.String(512), unique=True), sa.Column('value', sa.Text()), sa.Column('expires_at', sa.DateTime()))

def downgrade() -> None:
    for t in ['cache_entries','rate_limit_buckets','event_logs','subject_unlocks','subscriptions','redemptions','coupons','user_sessions','users','lesson_embeddings','chunks','toc_items','subjects']:
        op.drop_table(t)

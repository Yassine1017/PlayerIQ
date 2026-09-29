"""Initial private-schema ingestion and future-feature tables.

Supabase owns auth.users. RLS starts deny-by-default; access policies follow
when authenticated database operations are implemented.
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE SCHEMA IF NOT EXISTS playeriq
        """
    )
    op.execute(
        """
        REVOKE ALL ON SCHEMA playeriq FROM PUBLIC
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.players (
            owner_user_id UUID NOT NULL,
            display_name VARCHAR(160) NOT NULL,
            archived_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_players PRIMARY KEY (id),
            CONSTRAINT uq_players_owner_user_id UNIQUE (owner_user_id),
            CONSTRAINT fk_players_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES auth.users (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.players ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.profiles (
            user_id UUID NOT NULL,
            display_name VARCHAR(160) NOT NULL,
            timezone VARCHAR(80) NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_profiles PRIMARY KEY (user_id),
            CONSTRAINT fk_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES auth.users (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.profiles ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.report_uploads (
            uploaded_by_user_id UUID NOT NULL,
            storage_key TEXT NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            byte_size BIGINT NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            status VARCHAR(24) NOT NULL,
            parser_key VARCHAR(100),
            parser_version VARCHAR(40),
            error_code VARCHAR(100),
            processed_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_report_uploads PRIMARY KEY (id),
            CONSTRAINT ck_report_uploads_byte_size_nonnegative CHECK (byte_size >= 0),
            CONSTRAINT ck_report_uploads_status CHECK (status IN ('received','queued','extracting','validating','awaiting_link','rejected','failed_retryable','deleted')),
            CONSTRAINT fk_report_uploads_uploaded_by_user_id_users FOREIGN KEY(uploaded_by_user_id) REFERENCES auth.users (id),
            CONSTRAINT uq_report_uploads_storage_key UNIQUE (storage_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_report_uploads_uploader_created ON playeriq.report_uploads (uploaded_by_user_id, created_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_report_upload_active_hash ON playeriq.report_uploads (uploaded_by_user_id, sha256) WHERE status <> 'deleted'
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.report_uploads ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.activity_reports (
            report_upload_id UUID NOT NULL,
            report_kind VARCHAR(40) NOT NULL,
            source_activity_id VARCHAR(120),
            source_title VARCHAR(255) NOT NULL,
            source_team_name VARCHAR(160),
            source_venue_name VARCHAR(160),
            reported_local_datetime TIMESTAMP WITHOUT TIME ZONE,
            timezone VARCHAR(80),
            activity_total_time_s INTEGER,
            reported_athlete_count INTEGER,
            CONSTRAINT pk_activity_reports PRIMARY KEY (report_upload_id),
            CONSTRAINT ck_activity_reports_duration_nonnegative CHECK (activity_total_time_s IS NULL OR activity_total_time_s >= 0),
            CONSTRAINT ck_activity_reports_athlete_count_nonnegative CHECK (reported_athlete_count IS NULL OR reported_athlete_count >= 0),
            CONSTRAINT fk_activity_reports_report_upload_id_report_uploads FOREIGN KEY(report_upload_id) REFERENCES playeriq.report_uploads (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.activity_reports ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.chat_threads (
            player_id UUID NOT NULL,
            created_by_user_id UUID NOT NULL,
            title VARCHAR(255),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_chat_threads PRIMARY KEY (id),
            CONSTRAINT fk_chat_threads_player_id_players FOREIGN KEY(player_id) REFERENCES playeriq.players (id),
            CONSTRAINT fk_chat_threads_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES auth.users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_chat_threads_player_creator ON playeriq.chat_threads (player_id, created_by_user_id)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.chat_threads ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.coach_invitations (
            player_id UUID NOT NULL,
            email_normalized VARCHAR(320) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            accepted_by_user_id UUID,
            status VARCHAR(20) NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_coach_invitations PRIMARY KEY (id),
            CONSTRAINT ck_coach_invitations_status CHECK (status IN ('pending','accepted','expired','revoked')),
            CONSTRAINT fk_coach_invitations_player_id_players FOREIGN KEY(player_id) REFERENCES playeriq.players (id),
            CONSTRAINT uq_coach_invitations_token_hash UNIQUE (token_hash),
            CONSTRAINT fk_coach_invitations_accepted_by_user_id_users FOREIGN KEY(accepted_by_user_id) REFERENCES auth.users (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_coach_invitation_pending_email ON playeriq.coach_invitations (player_id, email_normalized) WHERE status = 'pending'
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.coach_invitations ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.ingestion_jobs (
            upload_id UUID NOT NULL,
            status VARCHAR(24) NOT NULL,
            attempts INTEGER NOT NULL,
            next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            locked_at TIMESTAMP WITH TIME ZONE,
            last_error_code VARCHAR(100),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_ingestion_jobs PRIMARY KEY (id),
            CONSTRAINT ck_ingestion_jobs_attempts_nonnegative CHECK (attempts >= 0),
            CONSTRAINT uq_ingestion_jobs_upload_id UNIQUE (upload_id),
            CONSTRAINT fk_ingestion_jobs_upload_id_report_uploads FOREIGN KEY(upload_id) REFERENCES playeriq.report_uploads (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ingestion_jobs_due ON playeriq.ingestion_jobs (status, next_attempt_at)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.ingestion_jobs ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.report_periods (
            report_upload_id UUID NOT NULL,
            ordinal INTEGER NOT NULL,
            source_label VARCHAR(160) NOT NULL,
            start_local TIME WITHOUT TIME ZONE,
            duration_s INTEGER,
            reported_athlete_count INTEGER,
            id UUID NOT NULL,
            CONSTRAINT pk_report_periods PRIMARY KEY (id),
            CONSTRAINT uq_report_periods_report_upload_id UNIQUE (report_upload_id, ordinal),
            CONSTRAINT ck_report_periods_ordinal_positive CHECK (ordinal > 0),
            CONSTRAINT ck_report_periods_duration_nonnegative CHECK (duration_s IS NULL OR duration_s >= 0),
            CONSTRAINT fk_report_periods_report_upload_id_report_uploads FOREIGN KEY(report_upload_id) REFERENCES playeriq.report_uploads (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.report_periods ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.source_athlete_rows (
            report_upload_id UUID NOT NULL,
            row_ordinal INTEGER NOT NULL,
            source_name VARCHAR(255) NOT NULL,
            source_position_code VARCHAR(20),
            participation_state VARCHAR(20) NOT NULL,
            id UUID NOT NULL,
            CONSTRAINT pk_source_athlete_rows PRIMARY KEY (id),
            CONSTRAINT uq_source_athlete_rows_report_upload_id UNIQUE (report_upload_id, row_ordinal),
            CONSTRAINT ck_source_athlete_rows_row_ordinal_positive CHECK (row_ordinal > 0),
            CONSTRAINT ck_source_athlete_rows_participation_state CHECK (participation_state IN ('ready','zero_recorded','needs_review')),
            CONSTRAINT fk_source_athlete_rows_report_upload_id_report_uploads FOREIGN KEY(report_upload_id) REFERENCES playeriq.report_uploads (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.source_athlete_rows ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.player_coaches (
            player_id UUID NOT NULL,
            coach_user_id UUID NOT NULL,
            invitation_id UUID,
            granted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT pk_player_coaches PRIMARY KEY (player_id, coach_user_id),
            CONSTRAINT fk_player_coaches_player_id_players FOREIGN KEY(player_id) REFERENCES playeriq.players (id),
            CONSTRAINT fk_player_coaches_coach_user_id_users FOREIGN KEY(coach_user_id) REFERENCES auth.users (id),
            CONSTRAINT fk_player_coaches_invitation_id_coach_invitations FOREIGN KEY(invitation_id) REFERENCES playeriq.coach_invitations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_player_coaches_coach_player ON playeriq.player_coaches (coach_user_id, player_id)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.player_coaches ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.player_sessions (
            player_id UUID NOT NULL,
            source_athlete_row_id UUID NOT NULL,
            local_date DATE NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            athlete_duration_s INTEGER,
            session_type VARCHAR(20) NOT NULL,
            quality_state VARCHAR(16) NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_player_sessions PRIMARY KEY (id),
            CONSTRAINT ck_player_sessions_session_type CHECK (session_type IN ('training','match','unknown')),
            CONSTRAINT ck_player_sessions_quality_state CHECK (quality_state IN ('accepted','held')),
            CONSTRAINT fk_player_sessions_player_id_players FOREIGN KEY(player_id) REFERENCES playeriq.players (id),
            CONSTRAINT uq_player_sessions_source_athlete_row_id UNIQUE (source_athlete_row_id),
            CONSTRAINT fk_player_sessions_source_athlete_row_id_source_athlete_rows FOREIGN KEY(source_athlete_row_id) REFERENCES playeriq.source_athlete_rows (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_player_sessions_player_date ON playeriq.player_sessions (player_id, local_date, id)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.player_sessions ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.source_metric_observations (
            scope VARCHAR(12) NOT NULL,
            report_upload_id UUID,
            period_id UUID,
            athlete_row_id UUID,
            source_label VARCHAR(160) NOT NULL,
            raw_value VARCHAR(120),
            raw_unit VARCHAR(40),
            parsed_value NUMERIC(12, 3),
            source_locator VARCHAR(255) NOT NULL,
            parser_version VARCHAR(40) NOT NULL,
            quality_state VARCHAR(24) NOT NULL,
            id UUID NOT NULL,
            CONSTRAINT pk_source_metric_observations PRIMARY KEY (id),
            CONSTRAINT ck_source_metric_observations_one_scope_parent CHECK ((CASE WHEN report_upload_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN period_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN athlete_row_id IS NOT NULL THEN 1 ELSE 0 END) = 1),
            CONSTRAINT ck_source_metric_observations_scope_matches_parent CHECK ((scope = 'report' AND report_upload_id IS NOT NULL) OR (scope = 'period' AND period_id IS NOT NULL) OR (scope = 'athlete' AND athlete_row_id IS NOT NULL)),
            CONSTRAINT fk_source_metric_observations_report_upload_id_activity_reports FOREIGN KEY(report_upload_id) REFERENCES playeriq.activity_reports (report_upload_id),
            CONSTRAINT fk_source_metric_observations_period_id_report_periods FOREIGN KEY(period_id) REFERENCES playeriq.report_periods (id),
            CONSTRAINT fk_source_metric_observations_athlete_row_id_source_ath_e074 FOREIGN KEY(athlete_row_id) REFERENCES playeriq.source_athlete_rows (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_source_metric_athlete ON playeriq.source_metric_observations (athlete_row_id)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.source_metric_observations ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.ai_runs (
            player_id UUID NOT NULL,
            actor_user_id UUID NOT NULL,
            kind VARCHAR(30) NOT NULL,
            session_id UUID,
            message_id UUID,
            status VARCHAR(30) NOT NULL,
            model VARCHAR(100) NOT NULL,
            prompt_version VARCHAR(60) NOT NULL,
            data_fingerprint VARCHAR(64) NOT NULL,
            evidence_snapshot JSONB NOT NULL,
            response_json JSONB,
            input_tokens INTEGER,
            output_tokens INTEGER,
            error_code VARCHAR(100),
            completed_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_ai_runs PRIMARY KEY (id),
            CONSTRAINT fk_ai_runs_player_id_players FOREIGN KEY(player_id) REFERENCES playeriq.players (id),
            CONSTRAINT fk_ai_runs_actor_user_id_users FOREIGN KEY(actor_user_id) REFERENCES auth.users (id),
            CONSTRAINT fk_ai_runs_session_id_player_sessions FOREIGN KEY(session_id) REFERENCES playeriq.player_sessions (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ai_runs_player_created ON playeriq.ai_runs (player_id, created_at)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.ai_runs ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.session_metric_values (
            player_session_id UUID NOT NULL,
            metric_key VARCHAR(100) NOT NULL,
            value NUMERIC(12, 3) NOT NULL,
            unit VARCHAR(40) NOT NULL,
            source_observation_id UUID NOT NULL,
            definition_id VARCHAR(100),
            comparability_key VARCHAR(160) NOT NULL,
            quality_state VARCHAR(24) NOT NULL,
            CONSTRAINT pk_session_metric_values PRIMARY KEY (player_session_id, metric_key),
            CONSTRAINT ck_session_metric_values_value_nonnegative CHECK (value >= 0),
            CONSTRAINT fk_session_metric_values_player_session_id_player_sessions FOREIGN KEY(player_session_id) REFERENCES playeriq.player_sessions (id),
            CONSTRAINT fk_session_metric_values_source_observation_id_source_m_03a7 FOREIGN KEY(source_observation_id) REFERENCES playeriq.source_metric_observations (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.session_metric_values ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.ai_tool_calls (
            ai_run_id UUID NOT NULL,
            provider_call_id VARCHAR(160) NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            arguments_json JSONB NOT NULL,
            result_json JSONB,
            result_hash VARCHAR(64),
            status VARCHAR(30) NOT NULL,
            duration_ms INTEGER,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_ai_tool_calls PRIMARY KEY (id),
            CONSTRAINT uq_ai_tool_calls_ai_run_id UNIQUE (ai_run_id, provider_call_id),
            CONSTRAINT fk_ai_tool_calls_ai_run_id_ai_runs FOREIGN KEY(ai_run_id) REFERENCES playeriq.ai_runs (id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.ai_tool_calls ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE TABLE playeriq.chat_messages (
            thread_id UUID NOT NULL,
            role VARCHAR(16) NOT NULL,
            content_json JSONB NOT NULL,
            ai_run_id UUID,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_chat_messages PRIMARY KEY (id),
            CONSTRAINT ck_chat_messages_role CHECK (role IN ('user','assistant')),
            CONSTRAINT fk_chat_messages_thread_id_chat_threads FOREIGN KEY(thread_id) REFERENCES playeriq.chat_threads (id),
            CONSTRAINT fk_chat_messages_ai_run_id_ai_runs FOREIGN KEY(ai_run_id) REFERENCES playeriq.ai_runs (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_chat_messages_thread_created ON playeriq.chat_messages (thread_id, created_at, id)
        """
    )
    op.execute(
        """
        ALTER TABLE playeriq.chat_messages ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON ALL TABLES IN SCHEMA playeriq FROM PUBLIC
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE playeriq.chat_messages")
    op.execute("DROP TABLE playeriq.ai_tool_calls")
    op.execute("DROP TABLE playeriq.session_metric_values")
    op.execute("DROP TABLE playeriq.ai_runs")
    op.execute("DROP TABLE playeriq.source_metric_observations")
    op.execute("DROP TABLE playeriq.player_sessions")
    op.execute("DROP TABLE playeriq.player_coaches")
    op.execute("DROP TABLE playeriq.source_athlete_rows")
    op.execute("DROP TABLE playeriq.report_periods")
    op.execute("DROP TABLE playeriq.ingestion_jobs")
    op.execute("DROP TABLE playeriq.coach_invitations")
    op.execute("DROP TABLE playeriq.chat_threads")
    op.execute("DROP TABLE playeriq.activity_reports")
    op.execute("DROP TABLE playeriq.report_uploads")
    op.execute("DROP TABLE playeriq.profiles")
    op.execute("DROP TABLE playeriq.players")
    op.execute("DROP SCHEMA playeriq")

"""
Utility functions for Supabase storage operations
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from reflexio_commons.api_schema.service_schemas import (
    UserProfile,
    Interaction,
    Request,
    ProfileTimeToLive,
    UserActionType,
    ProfileChangeLog,
    RawFeedback,
    Feedback,
    FeedbackSnapshot,
    FeedbackUpdateEntry,
    FeedbackAggregationChangeLog,
    Skill,
    SkillStatus,
    AgentSuccessEvaluationResult,
    BlockingIssue,
    BlockingIssueKind,
    ToolUsed,
)
import psycopg2

logger = logging.getLogger(__name__)


def _parse_iso_timestamp(ts: str) -> int:
    """
    Parse an ISO 8601 timestamp string to a Unix timestamp int.

    Handles variable-precision fractional seconds from Postgres (e.g. 5-digit microseconds)
    that Python 3.10's datetime.fromisoformat() cannot parse.

    Args:
        ts: ISO 8601 timestamp string

    Returns:
        int: Unix timestamp
    """
    ts = ts.replace("Z", "+00:00")
    # Normalize fractional seconds to exactly 6 digits for Python 3.10 compat
    ts = re.sub(
        r"\.(\d+)",
        lambda m: "." + m.group(1)[:6].ljust(6, "0"),
        ts,
    )
    return int(datetime.fromisoformat(ts).timestamp())


def response_to_user_profile(item: dict[str, Any]) -> UserProfile:
    """
    Convert a response item from Supabase to a UserProfile object.

    Args:
        item: Dictionary containing profile data from Supabase response

    Returns:
        UserProfile object
    """
    from reflexio_commons.api_schema.service_schemas import Status

    return UserProfile(
        profile_id=item["profile_id"],
        user_id=item["user_id"],
        profile_content=item["content"],
        last_modified_timestamp=item["last_modified_timestamp"],
        generated_from_request_id=item["generated_from_request_id"],
        profile_time_to_live=ProfileTimeToLive(item["profile_time_to_live"]),
        expiration_timestamp=item["expiration_timestamp"],
        custom_features=item["custom_features"],
        source=item.get("source", ""),
        status=Status(item["status"]) if item.get("status") else None,
        extractor_names=item.get("extractor_names"),
    )


def response_to_interaction(item: dict[str, Any]) -> Interaction:
    """
    Convert a response item from Supabase to an Interaction object.

    Args:
        item: Dictionary containing interaction data from Supabase response

    Returns:
        Interaction object
    """
    # Deserialize tools_used from JSONB array
    tools_used = []
    tools_used_data = item.get("tools_used")
    if tools_used_data and isinstance(tools_used_data, list):
        tools_used = [ToolUsed(**t) for t in tools_used_data if isinstance(t, dict)]

    return Interaction(
        interaction_id=item["interaction_id"],
        user_id=item["user_id"],
        content=item["content"],
        request_id=item["request_id"],
        created_at=int(
            datetime.fromisoformat(
                item["created_at"].replace("Z", "+00:00")
            ).timestamp()
        ),
        role=item.get("role", "User"),
        user_action=UserActionType(item["user_action"]),
        user_action_description=item["user_action_description"],
        interacted_image_url=item["interacted_image_url"],
        shadow_content=item.get("shadow_content") or "",
        tools_used=tools_used,
    )


def user_profile_to_data(profile: UserProfile) -> dict[str, Any]:
    """
    Convert a UserProfile object to data for upserting into Supabase.

    Args:
        profile: UserProfile object to convert
        embedding: Vector embedding for the profile content

    Returns:
        Dictionary containing data ready for upsert
    """
    return {
        "profile_id": profile.profile_id,
        "user_id": profile.user_id,
        "content": profile.profile_content,
        "last_modified_timestamp": profile.last_modified_timestamp,
        "generated_from_request_id": profile.generated_from_request_id,
        "profile_time_to_live": profile.profile_time_to_live.value,
        "expiration_timestamp": profile.expiration_timestamp,
        "custom_features": profile.custom_features,
        "embedding": profile.embedding,
        "source": profile.source,
        "status": profile.status.value if profile.status else None,
        "extractor_names": profile.extractor_names,
    }


def interaction_to_data(interaction: Interaction) -> dict[str, Any]:
    """
    Convert an Interaction object to data for upserting into Supabase.

    Args:
        interaction: Interaction object to convert
        embedding: Vector embedding for the interaction content

    Returns:
        Dictionary containing data ready for upsert
    """
    data = {
        "user_id": interaction.user_id,
        "content": interaction.content,
        "request_id": interaction.request_id,
        "created_at": datetime.fromtimestamp(
            interaction.created_at, tz=timezone.utc
        ).isoformat(),
        "role": interaction.role,
        "user_action": interaction.user_action.value,
        "user_action_description": interaction.user_action_description,
        "interacted_image_url": interaction.interacted_image_url,
        "shadow_content": interaction.shadow_content,
        "tools_used": [t.model_dump() for t in interaction.tools_used],
        "embedding": interaction.embedding,
    }
    # Only include interaction_id if it's set (non-zero), otherwise let DB auto-generate
    if interaction.interaction_id:
        data["interaction_id"] = interaction.interaction_id
    return data


def response_to_request(item: dict[str, Any]) -> Request:
    """
    Convert a response item from Supabase to a Request object.

    Args:
        item: Dictionary containing request data from Supabase response

    Returns:
        Request object
    """
    return Request(
        request_id=item["request_id"],
        user_id=item["user_id"],
        created_at=int(
            datetime.fromisoformat(
                item["created_at"].replace("Z", "+00:00")
            ).timestamp()
        ),
        source=item.get("source", ""),
        agent_version=item.get("agent_version", ""),
        request_group=item.get("request_group"),
    )


def request_to_data(request: Request) -> dict[str, Any]:
    """
    Convert a Request object to data for upserting into Supabase.

    Args:
        request: Request object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    return {
        "request_id": request.request_id,
        "user_id": request.user_id,
        "created_at": datetime.fromtimestamp(
            request.created_at, tz=timezone.utc
        ).isoformat(),
        "source": request.source,
        "agent_version": request.agent_version,
        "request_group": request.request_group or None,
    }


def response_list_to_user_profiles(
    response_data: list[dict[str, Any]],
) -> list[UserProfile]:
    """
    Convert a list of response items to UserProfile objects.

    Args:
        response_data: List of dictionaries containing profile data from Supabase response

    Returns:
        List of UserProfile objects
    """
    return [response_to_user_profile(item) for item in response_data]


def response_list_to_interactions(
    response_data: list[dict[str, Any]],
) -> list[Interaction]:
    """
    Convert a list of response items to Interaction objects.

    Args:
        response_data: List of dictionaries containing interaction data from Supabase response

    Returns:
        List of Interaction objects
    """
    return [response_to_interaction(item) for item in response_data]


def response_list_to_requests(response_data: list[dict[str, Any]]) -> list[Request]:
    """
    Convert a list of response items to Request objects.

    Args:
        response_data: List of dictionaries containing request data from Supabase response

    Returns:
        List of Request objects
    """
    return [response_to_request(item) for item in response_data]


def response_to_profile_change_log(item: dict[str, Any]) -> ProfileChangeLog:
    """
    Convert a response item from Supabase to a ProfileChangeLog object.

    Args:
        item: Dictionary containing profile change log data from Supabase response

    Returns:
        ProfileChangeLog object
    """
    return ProfileChangeLog(
        id=item["id"],
        user_id=item["user_id"],
        request_id=item["request_id"],
        created_at=item["created_at"],  # Already an integer timestamp
        added_profiles=[UserProfile(**profile) for profile in item["added_profiles"]],
        removed_profiles=[
            UserProfile(**profile) for profile in item["removed_profiles"]
        ],
        mentioned_profiles=[
            UserProfile(**profile) for profile in item["mentioned_profiles"]
        ],
    )


def profile_change_log_to_data(profile_change_log: ProfileChangeLog) -> dict[str, Any]:
    """
    Convert a ProfileChangeLog object to data for upserting into Supabase.

    Args:
        profile_change_log: ProfileChangeLog object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    # skip id as it is auto generated by supabase
    return {
        "user_id": profile_change_log.user_id,
        "request_id": profile_change_log.request_id,
        "created_at": profile_change_log.created_at,
        "added_profiles": [
            profile.model_dump() for profile in profile_change_log.added_profiles
        ],
        "removed_profiles": [
            profile.model_dump() for profile in profile_change_log.removed_profiles
        ],
        "mentioned_profiles": [
            profile.model_dump() for profile in profile_change_log.mentioned_profiles
        ],
    }


def response_list_to_profile_change_logs(
    response_data: list[dict[str, Any]],
) -> list[ProfileChangeLog]:
    """
    Convert a list of response items to ProfileChangeLog objects.

    Args:
        response_data: List of dictionaries containing profile change log data from Supabase response

    Returns:
        List of ProfileChangeLog objects
    """
    return [response_to_profile_change_log(item) for item in response_data]


def feedback_aggregation_change_log_to_data(
    change_log: FeedbackAggregationChangeLog,
) -> dict[str, Any]:
    """Convert a FeedbackAggregationChangeLog to data for upserting into Supabase.

    Args:
        change_log: FeedbackAggregationChangeLog object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    # skip id as it is auto generated by supabase
    return {
        "created_at": change_log.created_at,
        "feedback_name": change_log.feedback_name,
        "agent_version": change_log.agent_version,
        "run_mode": change_log.run_mode,
        "added_feedbacks": [fb.model_dump() for fb in change_log.added_feedbacks],
        "removed_feedbacks": [fb.model_dump() for fb in change_log.removed_feedbacks],
        "updated_feedbacks": [
            {"before": entry.before.model_dump(), "after": entry.after.model_dump()}
            for entry in change_log.updated_feedbacks
        ],
    }


def response_to_feedback_aggregation_change_log(
    item: dict[str, Any],
) -> FeedbackAggregationChangeLog:
    """Convert a response item from Supabase to a FeedbackAggregationChangeLog object.

    Args:
        item: Dictionary containing change log data from Supabase response

    Returns:
        FeedbackAggregationChangeLog object
    """
    return FeedbackAggregationChangeLog(
        id=item["id"],
        created_at=item["created_at"],
        feedback_name=item["feedback_name"],
        agent_version=item["agent_version"],
        run_mode=item["run_mode"],
        added_feedbacks=[
            FeedbackSnapshot(**fb) for fb in (item.get("added_feedbacks") or [])
        ],
        removed_feedbacks=[
            FeedbackSnapshot(**fb) for fb in (item.get("removed_feedbacks") or [])
        ],
        updated_feedbacks=[
            FeedbackUpdateEntry(
                before=FeedbackSnapshot(**entry["before"]),
                after=FeedbackSnapshot(**entry["after"]),
            )
            for entry in (item.get("updated_feedbacks") or [])
        ],
    )


def response_list_to_feedback_aggregation_change_logs(
    response_data: list[dict[str, Any]],
) -> list[FeedbackAggregationChangeLog]:
    """Convert a list of response items to FeedbackAggregationChangeLog objects.

    Args:
        response_data: List of dictionaries from Supabase response

    Returns:
        List of FeedbackAggregationChangeLog objects
    """
    return [response_to_feedback_aggregation_change_log(item) for item in response_data]


def raw_feedback_to_data(raw_feedback: RawFeedback) -> dict[str, Any]:
    """
    Convert a RawFeedback object to data for upserting into Supabase.

    Args:
        raw_feedback: RawFeedback object to convert
        embedding: Vector embedding for the feedback content

    Returns:
        Dictionary containing data ready for upsert
    """
    # skip id as it is auto generated by supabase
    return {
        "user_id": raw_feedback.user_id,
        "feedback_name": raw_feedback.feedback_name,
        "created_at": datetime.fromtimestamp(
            raw_feedback.created_at, tz=timezone.utc
        ).isoformat(),
        "request_id": raw_feedback.request_id,
        "agent_version": raw_feedback.agent_version,
        "feedback_content": raw_feedback.feedback_content,
        "do_action": raw_feedback.do_action,
        "do_not_action": raw_feedback.do_not_action,
        "when_condition": raw_feedback.when_condition,
        "blocking_issue": (
            raw_feedback.blocking_issue.model_dump()
            if raw_feedback.blocking_issue
            else None
        ),
        "indexed_content": raw_feedback.indexed_content,
        "source_interaction_ids": raw_feedback.source_interaction_ids or None,
        "status": raw_feedback.status,
        "source": raw_feedback.source,
        "embedding": raw_feedback.embedding,
    }


def feedback_to_data(feedback: Feedback) -> dict[str, Any]:
    """
    Convert a Feedback object to data for upserting into Supabase.

    Args:
        feedback: Feedback object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    # skip feedback_id as it is auto generated by supabase
    return {
        "feedback_name": feedback.feedback_name,
        "feedback_content": feedback.feedback_content,
        "do_action": feedback.do_action,
        "do_not_action": feedback.do_not_action,
        "when_condition": feedback.when_condition,
        "blocking_issue": (
            feedback.blocking_issue.model_dump() if feedback.blocking_issue else None
        ),
        "feedback_status": feedback.feedback_status,
        "agent_version": feedback.agent_version,
        "feedback_metadata": feedback.feedback_metadata,
        "embedding": feedback.embedding,
        "status": feedback.status,
    }


def agent_success_evaluation_result_to_data(
    result: AgentSuccessEvaluationResult,
) -> dict[str, Any]:
    """
    Convert an AgentSuccessEvaluationResult object to data for upserting into Supabase.

    Args:
        result: AgentSuccessEvaluationResult object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    # skip result_id as it is auto generated by supabase
    return {
        "request_id": result.request_id,
        "agent_version": result.agent_version,
        "evaluation_name": result.evaluation_name,
        "is_success": result.is_success,
        "failure_type": result.failure_type,
        "failure_reason": result.failure_reason,
        "agent_prompt_update": result.agent_prompt_update,
        "regular_vs_shadow": (
            result.regular_vs_shadow.value if result.regular_vs_shadow else None
        ),
        "embedding": result.embedding if len(result.embedding) > 0 else None,
    }


def skill_to_data(skill: Skill) -> dict[str, Any]:
    """
    Convert a Skill object to data for upserting into Supabase.

    Args:
        skill: Skill object to convert

    Returns:
        Dictionary containing data ready for upsert
    """
    data = {
        "skill_name": skill.skill_name,
        "description": skill.description,
        "version": skill.version,
        "agent_version": skill.agent_version,
        "feedback_name": skill.feedback_name,
        "instructions": skill.instructions,
        "allowed_tools": skill.allowed_tools,
        "blocking_issues": [bi.model_dump() for bi in skill.blocking_issues],
        "raw_feedback_ids": skill.raw_feedback_ids,
        "skill_status": skill.skill_status.value if skill.skill_status else "draft",
        "embedding": skill.embedding if len(skill.embedding) > 0 else None,
        "updated_at": datetime.fromtimestamp(
            skill.updated_at, tz=timezone.utc
        ).isoformat(),
    }
    # Only include skill_id if it's set (non-zero), otherwise let DB auto-generate
    if skill.skill_id:
        data["skill_id"] = skill.skill_id
    return data


def response_to_skill(item: dict[str, Any]) -> Skill:
    """
    Convert a response item from Supabase to a Skill object.

    Args:
        item: Dictionary containing skill data from Supabase response

    Returns:
        Skill object
    """
    # Parse blocking_issues from JSONB
    blocking_issues = []
    blocking_issues_data = item.get("blocking_issues")
    if blocking_issues_data and isinstance(blocking_issues_data, list):
        for bi in blocking_issues_data:
            if isinstance(bi, dict):
                blocking_issues.append(
                    BlockingIssue(
                        kind=BlockingIssueKind(bi["kind"]),
                        details=bi.get("details", ""),
                    )
                )

    # Parse created_at timestamp
    created_at = item.get("created_at")
    if isinstance(created_at, str):
        created_at = _parse_iso_timestamp(created_at)
    elif created_at is None:
        created_at = 0

    # Parse updated_at timestamp
    updated_at = item.get("updated_at")
    if isinstance(updated_at, str):
        updated_at = _parse_iso_timestamp(updated_at)
    elif updated_at is None:
        updated_at = 0

    return Skill(
        skill_id=item.get("skill_id", 0),
        skill_name=item.get("skill_name", ""),
        description=item.get("description", ""),
        version=item.get("version", "1.0.0"),
        agent_version=item.get("agent_version", ""),
        feedback_name=item.get("feedback_name", ""),
        instructions=item.get("instructions", ""),
        allowed_tools=item.get("allowed_tools") or [],
        blocking_issues=blocking_issues,
        raw_feedback_ids=item.get("raw_feedback_ids") or [],
        skill_status=(
            SkillStatus(item["skill_status"])
            if item.get("skill_status")
            else SkillStatus.DRAFT
        ),
        created_at=created_at,
        updated_at=updated_at,
    )


def is_localhost_url(db_url: str) -> bool:
    """
    Check if the database URL points to localhost.

    Args:
        db_url: Database connection URL

    Returns:
        bool: True if the URL is localhost, False otherwise
    """
    try:
        parsed = urlparse(db_url)
        host = parsed.hostname or ""
        return host in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def get_latest_migration_version() -> Optional[str]:
    """
    Get the version prefix of the latest migration file on disk.

    Returns:
        str | None: The version string of the latest migration, or None if no migrations found
    """
    import os
    import glob
    from pathlib import Path
    import reflexio

    migration_dir = (
        Path(os.path.dirname(reflexio.__file__)).parent / "supabase" / "migrations"
    )
    migration_files = sorted(glob.glob(os.path.join(migration_dir, "*.sql")))
    if not migration_files:
        return None

    filename = os.path.basename(migration_files[-1])
    return filename.split("_")[0]


def check_migration_needed(db_url: str) -> bool:
    """
    Quick check whether the latest migration has been applied to the given database.

    Connects with a short timeout, queries the schema_migrations table, and returns
    True if the latest migration version is NOT present (i.e. migration is needed).
    Returns False on any error (fail-safe: skip migration on uncertainty).

    Args:
        db_url: PostgreSQL connection string

    Returns:
        bool: True if migration is needed, False if up-to-date or on error
    """
    latest_version = get_latest_migration_version()
    if not latest_version:
        return False

    conn = None
    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM supabase_migrations.schema_migrations WHERE version = %s",
            (latest_version,),
        )
        row = cursor.fetchone()
        cursor.close()
        return row is None
    except Exception as e:
        logger.debug(f"check_migration_needed failed for {db_url}: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def extract_db_url_from_config_json(config_json_str: str) -> Optional[str]:
    """
    Parse a (already-decrypted) config JSON string and extract the database URL.

    Args:
        config_json_str: Decrypted JSON configuration string

    Returns:
        str | None: The db_url from storage_config, or None if not found
    """
    try:
        config_data = json.loads(str(config_json_str))
        storage_config = config_data.get("storage_config")
        if storage_config and "db_url" in storage_config:
            db_url = storage_config["db_url"]
            return db_url if db_url else None
        return None
    except Exception as e:
        logger.debug(f"extract_db_url_from_config_json failed: {e}")
        return None


def execute_sql_file_direct(db_url: str, file_path: str) -> list[Any]:
    """
    Execute SQL file using direct database connection
    Requires database URL with proper credentials

    Args:
        file_path: Path to the SQL file
    """
    if not db_url:
        raise ValueError("Database URL is required for direct execution")

    try:
        # Connect directly to PostgreSQL
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        # Read and execute SQL file
        with open(file_path, encoding="utf-8") as file:
            sql_content = file.read()

        # Execute the SQL (split by semicolons for multiple statements)
        statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

        results = []
        for statement in statements:
            cursor.execute(statement)
            try:
                # Try to fetch results (for SELECT statements)
                result = cursor.fetchall()
                results.append(result)
            except psycopg2.ProgrammingError:
                # No results to fetch (INSERT, UPDATE, DELETE, etc.)
                results.append(f"Executed: {statement[:50]}...")

        conn.commit()
        cursor.close()
        conn.close()

        return results

    except Exception as e:
        print(f"Error executing SQL file: {e}")
        if "conn" in locals():
            conn.rollback()
            conn.close()
        raise e


def execute_migration(db_url: str) -> tuple[bool, str]:
    """
    This routine pushes the current migration onto the remote db.

    Args:
        db_url (str): PostgreSQL connection string (use pooler URL with port 6543 for IPv4 support)

    Returns:
        tuple[bool, str]: (success, message)
    """
    import os
    import glob
    from pathlib import Path
    import reflexio
    from reflexio.server.services.storage.supabase_migrations import DATA_MIGRATIONS

    try:
        # Get migration files
        migration_dir = (
            Path(os.path.dirname(reflexio.__file__)).parent / "supabase" / "migrations"
        )
        migration_files = sorted(glob.glob(os.path.join(migration_dir, "*.sql")))
        if not migration_files:
            return False, "No migration files found"

        # Connect to database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        # Create schema and migrations table if they don't exist
        cursor.execute("CREATE SCHEMA IF NOT EXISTS supabase_migrations;")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations (
                version text PRIMARY KEY,
                statements text[],
                name text,
                applied_at timestamptz DEFAULT now()
            );
        """
        )

        executed_migrations = []

        for migration_file in migration_files:
            # Extract version from filename
            filename = os.path.basename(migration_file)
            version = filename.split("_")[0]

            # Check if migration already executed
            cursor.execute(
                "SELECT version FROM supabase_migrations.schema_migrations WHERE version = %s",
                (version,),
            )

            if cursor.fetchone() is None:
                # Read and execute migration
                with open(migration_file, encoding="utf-8") as f:
                    migration_sql = f.read()

                try:
                    # Execute migration
                    cursor.execute(migration_sql)

                    # Split SQL into individual statements for tracking
                    statements = [
                        s.strip() for s in migration_sql.split(";") if s.strip()
                    ]

                    # Record migration with statements
                    cursor.execute(
                        "INSERT INTO supabase_migrations.schema_migrations (version, statements, name) VALUES (%s, %s, %s)",
                        (version, statements, filename),
                    )

                    # Run data migration if one exists for this version
                    if version in DATA_MIGRATIONS:
                        DATA_MIGRATIONS[version](conn, cursor)

                    executed_migrations.append(filename)
                except Exception as e:
                    conn.rollback()
                    return False, f"Failed to execute {filename}: {str(e)}"

        conn.commit()
        cursor.close()
        conn.close()

        if executed_migrations:
            return True, f"Executed migrations: {', '.join(executed_migrations)}"
        else:
            return True, "All migrations already applied"

    except psycopg2.OperationalError as e:
        error_msg = str(e)
        if (
            "could not translate host name" in error_msg
            or "Name or service not known" in error_msg
        ):
            return (
                False,
                f"DNS resolution failed. Try using the pooler URL (port 6543) for IPv4 support. Error: {error_msg}",
            )
        elif "connection refused" in error_msg.lower():
            return (
                False,
                f"Connection refused. Check if your IP is allowed in Supabase network settings. Error: {error_msg}",
            )
        else:
            return False, f"Database connection error: {error_msg}"
    except Exception as e:
        return False, str(e)


def get_organization_config(client, org_id: str) -> str | None:
    """
    Get the configuration_json for an organization from Supabase.

    Args:
        client: Supabase client
        org_id: Organization ID

    Returns:
        str | None: The encrypted configuration JSON string, or None if not found
    """
    response = (
        client.table("organizations")
        .select("configuration_json")
        .eq("id", org_id)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        return None

    return response.data[0].get("configuration_json")


def set_organization_config(client, org_id: str, config_json: str) -> bool:
    """
    Set the configuration_json for an organization in Supabase.

    Args:
        client: Supabase client
        org_id: Organization ID
        config_json: The encrypted configuration JSON string

    Returns:
        bool: True if successful, False otherwise
    """
    # First check if org exists
    response = client.table("organizations").select("id").eq("id", org_id).execute()

    if not response.data or len(response.data) == 0:
        return False

    # Update the organization's configuration
    client.table("organizations").update({"configuration_json": config_json}).eq(
        "id", org_id
    ).execute()

    return True

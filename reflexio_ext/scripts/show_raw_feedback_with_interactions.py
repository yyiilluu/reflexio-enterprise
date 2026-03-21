"""
Script to display raw feedback content alongside the last 10 interactions
that were used to generate each raw feedback.

Usage:
    python scripts/show_raw_feedback_with_interactions.py [--limit N] [--user-id USER_ID] [--feedback-id ID]

Required environment variables:
    SUPABASE_DB_HOST, SUPABASE_DB_USER, SUPABASE_DB_PASSWORD
Optional:
    SUPABASE_DB_PORT (default: 6543), SUPABASE_DB_NAME (default: postgres)
"""

import argparse
import json
import os
import textwrap

import psycopg2
import psycopg2.extras

INTERACTIONS_WINDOW = 10


def get_db_config() -> dict:
    """Build database config from environment variables."""
    db_config = {
        "host": os.getenv("SUPABASE_DB_HOST"),
        "port": int(os.getenv("SUPABASE_DB_PORT", "6543")),
        "dbname": os.getenv("SUPABASE_DB_NAME", "postgres"),
        "user": os.getenv("SUPABASE_DB_USER"),
        "password": os.getenv("SUPABASE_DB_PASSWORD"),
    }

    missing = [key for key in ["host", "user", "password"] if not db_config[key]]
    if missing:
        missing_envs = ", ".join(f"SUPABASE_DB_{name.upper()}" for name in missing)
        raise ValueError(f"Missing required environment variables: {missing_envs}")

    return db_config


def get_raw_feedbacks(cursor, limit: int, user_id: str | None, feedback_id: int | None):
    """Fetch raw feedbacks with their associated request info."""
    query = """
        SELECT
            rf.raw_feedback_id,
            rf.created_at AS feedback_created_at,
            rf.request_id,
            rf.agent_version,
            rf.feedback_content,
            rf.feedback_name,
            rf.source AS feedback_source,
            rf.user_id AS feedback_user_id,
            rf.do_action,
            rf.do_not_action,
            rf.when_condition,
            rf.blocking_issue,
            rf.status,
            r.created_at AS request_created_at,
            r.user_id AS request_user_id,
            r.source AS request_source
        FROM raw_feedbacks rf
        LEFT JOIN requests r ON rf.request_id = r.request_id
        WHERE 1=1
    """
    params: list = []

    if user_id:
        query += " AND (rf.user_id = %s OR r.user_id = %s)"
        params.extend([user_id, user_id])

    if feedback_id:
        query += " AND rf.raw_feedback_id = %s"
        params.append(feedback_id)

    query += " ORDER BY rf.created_at DESC LIMIT %s"
    params.append(limit)

    cursor.execute(query, params)
    return cursor.fetchall()


def get_interactions_before(
    cursor, user_id: str, before_timestamp, limit: int = INTERACTIONS_WINDOW
):
    """
    Fetch the last N interactions for a user before a given timestamp.
    These are the interactions that were used to generate the raw feedback.
    """
    query = """
        SELECT
            i.interaction_id,
            i.user_id,
            i.content,
            i.shadow_content,
            i.role,
            i.request_id,
            i.user_action,
            i.user_action_description,
            i.created_at,
            i.tools_used,
            r.source,
            r.agent_version
        FROM interactions i
        LEFT JOIN requests r ON i.request_id = r.request_id
        WHERE i.user_id = %s
          AND i.created_at <= %s
        ORDER BY i.created_at DESC
        LIMIT %s
    """
    cursor.execute(query, [user_id, before_timestamp, limit])
    return cursor.fetchall()


def truncate_text(text: str | None, max_len: int = 200) -> str:
    if not text:
        return "(empty)"
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def format_json(obj) -> str:
    if obj is None:
        return "(none)"
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            return obj
    return json.dumps(obj, indent=2, ensure_ascii=False)


def print_separator(char: str = "=", width: int = 100):
    print(char * width)


def main():
    parser = argparse.ArgumentParser(
        description="Show raw feedbacks with their source interactions"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of raw feedbacks to show (default: 5)",
    )
    parser.add_argument("--user-id", type=str, default=None, help="Filter by user ID")
    parser.add_argument(
        "--feedback-id",
        type=int,
        default=None,
        help="Show a specific raw feedback by ID",
    )
    parser.add_argument(
        "--full", action="store_true", help="Show full content without truncation"
    )
    args = parser.parse_args()

    max_content_len = 10000 if args.full else 1000

    conn = psycopg2.connect(**get_db_config())
    conn.set_client_encoding("UTF8")
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    feedbacks = get_raw_feedbacks(cursor, args.limit, args.user_id, args.feedback_id)

    if not feedbacks:
        print("No raw feedbacks found.")
        return

    print(f"\nFound {len(feedbacks)} raw feedback(s)\n")

    for idx, fb in enumerate(feedbacks):
        print_separator("=")
        print(f"RAW FEEDBACK #{idx + 1}  (ID: {fb['raw_feedback_id']})")
        print_separator("=")
        print(f"  Feedback Name:    {fb['feedback_name'] or '(none)'}")
        print(f"  Created At:       {fb['feedback_created_at']}")
        print(f"  Request ID:       {fb['request_id']}")
        print(
            f"  User ID:          {fb['feedback_user_id'] or fb['request_user_id'] or '(unknown)'}"
        )
        print(f"  Agent Version:    {fb['agent_version'] or '(none)'}")
        print(
            f"  Source:           {fb['feedback_source'] or fb['request_source'] or '(none)'}"
        )
        print(f"  Status:           {fb['status'] or '(none)'}")

        print("\n  --- Feedback Content ---")
        content = fb["feedback_content"] or "(empty)"
        if args.full:
            print(textwrap.indent(content, "    "))
        else:
            print(f"    {truncate_text(content, max_content_len)}")

        if fb["do_action"] or fb["do_not_action"] or fb["when_condition"]:
            print("\n  --- Structured Fields ---")
            print(f"    DO:       {truncate_text(fb['do_action'], max_content_len)}")
            print(
                f"    DON'T:    {truncate_text(fb['do_not_action'], max_content_len)}"
            )
            print(
                f"    WHEN:     {truncate_text(fb['when_condition'], max_content_len)}"
            )

        if fb["blocking_issue"]:
            print("\n  --- Blocking Issue ---")
            print(f"    {format_json(fb['blocking_issue'])}")

        # Now get the interactions used to generate this feedback
        user_id = fb["feedback_user_id"] or fb["request_user_id"]
        request_created_at = fb["request_created_at"] or fb["feedback_created_at"]

        if not user_id:
            print("\n  (Cannot fetch interactions: no user_id available)")
            continue

        interactions = get_interactions_before(cursor, user_id, request_created_at)

        print(
            f"\n  --- Last {INTERACTIONS_WINDOW} Interactions (used for generation) ---"
        )
        if not interactions:
            print("    (no interactions found)")
        else:
            # Print in chronological order (oldest first)
            for i_idx, inter in enumerate(reversed(interactions)):
                print(f"\n    [{i_idx + 1}] Interaction ID: {inter['interaction_id']}")
                print(f"        Role:         {inter['role'] or '(none)'}")
                print(f"        Created At:   {inter['created_at']}")
                print(f"        Request ID:   {inter['request_id']}")
                print(f"        User Action:  {inter['user_action']}")
                if inter["user_action_description"]:
                    print(
                        f"        Action Desc:  {truncate_text(inter['user_action_description'], max_content_len)}"
                    )
                print(f"        Source:        {inter['source'] or '(none)'}")
                print(f"        Agent Version: {inter['agent_version'] or '(none)'}")
                if inter["tools_used"] and inter["tools_used"] != []:
                    print(f"        Tools Used:   {format_json(inter['tools_used'])}")

                print("        Content:")
                content = inter["content"] or "(empty)"
                if args.full:
                    print(textwrap.indent(content, "          "))
                else:
                    print(f"          {truncate_text(content, max_content_len)}")

                if inter["shadow_content"]:
                    print("        Shadow Content:")
                    if args.full:
                        print(textwrap.indent(inter["shadow_content"], "          "))
                    else:
                        print(
                            f"          {truncate_text(inter['shadow_content'], max_content_len)}"
                        )

        print()

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()

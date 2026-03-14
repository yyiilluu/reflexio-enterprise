#!/usr/bin/env python3
"""
Fetch user context from Reflexio: preferences and improvement suggestions.
Uses requests directly (no reflexio-client dependency needed).
"""
import argparse
import os
import sys


def api_post(base_url, path, api_key, payload):
    """Make a POST request to the Reflexio API."""
    import requests

    url = base_url.rstrip("/") + path
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Fetch user context from Reflexio")
    parser.add_argument("--user-id", required=True, help="User ID for profile search")
    parser.add_argument(
        "--task-query", required=True, help="Task description for search"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.1, help="Similarity threshold"
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="Max results to return"
    )
    parser.add_argument("--url", default=None, help="Reflexio server URL")
    parser.add_argument(
        "--agent-version", default=None, help="Agent version for feedback"
    )
    args = parser.parse_args()

    api_key = os.environ.get("REFLEXIO_API_KEY")
    if not api_key:
        print("Error: REFLEXIO_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    base_url = args.url or os.environ.get("REFLEXIO_URL", "http://127.0.0.1:8081")
    agent_version = args.agent_version or os.environ.get(
        "REFLEXIO_AGENT_VERSION", "MiniMax-M2.5"
    )

    print("=" * 60)
    print("REFLEXIO CONTEXT FETCH")
    print("=" * 60)

    # Search user profiles
    print(f"\n### User Preferences (query: '{args.task_query}') ###\n")
    try:
        data = api_post(
            base_url,
            "/api/search_profiles",
            api_key,
            {
                "user_id": args.user_id,
                "query": args.task_query,
                "threshold": args.threshold,
                "top_k": args.top_k,
            },
        )
        if data.get("success") and data.get("user_profiles"):
            for i, profile in enumerate(data["user_profiles"], 1):
                print(f"{i}. {profile.get('profile_content', '')}")
                cf = profile.get("custom_features")
                if cf:
                    print(f"   Metadata: {cf}")
        else:
            print(f"No profiles found. {data.get('msg', '')}")
    except Exception as e:
        print(f"Error searching profiles: {e}")

    # Search raw feedbacks
    print(
        f"\n### Improvement Suggestions (query: '{args.task_query}', agent: {agent_version}) ###\n"
    )
    try:
        data = api_post(
            base_url,
            "/api/search_raw_feedbacks",
            api_key,
            {
                "agent_version": agent_version,
                "query": args.task_query,
                "threshold": args.threshold,
            },
        )
        if data.get("success") and data.get("raw_feedbacks"):
            for i, fb in enumerate(data["raw_feedbacks"], 1):
                print(f"{i}. {fb.get('feedback_content', '')}")
        else:
            print("No improvement suggestions found.")
    except Exception as e:
        print(f"Error searching feedbacks: {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

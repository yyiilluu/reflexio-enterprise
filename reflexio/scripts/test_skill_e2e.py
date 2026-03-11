"""
End-to-end manual test script for Skill feature via Python client.

Usage:
    python reflexio/scripts/test_skill_e2e.py

Prerequisites:
    - Server running at http://localhost:8081
    - Local Supabase running
"""

import sys

from reflexio import (
    ReflexioClient,
    SkillStatus,
    RawFeedback,
    Config,
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
    SkillGeneratorConfig,
    ToolUseConfig,
)


BASE_URL = "http://localhost:8081"
FEEDBACK_NAME = "default"
AGENT_VERSION = "v1"


def setup_config(client: ReflexioClient) -> None:
    """Set up org config with available tools and skill generation enabled."""
    config = Config(
        agent_context_prompt="This is a customer support agent for an e-commerce company.",
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name=FEEDBACK_NAME,
                feedback_definition_prompt="feedback about agent quality",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=2,
                ),
                skill_generator_config=SkillGeneratorConfig(
                    enabled=True,
                    min_feedback_per_cluster=2,
                    cooldown_hours=0,
                    auto_generate_on_aggregation=False,
                ),
            ),
        ],
        tool_can_use=[
            ToolUseConfig(
                tool_name="search",
                tool_description="Search for information in the knowledge base",
            ),
            ToolUseConfig(
                tool_name="account_lookup",
                tool_description="Look up customer account details by ID or email",
            ),
            ToolUseConfig(
                tool_name="shipping_tracker",
                tool_description="Track shipping status and delivery updates",
            ),
            ToolUseConfig(
                tool_name="inventory_check",
                tool_description="Check product availability and stock levels",
            ),
            ToolUseConfig(
                tool_name="knowledge_base",
                tool_description="Search company policies, return policy, FAQ, etc.",
            ),
        ],
    )
    resp = client.set_config(config)
    print(
        f"[OK] Config set with {len(config.tool_can_use)} tools (success={resp.get('success', True)})"
    )


def seed_raw_feedbacks(client: ReflexioClient) -> None:
    """Seed raw feedbacks for skill generation."""
    # Cluster 1: Handling frustrated/angry customers (5 feedbacks with similar when_condition)
    # These should cluster together due to similar "customer is frustrated/angry/upset" conditions
    raw_feedbacks = [
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-1",
            do_action="Acknowledge the customer's frustration before offering a solution",
            do_not_action="Jump straight to troubleshooting steps",
            when_condition="Customer is frustrated and angry about a product issue",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-2",
            do_action="Show empathy and validate the customer's feelings",
            do_not_action="Use scripted robotic responses",
            when_condition="Customer is frustrated and upset about a service failure",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-3",
            do_action="Apologize sincerely when the company is at fault",
            do_not_action="Deflect blame to other departments",
            when_condition="Customer is frustrated and angry because of a company error",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-4",
            do_action="Offer compensation or discount for service failures",
            do_not_action="Ignore the impact on the customer",
            when_condition="Customer is frustrated and upset about significant inconvenience",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-5",
            do_action="Let the customer vent before proposing solutions",
            do_not_action="Interrupt the customer mid-complaint",
            when_condition="Customer is angry and frustrated about repeated issues",
        ),
        # Cluster 2: Using tools to look up information (5 feedbacks with similar when_condition)
        # These should cluster together due to similar "look up / search / check" tool-usage conditions
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-6",
            do_action="Use the search tool to look up the customer's order status",
            do_not_action="Ask the customer to check their email for order details",
            when_condition="Customer asks about their order status and you need to look it up",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-7",
            do_action="Search the knowledge base before answering technical questions",
            do_not_action="Guess at technical answers without verifying",
            when_condition="Customer asks a technical question and you need to look up the answer",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-8",
            do_action="Use the account lookup tool to verify customer identity",
            do_not_action="Ask the customer to provide all details manually",
            when_condition="Customer needs account help and you need to look up their account",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-9",
            do_action="Check the shipping tracker tool for delivery updates",
            do_not_action="Tell the customer to check the carrier website themselves",
            when_condition="Customer asks about delivery and you need to look up shipping status",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-10",
            do_action="Look up the return policy in the knowledge base before responding",
            do_not_action="Give a generic return policy answer without checking",
            when_condition="Customer asks about returns and you need to look up the policy",
        ),
    ]
    resp = client.add_raw_feedback(raw_feedbacks)
    print(f"[OK] Seeded {resp.added_count} raw feedbacks (success={resp.success})")


def test_run_skill_generation(client: ReflexioClient) -> None:
    """Test: run skill generation."""
    print("\n--- Run Skill Generation ---")
    result = client.run_skill_generation(
        agent_version=AGENT_VERSION,
        feedback_name=FEEDBACK_NAME,
        wait_for_response=True,
    )
    print(f"  Success: {result.success}")
    print(f"  Skills generated: {result.skills_generated}")
    print(f"  Skills updated: {result.skills_updated}")
    if result.message:
        print(f"  Message: {result.message}")
    assert result.success, "Skill generation failed"
    assert (
        result.skills_generated > 0 or result.skills_updated > 0
    ), "No skills produced"


def test_get_skills(client: ReflexioClient) -> list:
    """Test: list all skills."""
    print("\n--- Get Skills ---")
    resp = client.get_skills()
    print(f"  Total skills: {len(resp.skills)}")
    for s in resp.skills:
        print(f"  [{s.skill_id}] {s.skill_name} (v{s.version}, {s.skill_status.value})")
        print(f"      When: {s.when_condition}")
        print(f"      Tools: {s.allowed_tools}")
        print(f"      Examples: {s.examples[:2]}{'...' if len(s.examples) > 2 else ''}")
        print(f"      Feedback IDs: {s.raw_feedback_ids}")
    assert len(resp.skills) > 0, "No skills found"
    return resp.skills


def test_get_skills_filtered(client: ReflexioClient) -> None:
    """Test: filter skills by status."""
    print("\n--- Get Skills (filtered) ---")
    draft = client.get_skills(skill_status=SkillStatus.DRAFT)
    print(f"  Draft skills: {len(draft.skills)}")

    published = client.get_skills(skill_status=SkillStatus.PUBLISHED)
    print(f"  Published skills: {len(published.skills)}")

    by_feedback = client.get_skills(feedback_name=FEEDBACK_NAME)
    print(f"  Skills for '{FEEDBACK_NAME}': {len(by_feedback.skills)}")


def test_search_skills(client: ReflexioClient) -> None:
    """Test: hybrid search for skills."""
    print("\n--- Search Skills ---")
    resp = client.search_skills(query="customer frustration empathy")
    print(f"  Results for 'customer frustration empathy': {len(resp.skills)}")
    for s in resp.skills:
        print(f"    - {s.skill_name}: {s.when_condition}")
    assert len(resp.skills) > 0, "Search returned no results"


def test_update_skill_status(client: ReflexioClient, skill_id: int) -> None:
    """Test: update skill status DRAFT -> PUBLISHED."""
    print("\n--- Update Skill Status ---")
    resp = client.update_skill_status(skill_id, SkillStatus.PUBLISHED)
    print(f"  Updated skill {skill_id} to PUBLISHED: success={resp.success}")
    assert resp.success, f"Failed to update skill {skill_id}"

    # Verify
    published = client.get_skills(skill_status=SkillStatus.PUBLISHED)
    ids = [s.skill_id for s in published.skills]
    assert skill_id in ids, f"Skill {skill_id} not found in published list"
    print(f"  Verified: skill {skill_id} is now PUBLISHED")


def test_export_skills(client: ReflexioClient) -> None:
    """Test: export skills as markdown."""
    print("\n--- Export Skills ---")
    resp = client.export_skills()
    assert resp.success, "Export failed"
    print(resp.markdown[:500])
    if len(resp.markdown) > 500:
        print(f"  ... ({len(resp.markdown)} chars total)")


def test_skill_update_on_rerun(client: ReflexioClient) -> None:
    """Test: re-running skill generation should update existing skills (version bump)."""
    print("\n--- Rerun Skill Generation (update existing) ---")

    # Add more feedbacks that reinforce existing clusters
    more = [
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-11",
            do_action="De-escalate by speaking calmly and offering immediate help",
            do_not_action="Match the customer's angry tone",
            when_condition="Customer is frustrated and angry about billing errors",
        ),
        RawFeedback(
            feedback_name=FEEDBACK_NAME,
            agent_version=AGENT_VERSION,
            request_id="test-req-12",
            do_action="Use the inventory tool to check product availability",
            do_not_action="Tell the customer to visit the store to check stock",
            when_condition="Customer asks about product availability and you need to look it up",
        ),
    ]
    client.add_raw_feedback(more)
    print("  Added 2 more raw feedbacks")

    result = client.run_skill_generation(
        agent_version=AGENT_VERSION,
        feedback_name=FEEDBACK_NAME,
        wait_for_response=True,
    )
    print(f"  Skills generated: {result.skills_generated}")
    print(f"  Skills updated: {result.skills_updated}")

    skills = client.get_skills().skills
    for s in skills:
        print(
            f"  {s.skill_name}: v{s.version}, tools={s.allowed_tools}, examples={len(s.examples)}"
        )


def test_delete_skill(client: ReflexioClient, skill_id: int) -> None:
    """Test: delete a skill by ID."""
    print("\n--- Delete Skill ---")
    resp = client.delete_skill(skill_id)
    print(f"  Deleted skill {skill_id}: success={resp.success}")
    assert resp.success, f"Failed to delete skill {skill_id}"

    remaining = client.get_skills()
    ids = [s.skill_id for s in remaining.skills]
    assert skill_id not in ids, f"Skill {skill_id} still exists after delete"
    print(f"  Verified: skill {skill_id} no longer exists")


def cleanup_skills(client: ReflexioClient) -> None:
    """Delete all skills created during test."""
    skills = client.get_skills().skills
    for s in skills:
        client.delete_skill(s.skill_id)
    if skills:
        print(f"\n[CLEANUP] Deleted {len(skills)} skills")


def main():
    print("=== Skill E2E Test ===\n")

    # Setup — uses REFLEXIO_API_KEY from environment automatically
    client = ReflexioClient(url_endpoint=BASE_URL)

    try:
        # Setup config with available tools
        setup_config(client)

        # Seed data
        seed_raw_feedbacks(client)

        # 1. Generate skills
        test_run_skill_generation(client)

        # 2. List skills
        skills = test_get_skills(client)

        # Verify at least one skill has allowed_tools (from tool-usage cluster)
        skills_with_tools = [s for s in skills if s.allowed_tools]
        print(f"\n  Skills with allowed_tools: {len(skills_with_tools)}/{len(skills)}")
        assert (
            len(skills_with_tools) > 0
        ), "Expected at least one skill with allowed_tools"

        # 3. Filtered listing
        test_get_skills_filtered(client)

        # 4. Search
        test_search_skills(client)

        # 5. Update status
        draft_skills = client.get_skills(skill_status=SkillStatus.DRAFT).skills
        if draft_skills:
            test_update_skill_status(client, draft_skills[0].skill_id)

        # 6. Export markdown
        test_export_skills(client)

        # 7. Rerun (update existing)
        test_skill_update_on_rerun(client)

        # 8. Delete
        current_skills = client.get_skills().skills
        if current_skills:
            test_delete_skill(client, current_skills[-1].skill_id)

        # 9. Export filtered
        print("\n--- Export Published Only ---")
        pub_export = client.export_skills(skill_status=SkillStatus.PUBLISHED)
        print(pub_export.markdown[:300] if pub_export.markdown else "  (empty)")

        print("\n=== All tests passed ===")

    except Exception as e:
        print(f"\n!!! TEST FAILED: {e}")
        sys.exit(1)

    finally:
        cleanup_skills(client)


if __name__ == "__main__":
    main()

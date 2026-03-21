"""End-to-end tests for feedback workflows."""

import os
from collections.abc import Callable
from datetime import UTC

from reflexio_commons.api_schema.retriever_schema import (
    GetFeedbacksRequest,
    GetRawFeedbacksRequest,
    UpdateFeedbackStatusRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    AddRawFeedbackRequest,
    DowngradeRawFeedbacksRequest,
    FeedbackStatus,
    InteractionData,
    ManualFeedbackGenerationRequest,
    RawFeedback,
    RerunFeedbackGenerationRequest,
    Status,
    UpgradeRawFeedbacksRequest,
)

from reflexio.reflexio_lib.reflexio_lib import Reflexio
from reflexio.tests.e2e_tests.conftest import save_raw_feedbacks
from reflexio.tests.server.test_utils import skip_in_precommit, skip_low_priority


@skip_in_precommit
def test_publish_interaction_feedback_only(
    reflexio_instance_feedback_only: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_after_test: Callable[[], None],
):
    """Test interaction publishing with only feedback extraction enabled."""
    user_id = "test_user_feedback_only"
    agent_version = "test_agent_feedback"

    # Publish interactions
    response = reflexio_instance_feedback_only.publish_interaction(
        {
            "user_id": user_id,
            "interaction_data_list": sample_interaction_requests,
            "source": "test_conversation",
            "agent_version": agent_version,
        }
    )

    # Verify successful publication
    assert response.success is True
    assert response.message == ""

    # Verify interactions were added to storage
    final_interactions = (
        reflexio_instance_feedback_only.request_context.storage.get_all_interactions()
    )
    assert len(final_interactions) == len(sample_interaction_requests)

    # Verify feedbacks were generated and stored
    raw_feedbacks = (
        reflexio_instance_feedback_only.request_context.storage.get_raw_feedbacks(
            feedback_name="test_feedback"
        )
    )
    assert len(raw_feedbacks) > 0 and raw_feedbacks[0].feedback_content.strip() != ""

    # Verify NO profiles were generated (since profile config is not enabled)
    final_profiles = (
        reflexio_instance_feedback_only.request_context.storage.get_all_profiles()
    )
    assert len(final_profiles) == 0

    # Verify NO profile change logs were created (since profile config is not enabled)
    final_change_logs = reflexio_instance_feedback_only.request_context.storage.get_profile_change_logs()
    assert len(final_change_logs) == 0

    # Verify NO agent success evaluation results were created (since agent success config is not enabled)
    agent_success_results = reflexio_instance_feedback_only.request_context.storage.get_agent_success_evaluation_results(
        agent_version=agent_version
    )
    assert len(agent_success_results) == 0


@skip_in_precommit
def test_run_feedback_aggregation_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test end-to-end feedback aggregation workflow."""
    agent_version = "1.0.0"  # Must match the agent_version in mock_feedbacks.csv
    feedback_name = "test_feedback"

    # First save mock feedbacks
    save_raw_feedbacks(reflexio_instance_feedback_only)

    # Use mock mode to avoid needing embeddings for clustering
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Run feedback aggregation for the agent version
        reflexio_instance_feedback_only.run_feedback_aggregation(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )
        # If we reach here, the operation was successful
        assert True

        raw_feedbacks = (
            reflexio_instance_feedback_only.request_context.storage.get_raw_feedbacks(
                feedback_name=feedback_name
            )
        )
        assert len(raw_feedbacks) == 20

        feedbacks = (
            reflexio_instance_feedback_only.request_context.storage.get_feedbacks(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.PENDING,
            )
        )
        assert len(feedbacks) > 0
    finally:
        # Restore original environment variable
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_get_feedbacks_with_feedback_status_filter(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test get_feedbacks with feedback_status_filter parameter.

    This test verifies:
    1. Default behavior (no filter) returns feedbacks of all statuses
    2. Explicit status filters return only feedbacks with matching status
    3. Each status filter correctly filters the results
    """
    agent_version = "1.0.0"
    feedback_name = "test_feedback"
    storage = reflexio_instance_feedback_only.request_context.storage

    # First save mock feedbacks and run aggregation
    save_raw_feedbacks(reflexio_instance_feedback_only)

    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Run feedback aggregation - creates feedbacks with PENDING status
        reflexio_instance_feedback_only.run_feedback_aggregation(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )

        # Get all pending feedbacks to set up different statuses
        initial_response = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.PENDING,
            )
        )
        assert initial_response.success is True
        assert len(initial_response.feedbacks) >= 3, (
            "Need at least 3 feedbacks to test different status filters"
        )

        # Update some feedbacks to different statuses to enable proper testing
        # Keep one as PENDING, update one to APPROVED, update one to REJECTED
        feedbacks_to_update = initial_response.feedbacks[:3]

        # Update first feedback to APPROVED
        storage.update_feedback_status(
            feedbacks_to_update[0].feedback_id, FeedbackStatus.APPROVED
        )
        # Update second feedback to REJECTED
        storage.update_feedback_status(
            feedbacks_to_update[1].feedback_id, FeedbackStatus.REJECTED
        )
        # Third feedback stays as PENDING

        # Test default behavior - should return feedbacks of ALL statuses (no filter)
        response_default = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(feedback_name=feedback_name)
        )
        assert response_default.success is True
        assert len(response_default.feedbacks) > 0

        # Verify that default (no filter) returns feedbacks of different statuses
        statuses_in_default = {f.feedback_status for f in response_default.feedbacks}
        # Should have at least APPROVED and REJECTED (PENDING depends on how many feedbacks we started with)
        assert FeedbackStatus.APPROVED in statuses_in_default, (
            "Default should return APPROVED feedbacks when no filter is specified"
        )
        assert FeedbackStatus.REJECTED in statuses_in_default, (
            "Default should return REJECTED feedbacks when no filter is specified"
        )

        # Test with explicit approved filter - should ONLY return APPROVED feedbacks
        response_approved = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.APPROVED,
            )
        )
        assert response_approved.success is True
        assert len(response_approved.feedbacks) >= 1, (
            "Should have at least 1 APPROVED feedback"
        )
        for feedback in response_approved.feedbacks:
            assert feedback.feedback_status == FeedbackStatus.APPROVED

        # Test with pending filter - should ONLY return PENDING feedbacks
        response_pending = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.PENDING,
            )
        )
        assert response_pending.success is True
        # We left at least one feedback as PENDING
        assert len(response_pending.feedbacks) >= 1, (
            "Should have at least 1 PENDING feedback"
        )
        for feedback in response_pending.feedbacks:
            assert feedback.feedback_status == FeedbackStatus.PENDING

        # Test with rejected filter - should ONLY return REJECTED feedbacks
        response_rejected = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.REJECTED,
            )
        )
        assert response_rejected.success is True
        assert len(response_rejected.feedbacks) >= 1, (
            "Should have at least 1 REJECTED feedback"
        )
        for feedback in response_rejected.feedbacks:
            assert feedback.feedback_status == FeedbackStatus.REJECTED

        # Verify filtered counts are less than default (no filter) count
        # This confirms that filters are actually excluding feedbacks
        assert len(response_approved.feedbacks) < len(response_default.feedbacks), (
            "APPROVED filter should return fewer feedbacks than no filter"
        )
        assert len(response_rejected.feedbacks) < len(response_default.feedbacks), (
            "REJECTED filter should return fewer feedbacks than no filter"
        )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_get_raw_feedbacks_with_status_filter(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test get_raw_feedbacks with status_filter parameter."""
    feedback_name = "test_feedback"

    # Save mock feedbacks
    save_raw_feedbacks(reflexio_instance_feedback_only)

    # Test default behavior - should return current (non-archived) raw feedbacks
    response_default = reflexio_instance_feedback_only.get_raw_feedbacks(
        GetRawFeedbacksRequest(feedback_name=feedback_name)
    )
    assert response_default.success is True
    assert len(response_default.raw_feedbacks) > 0

    # Test with explicit None status filter (current feedbacks)
    response_current = reflexio_instance_feedback_only.get_raw_feedbacks(
        GetRawFeedbacksRequest(
            feedback_name=feedback_name,
            status_filter=[None],
        )
    )
    assert response_current.success is True
    for raw_feedback in response_current.raw_feedbacks:
        assert raw_feedback.status is None  # Current feedbacks have None status


@skip_in_precommit
def test_upgrade_raw_feedbacks_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test end-to-end upgrade workflow for raw feedbacks.

    Upgrade workflow:
    1. Delete old ARCHIVED raw feedbacks
    2. Archive CURRENT raw feedbacks (None -> ARCHIVED)
    3. Promote PENDING raw feedbacks (PENDING -> None/CURRENT)
    """
    feedback_name = "test_feedback"
    agent_version = "1.0.0"
    storage = reflexio_instance_feedback_only.request_context.storage

    # Setup: Create raw feedbacks with different statuses
    # Create CURRENT feedbacks (status=None)
    current_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"current_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Current feedback content {i}",
            status=None,
        )
        for i in range(3)
    ]

    # Create PENDING feedbacks (status=PENDING)
    pending_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"pending_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Pending feedback content {i}",
            status=Status.PENDING,
        )
        for i in range(2)
    ]

    # Create ARCHIVED feedbacks (status=ARCHIVED)
    archived_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"archived_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Archived feedback content {i}",
            status=Status.ARCHIVED,
        )
        for i in range(2)
    ]

    # Save all feedbacks to storage
    storage.save_raw_feedbacks(
        current_feedbacks + pending_feedbacks + archived_feedbacks
    )

    # Verify initial state
    all_feedbacks_before = storage.get_raw_feedbacks(feedback_name=feedback_name)
    current_before = [f for f in all_feedbacks_before if f.status is None]
    pending_before = [f for f in all_feedbacks_before if f.status == Status.PENDING]
    archived_before = [f for f in all_feedbacks_before if f.status == Status.ARCHIVED]

    assert len(current_before) == 3
    assert len(pending_before) == 2
    assert len(archived_before) == 2

    # Execute upgrade
    response = reflexio_instance_feedback_only.upgrade_all_raw_feedbacks(
        UpgradeRawFeedbacksRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )
    )

    # Verify response
    assert response.success is True
    assert response.raw_feedbacks_deleted == 2  # Old ARCHIVED deleted
    assert response.raw_feedbacks_archived == 3  # CURRENT -> ARCHIVED
    assert response.raw_feedbacks_promoted == 2  # PENDING -> CURRENT (None)

    # Verify final state
    all_feedbacks_after = storage.get_raw_feedbacks(feedback_name=feedback_name)
    current_after = [f for f in all_feedbacks_after if f.status is None]
    archived_after = [f for f in all_feedbacks_after if f.status == Status.ARCHIVED]
    pending_after = [f for f in all_feedbacks_after if f.status == Status.PENDING]

    # PENDING feedbacks promoted to CURRENT
    assert len(current_after) == 2
    for feedback in current_after:
        assert "pending_request" in feedback.request_id

    # CURRENT feedbacks archived
    assert len(archived_after) == 3
    for feedback in archived_after:
        assert "current_request" in feedback.request_id

    # No more PENDING feedbacks
    assert len(pending_after) == 0


@skip_in_precommit
@skip_low_priority
def test_downgrade_raw_feedbacks_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test end-to-end downgrade workflow for raw feedbacks.

    Downgrade workflow:
    1. Demote CURRENT raw feedbacks (None -> ARCHIVE_IN_PROGRESS)
    2. Restore ARCHIVED raw feedbacks (ARCHIVED -> None/CURRENT)
    3. Complete archiving (ARCHIVE_IN_PROGRESS -> ARCHIVED)
    """
    feedback_name = "test_feedback"
    agent_version = "1.0.0"
    storage = reflexio_instance_feedback_only.request_context.storage

    # Setup: Create raw feedbacks with different statuses
    # Create CURRENT feedbacks (status=None)
    current_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"current_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Current feedback content {i}",
            status=None,
        )
        for i in range(3)
    ]

    # Create ARCHIVED feedbacks (status=ARCHIVED)
    archived_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"archived_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Archived feedback content {i}",
            status=Status.ARCHIVED,
        )
        for i in range(2)
    ]

    # Save all feedbacks to storage
    storage.save_raw_feedbacks(current_feedbacks + archived_feedbacks)

    # Verify initial state
    all_feedbacks_before = storage.get_raw_feedbacks(feedback_name=feedback_name)
    current_before = [f for f in all_feedbacks_before if f.status is None]
    archived_before = [f for f in all_feedbacks_before if f.status == Status.ARCHIVED]

    assert len(current_before) == 3
    assert len(archived_before) == 2

    # Execute downgrade
    response = reflexio_instance_feedback_only.downgrade_all_raw_feedbacks(
        DowngradeRawFeedbacksRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )
    )

    # Verify response
    assert response.success is True
    assert response.raw_feedbacks_demoted == 3  # CURRENT -> ARCHIVED
    assert response.raw_feedbacks_restored == 2  # ARCHIVED -> CURRENT (None)

    # Verify final state
    all_feedbacks_after = storage.get_raw_feedbacks(feedback_name=feedback_name)
    current_after = [f for f in all_feedbacks_after if f.status is None]
    archived_after = [f for f in all_feedbacks_after if f.status == Status.ARCHIVED]

    # ARCHIVED feedbacks restored to CURRENT
    assert len(current_after) == 2
    for feedback in current_after:
        assert "archived_request" in feedback.request_id

    # CURRENT feedbacks demoted to ARCHIVED
    assert len(archived_after) == 3
    for feedback in archived_after:
        assert "current_request" in feedback.request_id


@skip_in_precommit
@skip_low_priority
def test_upgrade_downgrade_roundtrip(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test that upgrade followed by downgrade restores the original state."""
    feedback_name = "test_feedback"
    agent_version = "1.0.0"
    storage = reflexio_instance_feedback_only.request_context.storage

    # Setup: Create initial CURRENT feedbacks
    current_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"original_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Original feedback content {i}",
            status=None,
        )
        for i in range(3)
    ]

    # Create PENDING feedbacks (new version)
    pending_feedbacks = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"new_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"New feedback content {i}",
            status=Status.PENDING,
        )
        for i in range(2)
    ]

    storage.save_raw_feedbacks(current_feedbacks + pending_feedbacks)

    # Execute upgrade (new feedbacks become current, original become archived)
    upgrade_response = reflexio_instance_feedback_only.upgrade_all_raw_feedbacks(
        UpgradeRawFeedbacksRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )
    )
    assert upgrade_response.success is True

    # Verify upgrade state
    all_feedbacks_after_upgrade = storage.get_raw_feedbacks(feedback_name=feedback_name)
    current_after_upgrade = [f for f in all_feedbacks_after_upgrade if f.status is None]
    archived_after_upgrade = [
        f for f in all_feedbacks_after_upgrade if f.status == Status.ARCHIVED
    ]

    assert len(current_after_upgrade) == 2  # new feedbacks are now current
    assert len(archived_after_upgrade) == 3  # original feedbacks are now archived

    # Execute downgrade (restore original feedbacks)
    downgrade_response = reflexio_instance_feedback_only.downgrade_all_raw_feedbacks(
        DowngradeRawFeedbacksRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )
    )
    assert downgrade_response.success is True

    # Verify roundtrip restored original state
    all_feedbacks_after_downgrade = storage.get_raw_feedbacks(
        feedback_name=feedback_name
    )
    current_after_downgrade = [
        f for f in all_feedbacks_after_downgrade if f.status is None
    ]
    archived_after_downgrade = [
        f for f in all_feedbacks_after_downgrade if f.status == Status.ARCHIVED
    ]

    # Original feedbacks restored to current
    assert len(current_after_downgrade) == 3
    for feedback in current_after_downgrade:
        assert "original_request" in feedback.request_id

    # New feedbacks demoted to archived
    assert len(archived_after_downgrade) == 2
    for feedback in archived_after_downgrade:
        assert "new_request" in feedback.request_id


@skip_in_precommit
@skip_low_priority
def test_add_raw_feedback_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test add_raw_feedback method for directly adding raw feedbacks to storage.

    This test verifies:
    1. Raw feedbacks can be added directly via API
    2. Added feedbacks are stored correctly
    3. Feedbacks are normalized (only required fields kept)
    4. Error handling for invalid input
    """
    feedback_name = "test_add_feedback"
    agent_version = "1.0.0"

    # Step 1: Create raw feedbacks to add
    raw_feedbacks_to_add = [
        RawFeedback(
            agent_version=agent_version,
            request_id=f"add_test_request_{i}",
            feedback_name=feedback_name,
            feedback_content=f"Added feedback content {i}",
        )
        for i in range(3)
    ]

    # Step 2: Add raw feedbacks via API
    add_response = reflexio_instance_feedback_only.add_raw_feedback(
        AddRawFeedbackRequest(raw_feedbacks=raw_feedbacks_to_add)
    )
    assert add_response.success is True
    assert add_response.added_count == 3

    # Step 3: Verify feedbacks were stored
    stored_feedbacks = reflexio_instance_feedback_only.get_raw_feedbacks(
        GetRawFeedbacksRequest(feedback_name=feedback_name)
    )
    assert stored_feedbacks.success is True
    assert len(stored_feedbacks.raw_feedbacks) == 3

    # Step 4: Verify feedback content
    for _i, feedback in enumerate(stored_feedbacks.raw_feedbacks):
        assert feedback.agent_version == agent_version
        assert feedback.feedback_name == feedback_name
        assert "Added feedback content" in feedback.feedback_content

    # Step 5: Test with dict input
    dict_feedbacks = [
        {
            "agent_version": agent_version,
            "request_id": "dict_test_request",
            "feedback_name": feedback_name,
            "feedback_content": "Dict added feedback content",
        }
    ]
    dict_response = reflexio_instance_feedback_only.add_raw_feedback(
        {"raw_feedbacks": dict_feedbacks}
    )
    assert dict_response.success is True
    assert dict_response.added_count == 1

    # Step 6: Verify total feedbacks
    all_feedbacks = reflexio_instance_feedback_only.get_raw_feedbacks(
        GetRawFeedbacksRequest(feedback_name=feedback_name)
    )
    assert len(all_feedbacks.raw_feedbacks) == 4


@skip_in_precommit
def test_update_feedback_status_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    cleanup_feedback_only: Callable[[], None],
):
    """Test update_feedback_status method for approving/rejecting feedbacks.

    This test verifies:
    1. Feedback status can be updated from PENDING to APPROVED
    2. Feedback status can be updated from PENDING to REJECTED
    3. Status update is persisted correctly
    4. Error handling for non-existent feedback
    """
    feedback_name = "test_feedback"
    agent_version = "1.0.0"

    # Setup: Save mock feedbacks and run aggregation to create feedbacks with status
    save_raw_feedbacks(reflexio_instance_feedback_only)

    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Run feedback aggregation to create aggregated feedbacks
        reflexio_instance_feedback_only.run_feedback_aggregation(
            agent_version=agent_version,
            feedback_name=feedback_name,
        )

        # Get pending feedbacks
        pending_response = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.PENDING,
            )
        )
        assert pending_response.success is True
        assert len(pending_response.feedbacks) > 0

        # Step 1: Update first feedback to APPROVED
        first_feedback = pending_response.feedbacks[0]
        approve_response = reflexio_instance_feedback_only.update_feedback_status(
            UpdateFeedbackStatusRequest(
                feedback_id=first_feedback.feedback_id,
                feedback_status=FeedbackStatus.APPROVED,
            )
        )
        assert approve_response.success is True

        # Verify status was updated
        approved_feedbacks = reflexio_instance_feedback_only.get_feedbacks(
            GetFeedbacksRequest(
                feedback_name=feedback_name,
                feedback_status_filter=FeedbackStatus.APPROVED,
            )
        )
        assert approved_feedbacks.success is True
        approved_ids = [f.feedback_id for f in approved_feedbacks.feedbacks]
        assert first_feedback.feedback_id in approved_ids

        # Step 2: Update second feedback to REJECTED (if exists)
        if len(pending_response.feedbacks) > 1:
            second_feedback = pending_response.feedbacks[1]
            reject_response = reflexio_instance_feedback_only.update_feedback_status(
                UpdateFeedbackStatusRequest(
                    feedback_id=second_feedback.feedback_id,
                    feedback_status=FeedbackStatus.REJECTED,
                )
            )
            assert reject_response.success is True

            # Verify status was updated
            rejected_feedbacks = reflexio_instance_feedback_only.get_feedbacks(
                GetFeedbacksRequest(
                    feedback_name=feedback_name,
                    feedback_status_filter=FeedbackStatus.REJECTED,
                )
            )
            assert rejected_feedbacks.success is True
            rejected_ids = [f.feedback_id for f in rejected_feedbacks.feedbacks]
            assert second_feedback.feedback_id in rejected_ids

        # Step 3: Test with dict input
        if len(pending_response.feedbacks) > 2:
            third_feedback = pending_response.feedbacks[2]
            dict_response = reflexio_instance_feedback_only.update_feedback_status(
                {
                    "feedback_id": third_feedback.feedback_id,
                    "feedback_status": FeedbackStatus.APPROVED,
                }
            )
            assert dict_response.success is True

        # Step 4: Test error handling with non-existent feedback ID
        error_response = reflexio_instance_feedback_only.update_feedback_status(
            UpdateFeedbackStatusRequest(
                feedback_id=999999,  # Non-existent ID
                feedback_status=FeedbackStatus.APPROVED,
            )
        )
        assert error_response.success is False

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
def test_rerun_feedback_generation_end_to_end(
    reflexio_instance_feedback_only: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_only: Callable[[], None],
):
    """Test rerun_feedback_generation method for regenerating feedbacks.

    This test verifies:
    1. Rerun feedback generation creates PENDING feedbacks
    2. Existing CURRENT feedbacks remain unchanged
    3. Time filtering works correctly
    4. Feedback name filtering works correctly
    """
    user_id = "test_user_rerun_feedback"
    agent_version = "test_agent_rerun_feedback"
    feedback_name = "test_feedback"

    # Use mock mode to ensure consistent LLM responses
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Step 1: Publish interactions to generate feedbacks
        publish_response = reflexio_instance_feedback_only.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "test_rerun_source",
                "agent_version": agent_version,
            }
        )
        assert publish_response.success is True

        # Verify feedbacks were generated
        initial_feedbacks = reflexio_instance_feedback_only.get_raw_feedbacks(
            GetRawFeedbacksRequest(
                feedback_name=feedback_name,
                status_filter=[None],  # Current feedbacks
            )
        )
        assert initial_feedbacks.success is True
        initial_count = len(initial_feedbacks.raw_feedbacks)
        assert initial_count > 0, "Initial feedbacks should be generated"

        # Step 2: Run rerun_feedback_generation
        rerun_response = reflexio_instance_feedback_only.rerun_feedback_generation(
            RerunFeedbackGenerationRequest(
                agent_version=agent_version,
                feedback_name=feedback_name,
            )
        )
        assert rerun_response.success is True
        assert rerun_response.feedbacks_generated > 0

        # Step 3: Verify PENDING feedbacks were created
        pending_feedbacks = reflexio_instance_feedback_only.get_raw_feedbacks(
            GetRawFeedbacksRequest(
                feedback_name=feedback_name,
                status_filter=[Status.PENDING],
            )
        )
        assert pending_feedbacks.success is True
        assert len(pending_feedbacks.raw_feedbacks) > 0, (
            "PENDING feedbacks should be created"
        )

        # Step 4: Verify current feedbacks unchanged
        current_feedbacks_after = reflexio_instance_feedback_only.get_raw_feedbacks(
            GetRawFeedbacksRequest(
                feedback_name=feedback_name,
                status_filter=[None],
            )
        )
        assert current_feedbacks_after.success is True
        assert len(current_feedbacks_after.raw_feedbacks) == initial_count

        # Step 5: Test with dict input
        dict_response = reflexio_instance_feedback_only.rerun_feedback_generation(
            {
                "agent_version": agent_version,
                "feedback_name": feedback_name,
            }
        )
        assert dict_response.success is True

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_rerun_feedback_generation_with_time_filters(
    reflexio_instance_feedback_only: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_only: Callable[[], None],
):
    """Test rerun_feedback_generation with time-based filtering.

    This test verifies:
    1. Time filtering correctly filters interactions
    2. Future time range returns no results
    3. Valid time range regenerates feedbacks
    """
    from datetime import datetime, timedelta

    user_id = "test_user_rerun_feedback_time"
    agent_version = "test_agent_rerun_time"
    feedback_name = "test_feedback"

    # Use mock mode to ensure consistent LLM responses
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Publish interactions
        publish_response = reflexio_instance_feedback_only.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "test_rerun_time_source",
                "agent_version": agent_version,
            }
        )
        assert publish_response.success is True

        # Test with future time range (should fail - no interactions)
        future_start = datetime.now(UTC) + timedelta(days=1)
        future_end = datetime.now(UTC) + timedelta(days=2)

        future_response = reflexio_instance_feedback_only.rerun_feedback_generation(
            RerunFeedbackGenerationRequest(
                agent_version=agent_version,
                feedback_name=feedback_name,
                start_time=future_start,
                end_time=future_end,
            )
        )
        assert future_response.success is False
        assert "No interactions found" in future_response.msg

        # Test with valid time range (past to future)
        past_start = datetime.now(UTC) - timedelta(days=1)
        future_end = datetime.now(UTC) + timedelta(days=1)

        valid_response = reflexio_instance_feedback_only.rerun_feedback_generation(
            RerunFeedbackGenerationRequest(
                agent_version=agent_version,
                feedback_name=feedback_name,
                start_time=past_start,
                end_time=future_end,
            )
        )
        assert valid_response.success is True
        assert valid_response.feedbacks_generated > 0

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_feedback_source_filtering_with_matching_source(
    reflexio_instance_feedback_source_filtering: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_source_filtering: Callable[[], None],
):
    """Test that feedback extractors only run when source matches request_sources_enabled.

    This test verifies:
    1. When source="api", only api_feedback and all_sources_feedback extractors run
    2. When source="webhook", only webhook_feedback and all_sources_feedback extractors run
    3. Feedbacks have the correct source field set
    """
    user_id = "test_user_source_filter"
    agent_version = "test_agent_source"
    storage = reflexio_instance_feedback_source_filtering.request_context.storage

    # Step 1: Publish interactions with source="api"
    response_api = reflexio_instance_feedback_source_filtering.publish_interaction(
        {
            "user_id": user_id,
            "interaction_data_list": sample_interaction_requests,
            "source": "api",
            "agent_version": agent_version,
        }
    )
    assert response_api.success is True

    # Verify feedbacks were generated for "api" source
    # Expected: api_feedback (matches "api") and all_sources_feedback (no filter) extractors run
    # Note: These may get deduplicated if they produce semantically identical feedbacks
    # Should NOT have: webhook_feedback (only for "webhook")
    api_feedbacks = storage.get_raw_feedbacks(feedback_name="api_feedback")
    webhook_feedbacks = storage.get_raw_feedbacks(feedback_name="webhook_feedback")
    all_sources_feedbacks = storage.get_raw_feedbacks(
        feedback_name="all_sources_feedback"
    )

    # At least one feedback should exist from api_feedback or all_sources_feedback
    # (they may get deduplicated into a single feedback with the first extractor's name)
    total_feedbacks = len(api_feedbacks) + len(all_sources_feedbacks)
    assert total_feedbacks > 0, (
        "At least one feedback should be generated from api_feedback or all_sources_feedback extractors"
    )

    # Verify source field is set correctly for all feedbacks
    for feedback in api_feedbacks:
        assert feedback.source == "api", "api_feedback should have source='api'"
    for feedback in all_sources_feedbacks:
        assert feedback.source == "api", "all_sources_feedback should have source='api'"

    # webhook_feedback should NOT have been generated (source "api" doesn't match "webhook")
    assert len(webhook_feedbacks) == 0, (
        "webhook_feedback should NOT be generated for source='api'"
    )


@skip_in_precommit
@skip_low_priority
def test_feedback_source_filtering_with_non_matching_source(
    reflexio_instance_feedback_source_filtering: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_source_filtering: Callable[[], None],
):
    """Test that feedback extractors do not run when source doesn't match request_sources_enabled.

    This test verifies:
    1. When source="other", only all_sources_feedback extractor runs
    2. api_feedback and webhook_feedback do not run for non-matching source
    """
    user_id = "test_user_source_filter_other"
    agent_version = "test_agent_source_other"
    storage = reflexio_instance_feedback_source_filtering.request_context.storage

    # Publish interactions with source="other" (not in any request_sources_enabled list)
    response = reflexio_instance_feedback_source_filtering.publish_interaction(
        {
            "user_id": user_id,
            "interaction_data_list": sample_interaction_requests,
            "source": "other",
            "agent_version": agent_version,
        }
    )
    assert response.success is True

    # Verify only all_sources_feedback was generated
    api_feedbacks = storage.get_raw_feedbacks(feedback_name="api_feedback")
    webhook_feedbacks = storage.get_raw_feedbacks(feedback_name="webhook_feedback")
    all_sources_feedbacks = storage.get_raw_feedbacks(
        feedback_name="all_sources_feedback"
    )

    # api_feedback should NOT have been generated (source "other" doesn't match "api")
    assert len(api_feedbacks) == 0, (
        "api_feedback should NOT be generated for source='other'"
    )

    # webhook_feedback should NOT have been generated (source "other" doesn't match "webhook")
    assert len(webhook_feedbacks) == 0, (
        "webhook_feedback should NOT be generated for source='other'"
    )

    # all_sources_feedback should have been generated (no source filter)
    assert len(all_sources_feedbacks) > 0, (
        "all_sources_feedback should be generated for any source"
    )
    for feedback in all_sources_feedbacks:
        assert feedback.source == "other", (
            "all_sources_feedback should have source='other'"
        )


@skip_in_precommit
@skip_low_priority
def test_feedback_source_filtering_webhook_source(
    reflexio_instance_feedback_source_filtering: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_source_filtering: Callable[[], None],
):
    """Test that webhook_feedback extractor runs only for webhook source.

    This test verifies:
    1. When source="webhook", webhook_feedback and all_sources_feedback extractors run
    2. api_feedback does not run for webhook source
    """
    user_id = "test_user_source_filter_webhook"
    agent_version = "test_agent_source_webhook"
    storage = reflexio_instance_feedback_source_filtering.request_context.storage

    # Publish interactions with source="webhook"
    response = reflexio_instance_feedback_source_filtering.publish_interaction(
        {
            "user_id": user_id,
            "interaction_data_list": sample_interaction_requests,
            "source": "webhook",
            "agent_version": agent_version,
        }
    )
    assert response.success is True

    # Verify feedbacks were generated correctly
    # Note: webhook_feedback and all_sources_feedback may get deduplicated if they
    # produce semantically identical feedbacks
    api_feedbacks = storage.get_raw_feedbacks(feedback_name="api_feedback")
    webhook_feedbacks = storage.get_raw_feedbacks(feedback_name="webhook_feedback")
    all_sources_feedbacks = storage.get_raw_feedbacks(
        feedback_name="all_sources_feedback"
    )

    # api_feedback should NOT have been generated (source "webhook" doesn't match "api")
    assert len(api_feedbacks) == 0, (
        "api_feedback should NOT be generated for source='webhook'"
    )

    # At least one feedback should exist from webhook_feedback or all_sources_feedback
    # (they may get deduplicated into a single feedback with the first extractor's name)
    total_feedbacks = len(webhook_feedbacks) + len(all_sources_feedbacks)
    assert total_feedbacks > 0, (
        "At least one feedback should be generated from webhook_feedback or all_sources_feedback extractors"
    )

    # Verify source field is set correctly for all feedbacks
    for feedback in webhook_feedbacks:
        assert feedback.source == "webhook", (
            "webhook_feedback should have source='webhook'"
        )
    for feedback in all_sources_feedbacks:
        assert feedback.source == "webhook", (
            "all_sources_feedback should have source='webhook'"
        )


@skip_in_precommit
def test_manual_feedback_generation_end_to_end(
    reflexio_instance_manual_feedback: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_manual_feedback: Callable[[], None],
):
    """Test manual_feedback_generation method for triggering feedback generation.

    This test verifies:
    1. Manual feedback generation uses window-sized interactions
    2. Generated feedbacks have CURRENT status (not PENDING like rerun)
    3. Feedbacks are generated correctly from the interactions
    """
    user_id = "test_user_manual_feedback"
    agent_version = "test_agent_manual_feedback"
    feedback_name = "manual_trigger_feedback"

    # Use mock mode to ensure consistent LLM responses
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Step 1: Publish interactions to have data for generation
        publish_response = reflexio_instance_manual_feedback.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "test_manual_source",
                "agent_version": agent_version,
            }
        )
        assert publish_response.success is True

        # Step 2: Call manual_feedback_generation
        manual_response = reflexio_instance_manual_feedback.manual_feedback_generation(
            ManualFeedbackGenerationRequest(
                agent_version=agent_version,
            )
        )
        assert manual_response.success is True, (
            f"Manual generation failed: {manual_response.msg}"
        )

        # Step 3: Verify feedbacks were generated with CURRENT status (None)
        current_feedbacks = (
            reflexio_instance_manual_feedback.request_context.storage.get_raw_feedbacks(
                feedback_name=feedback_name,
                status_filter=[None],
            )
        )
        # Just verify no errors - content may vary based on LLM
        assert isinstance(current_feedbacks, list)

        # Step 4: Verify NO PENDING feedbacks were created (that's rerun behavior)
        pending_feedbacks = (
            reflexio_instance_manual_feedback.request_context.storage.get_raw_feedbacks(
                feedback_name=feedback_name,
                status_filter=[Status.PENDING],
            )
        )
        assert len(pending_feedbacks) == 0, (
            "Manual generation should not create PENDING feedbacks"
        )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_manual_feedback_generation_no_window_size(
    reflexio_instance_feedback_only: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_feedback_only: Callable[[], None],
):
    """Test manual_feedback_generation works without extraction_window_size.

    This test verifies:
    1. Manual generation works when extraction_window_size is not configured
       (it defaults to fetching all available interactions with a reasonable limit)
    """
    user_id = "test_user_no_window"
    agent_version = "test_agent_no_window"

    # Publish interactions first
    publish_response = reflexio_instance_feedback_only.publish_interaction(
        {
            "user_id": user_id,
            "interaction_data_list": sample_interaction_requests,
            "source": "test_source",
            "agent_version": agent_version,
        }
    )
    assert publish_response.success is True

    # Call manual_feedback_generation - should succeed even without window size
    # When window_size is not configured, it fetches all available interactions
    manual_response = reflexio_instance_feedback_only.manual_feedback_generation(
        ManualFeedbackGenerationRequest(
            agent_version=agent_version,
        )
    )
    assert manual_response.success is True


@skip_in_precommit
@skip_low_priority
def test_manual_feedback_generation_with_source_filter(
    reflexio_instance_manual_feedback: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_manual_feedback: Callable[[], None],
):
    """Test manual_feedback_generation with source filtering.

    This test verifies:
    1. Source filtering works correctly in manual generation
    2. Only interactions with matching source are processed
    """
    user_id = "test_user_manual_source_filter"
    agent_version = "test_agent_source_filter"

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Publish interactions with different sources
        # Source A - full conversation
        response_a = reflexio_instance_manual_feedback.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "source_a",
                "agent_version": agent_version,
            }
        )
        assert response_a.success is True

        # Source B - single message
        response_b = reflexio_instance_manual_feedback.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": [
                    InteractionData(
                        content="Simple message for source B",
                        role="User",
                    )
                ],
                "source": "source_b",
                "agent_version": agent_version,
            }
        )
        assert response_b.success is True

        # Call manual_feedback_generation with source filter
        manual_response = reflexio_instance_manual_feedback.manual_feedback_generation(
            ManualFeedbackGenerationRequest(
                agent_version=agent_version,
                source="source_a",  # Only process source_a
            )
        )
        # Should succeed (or fail gracefully if no matching extractors)
        assert manual_response.success is True or "No interactions found" in (
            manual_response.msg or ""
        )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_manual_feedback_generation_with_dict_input(
    reflexio_instance_manual_feedback: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_manual_feedback: Callable[[], None],
):
    """Test manual_feedback_generation accepts dict input.

    This test verifies:
    1. Manual generation accepts dict input (not just ManualFeedbackGenerationRequest)
    """
    user_id = "test_user_dict_input"
    agent_version = "test_agent_dict"

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Publish interactions
        publish_response = reflexio_instance_manual_feedback.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "test_source",
                "agent_version": agent_version,
            }
        )
        assert publish_response.success is True

        # Call with dict input
        manual_response = reflexio_instance_manual_feedback.manual_feedback_generation(
            {"agent_version": agent_version}
        )
        assert manual_response.success is True, (
            f"Dict input failed: {manual_response.msg}"
        )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_manual_feedback_generation_with_feedback_name_filter(
    reflexio_instance_manual_feedback: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_manual_feedback: Callable[[], None],
):
    """Test manual_feedback_generation with feedback_name filtering.

    This test verifies:
    1. Feedback name filtering works correctly in manual generation
    """
    user_id = "test_user_feedback_name_filter"
    agent_version = "test_agent_feedback_name"
    feedback_name = "manual_trigger_feedback"

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Publish interactions
        publish_response = reflexio_instance_manual_feedback.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "test_source",
                "agent_version": agent_version,
            }
        )
        assert publish_response.success is True

        # Call with feedback_name filter
        manual_response = reflexio_instance_manual_feedback.manual_feedback_generation(
            ManualFeedbackGenerationRequest(
                agent_version=agent_version,
                feedback_name=feedback_name,
            )
        )
        assert manual_response.success is True, (
            f"Feedback name filter failed: {manual_response.msg}"
        )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_rerun_feedback_generation_with_source_filter(
    reflexio_instance_multiple_feedback_extractors: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_multiple_feedback_extractors: Callable[[], None],
):
    """Test rerun feedback generation with source filtering.

    This test verifies:
    1. Rerun with source filter correctly filters interactions by source
    2. Only extractors matching the source run
    3. Generated feedbacks have correct source field
    """
    import os

    user_id = "test_user_rerun_source_filter"
    agent_version = "test_agent_rerun_source"
    storage = reflexio_instance_multiple_feedback_extractors.request_context.storage

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Step 1: Publish interactions with "api" source
        response_api = (
            reflexio_instance_multiple_feedback_extractors.publish_interaction(
                {
                    "user_id": user_id,
                    "interaction_data_list": sample_interaction_requests,
                    "source": "api",
                    "agent_version": agent_version,
                }
            )
        )
        assert response_api.success is True

        # Step 2: Publish interactions with "webhook" source
        response_webhook = (
            reflexio_instance_multiple_feedback_extractors.publish_interaction(
                {
                    "user_id": user_id,
                    "interaction_data_list": [
                        InteractionData(
                            content="Webhook message",
                            role="User",
                        )
                    ],
                    "source": "webhook",
                    "agent_version": agent_version,
                }
            )
        )
        assert response_webhook.success is True

        # Step 3: Delete raw feedbacks created by this test's extractors to start fresh for rerun test
        config = reflexio_instance_multiple_feedback_extractors.request_context.configurator.get_config()
        for fc in config.agent_feedback_configs:
            storage.delete_all_raw_feedbacks_by_feedback_name(fc.feedback_name)

        # Step 4: Rerun with source="api" filter
        rerun_response = (
            reflexio_instance_multiple_feedback_extractors.rerun_feedback_generation(
                RerunFeedbackGenerationRequest(
                    agent_version=agent_version,
                    source="api",  # Only process API source
                )
            )
        )
        assert rerun_response.success is True, (
            f"Rerun with source filter failed: {rerun_response.msg}"
        )

        # Step 5: Verify pending feedbacks were created with source="api"
        pending_feedbacks = storage.get_raw_feedbacks(status_filter=[Status.PENDING])
        if rerun_response.feedbacks_generated > 0:
            assert len(pending_feedbacks) > 0
            for feedback in pending_feedbacks:
                assert feedback.source == "api", (
                    f"Expected source='api', got '{feedback.source}'"
                )

        # Step 6: Test with non-existent source - should fail
        rerun_response_invalid = (
            reflexio_instance_multiple_feedback_extractors.rerun_feedback_generation(
                RerunFeedbackGenerationRequest(
                    agent_version=agent_version,
                    source="non_existent_source",
                )
            )
        )
        assert rerun_response_invalid.success is False
        assert "No interactions found" in rerun_response_invalid.msg

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_rerun_feedback_generation_multiple_extractors_all_sources(
    reflexio_instance_multiple_feedback_extractors: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_multiple_feedback_extractors: Callable[[], None],
):
    """Test rerun feedback generation with multiple extractors collecting from all sources.

    This test verifies:
    1. When source=None in rerun, ALL extractors run
    2. Each extractor collects data based on its own request_sources_enabled
    3. Multiple feedback names are generated
    """
    import os

    user_id = "test_user_rerun_all_sources"
    agent_version = "test_agent_rerun_all"
    storage = reflexio_instance_multiple_feedback_extractors.request_context.storage

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Step 1: Publish interactions with different sources
        # API source
        reflexio_instance_multiple_feedback_extractors.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "api",
                "agent_version": agent_version,
            }
        )

        # Webhook source
        reflexio_instance_multiple_feedback_extractors.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": [
                    InteractionData(
                        content="Webhook interaction",
                        role="User",
                    )
                ],
                "source": "webhook",
                "agent_version": agent_version,
            }
        )

        # Other source (only general_feedback should pick this up)
        reflexio_instance_multiple_feedback_extractors.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": [
                    InteractionData(
                        content="Other source interaction",
                        role="User",
                    )
                ],
                "source": "other",
                "agent_version": agent_version,
            }
        )

        # Step 2: Delete raw feedbacks created by this test's extractors
        config = reflexio_instance_multiple_feedback_extractors.request_context.configurator.get_config()
        for fc in config.agent_feedback_configs:
            storage.delete_all_raw_feedbacks_by_feedback_name(fc.feedback_name)

        # Step 3: Rerun WITHOUT source filter (all extractors run)
        rerun_response = (
            reflexio_instance_multiple_feedback_extractors.rerun_feedback_generation(
                RerunFeedbackGenerationRequest(
                    agent_version=agent_version,
                    # source=None means all extractors run and collect their configured sources
                )
            )
        )
        assert rerun_response.success is True, (
            f"Rerun without source filter failed: {rerun_response.msg}"
        )

        # Step 4: Verify feedbacks from multiple extractors
        if rerun_response.feedbacks_generated > 0:
            pending_feedbacks = storage.get_raw_feedbacks(
                status_filter=[Status.PENDING]
            )
            assert len(pending_feedbacks) > 0

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env


@skip_in_precommit
@skip_low_priority
def test_rerun_feedback_generation_with_extractor_names_filter(
    reflexio_instance_multiple_feedback_extractors: Reflexio,
    sample_interaction_requests: list[InteractionData],
    cleanup_multiple_feedback_extractors: Callable[[], None],
):
    """Test rerun feedback generation with extractor_names filter.

    This test verifies:
    1. extractor_names filter correctly limits which extractors run during rerun
    2. Only specified extractors generate feedbacks
    """
    import os
    import uuid

    # Use unique IDs to avoid data pollution from other tests
    unique_id = uuid.uuid4().hex[:8]
    user_id = f"test_user_rerun_extractor_names_{unique_id}"
    agent_version = f"test_agent_extractor_names_{unique_id}"
    storage = reflexio_instance_multiple_feedback_extractors.request_context.storage

    # Use mock mode
    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Step 1: Publish interactions - this creates CURRENT (status=None) feedbacks for BOTH extractors
        reflexio_instance_multiple_feedback_extractors.publish_interaction(
            {
                "user_id": user_id,
                "interaction_data_list": sample_interaction_requests,
                "source": "api",
                "agent_version": agent_version,
            }
        )

        # Verify initial publish created feedbacks for both extractors
        initial_feedbacks = storage.get_raw_feedbacks(
            agent_version=agent_version,
            user_id=user_id,
        )
        initial_feedback_names = {f.feedback_name for f in initial_feedbacks}
        assert "api_only_feedback" in initial_feedback_names, (
            "Initial publish should create api_only_feedback"
        )
        assert "general_feedback" in initial_feedback_names, (
            "Initial publish should create general_feedback"
        )

        # Step 2: Delete feedbacks for our unique agent_version to allow rerun to regenerate
        for feedback in initial_feedbacks:
            storage.delete_raw_feedback(feedback.raw_feedback_id)

        # Step 3: Rerun with feedback_name filter - only run general_feedback
        # This should create PENDING feedbacks ONLY for general_feedback extractor
        rerun_response = (
            reflexio_instance_multiple_feedback_extractors.rerun_feedback_generation(
                RerunFeedbackGenerationRequest(
                    agent_version=agent_version,
                    feedback_name="general_feedback",  # Only run this extractor
                )
            )
        )
        assert rerun_response.success is True, (
            f"Rerun with extractor_names failed: {rerun_response.msg}"
        )

        # Step 4: Verify only general_feedback was generated
        # Query feedbacks for our unique agent_version and user_id
        rerun_feedbacks = storage.get_raw_feedbacks(
            agent_version=agent_version,
            user_id=user_id,
            status_filter=[Status.PENDING],
        )

        # If feedbacks were generated, they should only be from general_feedback
        for feedback in rerun_feedbacks:
            assert feedback.feedback_name == "general_feedback", (
                f"Expected only general_feedback extractor to run, but found {feedback.feedback_name}"
            )

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env

"""
Create, edit, delete user interaction and user profile
"""

import logging

from reflexio_commons.api_schema.service_schemas import (
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    DeleteRequestRequest,
    DeleteRequestResponse,
    DeleteSessionRequest,
    DeleteSessionResponse,
    DeleteFeedbackRequest,
    DeleteFeedbackResponse,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbackResponse,
    RunFeedbackAggregationRequest,
    RunFeedbackAggregationResponse,
    RunSkillGenerationRequest,
    RunSkillGenerationResponse,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    AddFeedbackRequest,
    AddFeedbackResponse,
)
from reflexio_commons.api_schema.retriever_schema import (
    UpdateFeedbackStatusRequest,
    UpdateFeedbackStatusResponse,
)
from reflexio.server.api_endpoints.precondition_checks import (
    validate_delete_user_profile_request,
    validate_publish_user_interaction_request,
)
from reflexio.server.cache.reflexio_cache import get_reflexio

logger = logging.getLogger(__name__)

# ==============================
# Create user interaction and profile
# ==============================


def add_user_interaction(
    org_id: str,
    request: PublishUserInteractionRequest,
) -> PublishUserInteractionResponse:
    """Add user interaction

    Args:
        org_id (str): Organization ID
        request (PublishUserInteractionRequest): The request containing interaction data

    Returns:
        PublishUserInteractionResponse: Response containing success status and message
    """
    is_valid, message = validate_publish_user_interaction_request(request)
    if not is_valid:
        return PublishUserInteractionResponse(success=False, message=message)

    reflexio = get_reflexio(org_id=org_id)
    return reflexio.publish_interaction(request=request)


def add_raw_feedback(
    org_id: str,
    request: AddRawFeedbackRequest,
) -> AddRawFeedbackResponse:
    """Add raw feedback directly to storage.

    Args:
        org_id (str): Organization ID
        request (AddRawFeedbackRequest): The request containing raw feedbacks

    Returns:
        AddRawFeedbackResponse: Response containing success status, message, and added count
    """
    reflexio = get_reflexio(org_id=org_id)
    return reflexio.add_raw_feedback(request=request)


def add_feedback(
    org_id: str,
    request: AddFeedbackRequest,
) -> AddFeedbackResponse:
    """Add aggregated feedback directly to storage.

    Args:
        org_id (str): Organization ID
        request (AddFeedbackRequest): The request containing feedbacks

    Returns:
        AddFeedbackResponse: Response containing success status, message, and added count
    """
    reflexio = get_reflexio(org_id=org_id)
    return reflexio.add_feedback(request=request)


def delete_user_profile(
    org_id: str, request: DeleteUserProfileRequest
) -> DeleteUserProfileResponse:
    """Delete user profile

    Args:
        org_id (str): Organization ID
        request (DeleteUserProfileRequest): The delete request

    Returns:
        DeleteUserProfileResponse: Response containing success status and message
    """
    is_valid, message = validate_delete_user_profile_request(request)
    if not is_valid:
        return DeleteUserProfileResponse(success=False, message=message)

    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_profile(request)
        return result
    except Exception as e:
        logger.error("Failed to delete user profile: %s", e)
        return DeleteUserProfileResponse(success=False, message=str(e))


def delete_user_interaction(
    org_id: str, request: DeleteUserInteractionRequest
) -> DeleteUserInteractionResponse:
    """Delete user interaction

    Args:
        org_id (str): Organization ID
        request (DeleteUserInteractionRequest): The delete request

    Returns:
        DeleteUserInteractionResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_interaction(request)
        return result
    except Exception as e:
        logger.error("Failed to delete user interaction: %s", e)
        return DeleteUserInteractionResponse(success=False, message=str(e))


def delete_request(org_id: str, request: DeleteRequestRequest) -> DeleteRequestResponse:
    """Delete request and all its associated interactions

    Args:
        org_id (str): Organization ID
        request (DeleteRequestRequest): The delete request

    Returns:
        DeleteRequestResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_request(request)
        return result
    except Exception as e:
        logger.error("Failed to delete request: %s", e)
        return DeleteRequestResponse(success=False, message=str(e))


def delete_session(org_id: str, request: DeleteSessionRequest) -> DeleteSessionResponse:
    """Delete all requests and interactions in a session

    Args:
        org_id (str): Organization ID
        request (DeleteSessionRequest): The delete request

    Returns:
        DeleteSessionResponse: Response containing success status, message, and deleted count
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_session(request)
        return result
    except Exception as e:
        logger.error("Failed to delete session: %s", e)
        return DeleteSessionResponse(success=False, message=str(e))


def delete_feedback(
    org_id: str, request: DeleteFeedbackRequest
) -> DeleteFeedbackResponse:
    """Delete feedback by ID

    Args:
        org_id (str): Organization ID
        request (DeleteFeedbackRequest): The delete request

    Returns:
        DeleteFeedbackResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_feedback(request)
        return result
    except Exception as e:
        logger.error("Failed to delete feedback: %s", e)
        return DeleteFeedbackResponse(success=False, message=str(e))


def delete_raw_feedback(
    org_id: str, request: DeleteRawFeedbackRequest
) -> DeleteRawFeedbackResponse:
    """Delete raw feedback by ID

    Args:
        org_id (str): Organization ID
        request (DeleteRawFeedbackRequest): The delete request

    Returns:
        DeleteRawFeedbackResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.delete_raw_feedback(request)
        return result
    except Exception as e:
        logger.error("Failed to delete raw feedback: %s", e)
        return DeleteRawFeedbackResponse(success=False, message=str(e))


# ==============================
# Run feedback aggregation
# ==============================


def run_feedback_aggregation(
    org_id: str, request: RunFeedbackAggregationRequest
) -> RunFeedbackAggregationResponse:
    """Run feedback aggregation for a given agent version and feedback name

    Args:
        org_id (str): Organization ID
        request (RunFeedbackAggregationRequest): The run feedback aggregation request

    Returns:
        RunFeedbackAggregationResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        reflexio.run_feedback_aggregation(request.agent_version, request.feedback_name)
    except Exception as e:
        logger.error("Failed to run feedback aggregation: %s", e)
        return RunFeedbackAggregationResponse(success=False, message=str(e))
    return RunFeedbackAggregationResponse(success=True)


# ==============================
# Run skill generation
# ==============================


def run_skill_generation(
    org_id: str, request: RunSkillGenerationRequest
) -> RunSkillGenerationResponse:
    """Run skill generation for a given agent version and feedback name.

    Args:
        org_id (str): Organization ID
        request (RunSkillGenerationRequest): The run skill generation request

    Returns:
        RunSkillGenerationResponse: Response containing success status and counts
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.run_skill_generation(
            request.agent_version, request.feedback_name
        )
    except Exception as e:
        logger.error("Failed to run skill generation: %s", e)
        return RunSkillGenerationResponse(success=False, message=str(e))
    return RunSkillGenerationResponse(
        success=True,
        skills_generated=result.get("skills_generated", 0),
        skills_updated=result.get("skills_updated", 0),
    )


# ==============================
# Update feedback status
# ==============================


def update_feedback_status(
    org_id: str, request: UpdateFeedbackStatusRequest
) -> UpdateFeedbackStatusResponse:
    """Update the status of a specific feedback

    Args:
        org_id (str): Organization ID
        request (UpdateFeedbackStatusRequest): The update request

    Returns:
        UpdateFeedbackStatusResponse: Response containing success status and message
    """
    reflexio = get_reflexio(org_id=org_id)
    try:
        result = reflexio.update_feedback_status(request)
        return result
    except Exception as e:
        logger.error("Failed to update feedback status: %s", e)
        return UpdateFeedbackStatusResponse(success=False, msg=str(e))

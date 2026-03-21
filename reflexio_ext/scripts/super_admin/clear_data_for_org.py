from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.db import db_models
from reflexio.server.db.db_operations import db_session_context
from reflexio_commons.api_schema.service_schemas import (
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
)


def clear_organization_data(org_id: str):
    """
    Clear all data for a given organization.

    Args:
        org_id (str): The organization ID to clear data for
    """
    # Initialize storage
    storage = RequestContext(org_id=org_id).storage

    # Get all profiles and delete them
    profiles = storage.get_all_profiles()
    for profile in profiles:
        request = DeleteUserProfileRequest(
            user_id=profile.user_id, profile_id=profile.profile_id
        )
        storage.delete_user_profile(request)

    # Get all interactions and delete them
    interactions = storage.get_all_interactions()
    for interaction in interactions:
        request = DeleteUserInteractionRequest(
            user_id=interaction.user_id, interaction_id=interaction.interaction_id
        )
        storage.delete_user_interaction(request)

    # Delete all profile change logs for the organization
    storage.delete_all_profile_change_logs()

    # Delete all raw feedbacks and feedbacks
    storage.delete_all_raw_feedbacks()
    storage.delete_all_feedbacks()

    # Delete organization from database if it exists
    with db_session_context() as session:
        org = (
            session.query(db_models.Organization)
            .filter(db_models.Organization.id == org_id)
            .first()
        )
        if org:
            session.delete(org)
            session.commit()


if __name__ == "__main__":
    org_id = "3"  # Replace with the actual organization ID
    clear_organization_data(org_id)
    print(f"Successfully cleared all data for organization {org_id}")

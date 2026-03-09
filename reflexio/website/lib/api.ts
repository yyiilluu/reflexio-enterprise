import Cookies from "js-cookie"

// Use empty string to make requests relative (proxied through Next.js rewrites)
// This works both locally and in production deployments
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || ""
const SELF_HOST = process.env.NEXT_PUBLIC_SELF_HOST === "true"
const TOKEN_COOKIE_NAME = "reflexio_token"

// Helper function to get headers with optional authentication
function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  }

  // Only add authorization header if not in self-host mode
  if (!SELF_HOST) {
    const token = Cookies.get(TOKEN_COOKIE_NAME)
    if (token) {
      headers["Authorization"] = `Bearer ${token}`
    }
  }

  return headers
}

export type UserActionType = "click" | "scroll" | "type" | "none"

export type Status = "archived" | "pending" | null
// Alias for backwards compatibility
export type ProfileStatus = Status

export interface Interaction {
  interaction_id: string
  user_id: string
  request_id: string
  created_at: number
  role: string
  content: string
  user_action: UserActionType
  user_action_description: string
  interacted_image_url: string
  image_encoding: string
  shadow_content?: string
  tools_used?: { tool_name: string; tool_input: Record<string, any> }[]
  embedding: number[]
  shadow_redacted_content?: string
}

export interface UserProfile {
  profile_id: string
  user_id: string
  profile_content: string
  last_modified_timestamp: number
  generated_from_request_id: string
  profile_time_to_live: "one_day" | "one_week" | "one_month" | "one_quarter" | "one_year" | "infinity"
  expiration_timestamp: number
  custom_features?: Record<string, unknown>
  source: string
  status?: Status
  embedding: number[]
}

export interface GetUserProfilesRequest {
  user_id: string
  start_time?: string
  end_time?: string
  top_k?: number
}

export interface GetUserProfilesResponse {
  success: boolean
  user_profiles: UserProfile[]
  msg?: string
}

export async function getProfiles(request: GetUserProfilesRequest): Promise<GetUserProfilesResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_profiles`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching profiles:", error)
    throw error
  }
}

export async function getAllProfiles(limit: number = 100, statusFilter?: string): Promise<GetUserProfilesResponse> {
  try {
    const params = new URLSearchParams({ limit: limit.toString() })
    if (statusFilter) {
      params.append("status_filter", statusFilter)
    }

    const response = await fetch(`${API_BASE_URL}/api/get_all_profiles?${params.toString()}`, {
      method: "GET",
      headers: getHeaders(),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching all profiles:", error)
    throw error
  }
}

export interface ProfileStatistics {
  success: boolean
  current_count: number
  pending_count: number
  archived_count: number
  expiring_soon_count: number
  msg?: string
}

export async function getProfileStatistics(): Promise<ProfileStatistics> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_profile_statistics`, {
      method: "GET",
      headers: getHeaders(),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching profile statistics:", error)
    throw error
  }
}

export interface GetInteractionsRequest {
  user_id: string
  start_time?: string
  end_time?: string
  top_k?: number
}

export interface GetInteractionsResponse {
  success: boolean
  interactions: Interaction[]
  msg?: string
}

export async function getInteractions(request: GetInteractionsRequest): Promise<GetInteractionsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_interactions`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching interactions:", error)
    throw error
  }
}

export async function getAllInteractions(limit: number = 100): Promise<GetInteractionsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_all_interactions?limit=${limit}`, {
      method: "GET",
      headers: getHeaders(),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching all interactions:", error)
    throw error
  }
}

// Request and Session types
export interface Request {
  request_id: string
  user_id: string
  created_at: number
  source: string
  agent_version: string
  session_id: string
}

export interface RequestData {
  request: Request
  interactions: Interaction[]
}

export interface Session {
  session_id: string
  requests: RequestData[]
}

export interface GetRequestsRequest {
  user_id?: string
  request_id?: string
  session_id?: string
  start_time?: string
  end_time?: string
  top_k?: number
  offset?: number
}

export interface GetRequestsResponse {
  success: boolean
  sessions: Session[]
  has_more: boolean
  msg?: string
}

export async function getRequests(request: GetRequestsRequest): Promise<GetRequestsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_requests`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching requests:", error)
    throw error
  }
}

// Feedback types
export type FeedbackStatus = "pending" | "approved" | "rejected"

export interface BlockingIssue {
  kind: "missing_tool" | "permission_denied" | "external_dependency" | "policy_restriction"
  details: string
}

export interface RawFeedback {
  raw_feedback_id: number
  agent_version: string
  request_id: string
  feedback_name: string
  created_at: number
  feedback_content: string
  do_action?: string | null
  do_not_action?: string | null
  when_condition?: string | null
  blocking_issue?: BlockingIssue | null
  embedding: number[]
  status?: Status
  source?: string
}

export interface Feedback {
  feedback_id: number
  feedback_name: string
  agent_version: string
  created_at: number
  feedback_content: string
  do_action?: string | null
  do_not_action?: string | null
  when_condition?: string | null
  blocking_issue?: BlockingIssue | null
  feedback_status: FeedbackStatus
  feedback_metadata: string
  embedding: number[]
}

export interface GetRawFeedbacksRequest {
  limit?: number
  feedback_name?: string
  status_filter?: (Status | null)[]
}

export interface GetRawFeedbacksResponse {
  success: boolean
  raw_feedbacks: RawFeedback[]
  msg?: string
}

export interface GetFeedbacksRequest {
  limit?: number
  feedback_name?: string
}

export interface GetFeedbacksResponse {
  success: boolean
  feedbacks: Feedback[]
  msg?: string
}

export async function getRawFeedbacks(request: GetRawFeedbacksRequest): Promise<GetRawFeedbacksResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_raw_feedbacks`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching raw feedbacks:", error)
    throw error
  }
}

export async function getFeedbacks(request: GetFeedbacksRequest): Promise<GetFeedbacksResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_feedbacks`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching feedbacks:", error)
    throw error
  }
}

export interface UpdateFeedbackStatusRequest {
  feedback_id: number
  feedback_status: FeedbackStatus
}

export interface UpdateFeedbackStatusResponse {
  success: boolean
  msg?: string
}

export async function updateFeedbackStatus(
  request: UpdateFeedbackStatusRequest
): Promise<UpdateFeedbackStatusResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/update_feedback_status`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error updating feedback status:", error)
    throw error
  }
}

// Delete profile types
export interface DeleteUserProfileRequest {
  user_id: string
  profile_id?: string
  search_query?: string
}

export interface DeleteUserProfileResponse {
  success: boolean
  message?: string
}

export async function deleteProfile(request: DeleteUserProfileRequest): Promise<DeleteUserProfileResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_profile`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting profile:", error)
    throw error
  }
}

export interface DeleteUserInteractionRequest {
  user_id: string
  interaction_id: string
}

export interface DeleteUserInteractionResponse {
  success: boolean
  message?: string
}

export async function deleteInteraction(
  request: DeleteUserInteractionRequest
): Promise<DeleteUserInteractionResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_interaction`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting interaction:", error)
    throw error
  }
}

export interface DeleteRequestRequest {
  request_id: string
}

export interface DeleteRequestResponse {
  success: boolean
  message?: string
}

export async function deleteRequest(request: DeleteRequestRequest): Promise<DeleteRequestResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_request`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting request:", error)
    throw error
  }
}

export interface DeleteSessionRequest {
  session_id: string
}

export interface DeleteSessionResponse {
  success: boolean
  message?: string
  deleted_requests_count?: number
}

export async function deleteSession(
  request: DeleteSessionRequest
): Promise<DeleteSessionResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_session`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting session:", error)
    throw error
  }
}

// Dashboard stats types
export interface TimeSeriesDataPoint {
  timestamp: number
  value: number
}

export interface PeriodStats {
  total_profiles: number
  total_interactions: number
  total_feedbacks: number
  success_rate: number
}

export interface DashboardStats {
  current_period: PeriodStats
  previous_period: PeriodStats
  interactions_time_series: TimeSeriesDataPoint[]
  profiles_time_series: TimeSeriesDataPoint[]
  feedbacks_time_series: TimeSeriesDataPoint[]
  evaluations_time_series: TimeSeriesDataPoint[]
}

export interface GetDashboardStatsRequest {
  days_back?: number
}

export interface GetDashboardStatsResponse {
  success: boolean
  stats?: DashboardStats
  msg?: string
}

export async function getDashboardStats(
  request: GetDashboardStatsRequest = {}
): Promise<GetDashboardStatsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_dashboard_stats`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching dashboard stats:", error)
    throw error
  }
}

// Agent success evaluation types
export type RegularVsShadow =
  | "regular_is_better"
  | "regular_is_slightly_better"
  | "shadow_is_better"
  | "shadow_is_slightly_better"
  | "tied"

export interface AgentSuccessEvaluationResult {
  result_id: number
  agent_version: string
  session_id: string
  evaluation_name?: string | null
  is_success: boolean
  failure_type: string
  failure_reason: string
  agent_prompt_update: string
  created_at: number
  embedding: number[]
  regular_vs_shadow?: RegularVsShadow | null
}

export interface GetAgentSuccessEvaluationResultsRequest {
  limit?: number
  agent_version?: string | null
}

export interface GetAgentSuccessEvaluationResultsResponse {
  success: boolean
  agent_success_evaluation_results: AgentSuccessEvaluationResult[]
  msg?: string
}

export async function getAgentSuccessEvaluationResults(
  request: GetAgentSuccessEvaluationResultsRequest = {}
): Promise<GetAgentSuccessEvaluationResultsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_agent_success_evaluation_results`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching agent success evaluation results:", error)
    throw error
  }
}

// Config types (simplified for API layer)
export interface ConfigResponse {
  [key: string]: any
}

export async function getConfig(): Promise<ConfigResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_config`, {
      method: "GET",
      headers: getHeaders(),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching config:", error)
    throw error
  }
}

export interface SetConfigResponse {
  success: boolean
  msg?: string
}

export async function setConfig(config: ConfigResponse): Promise<SetConfigResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/set_config`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(config),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error setting config:", error)
    throw error
  }
}

// Profile upgrade/downgrade types
export interface UpgradeProfilesResponse {
  success: boolean
  profiles_archived: number
  profiles_promoted: number
  profiles_deleted: number
  message?: string
}

export interface DowngradeProfilesResponse {
  success: boolean
  profiles_demoted: number
  profiles_restored: number
  message?: string
}

export async function upgradeAllProfiles(onlyAffectedUsers: boolean = false): Promise<UpgradeProfilesResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/upgrade_all_profiles`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({
        user_id: "",  // Not used but required by schema
        only_affected_users: onlyAffectedUsers
      }),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error upgrading all profiles:", error)
    throw error
  }
}

export async function downgradeAllProfiles(onlyAffectedUsers: boolean = false): Promise<DowngradeProfilesResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/downgrade_all_profiles`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({
        user_id: "",  // Not used but required by schema
        only_affected_users: onlyAffectedUsers
      }),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error downgrading all profiles:", error)
    throw error
  }
}

// Raw feedback upgrade/downgrade types
export interface UpgradeRawFeedbacksRequest {
  agent_version?: string
  feedback_name?: string
  archive_current?: boolean
}

export interface UpgradeRawFeedbacksResponse {
  success: boolean
  raw_feedbacks_archived: number
  raw_feedbacks_promoted: number
  raw_feedbacks_deleted: number
  message?: string
}

export interface DowngradeRawFeedbacksRequest {
  agent_version?: string
  feedback_name?: string
}

export interface DowngradeRawFeedbacksResponse {
  success: boolean
  raw_feedbacks_demoted: number
  raw_feedbacks_restored: number
  message?: string
}

export async function upgradeAllRawFeedbacks(
  request: UpgradeRawFeedbacksRequest = {}
): Promise<UpgradeRawFeedbacksResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/upgrade_all_raw_feedbacks`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error upgrading all raw feedbacks:", error)
    throw error
  }
}

export async function downgradeAllRawFeedbacks(
  request: DowngradeRawFeedbacksRequest = {}
): Promise<DowngradeRawFeedbacksResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/downgrade_all_raw_feedbacks`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error downgrading all raw feedbacks:", error)
    throw error
  }
}

// Rerun profile generation types
export interface RerunProfileGenerationRequest {
  user_id?: string
  start_time?: string
  end_time?: string
  source?: string
  extractor_names?: string[]
}

export interface RerunProfileGenerationResponse {
  success: boolean
  msg?: string
  profiles_generated?: number
  operation_id?: string
}

export async function rerunProfileGeneration(
  request: RerunProfileGenerationRequest
): Promise<RerunProfileGenerationResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/rerun_profile_generation`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error rerunning profile generation:", error)
    throw error
  }
}

export interface RerunFeedbackGenerationRequest {
  agent_version: string
  start_time?: string
  end_time?: string
  feedback_name?: string
}

export interface RerunFeedbackGenerationResponse {
  success: boolean
  msg?: string
  feedbacks_generated?: number
  operation_id?: string
}

export async function rerunFeedbackGeneration(
  request: RerunFeedbackGenerationRequest
): Promise<RerunFeedbackGenerationResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/rerun_feedback_generation`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error rerunning feedback generation:", error)
    throw error
  }
}

// Run feedback aggregation types
export interface RunFeedbackAggregationRequest {
  agent_version: string
  feedback_name: string
}

export interface RunFeedbackAggregationResponse {
  success: boolean
  message: string
}

export async function runFeedbackAggregation(
  request: RunFeedbackAggregationRequest
): Promise<RunFeedbackAggregationResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/run_feedback_aggregation`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error running feedback aggregation:", error)
    throw error
  }
}

// Delete feedback types
export interface DeleteFeedbackRequest {
  feedback_id: number
}

export interface DeleteFeedbackResponse {
  success: boolean
  message?: string
}

export async function deleteFeedback(request: DeleteFeedbackRequest): Promise<DeleteFeedbackResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_feedback`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting feedback:", error)
    throw error
  }
}

// Delete raw feedback types
export interface DeleteRawFeedbackRequest {
  raw_feedback_id: number
}

export interface DeleteRawFeedbackResponse {
  success: boolean
  message?: string
}

export async function deleteRawFeedback(request: DeleteRawFeedbackRequest): Promise<DeleteRawFeedbackResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_raw_feedback`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting raw feedback:", error)
    throw error
  }
}

// Operation status types
export type OperationStatus = "in_progress" | "completed" | "failed" | "cancelled"

export interface OperationStatusInfo {
  service_name: string
  status: OperationStatus
  started_at: number
  completed_at?: number
  total_users: number
  processed_users: number
  failed_users: number
  current_user_id?: string
  processed_user_ids: string[]
  failed_user_ids: { user_id: string; error: string }[]
  request_params: Record<string, any>
  stats: Record<string, any>
  error_message?: string
  progress_percentage: number
}

export interface GetOperationStatusResponse {
  success: boolean
  operation_status?: OperationStatusInfo
  msg?: string
}

export async function getOperationStatus(
  serviceName: string = "rerun_profile_generation"
): Promise<GetOperationStatusResponse> {
  try {
    const params = new URLSearchParams({ service_name: serviceName })
    const response = await fetch(`${API_BASE_URL}/api/get_operation_status?${params.toString()}`, {
      method: "GET",
      headers: getHeaders(),
    })

    // Handle 404 gracefully - no operation found is a valid state
    if (response.status === 404) {
      return {
        success: true,
        operation_status: undefined,
      }
    }

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error getting operation status:", error)
    throw error
  }
}

export interface CancelOperationResponse {
  success: boolean
  cancelled_services: string[]
  msg?: string
}

export async function cancelOperation(
  serviceName?: string
): Promise<CancelOperationResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/cancel_operation`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ service_name: serviceName ?? null }),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error cancelling operation:", error)
    throw error
  }
}

// Skill types
export type SkillStatus = "draft" | "published" | "deprecated"

export interface Skill {
  skill_id: number
  skill_name: string
  description: string
  version: string
  agent_version: string
  feedback_name: string
  instructions: string
  allowed_tools: string[]
  blocking_issues: BlockingIssue[]
  raw_feedback_ids: number[]
  skill_status: SkillStatus
  created_at: number
  updated_at: number
}

export interface GetSkillsRequest {
  limit?: number
  feedback_name?: string
  agent_version?: string
  skill_status?: SkillStatus
}

export interface GetSkillsResponse {
  success: boolean
  skills: Skill[]
  msg?: string
}

export interface SearchSkillsRequest {
  query?: string
  feedback_name?: string
  agent_version?: string
  skill_status?: SkillStatus
  threshold?: number
  top_k?: number
}

export interface SearchSkillsResponse {
  success: boolean
  skills: Skill[]
  msg?: string
}

export interface UpdateSkillStatusRequest {
  skill_id: number
  skill_status: SkillStatus
}

export interface UpdateSkillStatusResponse {
  success: boolean
  message?: string
}

export interface DeleteSkillRequest {
  skill_id: number
}

export interface DeleteSkillResponse {
  success: boolean
  message?: string
}

export interface ExportSkillsRequest {
  feedback_name?: string
  agent_version?: string
  skill_status?: SkillStatus
}

export interface ExportSkillsResponse {
  success: boolean
  markdown: string
}

export interface RunSkillGenerationRequest {
  agent_version: string
  feedback_name: string
}

export interface RunSkillGenerationResponse {
  success: boolean
  message: string
  skills_generated: number
  skills_updated: number
}

export async function getSkills(request: GetSkillsRequest): Promise<GetSkillsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/get_skills`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching skills:", error)
    throw error
  }
}

export async function searchSkills(request: SearchSkillsRequest): Promise<SearchSkillsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/search_skills`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error searching skills:", error)
    throw error
  }
}

export async function updateSkillStatus(
  request: UpdateSkillStatusRequest
): Promise<UpdateSkillStatusResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/update_skill_status`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error updating skill status:", error)
    throw error
  }
}

export async function deleteSkill(request: DeleteSkillRequest): Promise<DeleteSkillResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/delete_skill`, {
      method: "DELETE",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error deleting skill:", error)
    throw error
  }
}

export async function exportSkills(request: ExportSkillsRequest): Promise<ExportSkillsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/export_skills`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error exporting skills:", error)
    throw error
  }
}

export async function runSkillGeneration(
  request: RunSkillGenerationRequest
): Promise<RunSkillGenerationResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/run_skill_generation`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error("Error running skill generation:", error)
    throw error
  }
}

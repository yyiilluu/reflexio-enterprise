"use client"

import { useState, useMemo, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Users,
  Clock,
  AlertCircle,
  FileText,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  Pencil,
  Save,
  XCircle,
  Calendar,
  Loader2,
  RefreshCw,
  Trash2,
  CheckCircle2,
  Archive,
  CheckCircle,
  RotateCcw,
} from "lucide-react"
import { getProfiles, getAllProfiles, deleteProfile, getProfileStatistics, upgradeAllProfiles, downgradeAllProfiles, rerunProfileGeneration, getOperationStatus, cancelOperation, type UserProfile as ApiUserProfile, type ProfileStatistics, type Status, type OperationStatusInfo } from "@/lib/api"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"

// Types matching the UserProfile schema
type ProfileTimeToLive = "one_day" | "one_week" | "one_month" | "one_quarter" | "one_year" | "infinity"

interface UserProfile extends ApiUserProfile {
  profile_time_to_live: ProfileTimeToLive
}

// Helper function to format timestamp
const formatTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp * 1000)
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

// Helper function to get relative time
const getRelativeTime = (timestamp: number): string => {
  const now = Date.now() / 1000
  const diff = now - timestamp

  if (diff < 60) return "Just now"
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// Helper function to format TTL
const formatTTL = (ttl: ProfileTimeToLive): string => {
  return ttl.split("_").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")
}

// Helper function to check if profile is expiring soon (within 7 days)
const isExpiringSoon = (expirationTimestamp: number): boolean => {
  const now = Date.now() / 1000
  const sevenDays = 7 * 24 * 60 * 60
  return expirationTimestamp !== 4102444800 && expirationTimestamp - now < sevenDays && expirationTimestamp > now
}

// Helper function to check if profile is expired
const isExpired = (expirationTimestamp: number): boolean => {
  const now = Date.now() / 1000
  return expirationTimestamp !== 4102444800 && expirationTimestamp < now
}

// Profile row component
interface ProfileRowProps {
  profile: UserProfile
  onEdit: (profile: UserProfile) => void
  onDelete: (profile: UserProfile) => void
  isEditing: boolean
  editedProfile: UserProfile | null
  onSave: () => void
  onCancel: () => void
  onUpdateField: (field: keyof UserProfile, value: unknown) => void
  customFeaturesJson: string
  setCustomFeaturesJson: (value: string) => void
  jsonError: string
  setJsonError: (error: string) => void
}

function ProfileRow({
  profile,
  onEdit,
  onDelete,
  isEditing,
  editedProfile,
  onSave,
  onCancel,
  onUpdateField,
  customFeaturesJson,
  setCustomFeaturesJson,
  jsonError,
  setJsonError,
}: ProfileRowProps) {
  const [expanded, setExpanded] = useState(false)
  const expired = isExpired(profile.expiration_timestamp)
  const expiringSoon = isExpiringSoon(profile.expiration_timestamp)

  return (
    <div className="hover:bg-slate-50/50 transition-colors">
      <div
        className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors ${expired ? "opacity-60" : ""}`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* Status Icon */}
            <div className="flex-shrink-0">
              {expired ? (
                <div className="h-8 w-8 rounded-lg bg-red-100 flex items-center justify-center">
                  <XCircle className="h-4 w-4 text-red-600" />
                </div>
              ) : expiringSoon ? (
                <div className="h-8 w-8 rounded-lg bg-amber-100 flex items-center justify-center">
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                </div>
              ) : (
                <div className="h-8 w-8 rounded-lg bg-purple-100 flex items-center justify-center">
                  <FileText className="h-4 w-4 text-purple-600" />
                </div>
              )}
            </div>

            {/* Main Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                  Profile
                </span>
                <span className="font-semibold text-sm font-mono text-slate-800">
                  {profile.profile_id}
                </span>
                <Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
                  <Users className="h-3 w-3 mr-1" />
                  {profile.user_id}
                </Badge>
                <Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
                  {profile.source}
                </Badge>
                {profile.status === "pending" && (
                  <Badge className="text-xs bg-amber-100 text-amber-700 hover:bg-amber-100">
                    <Clock className="h-3 w-3 mr-1" />
                    Pending
                  </Badge>
                )}
                {profile.status === "archived" && (
                  <Badge className="text-xs bg-slate-200 text-slate-700 hover:bg-slate-200">
                    <Archive className="h-3 w-3 mr-1" />
                    Archived
                  </Badge>
                )}
                {expired && (
                  <Badge className="text-xs bg-red-100 text-red-700 hover:bg-red-100">
                    Expired
                  </Badge>
                )}
                {expiringSoon && !expired && (
                  <Badge className="text-xs bg-amber-100 text-amber-700 hover:bg-amber-100">
                    Expiring Soon
                  </Badge>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-1 truncate">
                {profile.profile_content}
              </p>
            </div>
          </div>

          {/* Right side: TTL, time and expand button */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="text-right">
              <Badge variant="outline" className="text-xs mb-1 border-slate-200 text-slate-600">
                {formatTTL(profile.profile_time_to_live)}
              </Badge>
              <p className="text-xs text-slate-400">{getRelativeTime(profile.last_modified_timestamp)}</p>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit(profile)
                  setExpanded(true)
                }}
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(profile)
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600">
                {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-slate-100 p-4 space-y-4">
          {isEditing && editedProfile ? (
            /* Edit Mode */
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-800">Edit Profile</h3>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={onCancel} className="border-slate-200 text-slate-700 hover:bg-slate-100">
                    <XCircle className="h-4 w-4 mr-1" />
                    Cancel
                  </Button>
                  <Button variant="default" size="sm" onClick={onSave} className="bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 border-0">
                    <Save className="h-4 w-4 mr-1" />
                    Save Changes
                  </Button>
                </div>
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                {/* Left Column */}
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-semibold mb-2 block text-slate-700">Profile Content</label>
                    <textarea
                      value={editedProfile.profile_content}
                      onChange={(e) => onUpdateField("profile_content", e.target.value)}
                      className="flex min-h-[120px] w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300 resize-none"
                      placeholder="Enter profile content..."
                    />
                  </div>

                  <div>
                    <label className="text-sm font-semibold mb-2 block text-slate-700">Custom Features (JSON)</label>
                    <textarea
                      value={customFeaturesJson}
                      onChange={(e) => {
                        setCustomFeaturesJson(e.target.value)
                        setJsonError("")
                      }}
                      className={`flex min-h-[120px] w-full rounded-lg border ${
                        jsonError ? "border-red-300" : "border-slate-200"
                      } bg-white px-3 py-2 text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300 resize-none`}
                      placeholder='{"key": "value"}'
                    />
                    {jsonError && <p className="text-sm text-red-500 mt-1">{jsonError}</p>}
                    <p className="text-xs text-slate-500 mt-1">
                      Enter a valid JSON object. Use {"{}"} for no custom features.
                    </p>
                  </div>
                </div>

                {/* Right Column */}
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-semibold mb-2 block text-slate-700">Time To Live</label>
                    <select
                      value={editedProfile.profile_time_to_live}
                      onChange={(e) => onUpdateField("profile_time_to_live", e.target.value as ProfileTimeToLive)}
                      className="flex h-10 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
                    >
                      <option value="one_day">One Day</option>
                      <option value="one_week">One Week</option>
                      <option value="one_month">One Month</option>
                      <option value="one_quarter">One Quarter</option>
                      <option value="one_year">One Year</option>
                      <option value="infinity">Infinity</option>
                    </select>
                  </div>

                  <div>
                    <h4 className="text-sm font-semibold mb-3 text-slate-700">Read-Only Details</h4>
                    <div className="space-y-2 bg-slate-50 p-3 rounded-lg">
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Profile ID:</span>
                        <span className="font-mono text-xs text-slate-700">{editedProfile.profile_id}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">User ID:</span>
                        <span className="text-slate-700">{editedProfile.user_id}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Source:</span>
                        <span className="text-slate-700">{editedProfile.source}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Request ID:</span>
                        <span className="font-mono text-xs text-slate-700">{editedProfile.generated_from_request_id}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* View Mode */
            <div className="grid gap-6 md:grid-cols-2">
              {/* Left Column */}
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold mb-2 text-slate-800">Profile Content</h4>
                  <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg">
                    {profile.profile_content}
                  </p>
                </div>

                {profile.custom_features && (
                  <div>
                    <h4 className="text-sm font-semibold mb-2 text-slate-800">Custom Features</h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(profile.custom_features).map(([key, value]) => (
                        <Badge key={key} className="text-xs bg-purple-100 text-purple-700 hover:bg-purple-100">
                          {key}: {String(value)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column */}
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold mb-3 text-slate-800">Details</h4>
                  <div className="space-y-2 bg-slate-50 p-3 rounded-lg">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Profile ID:</span>
                      <span className="font-mono text-xs text-slate-700">{profile.profile_id}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">User ID:</span>
                      <span className="text-slate-700">{profile.user_id}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Source:</span>
                      <span className="text-slate-700">{profile.source}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Request ID:</span>
                      <span className="font-mono text-xs text-slate-700">{profile.generated_from_request_id}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Last Modified:</span>
                      <span className="text-xs text-slate-700">{formatTimestamp(profile.last_modified_timestamp)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Expires:</span>
                      <span className="text-xs text-slate-700">
                        {profile.expiration_timestamp === 4102444800
                          ? "Never (∞)"
                          : formatTimestamp(profile.expiration_timestamp)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<UserProfile[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedUser, setSelectedUser] = useState<string>("all")
  const [selectedSource, setSelectedSource] = useState<string>("all")
  const [selectedTTL, setSelectedTTL] = useState<string>("all")
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null)
  const [editedProfile, setEditedProfile] = useState<UserProfile | null>(null)
  const [customFeaturesJson, setCustomFeaturesJson] = useState<string>("")
  const [jsonError, setJsonError] = useState<string>("")

  // API-related state
  const [userId, setUserId] = useState<string>("")
  const [topK, setTopK] = useState<number>(100)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>("")

  // Delete confirmation state
  const [profileToDelete, setProfileToDelete] = useState<UserProfile | null>(null)
  const [deleting, setDeleting] = useState<boolean>(false)

  // Status tab and statistics state
  const [activeStatusTab, setActiveStatusTab] = useState<"current" | "archived" | "pending">("current")
  const [profileStatistics, setProfileStatistics] = useState<ProfileStatistics | null>(null)

  // Upgrade/Downgrade state
  const [upgrading, setUpgrading] = useState<boolean>(false)
  const [downgrading, setDowngrading] = useState<boolean>(false)
  const [upgradeScope, setUpgradeScope] = useState<"affected" | "all">("affected")
  const [downgradeScope, setDowngradeScope] = useState<"affected" | "all">("affected")

  // Rerun profile generation state
  const [showRerunModal, setShowRerunModal] = useState<boolean>(false)
  const [rerunning, setRerunning] = useState<boolean>(false)
  const [rerunStartDate, setRerunStartDate] = useState<string>("")
  const [rerunEndDate, setRerunEndDate] = useState<string>("")
  const [rerunSource, setRerunSource] = useState<string>("")
  const [selectedExtractorNames, setSelectedExtractorNames] = useState<string[]>([])

  // Operation status state
  const [operationStatus, setOperationStatus] = useState<OperationStatusInfo | null>(null)
  const [showOperationBanner, setShowOperationBanner] = useState<boolean>(true)
  const [shouldPollStatus, setShouldPollStatus] = useState<boolean>(false)

  // Confirmation modal state
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false)
  const [confirmModalConfig, setConfirmModalConfig] = useState<{
    title: string
    description: string
    confirmText: string
    confirmAction: () => void
    variant?: "default" | "destructive"
    modalType?: "upgrade" | "downgrade" | "other"
  } | null>(null)

  // Message modal state
  const [showMessageModal, setShowMessageModal] = useState<boolean>(false)
  const [messageModalConfig, setMessageModalConfig] = useState<{
    title: string
    message: string
    type: "success" | "error"
  } | null>(null)

  // Fetch profiles from API based on status
  const fetchProfiles = async (searchUserId: string, limit: number, status: "current" | "archived" | "pending") => {
    setLoading(true)
    setError("")

    try {
      let response

      // If user_id is provided, fetch profiles for that user
      if (searchUserId.trim()) {
        response = await getProfiles({
          user_id: searchUserId.trim(),
          top_k: limit,
        })

        // Filter by status client-side for user-specific queries
        if (response.success) {
          response.user_profiles = response.user_profiles.filter(profile => {
            if (status === "current") {
              return !profile.status || profile.status === null
            } else if (status === "pending") {
              return profile.status === "pending"
            } else if (status === "archived") {
              return profile.status === "archived"
            }
            return true
          })
        }
      } else {
        // If no user_id, fetch all profiles with status filter
        response = await getAllProfiles(limit, status)
      }

      if (response.success) {
        setProfiles(response.user_profiles as UserProfile[])
        setError("")
      } else {
        setError(response.msg || "Failed to fetch profiles")
        setProfiles([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred while fetching profiles")
      setProfiles([])
    } finally {
      setLoading(false)
    }
  }

  // Debounced search effect - auto-fetch when userId, topK, or activeStatusTab changes
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchProfiles(userId, topK, activeStatusTab)
    }, 1000)

    return () => clearTimeout(timer)
  }, [userId, topK, activeStatusTab])

  // Initial load - fetch all profiles immediately on mount
  useEffect(() => {
    fetchProfiles("", topK, "current")
  }, [])

  // Fetch profile statistics on mount
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const stats = await getProfileStatistics()
        if (stats.success) {
          setProfileStatistics(stats)
        }
      } catch (err) {
        console.error("Failed to fetch statistics:", err)
      }
    }
    fetchStats()
  }, [])

  // Check for in-progress operation on mount (e.g., if user refreshes during operation)
  useEffect(() => {
    const checkInitialOperationStatus = async () => {
      try {
        const response = await getOperationStatus("profile_generation")
        if (response.success && response.operation_status) {
          setOperationStatus(response.operation_status)
          // If there's an in-progress operation, start polling
          if (response.operation_status.status === "in_progress") {
            setShouldPollStatus(true)
          }
        }
      } catch (err) {
        console.error("Failed to check initial operation status:", err)
      }
    }
    checkInitialOperationStatus()
  }, [])

  // Poll for operation status - only when shouldPollStatus is true
  useEffect(() => {
    // Don't poll if not needed
    if (!shouldPollStatus) {
      return
    }

    let previousStatus: string | null = operationStatus?.status || null

    const checkOperationStatus = async () => {
      try {
        const response = await getOperationStatus("profile_generation")
        if (response.success && response.operation_status) {
          const status = response.operation_status

          // Show toast when operation transitions from in_progress to completed/failed/cancelled
          if (previousStatus === "in_progress" && status.status === "completed") {
            setMessageModalConfig({
              title: "Profile Generation Completed",
              message: `Successfully processed ${status.processed_users}/${status.total_users} users. ${status.stats.total_profiles_generated || 0} profiles generated.`,
              type: "success"
            })
            setShowMessageModal(true)
            setShowOperationBanner(true) // Re-show banner for final status
            // Refresh profiles after completion
            fetchProfiles(userId, topK, activeStatusTab)
            fetchProfileStatistics()
            // Stop polling since operation is complete
            setShouldPollStatus(false)
          } else if (previousStatus === "in_progress" && status.status === "cancelled") {
            setMessageModalConfig({
              title: "Profile Generation Cancelled",
              message: `Operation was cancelled after processing ${status.processed_users}/${status.total_users} users.`,
              type: "success"
            })
            setShowMessageModal(true)
            setShowOperationBanner(false)
            // Refresh profiles after cancellation
            fetchProfiles(userId, topK, activeStatusTab)
            fetchProfileStatistics()
            setShouldPollStatus(false)
          } else if (previousStatus === "in_progress" && status.status === "failed") {
            setMessageModalConfig({
              title: "Profile Generation Failed",
              message: status.error_message || "An error occurred during profile generation",
              type: "error"
            })
            setShowMessageModal(true)
            setShowOperationBanner(true) // Re-show banner for final status
            // Stop polling since operation failed
            setShouldPollStatus(false)
          } else if (status.status !== "in_progress") {
            // If status is not in_progress (completed/failed/cancelled), stop polling
            setShouldPollStatus(false)
          }

          previousStatus = status.status
          setOperationStatus(status)
        } else {
          // No operation found, stop polling and clear status
          previousStatus = null
          setOperationStatus(null)
          setShouldPollStatus(false)
        }
      } catch (err) {
        console.error("Failed to check operation status:", err)
      }
    }

    // Check immediately when polling starts
    checkOperationStatus()

    // Poll every 3 seconds while shouldPollStatus is true
    const intervalId = setInterval(() => {
      checkOperationStatus()
    }, 3000)

    return () => clearInterval(intervalId)
  }, [shouldPollStatus]) // Only depend on shouldPollStatus

  // Helper to fetch profile statistics
  const fetchProfileStatistics = async () => {
    try {
      const stats = await getProfileStatistics()
      if (stats.success) {
        setProfileStatistics(stats)
      }
    } catch (err) {
      console.error("Failed to fetch statistics:", err)
    }
  }

  // Calculate statistics
  const totalProfiles = profiles.length
  const activeProfiles = profiles.filter((p) => !isExpired(p.expiration_timestamp)).length
  const expiringSoonCount = profiles.filter((p) => isExpiringSoon(p.expiration_timestamp)).length
  const recentProfiles = profiles.filter((p) => {
    const dayAgo = Date.now() / 1000 - 24 * 60 * 60
    return p.last_modified_timestamp > dayAgo
  }).length

  // Get unique values for filters
  const uniqueUsers = useMemo(() => {
    return Array.from(new Set(profiles.map((p) => p.user_id))).sort()
  }, [profiles])

  const uniqueSources = useMemo(() => {
    return Array.from(new Set(profiles.map((p) => p.source || "(empty)"))).sort()
  }, [profiles])

  const uniqueTTLs = useMemo(() => {
    return Array.from(new Set(profiles.map((p) => p.profile_time_to_live))).sort()
  }, [profiles])

  // Filter profiles (status filtering is now done server-side)
  const filteredProfiles = useMemo(() => {
    return profiles.filter((profile) => {
      const matchesSearch =
        searchQuery === "" ||
        profile.profile_content.toLowerCase().includes(searchQuery.toLowerCase()) ||
        profile.profile_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        profile.user_id.toLowerCase().includes(searchQuery.toLowerCase())

      const matchesUser = selectedUser === "all" || profile.user_id === selectedUser
      const matchesSource = selectedSource === "all" || (profile.source || "(empty)") === selectedSource
      const matchesTTL = selectedTTL === "all" || profile.profile_time_to_live === selectedTTL

      return matchesSearch && matchesUser && matchesSource && matchesTTL
    })
  }, [profiles, searchQuery, selectedUser, selectedSource, selectedTTL])

  const startEdit = (profile: UserProfile) => {
    setEditingProfileId(profile.profile_id)
    setEditedProfile({ ...profile })
    setCustomFeaturesJson(profile.custom_features ? JSON.stringify(profile.custom_features, null, 2) : "{}")
    setJsonError("")
  }

  const saveEdit = () => {
    if (editedProfile) {
      try {
        const parsedFeatures =
          customFeaturesJson.trim() === "" || customFeaturesJson.trim() === "{}"
            ? undefined
            : JSON.parse(customFeaturesJson)

        const updatedProfile = {
          ...editedProfile,
          custom_features: parsedFeatures,
        }

        setProfiles(profiles.map((p) => (p.profile_id === updatedProfile.profile_id ? updatedProfile : p)))
        setEditingProfileId(null)
        setEditedProfile(null)
        setCustomFeaturesJson("")
        setJsonError("")
      } catch (error) {
        setJsonError("Invalid JSON format. Please fix the JSON before saving.")
      }
    }
  }

  const cancelEdit = () => {
    setEditingProfileId(null)
    setEditedProfile(null)
    setCustomFeaturesJson("")
    setJsonError("")
  }

  const updateEditedField = (field: keyof UserProfile, value: unknown) => {
    if (editedProfile) {
      setEditedProfile({
        ...editedProfile,
        [field]: value,
      })
    }
  }

  const handleDeleteClick = (profile: UserProfile) => {
    setProfileToDelete(profile)
  }

  const confirmDelete = async () => {
    if (!profileToDelete) return

    setDeleting(true)
    setError("")

    try {
      const response = await deleteProfile({
        user_id: profileToDelete.user_id,
        profile_id: profileToDelete.profile_id,
      })

      if (response.success) {
        // Remove the deleted profile from the list
        setProfiles(profiles.filter((p) => p.profile_id !== profileToDelete.profile_id))
        setProfileToDelete(null)
        // Optionally refetch to ensure sync
        await fetchProfiles(userId, topK, activeStatusTab)
      } else {
        setError(response.message || "Failed to delete profile")
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred while deleting the profile")
    } finally {
      setDeleting(false)
    }
  }

  const cancelDelete = () => {
    setProfileToDelete(null)
  }

  // Refresh statistics after upgrade/downgrade
  const refreshData = async () => {
    try {
      const stats = await getProfileStatistics()
      if (stats.success) {
        setProfileStatistics(stats)
      }
      await fetchProfiles(userId, topK, activeStatusTab)
    } catch (err) {
      console.error("Failed to refresh data:", err)
    }
  }

  const handleUpgradeAllProfiles = async () => {
    setUpgrading(true)
    setError("")

    try {
      const onlyAffectedUsers = upgradeScope === "affected"
      const response = await upgradeAllProfiles(onlyAffectedUsers)

      if (response.success) {
        setMessageModalConfig({
          title: "Profiles Upgraded Successfully",
          message: `${response.message}\n\nArchived: ${response.profiles_archived}\nPromoted: ${response.profiles_promoted}\nDeleted: ${response.profiles_deleted}`,
          type: "success"
        })
        setShowMessageModal(true)
        await refreshData()
      } else {
        setError(response.message || "Failed to upgrade profiles")
        setMessageModalConfig({
          title: "Failed to Upgrade Profiles",
          message: response.message || "An error occurred",
          type: "error"
        })
        setShowMessageModal(true)
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "An unexpected error occurred"
      setError(errorMsg)
      setMessageModalConfig({
        title: "Error Upgrading Profiles",
        message: errorMsg,
        type: "error"
      })
      setShowMessageModal(true)
    } finally {
      setUpgrading(false)
    }
  }

  const confirmUpgradeAllProfiles = () => {
    setConfirmModalConfig({
      title: "Adopt All Pending Profiles?",
      description: "This will:\n• Archive all current profiles\n• Promote all pending profiles to current\n• Delete old archived profiles\n\nThis action cannot be undone.",
      confirmText: "Adopt Pending Profiles",
      confirmAction: handleUpgradeAllProfiles,
      variant: "default",
      modalType: "upgrade"
    })
    setShowConfirmModal(true)
  }

  const handleDowngradeAllProfiles = async () => {
    setDowngrading(true)
    setError("")

    try {
      const onlyAffectedUsers = downgradeScope === "affected"
      const response = await downgradeAllProfiles(onlyAffectedUsers)

      if (response.success) {
        setMessageModalConfig({
          title: "Profiles Restored Successfully",
          message: `${response.message}\n\nDemoted: ${response.profiles_demoted}\nRestored: ${response.profiles_restored}`,
          type: "success"
        })
        setShowMessageModal(true)
        await refreshData()
      } else {
        setError(response.message || "Failed to restore profiles")
        setMessageModalConfig({
          title: "Failed to Restore Profiles",
          message: response.message || "An error occurred",
          type: "error"
        })
        setShowMessageModal(true)
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "An unexpected error occurred"
      setError(errorMsg)
      setMessageModalConfig({
        title: "Error Restoring Profiles",
        message: errorMsg,
        type: "error"
      })
      setShowMessageModal(true)
    } finally {
      setDowngrading(false)
    }
  }

  const confirmDowngradeAllProfiles = () => {
    setConfirmModalConfig({
      title: "Restore All Archived Profiles?",
      description: "This will:\n• Demote all current profiles to archived\n• Restore all archived profiles to current\n\nThis action cannot be undone.",
      confirmText: "Restore Archived Profiles",
      confirmAction: handleDowngradeAllProfiles,
      variant: "default",
      modalType: "downgrade"
    })
    setShowConfirmModal(true)
  }

  const handleRerunProfileGeneration = async () => {
    setRerunning(true)
    setError("")

    try {
      // Convert date strings to ISO format if provided
      const startTime = rerunStartDate ? new Date(rerunStartDate).toISOString() : undefined
      const endTime = rerunEndDate ? new Date(rerunEndDate).toISOString() : undefined

      // Use selected extractor names if any are selected
      const extractorNames = selectedExtractorNames.length > 0 ? selectedExtractorNames : undefined

      // Fire the API call without awaiting - it will run in the background
      rerunProfileGeneration({
        user_id: userId.trim() || undefined,
        start_time: startTime,
        end_time: endTime,
        source: rerunSource.trim() || undefined,
        extractor_names: extractorNames,
      }).catch((err) => {
        // Log errors but don't show to user since modal is already closed
        console.error("Background profile generation error:", err)
      })

      // Close modal immediately and show success message
      setShowRerunModal(false)
      setMessageModalConfig({
        title: "Profile Generation Started",
        message: "Profile generation has been started in the background. You can continue using the app while it processes.",
        type: "success"
      })
      setShowMessageModal(true)

      // Start polling for operation status after a short delay
      // This gives the backend time to create the operation status entry
      setTimeout(() => {
        setShouldPollStatus(true)
      }, 1500)

      // Reset modal fields
      setRerunStartDate("")
      setRerunEndDate("")
      setRerunSource("")
      setSelectedExtractorNames([])
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "An unexpected error occurred"
      setError(errorMsg)
      setMessageModalConfig({
        title: "Error Starting Profile Generation",
        message: errorMsg,
        type: "error"
      })
      setShowMessageModal(true)
    } finally {
      setRerunning(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
        <div className="p-8">
          <div className="max-w-[1800px] mx-auto">
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/25">
                <Users className="h-5 w-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-800">User Profiles</h1>
            </div>
            <p className="text-slate-500 mt-1 ml-13">
              View and manage all user profiles or search by user ID
            </p>
          </div>
        </div>
      </div>

      {/* Operation Status Banner */}
      {operationStatus && operationStatus.status === "in_progress" && showOperationBanner && (
        <div className="border-b" style={{ backgroundColor: "#a8dadc" }}>
          <div className="p-4 max-w-[1800px] mx-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin" style={{ color: "#1d3557" }} />
                <div>
                  <p className="font-semibold" style={{ color: "#1d3557" }}>
                    Profile generation in progress
                  </p>
                  <p className="text-sm" style={{ color: "#1d3557" }}>
                    {operationStatus.processed_users}/{operationStatus.total_users} users processed ({operationStatus.progress_percentage.toFixed(0)}%)
                    {operationStatus.current_user_id && ` - Currently processing: ${operationStatus.current_user_id}`}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  try {
                    const result = await cancelOperation("profile_generation")
                    if (result.success && result.cancelled_services.length > 0) {
                      setMessageModalConfig({
                        title: "Cancellation Requested",
                        message: `Cancellation requested. The current user will finish processing, then the operation will stop.`,
                        type: "success"
                      })
                      setShowMessageModal(true)
                      // Keep polling so we see the status transition to "cancelled"
                      setShouldPollStatus(true)
                    }
                  } catch (err) {
                    console.error("Failed to cancel operation:", err)
                  }
                }}
                className="border-red-300 text-red-700 hover:bg-red-50"
              >
                <XCircle className="h-4 w-4 mr-1" />
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="p-8">
        <div className="max-w-[1800px] mx-auto space-y-6">
          {/* Performance Overview */}
          <Card className="border-slate-200 bg-white hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/25">
                  <Users className="h-5 w-5 text-white" />
                </div>
                <div>
                  <CardTitle className="text-lg font-semibold text-slate-800">Profile Overview</CardTitle>
                  <CardDescription className="text-xs mt-0.5 text-slate-500">
                    {(profileStatistics?.current_count ?? 0) + (profileStatistics?.pending_count ?? 0) + (profileStatistics?.archived_count ?? 0)} total profiles across all statuses
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 md:flex md:gap-0 md:divide-x md:divide-slate-200">
                {/* Current Total */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Current</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{profileStatistics?.current_count ?? 0}</span>
                  <span className="text-xs text-slate-400 mt-0.5">active profiles</span>
                </div>

                {/* Pending Total */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Clock className="h-3.5 w-3.5 text-amber-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Pending</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{profileStatistics?.pending_count ?? 0}</span>
                  <span className="text-xs text-slate-400 mt-0.5">awaiting approval</span>
                </div>

                {/* Archived Total */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Archive className="h-3.5 w-3.5 text-purple-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Archived</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{profileStatistics?.archived_count ?? 0}</span>
                  <span className="text-xs text-slate-400 mt-0.5">old profiles</span>
                </div>

                {/* Expiring Soon */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <AlertCircle className="h-3.5 w-3.5 text-blue-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Expiring Soon</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{profileStatistics?.expiring_soon_count ?? 0}</span>
                  <span className="text-xs text-slate-400 mt-0.5">within 7 days</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Status Tabs */}
          <div className="flex gap-2 border-b border-slate-200">
            <Button
              variant={activeStatusTab === "current" ? "default" : "ghost"}
              onClick={() => setActiveStatusTab("current")}
              className={`rounded-b-none transition-colors ${
                activeStatusTab === "current" ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 border-0" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Current
              <Badge className={`ml-2 ${activeStatusTab === "current" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}>
                {profileStatistics?.current_count ?? 0}
              </Badge>
            </Button>
            <Button
              variant={activeStatusTab === "pending" ? "default" : "ghost"}
              onClick={() => setActiveStatusTab("pending")}
              className={`rounded-b-none transition-colors ${
                activeStatusTab === "pending" ? "bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 border-0" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Clock className="h-4 w-4 mr-2" />
              Pending
              <Badge className={`ml-2 ${activeStatusTab === "pending" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}>
                {profileStatistics?.pending_count ?? 0}
              </Badge>
            </Button>
            <Button
              variant={activeStatusTab === "archived" ? "default" : "ghost"}
              onClick={() => setActiveStatusTab("archived")}
              className={`rounded-b-none transition-colors ${
                activeStatusTab === "archived" ? "bg-gradient-to-r from-slate-500 to-slate-600 hover:from-slate-600 hover:to-slate-700 border-0" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Archive className="h-4 w-4 mr-2" />
              Archived
              <Badge className={`ml-2 ${activeStatusTab === "archived" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}>
                {profileStatistics?.archived_count ?? 0}
              </Badge>
            </Button>
          </div>

          {/* Context-aware Action Buttons */}
          {activeStatusTab === "pending" && (profileStatistics?.pending_count ?? 0) > 0 && (
            <Card className="border-[#588157]/30 bg-[#588157]/5">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-[#588157]/20 flex items-center justify-center">
                      <CheckCircle className="h-5 w-5 text-[#588157]" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-foreground">Adopt All Pending Profiles as Current</h3>
                      <p className="text-sm text-muted-foreground">
                        Promote all {profileStatistics?.pending_count} pending profiles to current status, archive all current profiles, and delete all archived profiles.
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={confirmUpgradeAllProfiles}
                    disabled={upgrading || loading}
                    className="bg-[#588157] hover:bg-[#588157]/90 text-white"
                  >
                    {upgrading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Adopting...
                      </>
                    ) : (
                      <>
                        <CheckCircle className="h-4 w-4 mr-2" />
                        Adopt Pending Profiles
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {activeStatusTab === "archived" && (profileStatistics?.archived_count ?? 0) > 0 && (
            <Card className="border-[#457b9d]/30 bg-[#457b9d]/5">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-[#457b9d]/20 flex items-center justify-center">
                      <RotateCcw className="h-5 w-5 text-[#457b9d]" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-foreground">Restore All Archived Profiles to Current</h3>
                      <p className="text-sm text-muted-foreground">
                        Restore all {profileStatistics?.archived_count} archived profiles to current status and archive all current profiles.
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={confirmDowngradeAllProfiles}
                    disabled={downgrading || loading}
                    className="bg-[#457b9d] hover:bg-[#457b9d]/90 text-white"
                  >
                    {downgrading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Restoring...
                      </>
                    ) : (
                      <>
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Restore Archived Profiles
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {activeStatusTab === "current" && (
            <Card className="border-[#a8dadc]/30 bg-[#a8dadc]/5">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-[#a8dadc]/20 flex items-center justify-center">
                      <RefreshCw className="h-5 w-5 text-[#457b9d]" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-foreground">Rerun Profile Generation</h3>
                      <p className="text-sm text-muted-foreground">
                        Regenerate profiles for a specific user or all users with optional date range and source filtering.
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={() => setShowRerunModal(true)}
                    disabled={loading || (operationStatus?.status === "in_progress")}
                    className="bg-[#a8dadc] hover:bg-[#a8dadc]/90 text-[#1d3557]"
                  >
                    {operationStatus?.status === "in_progress" ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        In Progress
                      </>
                    ) : (
                      <>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Rerun Generation
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Search and Filters */}
          <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Filter className="h-4 w-4 text-slate-400" />
                  <div>
                    <CardTitle className="text-lg font-semibold text-slate-800">Search & Filters</CardTitle>
                    <CardDescription className="text-xs mt-1 text-slate-500">
                      {loading ? "Searching..." : userId.trim() ? `Filtering profiles for ${userId}` : "Showing all profiles"}
                    </CardDescription>
                  </div>
                </div>
                {loading && <div className="animate-spin rounded-full h-5 w-5 border-2 border-transparent border-t-indigo-500 border-r-indigo-500"></div>}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Primary Search Row */}
                <div className="grid gap-4 md:grid-cols-5">
                  {/* User ID Search */}
                  <div className="md:col-span-2">
                    <label className="text-sm font-medium mb-2 block text-slate-700">
                      User ID <span className="text-slate-400 text-xs font-normal">(optional - leave empty for all)</span>
                    </label>
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        placeholder="e.g., student_002"
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        className="pl-9 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                        disabled={loading}
                      />
                      {userId && (
                        <button
                          onClick={() => setUserId("")}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        >
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Content Search */}
                  <div className="md:col-span-2">
                    <label className="text-sm font-medium mb-2 block text-slate-700">Search Content</label>
                    <div className="relative">
                      <FileText className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        placeholder="Search profile content..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-9 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                      />
                    </div>
                  </div>

                  {/* Max Results */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Max Results</label>
                    <Input
                      type="number"
                      min="1"
                      max="1000"
                      value={topK}
                      onChange={(e) => setTopK(parseInt(e.target.value) || 100)}
                      disabled={loading}
                      className="border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                    />
                  </div>
                </div>

                {/* Secondary Filter Row */}
                <div className="grid gap-4 md:grid-cols-3">
                  {/* Source Filter */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Source</label>
                    <select
                      value={selectedSource}
                      onChange={(e) => setSelectedSource(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
                    >
                      <option value="all">All Sources</option>
                      {uniqueSources.map((source, index) => (
                        <option key={`${source}-${index}`} value={source}>
                          {source}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* TTL Filter */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Time To Live</label>
                    <select
                      value={selectedTTL}
                      onChange={(e) => setSelectedTTL(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
                    >
                      <option value="all">All TTL</option>
                      {uniqueTTLs.map((ttl, index) => (
                        <option key={`${ttl}-${index}`} value={ttl}>
                          {formatTTL(ttl)}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* User Filter - for filtering within loaded results */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Filter by User</label>
                    <select
                      value={selectedUser}
                      onChange={(e) => setSelectedUser(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
                    >
                      <option value="all">All Users</option>
                      {uniqueUsers.map((user, index) => (
                        <option key={`${user}-${index}`} value={user}>
                          {user}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Active filters indicator */}
                {(userId || searchQuery || selectedUser !== "all" || selectedSource !== "all" || selectedTTL !== "all") && (
                  <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-100">
                    <span className="text-sm font-medium text-slate-500">Active:</span>
                    {userId && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        <Users className="h-3 w-3 mr-1" />
                        User ID: {userId}
                      </Badge>
                    )}
                    {searchQuery && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        <Search className="h-3 w-3 mr-1" />
                        "{searchQuery}"
                      </Badge>
                    )}
                    {selectedUser !== "all" && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        User: {selectedUser}
                      </Badge>
                    )}
                    {selectedSource !== "all" && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        Source: {selectedSource}
                      </Badge>
                    )}
                    {selectedTTL !== "all" && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        TTL: {formatTTL(selectedTTL as ProfileTimeToLive)}
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs ml-auto text-slate-500 hover:text-slate-700"
                      onClick={() => {
                        setUserId("")
                        setSearchQuery("")
                        setSelectedUser("all")
                        setSelectedSource("all")
                        setSelectedTTL("all")
                      }}
                    >
                      <XCircle className="h-3 w-3 mr-1" />
                      Clear all
                    </Button>
                  </div>
                )}

                {/* Error message */}
                {error && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    <p className="text-sm text-red-600">{error}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Results */}
          <div>
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-800">Profile Results</h2>
              <p className="text-xs mt-1 text-slate-500">
                Showing {filteredProfiles.length} of {totalProfiles} profiles
              </p>
            </div>
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-12 w-12 border-3 border-transparent border-t-purple-500 border-r-purple-500 mx-auto mb-4"></div>
                <h3 className="text-lg font-semibold text-slate-800 mb-2">Loading profiles...</h3>
                <p className="text-sm text-slate-500">
                  Fetching data from the API
                </p>
              </div>
            ) : filteredProfiles.length === 0 ? (
              <div className="text-center py-12">
                <Calendar className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-slate-800 mb-2">No profiles found</h3>
                <p className="text-sm text-slate-500">
                  {profiles.length === 0
                    ? "No profiles available. Try creating some profiles first."
                    : "Try adjusting your filters or search query"}
                </p>
              </div>
            ) : (
              <div className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100">
                {filteredProfiles.map((profile) => (
                  <ProfileRow
                    key={profile.profile_id}
                    profile={profile}
                    onEdit={startEdit}
                    onDelete={handleDeleteClick}
                    isEditing={editingProfileId === profile.profile_id}
                    editedProfile={editedProfile}
                    onSave={saveEdit}
                    onCancel={cancelEdit}
                    onUpdateField={updateEditedField}
                    customFeaturesJson={customFeaturesJson}
                    setCustomFeaturesJson={setCustomFeaturesJson}
                    jsonError={jsonError}
                    setJsonError={setJsonError}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Rerun Profile Generation Modal */}
      <Dialog open={showRerunModal} onOpenChange={setShowRerunModal}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-50 to-pink-50 flex items-center justify-center flex-shrink-0 border border-purple-200">
                <RefreshCw className="h-5 w-5 text-purple-600" />
              </div>
              <DialogTitle className="text-xl font-semibold text-slate-800">
                Rerun Profile Generation
              </DialogTitle>
            </div>
            <DialogDescription className="text-slate-600">
              Configure the parameters for regenerating user profiles. Leave User ID empty to regenerate profiles for all users. All other fields are optional filters.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="rerun-user-id">User ID</Label>
              <Input
                id="rerun-user-id"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="Leave empty for all users"
                disabled={rerunning}
              />
              <p className="text-xs text-muted-foreground">
                Leave empty to regenerate for all users. Current: {userId.trim() || "all users"}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="rerun-start-date">Start Date & Time (Optional)</Label>
              <Input
                id="rerun-start-date"
                type="datetime-local"
                value={rerunStartDate}
                onChange={(e) => setRerunStartDate(e.target.value)}
                disabled={rerunning}
              />
              <p className="text-xs text-muted-foreground">
                Generate profiles from this date onwards
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="rerun-end-date">End Date & Time (Optional)</Label>
              <Input
                id="rerun-end-date"
                type="datetime-local"
                value={rerunEndDate}
                onChange={(e) => setRerunEndDate(e.target.value)}
                disabled={rerunning}
              />
              <p className="text-xs text-muted-foreground">
                Generate profiles up to this date
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="rerun-source">Source Filter (Optional)</Label>
              <Input
                id="rerun-source"
                value={rerunSource}
                onChange={(e) => setRerunSource(e.target.value)}
                placeholder="e.g., web_app, mobile_app"
                disabled={rerunning}
              />
              <p className="text-xs text-muted-foreground">
                Only generate profiles from this source
              </p>
            </div>
            <div className="space-y-2">
              <Label>Extractor Names (Optional)</Label>
              <p className="text-xs text-muted-foreground mb-2">
                Type extractor name and press Enter to add. Leave empty to run all extractors.
              </p>
              <Input
                placeholder="Type extractor name and press Enter"
                className="h-10 text-sm"
                disabled={rerunning}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && e.currentTarget.value.trim()) {
                    e.preventDefault()
                    const value = e.currentTarget.value.trim()
                    if (!selectedExtractorNames.includes(value)) {
                      setSelectedExtractorNames([...selectedExtractorNames, value])
                    }
                    e.currentTarget.value = ""
                  }
                }}
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {selectedExtractorNames.length > 0 ? (
                  selectedExtractorNames.map((name, index) => (
                    <Badge key={index} variant="secondary" className="text-sm h-7 px-3">
                      {name}
                      <button
                        type="button"
                        onClick={() => setSelectedExtractorNames(selectedExtractorNames.filter((_, idx) => idx !== index))}
                        className="ml-2 hover:text-destructive"
                        disabled={rerunning}
                      >
                        ×
                      </button>
                    </Badge>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground italic">All extractors will run (default)</p>
                )}
              </div>
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setShowRerunModal(false)}
              disabled={rerunning}
              className="border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </Button>
            <Button
              onClick={handleRerunProfileGeneration}
              disabled={rerunning}
              className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white border-0 shadow-md shadow-purple-500/25"
            >
              {rerunning ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Start Generation
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmDialog
        open={!!profileToDelete}
        onOpenChange={(open) => {
          if (!open) setProfileToDelete(null)
        }}
        onConfirm={confirmDelete}
        title="Delete Profile"
        description="Are you sure you want to delete this profile?"
        itemDetails={
          profileToDelete && (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Profile ID:</span>
                <span className="font-mono text-xs">{profileToDelete.profile_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">User ID:</span>
                <span>{profileToDelete.user_id}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Content:</span>
                <p className="text-sm mt-1 line-clamp-2">{profileToDelete.profile_content}</p>
              </div>
            </>
          )
        }
        loading={deleting}
        confirmButtonText="Delete Profile"
      />

      {/* Confirmation Modal */}
      <Dialog open={showConfirmModal} onOpenChange={setShowConfirmModal}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center flex-shrink-0 border border-indigo-200">
                <AlertCircle className="h-5 w-5 text-indigo-600" />
              </div>
              <DialogTitle className="text-xl font-semibold text-slate-800">
                {confirmModalConfig?.title}
              </DialogTitle>
            </div>
            <DialogDescription className="whitespace-pre-line pt-2 text-slate-600">
              {confirmModalConfig?.description}
            </DialogDescription>
          </DialogHeader>

          {/* Radio buttons for upgrade/downgrade scope selection */}
          {confirmModalConfig?.modalType === "upgrade" && (
            <div className="space-y-3 pt-2">
              <Label className="text-sm font-medium text-slate-700">Apply to:</Label>
              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg hover:bg-emerald-50/50 border border-transparent hover:border-emerald-200 transition-colors">
                  <input
                    type="radio"
                    name="upgradeScope"
                    value="affected"
                    checked={upgradeScope === "affected"}
                    onChange={(e) => setUpgradeScope(e.target.value as "affected" | "all")}
                    className="h-4 w-4 text-emerald-600 focus:ring-emerald-500 border-slate-300"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-medium text-slate-800">Only affected users</span>
                    <p className="text-xs text-slate-500">Users who have pending profiles</p>
                  </div>
                </label>
                <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg hover:bg-emerald-50/50 border border-transparent hover:border-emerald-200 transition-colors">
                  <input
                    type="radio"
                    name="upgradeScope"
                    value="all"
                    checked={upgradeScope === "all"}
                    onChange={(e) => setUpgradeScope(e.target.value as "affected" | "all")}
                    className="h-4 w-4 text-emerald-600 focus:ring-emerald-500 border-slate-300"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-medium text-slate-800">All users</span>
                    <p className="text-xs text-slate-500">All users with current profiles</p>
                  </div>
                </label>
              </div>
            </div>
          )}

          {confirmModalConfig?.modalType === "downgrade" && (
            <div className="space-y-3 pt-2">
              <Label className="text-sm font-medium text-slate-700">Apply to:</Label>
              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg hover:bg-blue-50/50 border border-transparent hover:border-blue-200 transition-colors">
                  <input
                    type="radio"
                    name="downgradeScope"
                    value="affected"
                    checked={downgradeScope === "affected"}
                    onChange={(e) => setDowngradeScope(e.target.value as "affected" | "all")}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-medium text-slate-800">Only affected users</span>
                    <p className="text-xs text-slate-500">Users who have archived profiles</p>
                  </div>
                </label>
                <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg hover:bg-blue-50/50 border border-transparent hover:border-blue-200 transition-colors">
                  <input
                    type="radio"
                    name="downgradeScope"
                    value="all"
                    checked={downgradeScope === "all"}
                    onChange={(e) => setDowngradeScope(e.target.value as "affected" | "all")}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-medium text-slate-800">All users</span>
                    <p className="text-xs text-slate-500">All users with current profiles</p>
                  </div>
                </label>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setShowConfirmModal(false)}
              className="border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                setShowConfirmModal(false)
                confirmModalConfig?.confirmAction()
              }}
              className={
                confirmModalConfig?.modalType === "downgrade"
                  ? "bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white border-0 shadow-md shadow-blue-500/25"
                  : "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white border-0 shadow-md shadow-emerald-500/25"
              }
            >
              {confirmModalConfig?.confirmText}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Message Modal */}
      <Dialog open={showMessageModal} onOpenChange={setShowMessageModal}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <div className="flex items-center gap-3 mb-2">
              {messageModalConfig?.type === "success" ? (
                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 flex items-center justify-center flex-shrink-0 border border-emerald-200">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                </div>
              ) : (
                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-red-50 to-red-100 flex items-center justify-center flex-shrink-0 border border-red-200">
                  <XCircle className="h-5 w-5 text-red-500" />
                </div>
              )}
              <DialogTitle className="text-xl font-semibold text-slate-800">
                {messageModalConfig?.title}
              </DialogTitle>
            </div>
            <DialogDescription className="whitespace-pre-line pt-2 text-slate-600">
              {messageModalConfig?.message}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={() => setShowMessageModal(false)}
              className={
                messageModalConfig?.type === "success"
                  ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white border-0 shadow-md shadow-emerald-500/25"
                  : "bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white border-0 shadow-md shadow-indigo-500/25"
              }
            >
              OK
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

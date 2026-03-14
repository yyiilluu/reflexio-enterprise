"use client"

import { useState, useMemo, useEffect, useRef, createElement } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  MessageSquare,
  MousePointer,
  Keyboard,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  Scroll,
  AlertCircle,
  Users,
  XCircle,
  FileText,
  Layers,
  CheckCircle2,
  GitBranch,
  Trash2,
  Wrench,
} from "lucide-react"
import {
  type UserActionType,
  type Request,
  type Interaction,
  type RequestData,
  type Session,
  type GetRequestsRequest,
  getRequests,
  deleteInteraction,
  deleteRequest,
  deleteSession,
} from "@/lib/api"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"

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
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return `${Math.floor(diff / 604800)}w ago`
}

// Helper function to get action icon
const getActionIcon = (action: UserActionType) => {
  switch (action) {
    case "click":
      return MousePointer
    case "scroll":
      return Scroll
    case "type":
      return Keyboard
    case "none":
      return MessageSquare
  }
}

// Interaction component (innermost level)
interface InteractionItemProps {
  interaction: Interaction
  onDelete: (interaction: Interaction) => void
}

function InteractionItem({ interaction, onDelete }: InteractionItemProps) {
  const [expanded, setExpanded] = useState(false)
  const actionIcon = getActionIcon(interaction.user_action)

  return (
    <div className="hover:bg-slate-50/50 transition-colors">
      <div className="p-3">
        <div className="flex items-center justify-between gap-3">
          <div
            className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            {/* Action Icon */}
            <div className="h-6 w-6 rounded-md bg-blue-100 flex items-center justify-center flex-shrink-0">
              {createElement(actionIcon, { className: "h-3.5 w-3.5 text-blue-600" })}
            </div>

            {/* Main Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                  Interaction
                </span>
                <Badge className={`text-xs ${interaction.role === 'User' ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-100' : interaction.role === 'Assistant' ? 'bg-purple-100 text-purple-700 hover:bg-purple-100' : 'bg-slate-100 text-slate-700 hover:bg-slate-100'}`}>
                  {interaction.role}
                </Badge>
                <Badge className="text-xs flex items-center gap-1 bg-slate-100 text-slate-600 hover:bg-slate-100">
                  {createElement(actionIcon, { className: "h-3 w-3" })}
                  {interaction.user_action}
                </Badge>
                {interaction.tools_used && interaction.tools_used.length > 0 && interaction.tools_used.map((tool, idx) => (
                  <Badge key={idx} className="text-xs flex items-center gap-1 bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                    <Wrench className="h-3 w-3" />
                    {tool.tool_name}
                  </Badge>
                ))}
                {interaction.interacted_image_url && (
                  <Badge variant="outline" className="text-xs flex items-center gap-1 border-slate-200 text-slate-600">
                    <ImageIcon className="h-3 w-3" />
                    Image
                  </Badge>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-1 truncate">{interaction.content}</p>
              {interaction.shadow_content && (
                <p className="text-sm text-amber-600 mt-0.5 truncate">Shadow: {interaction.shadow_content}</p>
              )}
            </div>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <p className="text-xs text-slate-400">{getRelativeTime(interaction.created_at)}</p>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(interaction)
              }}
              title="Delete interaction"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 text-slate-400 hover:text-slate-600"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-slate-100 p-3 space-y-3">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Left Column */}
            <div className="space-y-3">
              <div>
                <h4 className="text-xs font-semibold mb-1 text-slate-800">Content</h4>
                <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-2 rounded-lg">
                  {interaction.content}
                </p>
              </div>

              {interaction.shadow_content && (
                <div>
                  <h4 className="text-xs font-semibold mb-1 text-amber-700">Shadow Content</h4>
                  <p className="text-sm text-amber-600 leading-relaxed bg-amber-50 p-2 rounded-lg border border-amber-200">
                    {interaction.shadow_content}
                  </p>
                </div>
              )}

              {interaction.tools_used && interaction.tools_used.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold mb-1 text-emerald-700">Tools Used ({interaction.tools_used.length})</h4>
                  <div className="space-y-2">
                    {interaction.tools_used.map((tool, idx) => (
                      <div key={idx} className="text-sm text-emerald-600 bg-emerald-50 p-2 rounded-lg border border-emerald-200">
                        <span className="font-medium">{tool.tool_name}</span>
                        {tool.tool_input && Object.keys(tool.tool_input).length > 0 && (
                          <pre className="mt-1 text-xs text-emerald-500 overflow-x-auto">
                            {JSON.stringify(tool.tool_input, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {interaction.user_action_description && (
                <div>
                  <h4 className="text-xs font-semibold mb-1 text-slate-800">Action Description</h4>
                  <p className="text-sm text-slate-600 bg-slate-50 p-2 rounded-lg">
                    {interaction.user_action_description}
                  </p>
                </div>
              )}
            </div>

            {/* Right Column */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-slate-800">Details</h4>
              <div className="space-y-1 bg-slate-50 p-2 rounded-lg text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Interaction ID:</span>
                  <span className="font-mono text-[10px] text-slate-700">{interaction.interaction_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Created:</span>
                  <span className="text-slate-700">{formatTimestamp(interaction.created_at)}</span>
                </div>
                {interaction.embedding.length > 0 && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Embedding:</span>
                    <span className="text-slate-700">{interaction.embedding.length} dimensions</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Request component (middle level)
interface RequestItemProps {
  requestData: RequestData
  onDeleteRequest: (request: Request) => void
  onDeleteInteraction: (interaction: Interaction) => void
}

function RequestItem({ requestData, onDeleteRequest, onDeleteInteraction }: RequestItemProps) {
  const [expanded, setExpanded] = useState(false)
  const { request, interactions } = requestData
  const hasShadowContent = interactions.some((i) => i.shadow_content)

  return (
    <div
      className="hover:bg-slate-50/50 transition-colors"
    >
      <div className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div
            className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            {/* Request Type Icon */}
            <div
              className="h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-indigo-100"
            >
              <CheckCircle2 className="h-4 w-4 text-indigo-600" />
            </div>

            {/* Main Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                  Request
                </span>
                <span className="font-semibold text-sm font-mono text-slate-800">{request.request_id}</span>
                <Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
                  <Users className="h-3 w-3 mr-1" />
                  {request.user_id}
                </Badge>
                <Badge variant="outline" className="text-xs flex items-center gap-1 border-slate-200 text-slate-600">
                  <MessageSquare className="h-3 w-3" />
                  {interactions.length} interactions
                </Badge>
                {hasShadowContent && (
                  <Badge className="text-xs bg-amber-100 text-amber-700 hover:bg-amber-100 border border-amber-200">
                    Shadow
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap text-xs text-slate-500">
                {request.source && (
                  <span className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    {request.source}
                  </span>
                )}
                {request.agent_version && (
                  <span className="flex items-center gap-1">
                    <GitBranch className="h-3 w-3" />
                    {request.agent_version}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="text-right">
              <p className="text-xs text-slate-500">{getRelativeTime(request.created_at)}</p>
              <p className="text-xs text-slate-400">
                {new Date(request.created_at * 1000).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
              onClick={(e) => {
                e.stopPropagation()
                onDeleteRequest(request)
              }}
              title="Delete entire request"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Expanded: Show Interactions */}
      {expanded && (
        <div className="border-t border-slate-100 p-4">
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-slate-800">
            <Layers className="h-4 w-4 text-slate-600" />
            Interactions ({interactions.length})
          </h4>
          <div className="border-l-2 border-indigo-200 pl-4 divide-y divide-slate-50">
            {interactions.map((interaction) => (
              <InteractionItem
                key={interaction.interaction_id}
                interaction={interaction}
                onDelete={onDeleteInteraction}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Session component (outermost level)
interface SessionProps {
  groupData: Session
  onDeleteRequest: (request: Request) => void
  onDeleteInteraction: (interaction: Interaction) => void
  onDeleteGroup: (sessionId: string) => void
}

function SessionGroup({ groupData, onDeleteRequest, onDeleteInteraction, onDeleteGroup }: SessionProps) {
  const [expanded, setExpanded] = useState(true)
  const { session_id, requests } = groupData

  // Sort requests from oldest to latest
  const sortedRequests = useMemo(() => {
    return [...requests].sort((a, b) => a.request.created_at - b.request.created_at)
  }, [requests])

  const totalInteractions = requests.reduce((sum, rd) => sum + rd.interactions.length, 0)

  // Get timestamp range
  const timestamps = requests.map((rd) => rd.request.created_at)
  const minTimestamp = Math.min(...timestamps)
  const maxTimestamp = Math.max(...timestamps)

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
      <div className="bg-slate-50/50 border-b border-slate-200 hover:bg-slate-100 transition-colors">
        <div className="p-4 pb-3">
          <div className="flex items-center justify-between">
            <div
              className="flex items-center gap-3 flex-1 cursor-pointer"
              onClick={() => setExpanded(!expanded)}
            >
              <div className="h-8 w-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                <Layers className="h-4 w-4 text-indigo-600" />
              </div>
              <div className="flex-1">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                  Session
                </span>
                <h3 className="text-lg font-semibold flex items-center gap-2 text-slate-800">
                  {session_id || "Ungrouped"}
                </h3>
                <p className="text-xs mt-1 flex items-center gap-3 flex-wrap text-slate-500">
                  <span className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    {requests.length} requests
                  </span>
                  <span className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {totalInteractions} interactions
                  </span>
                  {minTimestamp === maxTimestamp ? (
                    <span className="text-slate-400">{formatTimestamp(minTimestamp)}</span>
                  ) : (
                    <span className="text-slate-400">
                      {formatTimestamp(minTimestamp)} - {formatTimestamp(maxTimestamp)}
                    </span>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteGroup(session_id)
                }}
                title="Delete entire session"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Expanded: Show Requests */}
      {expanded && (
        <div className="pt-4 px-4 pb-4">
          <div className="divide-y divide-slate-100">
            {sortedRequests.map((requestData) => (
              <RequestItem
                key={requestData.request.request_id}
                requestData={requestData}
                onDeleteRequest={onDeleteRequest}
                onDeleteInteraction={onDeleteInteraction}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Merge new sessions into existing ones (append requests to existing sessions, add new sessions)
const mergeSessions = (existing: Session[], incoming: Session[]): Session[] => {
  const merged = [...existing]
  for (const incomingGroup of incoming) {
    const existingGroup = merged.find((g) => g.session_id === incomingGroup.session_id)
    if (existingGroup) {
      // Append new requests that aren't already present
      const existingIds = new Set(existingGroup.requests.map((r) => r.request.request_id))
      const newRequests = incomingGroup.requests.filter((r) => !existingIds.has(r.request.request_id))
      existingGroup.requests = [...existingGroup.requests, ...newRequests]
    } else {
      merged.push(incomingGroup)
    }
  }
  return merged
}

export default function InteractionsPage() {
  // State for API data
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>("")

  // Pagination state
  const [offset, setOffset] = useState<number>(0)
  const [hasMore, setHasMore] = useState<boolean>(false)
  const [loadingMore, setLoadingMore] = useState<boolean>(false)
  const fetchRequestSeqRef = useRef(0)

  // Filter state
  const [userId, setUserId] = useState<string>("")
  const [sessionFilter, setSessionFilter] = useState<string>("")
  const [sourceFilter, setSourceFilter] = useState<string>("all")
  const [topK, setTopK] = useState<number>(30)

  // Delete state
  const [requestToDelete, setRequestToDelete] = useState<Request | null>(null)
  const [interactionToDelete, setInteractionToDelete] = useState<Interaction | null>(null)
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<boolean>(false)
  const [deleteError, setDeleteError] = useState<string>("")

  // Fetch sessions from API
  const fetchSessions = async (searchUserId: string, limit: number, pageOffset: number = 0) => {
    const fetchSeq = ++fetchRequestSeqRef.current
    if (pageOffset === 0) {
      setLoading(true)
    } else {
      setLoadingMore(true)
    }
    setError("")

    try {
      const requestParams: GetRequestsRequest = {
        top_k: limit,
        offset: pageOffset,
      }

      // Only add user_id if it's provided
      if (searchUserId.trim()) {
        requestParams.user_id = searchUserId.trim()
      }

      const response = await getRequests(requestParams)
      if (fetchSeq !== fetchRequestSeqRef.current) {
        return
      }

      if (response.success) {
        if (pageOffset === 0) {
          setSessions(response.sessions)
        } else {
          setSessions((prev) => mergeSessions(prev, response.sessions))
        }
        setHasMore(response.has_more)
        setError("")
      } else {
        setError(response.msg || "Failed to fetch requests")
        if (pageOffset === 0) {
          setSessions([])
          setHasMore(false)
        }
      }
    } catch (err) {
      if (fetchSeq !== fetchRequestSeqRef.current) {
        return
      }
      setError(err instanceof Error ? err.message : "An error occurred while fetching requests")
      if (pageOffset === 0) {
        setSessions([])
        setHasMore(false)
      }
    } finally {
      if (fetchSeq === fetchRequestSeqRef.current) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }

  // Handle "Load More" click
  const handleLoadMore = () => {
    const newOffset = offset + topK
    setOffset(newOffset)
    fetchSessions(userId, topK, newOffset)
  }

  // Debounced search effect - auto-fetch when userId or topK changes (reset pagination)
  useEffect(() => {
    setOffset(0)
    // Invalidate in-flight requests from the previous filter state.
    fetchRequestSeqRef.current += 1
    setHasMore(false)
    const timer = setTimeout(() => {
      fetchSessions(userId, topK, 0)
    }, 1000)

    return () => clearTimeout(timer)
  }, [userId, topK])

  // Delete handlers
  const handleDeleteRequest = (request: Request) => {
    setRequestToDelete(request)
    setDeleteError("")
  }

  const handleDeleteInteraction = (interaction: Interaction) => {
    setInteractionToDelete(interaction)
    setDeleteError("")
  }

  const handleDeleteSession = (sessionId: string) => {
    setSessionToDelete(sessionId)
    setDeleteError("")
  }

  const confirmDeleteRequest = async () => {
    if (!requestToDelete) return

    setDeleting(true)
    setDeleteError("")

    try {
      const response = await deleteRequest({
        request_id: requestToDelete.request_id,
      })

      if (response.success) {
        // Refresh data (reset pagination)
        setOffset(0)
        await fetchSessions(userId, topK, 0)
        setRequestToDelete(null)
      } else {
        setDeleteError(response.message || "Failed to delete request")
      }
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "An error occurred while deleting the request")
    } finally {
      setDeleting(false)
    }
  }

  const confirmDeleteInteraction = async () => {
    if (!interactionToDelete) return

    setDeleting(true)
    setDeleteError("")

    try {
      const response = await deleteInteraction({
        user_id: interactionToDelete.user_id,
        interaction_id: interactionToDelete.interaction_id,
      })

      if (response.success) {
        // Refresh data (reset pagination)
        setOffset(0)
        await fetchSessions(userId, topK, 0)
        setInteractionToDelete(null)
      } else {
        setDeleteError(response.message || "Failed to delete interaction")
      }
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : "An error occurred while deleting the interaction"
      )
    } finally {
      setDeleting(false)
    }
  }

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return

    setDeleting(true)
    setDeleteError("")

    try {
      const response = await deleteSession({
        session_id: sessionToDelete,
      })

      if (response.success) {
        // Refresh data (reset pagination)
        setOffset(0)
        await fetchSessions(userId, topK, 0)
        setSessionToDelete(null)
      } else {
        setDeleteError(response.message || "Failed to delete session")
      }
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : "An error occurred while deleting the session"
      )
    } finally {
      setDeleting(false)
    }
  }

  // Apply client-side filters to the sessions from API
  const filteredSessions = useMemo(() => {
    let filtered = sessions

    // Filter by session name
    if (sessionFilter.trim()) {
      filtered = filtered.filter((group) =>
        group.session_id.toLowerCase().includes(sessionFilter.toLowerCase())
      )
    }

    // Filter by source within each group
    if (sourceFilter !== "all") {
      filtered = filtered.map((group) => ({
        ...group,
        requests: group.requests.filter((rd) => rd.request.source === sourceFilter),
      }))

      // Remove groups with no requests after filtering
      filtered = filtered.filter((group) => group.requests.length > 0)
    }

    return filtered
  }, [sessions, sessionFilter, sourceFilter])

  // Calculate statistics from all sessions
  const allRequests = useMemo(() => {
    return sessions.flatMap((group) => group.requests)
  }, [sessions])

  const totalGroups = filteredSessions.length
  const totalRequests = allRequests.length
  const totalInteractions = allRequests.reduce((sum, rd) => sum + rd.interactions.length, 0)

  // Get unique sources
  const uniqueSources = useMemo(() => {
    return Array.from(new Set(allRequests.map((rd) => rd.request.source))).filter(Boolean).sort()
  }, [allRequests])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
        <div className="p-8">
          <div className="max-w-[1800px] mx-auto">
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-blue-500/25">
                <MessageSquare className="h-5 w-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-800">Sessions & Interactions</h1>
            </div>
            <p className="text-slate-500 mt-1 ml-13">
              View and manage requests grouped by session
            </p>
          </div>
        </div>
      </div>

      <div className="p-8">
        <div className="max-w-[1800px] mx-auto space-y-6">
          {/* Performance Overview */}
          <Card className="border-slate-200 bg-white hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-blue-500/25">
                  <MessageSquare className="h-5 w-5 text-white" />
                </div>
                <div>
                  <CardTitle className="text-lg font-semibold text-slate-800">Overview</CardTitle>
                  <CardDescription className="text-xs mt-0.5 text-slate-500">
                    {totalGroups} session{totalGroups !== 1 ? "s" : ""} loaded
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 md:flex md:gap-0 md:divide-x md:divide-slate-200">
                {/* Sessions */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Layers className="h-3.5 w-3.5 text-purple-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Sessions</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{totalGroups}</span>
                  <span className="text-xs text-slate-400 mt-0.5">unique sessions</span>
                </div>

                {/* Total Requests */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <FileText className="h-3.5 w-3.5 text-blue-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Requests</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{totalRequests}</span>
                  <span className="text-xs text-slate-400 mt-0.5">all requests</span>
                </div>

                {/* Total Interactions */}
                <div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <MessageSquare className="h-3.5 w-3.5 text-indigo-500" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Interactions</span>
                  </div>
                  <span className="text-2xl font-bold text-slate-800">{totalInteractions}</span>
                  <span className="text-xs text-slate-400 mt-0.5">all interactions</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Search and Filters */}
          <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Filter className="h-4 w-4 text-slate-400" />
                  <div>
                    <CardTitle className="text-lg font-semibold text-slate-800">Filters</CardTitle>
                    <CardDescription className="text-xs mt-1 text-slate-500">
                      {loading ? "Searching..." : userId.trim() ? `Showing requests for ${userId}` : "Showing top sessions across all users"}
                    </CardDescription>
                  </div>
                </div>
                {loading && <div className="animate-spin rounded-full h-5 w-5 border-2 border-transparent border-t-indigo-500 border-r-indigo-500"></div>}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Primary Filter Row */}
                <div className="grid gap-4 md:grid-cols-4">
                  {/* User ID Filter */}
                  <div className="md:col-span-1">
                    <label className="text-sm font-medium mb-2 block text-slate-700">
                      User ID <span className="text-slate-400 text-xs font-normal">(optional)</span>
                    </label>
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        placeholder="Leave empty to show top sessions across all users"
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

                  {/* Session Filter */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Session</label>
                    <div className="relative">
                      <Layers className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        placeholder="e.g., experiment_a"
                        value={sessionFilter}
                        onChange={(e) => setSessionFilter(e.target.value)}
                        className="pl-9 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                      />
                      {sessionFilter && (
                        <button
                          onClick={() => setSessionFilter("")}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        >
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Source Filter */}
                  <div>
                    <label className="text-sm font-medium mb-2 block text-slate-700">Source</label>
                    <select
                      value={sourceFilter}
                      onChange={(e) => setSourceFilter(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
                    >
                      <option value="all">All Sources</option>
                      {uniqueSources.map((source) => (
                        <option key={source} value={source}>
                          {source}
                        </option>
                      ))}
                    </select>
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

                {/* Active filters indicator */}
                {(userId || sessionFilter || sourceFilter !== "all") && (
                  <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-100">
                    <span className="text-sm font-medium text-slate-500">Active:</span>
                    {userId && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        <Users className="h-3 w-3 mr-1" />
                        User: {userId}
                      </Badge>
                    )}
                    {sessionFilter && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        <Layers className="h-3 w-3 mr-1" />
                        Session: {sessionFilter}
                      </Badge>
                    )}
                    {sourceFilter !== "all" && (
                      <Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                        <FileText className="h-3 w-3 mr-1" />
                        Source: {sourceFilter}
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs ml-auto text-slate-500 hover:text-slate-700"
                      onClick={() => {
                        setUserId("")
                        setSessionFilter("")
                        setSourceFilter("all")
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
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-3 border-transparent border-t-indigo-500 border-r-indigo-500 mx-auto mb-4"></div>
              <h3 className="text-lg font-semibold text-slate-800 mb-2">Loading sessions...</h3>
              <p className="text-sm text-slate-500">Fetching data from the API</p>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="text-center py-12">
              <Layers className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-slate-800 mb-2">No sessions found</h3>
              <p className="text-sm text-slate-500">
                {sessions.length === 0
                  ? userId.trim()
                    ? "No requests found for this user. Try a different user ID or publish some interactions first."
                    : "No sessions found. Publish some interactions first."
                  : "No requests match your current filters. Try adjusting the filters."}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredSessions.map((group) => (
                <SessionGroup
                  key={group.session_id}
                  groupData={group}
                  onDeleteRequest={handleDeleteRequest}
                  onDeleteInteraction={handleDeleteInteraction}
                  onDeleteGroup={handleDeleteSession}
                />
              ))}
              {hasMore && (
                <div className="flex justify-center pt-4">
                  <Button
                    variant="outline"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="border-slate-200 text-slate-600 hover:bg-slate-50"
                  >
                    {loadingMore ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-transparent border-t-slate-500 border-r-slate-500 mr-2" />
                        Loading...
                      </>
                    ) : (
                      "Load More"
                    )}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Delete Session Confirmation Dialog */}
      <DeleteConfirmDialog
        open={!!sessionToDelete}
        onOpenChange={(open) => {
          if (!open) setSessionToDelete(null)
        }}
        onConfirm={confirmDeleteSession}
        title="Delete Session"
        description="Are you sure you want to delete this entire session and all its requests and interactions?"
        itemDetails={
          sessionToDelete && (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Session:</span>
                <span className="font-mono text-xs">{sessionToDelete}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total Requests:</span>
                <span>
                  {
                    sessions
                      .find((s) => s.session_id === sessionToDelete)
                      ?.requests.length || 0
                  }
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total Interactions:</span>
                <span>
                  {sessions
                    .find((s) => s.session_id === sessionToDelete)
                    ?.requests.reduce((sum, rd) => sum + rd.interactions.length, 0) || 0}
                </span>
              </div>
            </>
          )
        }
        loading={deleting}
        confirmButtonText="Delete Session"
      />

      {/* Delete Request Confirmation Dialog */}
      <DeleteConfirmDialog
        open={!!requestToDelete}
        onOpenChange={(open) => {
          if (!open) setRequestToDelete(null)
        }}
        onConfirm={confirmDeleteRequest}
        title="Delete Request"
        description="Are you sure you want to delete this entire request and all its interactions?"
        itemDetails={
          requestToDelete && (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Request ID:</span>
                <span className="font-mono text-xs">{requestToDelete.request_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">User ID:</span>
                <span className="font-mono text-xs">{requestToDelete.user_id}</span>
              </div>
              {requestToDelete.source && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Source:</span>
                  <span>{requestToDelete.source}</span>
                </div>
              )}
            </>
          )
        }
        loading={deleting}
        confirmButtonText="Delete Request"
      />

      {/* Delete Interaction Confirmation Dialog */}
      <DeleteConfirmDialog
        open={!!interactionToDelete}
        onOpenChange={(open) => {
          if (!open) setInteractionToDelete(null)
        }}
        onConfirm={confirmDeleteInteraction}
        title="Delete Interaction"
        description="Are you sure you want to delete this interaction?"
        itemDetails={
          interactionToDelete && (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Interaction ID:</span>
                <span className="font-mono text-xs">{interactionToDelete.interaction_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Role:</span>
                <span>{interactionToDelete.role}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Action:</span>
                <span>{interactionToDelete.user_action}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Content:</span>
                <p className="text-sm mt-1 line-clamp-3">{interactionToDelete.content}</p>
              </div>
            </>
          )
        }
        loading={deleting}
        confirmButtonText="Delete Interaction"
      />

      {/* Delete Error Display */}
      {deleteError && (
        <div className="fixed bottom-4 right-4 max-w-md bg-destructive/10 border border-destructive/20 rounded-md p-4 flex items-start gap-3 shadow-lg">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-destructive mb-1">Delete Failed</p>
            <p className="text-sm text-destructive/80">{deleteError}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setDeleteError("")}
          >
            <XCircle className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

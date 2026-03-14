"use client";

import {
	AlertCircle,
	Archive,
	BarChart3,
	Calendar,
	CheckCircle,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	Clock,
	FileText,
	Filter,
	Layers,
	Loader2,
	RefreshCw,
	RotateCcw,
	Search,
	ThumbsDown,
	ThumbsUp,
	Trash2,
	XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	cancelOperation,
	deleteFeedback,
	deleteRawFeedback,
	downgradeAllRawFeedbacks,
	type Feedback,
	type FeedbackStatus,
	getFeedbacks,
	getOperationStatus,
	getRawFeedbacks,
	type OperationStatusInfo,
	type RawFeedback,
	rerunFeedbackGeneration,
	runFeedbackAggregation,
	updateFeedbackStatus as updateFeedbackStatusAPI,
	upgradeAllRawFeedbacks,
} from "@/lib/api";

// Helper functions
const formatTimestamp = (timestamp: number): string => {
	const date = new Date(timestamp * 1000);
	return date.toLocaleDateString("en-US", {
		year: "numeric",
		month: "short",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
};

const getRelativeTime = (timestamp: number): string => {
	const now = Date.now() / 1000;
	const diff = now - timestamp;

	if (diff < 60) return "Just now";
	if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
	if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
	if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
	return `${Math.floor(diff / 604800)}w ago`;
};

const getStatusIcon = (status: FeedbackStatus) => {
	switch (status) {
		case "approved":
			return ThumbsUp;
		case "rejected":
			return ThumbsDown;
		case "pending":
			return Clock;
	}
};

const formatFeedbackName = (name: string): string => {
	return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

const formatFeedbackContent = (feedback: {
	feedback_content: string;
	when_condition?: string | null;
	do_action?: string | null;
	do_not_action?: string | null;
	blocking_issue?: { kind: string; details: string } | null;
}): string => {
	if (feedback.when_condition || feedback.do_action || feedback.do_not_action) {
		const lines: string[] = [];
		if (feedback.when_condition) lines.push(`When: ${feedback.when_condition}`);
		if (feedback.do_action) lines.push(`Do: ${feedback.do_action}`);
		if (feedback.do_not_action) lines.push(`Don't: ${feedback.do_not_action}`);
		if (feedback.blocking_issue)
			lines.push(
				`Blocked by: [${feedback.blocking_issue.kind}] ${feedback.blocking_issue.details}`,
			);
		return lines.join("\n");
	}
	return feedback.feedback_content;
};

// Raw Feedback Row Component
interface RawFeedbackRowProps {
	feedback: RawFeedback;
	onDelete: (feedback: RawFeedback) => void;
}

function RawFeedbackRow({ feedback, onDelete }: RawFeedbackRowProps) {
	const [expanded, setExpanded] = useState(false);

	return (
		<div className="hover:bg-slate-50/50 transition-colors">
			<div
				className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
				onClick={() => setExpanded(!expanded)}
			>
				<div className="flex items-center justify-between gap-4">
					<div className="flex items-center gap-3 flex-1 min-w-0">
						{/* Icon */}
						<div className="flex-shrink-0">
							<div className="h-8 w-8 rounded-lg bg-orange-100 flex items-center justify-center">
								<FileText className="h-4 w-4 text-orange-600" />
							</div>
						</div>

						{/* Main Info */}
						<div className="flex-1 min-w-0">
							<div className="flex items-center gap-2 flex-wrap">
								<span className="font-semibold text-slate-800 font-mono text-sm">
									#{feedback.raw_feedback_id}
								</span>
								<Badge
									variant="outline"
									className="text-xs border-slate-200 text-slate-600"
								>
									{formatFeedbackName(feedback.feedback_name)}
								</Badge>
								<Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
									{feedback.agent_version}
								</Badge>
							</div>
							<p className="text-sm text-slate-500 mt-1 truncate">
								{formatFeedbackContent(feedback)}
							</p>
						</div>
					</div>

					{/* Right side: time and expand button */}
					<div className="flex items-center gap-3 flex-shrink-0">
						<div className="text-right">
							<p className="text-xs text-slate-500">
								{getRelativeTime(feedback.created_at)}
							</p>
							<p className="text-xs text-slate-400">
								{new Date(feedback.created_at * 1000).toLocaleDateString(
									"en-US",
									{
										month: "short",
										day: "numeric",
									},
								)}
							</p>
						</div>
						<div className="flex items-center gap-1">
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
								onClick={(e) => {
									e.stopPropagation();
									onDelete(feedback);
								}}
							>
								<Trash2 className="h-4 w-4" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
							>
								{expanded ? (
									<ChevronUp className="h-4 w-4" />
								) : (
									<ChevronDown className="h-4 w-4" />
								)}
							</Button>
						</div>
					</div>
				</div>
			</div>

			{/* Expanded Details */}
			{expanded && (
				<div className="border-t border-slate-100 p-4 space-y-4">
					<div className="grid gap-6 md:grid-cols-2">
						{/* Left Column */}
						<div className="space-y-4">
							<div>
								<h4 className="text-sm font-semibold mb-2 text-slate-800">
									Feedback Content
								</h4>
								<p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg whitespace-pre-wrap">
									{formatFeedbackContent(feedback)}
								</p>
							</div>
						</div>

						{/* Right Column */}
						<div className="space-y-4">
							<div>
								<h4 className="text-sm font-semibold mb-3 text-slate-800">
									Details
								</h4>
								<div className="space-y-2 bg-slate-50 p-3 rounded-lg">
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Feedback ID:</span>
										<span className="font-mono text-slate-700">
											#{feedback.raw_feedback_id}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Agent Version:</span>
										<span className="text-slate-700">
											{feedback.agent_version}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Feedback Type:</span>
										<span className="text-slate-700">
											{formatFeedbackName(feedback.feedback_name)}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Request ID:</span>
										<span className="font-mono text-xs text-slate-700">
											{feedback.request_id}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Source:</span>
										<span className="text-slate-700">
											{feedback.source || "N/A"}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Created At:</span>
										<span className="text-xs text-slate-700">
											{formatTimestamp(feedback.created_at)}
										</span>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}

// Aggregated Feedback Row Component
interface FeedbackRowProps {
	feedback: Feedback;
	onUpdateStatus: (feedbackId: number, status: FeedbackStatus) => void;
	onDelete: (feedback: Feedback) => void;
	isUpdating?: boolean;
}

function FeedbackRow({
	feedback,
	onUpdateStatus,
	onDelete,
	isUpdating = false,
}: FeedbackRowProps) {
	const [expanded, setExpanded] = useState(false);
	const StatusIcon = getStatusIcon(feedback.feedback_status);

	const getStatusBg = () => {
		switch (feedback.feedback_status) {
			case "approved":
				return "bg-emerald-100";
			case "rejected":
				return "bg-red-100";
			case "pending":
				return "bg-amber-100";
		}
	};

	const getStatusIconColor = () => {
		switch (feedback.feedback_status) {
			case "approved":
				return "text-emerald-600";
			case "rejected":
				return "text-red-600";
			case "pending":
				return "text-amber-600";
		}
	};

	const getStatusBadgeClass = () => {
		switch (feedback.feedback_status) {
			case "approved":
				return "bg-emerald-100 text-emerald-700 hover:bg-emerald-100";
			case "rejected":
				return "bg-red-100 text-red-700 hover:bg-red-100";
			case "pending":
				return "bg-amber-100 text-amber-700 hover:bg-amber-100";
		}
	};

	return (
		<div className="hover:bg-slate-50/50 transition-colors">
			<div
				className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
				onClick={() => setExpanded(!expanded)}
			>
				<div className="flex items-center justify-between gap-4">
					<div className="flex items-center gap-3 flex-1 min-w-0">
						{/* Status Icon */}
						<div className="flex-shrink-0">
							<div
								className={`h-8 w-8 rounded-lg ${getStatusBg()} flex items-center justify-center`}
							>
								<StatusIcon className={`h-4 w-4 ${getStatusIconColor()}`} />
							</div>
						</div>

						{/* Main Info */}
						<div className="flex-1 min-w-0">
							<div className="flex items-center gap-2 flex-wrap">
								<span className="font-semibold text-slate-800 font-mono text-sm">
									#{feedback.feedback_id}
								</span>
								<Badge
									variant="outline"
									className="text-xs border-slate-200 text-slate-600"
								>
									{formatFeedbackName(feedback.feedback_name)}
								</Badge>
								<Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
									{feedback.agent_version}
								</Badge>
								<Badge
									className={`text-xs flex items-center gap-1 ${getStatusBadgeClass()}`}
								>
									<StatusIcon className="h-3 w-3" />
									{feedback.feedback_status.charAt(0).toUpperCase() +
										feedback.feedback_status.slice(1)}
								</Badge>
							</div>
							<p className="text-sm text-slate-500 mt-1 truncate">
								{formatFeedbackContent(feedback)}
							</p>
						</div>
					</div>

					{/* Right side: time and expand button */}
					<div className="flex items-center gap-3 flex-shrink-0">
						<div className="text-right">
							<p className="text-xs text-slate-500">
								{getRelativeTime(feedback.created_at)}
							</p>
							<p className="text-xs text-slate-400">
								{new Date(feedback.created_at * 1000).toLocaleDateString(
									"en-US",
									{
										month: "short",
										day: "numeric",
									},
								)}
							</p>
						</div>
						<div className="flex items-center gap-1">
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
								onClick={(e) => {
									e.stopPropagation();
									onDelete(feedback);
								}}
							>
								<Trash2 className="h-4 w-4" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
							>
								{expanded ? (
									<ChevronUp className="h-4 w-4" />
								) : (
									<ChevronDown className="h-4 w-4" />
								)}
							</Button>
						</div>
					</div>
				</div>
			</div>

			{/* Expanded Details */}
			{expanded && (
				<div className="border-t border-slate-100 p-4 space-y-4">
					<div className="grid gap-6 md:grid-cols-2">
						{/* Left Column */}
						<div className="space-y-4">
							<div>
								<h4 className="text-sm font-semibold mb-2 text-slate-800">
									Aggregated Feedback Content
								</h4>
								<p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg whitespace-pre-wrap">
									{formatFeedbackContent(feedback)}
								</p>
							</div>

							{feedback.feedback_metadata && (
								<div>
									<h4 className="text-sm font-semibold mb-2 text-slate-800">
										Metadata
									</h4>
									<div className="bg-slate-50 p-3 rounded-lg">
										<pre className="text-xs font-mono whitespace-pre-wrap text-slate-700">
											{(() => {
												try {
													return JSON.stringify(
														JSON.parse(feedback.feedback_metadata),
														null,
														2,
													);
												} catch {
													return feedback.feedback_metadata;
												}
											})()}
										</pre>
									</div>
								</div>
							)}
						</div>

						{/* Right Column */}
						<div className="space-y-4">
							<div>
								<h4 className="text-sm font-semibold mb-3 text-slate-800">
									Details
								</h4>
								<div className="space-y-2 bg-slate-50 p-3 rounded-lg">
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Feedback ID:</span>
										<span className="font-mono text-slate-700">
											#{feedback.feedback_id}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Agent Version:</span>
										<span className="text-slate-700">
											{feedback.agent_version}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Feedback Type:</span>
										<span className="text-slate-700">
											{formatFeedbackName(feedback.feedback_name)}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Status:</span>
										<Badge
											className={`text-xs flex items-center gap-1 ${getStatusBadgeClass()}`}
										>
											<StatusIcon className="h-3 w-3" />
											{feedback.feedback_status}
										</Badge>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Created At:</span>
										<span className="text-xs text-slate-700">
											{formatTimestamp(feedback.created_at)}
										</span>
									</div>
								</div>
							</div>

							<div>
								<h4 className="text-sm font-semibold mb-2 text-slate-800">
									Status Management
								</h4>
								<div className="flex gap-2">
									<Button
										size="sm"
										onClick={(e) => {
											e.stopPropagation();
											onUpdateStatus(feedback.feedback_id, "approved");
										}}
										disabled={isUpdating}
										className={`flex-1 ${feedback.feedback_status === "approved" ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 border-0" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
										variant={
											feedback.feedback_status === "approved"
												? "default"
												: "outline"
										}
									>
										{isUpdating ? (
											<RefreshCw className="h-4 w-4 mr-1 animate-spin" />
										) : (
											<ThumbsUp className="h-4 w-4 mr-1" />
										)}
										Approve
									</Button>
									<Button
										size="sm"
										onClick={(e) => {
											e.stopPropagation();
											onUpdateStatus(feedback.feedback_id, "rejected");
										}}
										disabled={isUpdating}
										className={`flex-1 ${feedback.feedback_status === "rejected" ? "bg-gradient-to-r from-red-500 to-rose-500 hover:from-red-600 hover:to-rose-600 border-0" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
										variant={
											feedback.feedback_status === "rejected"
												? "default"
												: "outline"
										}
									>
										{isUpdating ? (
											<RefreshCw className="h-4 w-4 mr-1 animate-spin" />
										) : (
											<ThumbsDown className="h-4 w-4 mr-1" />
										)}
										Reject
									</Button>
								</div>
							</div>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}

export default function FeedbacksPage() {
	const [activeTab, setActiveTab] = useState<
		"aggregated" | "current" | "pending" | "archived"
	>("aggregated");
	const [searchQuery, setSearchQuery] = useState("");
	const [selectedAgent, setSelectedAgent] = useState<string>("all");
	const [selectedFeedbackName, setSelectedFeedbackName] =
		useState<string>("all");
	const [selectedStatus, setSelectedStatus] = useState<string>("all");
	const [rawFeedbacks, setRawFeedbacks] = useState<RawFeedback[]>([]);
	const [rawFeedbackCounts, setRawFeedbackCounts] = useState<{
		current: number;
		pending: number;
		archived: number;
	}>({ current: 0, pending: 0, archived: 0 });
	const [feedbacks, setFeedbacks] = useState<Feedback[]>([]);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [updatingFeedbackId, setUpdatingFeedbackId] = useState<number | null>(
		null,
	);

	// Rerun feedback generation state
	const [showRerunFeedbackModal, setShowRerunFeedbackModal] = useState(false);
	const [rerunningFeedback, setRerunningFeedback] = useState(false);
	const [rerunAgentVersion, setRerunAgentVersion] = useState("");
	const [rerunFeedbackName, setRerunFeedbackName] = useState("");
	const [rerunSource, setRerunSource] = useState("");
	const [rerunStartDate, setRerunStartDate] = useState("");
	const [rerunEndDate, setRerunEndDate] = useState("");
	const [operationStatusFeedback, setOperationStatusFeedback] =
		useState<OperationStatusInfo | null>(null);
	const [showOperationBannerFeedback, setShowOperationBannerFeedback] =
		useState(false);

	// Run feedback aggregation state
	const [showRunAggregationModal, setShowRunAggregationModal] = useState(false);
	const [runningAggregation, setRunningAggregation] = useState(false);
	const [aggregationAgentVersion, setAggregationAgentVersion] = useState("");
	const [aggregationFeedbackName, setAggregationFeedbackName] = useState("");

	// Message modal state (matching profiles page pattern)
	const [showMessageModal, setShowMessageModal] = useState<boolean>(false);
	const [messageModalConfig, setMessageModalConfig] = useState<{
		title: string;
		message: string;
		type: "success" | "error";
	} | null>(null);

	// Delete confirmation state for raw feedbacks
	const [rawFeedbackToDelete, setRawFeedbackToDelete] =
		useState<RawFeedback | null>(null);
	const [deletingRawFeedback, setDeletingRawFeedback] =
		useState<boolean>(false);

	// Delete confirmation state for aggregated feedbacks
	const [feedbackToDelete, setFeedbackToDelete] = useState<Feedback | null>(
		null,
	);
	const [deletingFeedback, setDeletingFeedback] = useState<boolean>(false);

	// Upgrade/Downgrade state
	const [upgrading, setUpgrading] = useState<boolean>(false);
	const [downgrading, setDowngrading] = useState<boolean>(false);
	const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
	const [confirmModalConfig, setConfirmModalConfig] = useState<{
		title: string;
		description: string;
		action: "upgrade" | "downgrade";
	} | null>(null);

	// Adopt modal state
	const [showAdoptModal, setShowAdoptModal] = useState<boolean>(false);
	const [adoptArchiveCurrent, setAdoptArchiveCurrent] = useState<boolean>(true);
	const [adoptFeedbackName, setAdoptFeedbackName] = useState<string>("all");
	const [adoptAgentVersion, setAdoptAgentVersion] = useState<string>("all");

	// Fetch data from API
	useEffect(() => {
		const fetchData = async () => {
			setIsLoading(true);
			setError(null);
			try {
				const [rawResponse, feedbackResponse] = await Promise.all([
					getRawFeedbacks({ limit: 10000 }),
					getFeedbacks({ limit: 1000 }),
				]);

				if (rawResponse.success) {
					const allRaw = rawResponse.raw_feedbacks.sort(
						(a, b) => b.created_at - a.created_at,
					);
					setRawFeedbacks(allRaw);

					// Calculate counts by status
					setRawFeedbackCounts({
						current: allRaw.filter(
							(f) => f.status === null || f.status === undefined,
						).length,
						pending: allRaw.filter((f) => f.status === "pending").length,
						archived: allRaw.filter((f) => f.status === "archived").length,
					});
				}

				if (feedbackResponse.success) {
					setFeedbacks(
						feedbackResponse.feedbacks.sort(
							(a, b) => b.created_at - a.created_at,
						),
					);
				}
			} catch (err) {
				console.error("Error fetching feedbacks:", err);
				setError("Failed to load feedbacks. Please try again.");
			} finally {
				setIsLoading(false);
			}
		};

		fetchData();
	}, []);

	// Poll operation status for feedback generation rerun
	useEffect(() => {
		let intervalId: NodeJS.Timeout | null = null;

		const pollStatus = async () => {
			try {
				const response = await getOperationStatus("feedback_generation");
				if (response.success && response.operation_status) {
					setOperationStatusFeedback(response.operation_status);

					// If operation completed, failed, or cancelled, refresh data and stop polling
					if (
						response.operation_status.status === "completed" ||
						response.operation_status.status === "failed" ||
						response.operation_status.status === "cancelled"
					) {
						// Refresh feedback data
						const [rawResponse, feedbackResponse] = await Promise.all([
							getRawFeedbacks({ limit: 10000 }),
							getFeedbacks({ limit: 1000 }),
						]);

						if (rawResponse.success) {
							const allRaw = rawResponse.raw_feedbacks.sort(
								(a, b) => b.created_at - a.created_at,
							);
							setRawFeedbacks(allRaw);

							// Recalculate counts by status
							setRawFeedbackCounts({
								current: allRaw.filter(
									(f) => f.status === null || f.status === undefined,
								).length,
								pending: allRaw.filter((f) => f.status === "pending").length,
								archived: allRaw.filter((f) => f.status === "archived").length,
							});
						}

						if (feedbackResponse.success) {
							setFeedbacks(
								feedbackResponse.feedbacks.sort(
									(a, b) => b.created_at - a.created_at,
								),
							);
						}

						// Stop polling
						if (intervalId) {
							clearInterval(intervalId);
						}

						// Show completion/failure/cancellation message via modal
						if (response.operation_status.status === "completed") {
							setMessageModalConfig({
								title: "Feedback Generation Completed",
								message: `Successfully processed ${response.operation_status.stats?.total_interactions_processed || 0} interactions.`,
								type: "success",
							});
							setShowMessageModal(true);
						} else if (response.operation_status.status === "cancelled") {
							setMessageModalConfig({
								title: "Feedback Generation Cancelled",
								message: `Operation was cancelled after processing ${response.operation_status.processed_users}/${response.operation_status.total_users} users.`,
								type: "success",
							});
							setShowMessageModal(true);
							setShowOperationBannerFeedback(false);
						} else if (response.operation_status.status === "failed") {
							setMessageModalConfig({
								title: "Feedback Generation Failed",
								message:
									response.operation_status.error_message ||
									"An error occurred during feedback generation",
								type: "error",
							});
							setShowMessageModal(true);
						}
					}
				} else {
					// No operation in progress, stop polling if we were
					setOperationStatusFeedback(null);
					setShowOperationBannerFeedback(false);
					if (intervalId) {
						clearInterval(intervalId);
					}
				}
			} catch (error) {
				console.error("Error polling operation status:", error);
			}
		};

		// Start polling if banner is shown
		if (showOperationBannerFeedback) {
			pollStatus(); // Initial poll
			intervalId = setInterval(pollStatus, 3000); // Poll every 3 seconds
		}

		return () => {
			if (intervalId) {
				clearInterval(intervalId);
			}
		};
	}, [showOperationBannerFeedback]);

	// Helper to check if showing raw feedbacks
	const isRawTab =
		activeTab === "current" ||
		activeTab === "pending" ||
		activeTab === "archived";

	// Get unique values for filters
	const uniqueAgents = useMemo(() => {
		const agents = isRawTab
			? rawFeedbacks.map((f) => f.agent_version)
			: feedbacks.map((f) => f.agent_version);
		return Array.from(new Set(agents)).sort();
	}, [isRawTab, rawFeedbacks, feedbacks]);

	const uniqueFeedbackNames = useMemo(() => {
		const names = isRawTab
			? rawFeedbacks.map((f) => f.feedback_name)
			: feedbacks.map((f) => f.feedback_name);
		return Array.from(new Set(names)).sort();
	}, [isRawTab, rawFeedbacks, feedbacks]);

	// Unique values from pending raw feedbacks only (for adopt modal filters)
	const pendingFeedbackNames = useMemo(() => {
		const names = rawFeedbacks
			.filter((f) => f.status === "pending")
			.map((f) => f.feedback_name);
		return Array.from(new Set(names)).sort();
	}, [rawFeedbacks]);

	const pendingAgentVersions = useMemo(() => {
		const versions = rawFeedbacks
			.filter((f) => f.status === "pending")
			.map((f) => f.agent_version);
		return Array.from(new Set(versions)).sort();
	}, [rawFeedbacks]);

	// Filter raw feedbacks
	const filteredRawFeedbacks = useMemo(() => {
		return rawFeedbacks.filter((feedback) => {
			// Filter by status tab
			const matchesStatusTab = (() => {
				switch (activeTab) {
					case "current":
						return feedback.status === null || feedback.status === undefined;
					case "pending":
						return feedback.status === "pending";
					case "archived":
						return feedback.status === "archived";
					default:
						return true; // aggregated tab doesn't show raw feedbacks
				}
			})();

			const matchesSearch =
				searchQuery === "" ||
				feedback.feedback_content
					.toLowerCase()
					.includes(searchQuery.toLowerCase()) ||
				feedback.request_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
				feedback.feedback_name
					.toLowerCase()
					.includes(searchQuery.toLowerCase());

			const matchesAgent =
				selectedAgent === "all" || feedback.agent_version === selectedAgent;
			const matchesFeedbackName =
				selectedFeedbackName === "all" ||
				feedback.feedback_name === selectedFeedbackName;

			return (
				matchesStatusTab && matchesSearch && matchesAgent && matchesFeedbackName
			);
		});
	}, [
		rawFeedbacks,
		activeTab,
		searchQuery,
		selectedAgent,
		selectedFeedbackName,
	]);

	// Filter aggregated feedbacks
	const filteredFeedbacks = useMemo(() => {
		return feedbacks.filter((feedback) => {
			const matchesSearch =
				searchQuery === "" ||
				feedback.feedback_content
					.toLowerCase()
					.includes(searchQuery.toLowerCase()) ||
				feedback.feedback_name
					.toLowerCase()
					.includes(searchQuery.toLowerCase()) ||
				feedback.feedback_metadata
					.toLowerCase()
					.includes(searchQuery.toLowerCase());

			const matchesAgent =
				selectedAgent === "all" || feedback.agent_version === selectedAgent;
			const matchesFeedbackName =
				selectedFeedbackName === "all" ||
				feedback.feedback_name === selectedFeedbackName;
			const matchesStatus =
				selectedStatus === "all" || feedback.feedback_status === selectedStatus;

			return (
				matchesSearch && matchesAgent && matchesFeedbackName && matchesStatus
			);
		});
	}, [
		feedbacks,
		searchQuery,
		selectedAgent,
		selectedFeedbackName,
		selectedStatus,
	]);

	// Calculate statistics
	const totalRaw = rawFeedbacks.length;
	const totalAggregated = feedbacks.length;
	const pending = feedbacks.filter(
		(f) => f.feedback_status === "pending",
	).length;
	const approved = feedbacks.filter(
		(f) => f.feedback_status === "approved",
	).length;
	const recentRaw = rawFeedbacks.filter((f) => {
		const hourAgo = Date.now() / 1000 - 60 * 60;
		return f.created_at > hourAgo;
	}).length;

	const updateFeedbackStatus = async (
		feedbackId: number,
		status: FeedbackStatus,
	) => {
		// Optimistically update the UI
		setFeedbacks(
			feedbacks.map((f) =>
				f.feedback_id === feedbackId ? { ...f, feedback_status: status } : f,
			),
		);
		setUpdatingFeedbackId(feedbackId);

		try {
			// Call the API to persist the status update
			const response = await updateFeedbackStatusAPI({
				feedback_id: feedbackId,
				feedback_status: status,
			});

			if (!response.success) {
				// Revert on failure
				setError(
					`Failed to update feedback status: ${response.msg || "Unknown error"}`,
				);
				// Fetch fresh data to revert the optimistic update
				const feedbackResponse = await getFeedbacks({ limit: 1000 });
				if (feedbackResponse.success) {
					setFeedbacks(
						feedbackResponse.feedbacks.sort(
							(a, b) => b.created_at - a.created_at,
						),
					);
				}
			}
		} catch (err) {
			console.error("Error updating feedback status:", err);
			setError("Failed to update feedback status. Please try again.");
			// Fetch fresh data to revert the optimistic update
			try {
				const feedbackResponse = await getFeedbacks({ limit: 1000 });
				if (feedbackResponse.success) {
					setFeedbacks(
						feedbackResponse.feedbacks.sort(
							(a, b) => b.created_at - a.created_at,
						),
					);
				}
			} catch (fetchErr) {
				console.error(
					"Error fetching feedbacks after failed update:",
					fetchErr,
				);
			}
		} finally {
			setUpdatingFeedbackId(null);
		}
	};

	const handleRefresh = async () => {
		setIsLoading(true);
		setError(null);
		try {
			const [rawResponse, feedbackResponse] = await Promise.all([
				getRawFeedbacks({ limit: 10000 }),
				getFeedbacks({ limit: 1000 }),
			]);

			if (rawResponse.success) {
				const allRaw = rawResponse.raw_feedbacks.sort(
					(a, b) => b.created_at - a.created_at,
				);
				setRawFeedbacks(allRaw);

				// Recalculate counts by status
				setRawFeedbackCounts({
					current: allRaw.filter(
						(f) => f.status === null || f.status === undefined,
					).length,
					pending: allRaw.filter((f) => f.status === "pending").length,
					archived: allRaw.filter((f) => f.status === "archived").length,
				});
			}

			if (feedbackResponse.success) {
				setFeedbacks(
					feedbackResponse.feedbacks.sort(
						(a, b) => b.created_at - a.created_at,
					),
				);
			}
		} catch (err) {
			console.error("Error fetching feedbacks:", err);
			setError("Failed to load feedbacks. Please try again.");
		} finally {
			setIsLoading(false);
		}
	};

	// Delete handlers for raw feedbacks
	const handleDeleteRawFeedbackClick = (feedback: RawFeedback) => {
		setRawFeedbackToDelete(feedback);
	};

	const confirmDeleteRawFeedback = async () => {
		if (!rawFeedbackToDelete) return;

		setDeletingRawFeedback(true);
		try {
			const response = await deleteRawFeedback({
				raw_feedback_id: rawFeedbackToDelete.raw_feedback_id,
			});

			if (response.success) {
				// Remove from the list
				setRawFeedbacks(
					rawFeedbacks.filter(
						(f) => f.raw_feedback_id !== rawFeedbackToDelete.raw_feedback_id,
					),
				);
				// Recalculate counts
				const updatedRaw = rawFeedbacks.filter(
					(f) => f.raw_feedback_id !== rawFeedbackToDelete.raw_feedback_id,
				);
				setRawFeedbackCounts({
					current: updatedRaw.filter(
						(f) => f.status === null || f.status === undefined,
					).length,
					pending: updatedRaw.filter((f) => f.status === "pending").length,
					archived: updatedRaw.filter((f) => f.status === "archived").length,
				});
				setRawFeedbackToDelete(null);
			} else {
				setMessageModalConfig({
					title: "Delete Failed",
					message: response.message || "Failed to delete raw feedback",
					type: "error",
				});
				setShowMessageModal(true);
			}
		} catch (err) {
			console.error("Error deleting raw feedback:", err);
			setMessageModalConfig({
				title: "Delete Failed",
				message:
					err instanceof Error
						? err.message
						: "An error occurred while deleting the raw feedback",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setDeletingRawFeedback(false);
		}
	};

	// Delete handlers for aggregated feedbacks
	const handleDeleteFeedbackClick = (feedback: Feedback) => {
		setFeedbackToDelete(feedback);
	};

	const confirmDeleteFeedback = async () => {
		if (!feedbackToDelete) return;

		setDeletingFeedback(true);
		try {
			const response = await deleteFeedback({
				feedback_id: feedbackToDelete.feedback_id,
			});

			if (response.success) {
				// Remove from the list
				setFeedbacks(
					feedbacks.filter(
						(f) => f.feedback_id !== feedbackToDelete.feedback_id,
					),
				);
				setFeedbackToDelete(null);
			} else {
				setMessageModalConfig({
					title: "Delete Failed",
					message: response.message || "Failed to delete feedback",
					type: "error",
				});
				setShowMessageModal(true);
			}
		} catch (err) {
			console.error("Error deleting feedback:", err);
			setMessageModalConfig({
				title: "Delete Failed",
				message:
					err instanceof Error
						? err.message
						: "An error occurred while deleting the feedback",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setDeletingFeedback(false);
		}
	};

	const handleRerunFeedbackGeneration = async () => {
		if (!rerunAgentVersion.trim()) {
			setMessageModalConfig({
				title: "Validation Error",
				message: "Agent version is required",
				type: "error",
			});
			setShowMessageModal(true);
			return;
		}

		setRerunningFeedback(true);
		try {
			const request: any = {
				agent_version: rerunAgentVersion.trim(),
			};

			// Add optional filters if provided
			if (rerunFeedbackName.trim()) {
				request.feedback_name = rerunFeedbackName.trim();
			}
			if (rerunSource.trim()) {
				request.source = rerunSource.trim();
			}
			if (rerunStartDate) {
				request.start_time = new Date(rerunStartDate).toISOString();
			}
			if (rerunEndDate) {
				request.end_time = new Date(rerunEndDate).toISOString();
			}

			// Fire-and-forget API call
			rerunFeedbackGeneration(request);

			// Close modal immediately and show success message
			setShowRerunFeedbackModal(false);

			// Start polling for operation status after a short delay
			// This gives the backend time to create the operation status entry
			setTimeout(() => {
				setShowOperationBannerFeedback(true);
			}, 1500);

			// Reset form fields
			setRerunAgentVersion("");
			setRerunFeedbackName("");
			setRerunSource("");
			setRerunStartDate("");
			setRerunEndDate("");

			setMessageModalConfig({
				title: "Feedback Generation Started",
				message:
					"Feedback generation has been started in the background. You can monitor progress in the banner above.",
				type: "success",
			});
			setShowMessageModal(true);
		} catch (error: any) {
			console.error("Error starting feedback rerun:", error);
			setMessageModalConfig({
				title: "Error Starting Feedback Generation",
				message: error.message || "An unexpected error occurred",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setRerunningFeedback(false);
		}
	};

	const handleRunFeedbackAggregation = async () => {
		if (!aggregationAgentVersion.trim()) {
			setMessageModalConfig({
				title: "Validation Error",
				message: "Agent version is required",
				type: "error",
			});
			setShowMessageModal(true);
			return;
		}

		if (!aggregationFeedbackName.trim()) {
			setMessageModalConfig({
				title: "Validation Error",
				message: "Feedback name is required",
				type: "error",
			});
			setShowMessageModal(true);
			return;
		}

		setRunningAggregation(true);
		try {
			const response = await runFeedbackAggregation({
				agent_version: aggregationAgentVersion.trim(),
				feedback_name: aggregationFeedbackName.trim(),
			});

			setShowRunAggregationModal(false);

			if (response.success) {
				setMessageModalConfig({
					title: "Feedback Aggregation Completed",
					message:
						response.message || "Feedback aggregation completed successfully.",
					type: "success",
				});
				setShowMessageModal(true);
				// Refresh data
				await handleRefresh();
			} else {
				setMessageModalConfig({
					title: "Feedback Aggregation Failed",
					message: response.message || "Failed to run feedback aggregation",
					type: "error",
				});
				setShowMessageModal(true);
			}

			// Reset form fields
			setAggregationAgentVersion("");
			setAggregationFeedbackName("");
		} catch (error: any) {
			console.error("Error running feedback aggregation:", error);
			setMessageModalConfig({
				title: "Error Running Feedback Aggregation",
				message: error.message || "An unexpected error occurred",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setRunningAggregation(false);
		}
	};

	const confirmUpgradeAllRawFeedbacks = () => {
		// Reset modal state to defaults
		setAdoptArchiveCurrent(true);
		setAdoptFeedbackName("all");
		setAdoptAgentVersion("all");
		setShowAdoptModal(true);
	};

	const handleUpgradeAllRawFeedbacks = async () => {
		setShowAdoptModal(false);
		setUpgrading(true);
		try {
			const request: import("@/lib/api").UpgradeRawFeedbacksRequest = {
				archive_current: adoptArchiveCurrent,
				...(adoptFeedbackName !== "all" && {
					feedback_name: adoptFeedbackName,
				}),
				...(adoptAgentVersion !== "all" && {
					agent_version: adoptAgentVersion,
				}),
			};
			const response = await upgradeAllRawFeedbacks(request);

			if (response.success) {
				const lines = [
					`${response.raw_feedbacks_promoted} raw feedbacks promoted to current`,
				];
				if (adoptArchiveCurrent) {
					lines.push(
						`${response.raw_feedbacks_archived} raw feedbacks archived`,
					);
					lines.push(
						`${response.raw_feedbacks_deleted} old archived raw feedbacks deleted`,
					);
				}
				setMessageModalConfig({
					title: "Raw Feedbacks Upgraded Successfully",
					message: lines.join("\n"),
					type: "success",
				});
				setShowMessageModal(true);
				// Refresh data
				await handleRefresh();
			} else {
				setMessageModalConfig({
					title: "Upgrade Failed",
					message: response.message || "Failed to upgrade raw feedbacks",
					type: "error",
				});
				setShowMessageModal(true);
			}
		} catch (error: any) {
			console.error("Error upgrading raw feedbacks:", error);
			setMessageModalConfig({
				title: "Upgrade Failed",
				message: error.message || "An unexpected error occurred",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setUpgrading(false);
		}
	};

	const confirmDowngradeAllRawFeedbacks = () => {
		setConfirmModalConfig({
			title: "Restore All Archived Raw Feedbacks?",
			description: `This will restore ${rawFeedbackCounts.archived} archived raw feedbacks to current status and archive ${rawFeedbackCounts.current} current raw feedbacks. This action cannot be undone.`,
			action: "downgrade",
		});
		setShowConfirmModal(true);
	};

	const handleDowngradeAllRawFeedbacks = async () => {
		setShowConfirmModal(false);
		setDowngrading(true);
		try {
			const response = await downgradeAllRawFeedbacks({});

			if (response.success) {
				setMessageModalConfig({
					title: "Raw Feedbacks Restored Successfully",
					message: `${response.raw_feedbacks_restored} raw feedbacks restored to current\n${response.raw_feedbacks_demoted} raw feedbacks archived`,
					type: "success",
				});
				setShowMessageModal(true);
				// Refresh data
				await handleRefresh();
			} else {
				setMessageModalConfig({
					title: "Restore Failed",
					message: response.message || "Failed to restore raw feedbacks",
					type: "error",
				});
				setShowMessageModal(true);
			}
		} catch (error: any) {
			console.error("Error downgrading raw feedbacks:", error);
			setMessageModalConfig({
				title: "Restore Failed",
				message: error.message || "An unexpected error occurred",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setDowngrading(false);
		}
	};

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
			{/* Header */}
			<div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
				<div className="p-8">
					<div className="max-w-[1800px] mx-auto">
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center shadow-lg shadow-orange-500/25">
								<BarChart3 className="h-5 w-5 text-white" />
							</div>
							<h1 className="text-3xl font-bold tracking-tight text-slate-800">
								Feedbacks
							</h1>
						</div>
						<p className="text-slate-500 mt-1 ml-13">
							Monitor and manage agent feedback data and performance insights
						</p>
					</div>
				</div>
			</div>

			{/* Operation Status Banner for Feedback Rerun */}
			{showOperationBannerFeedback &&
				operationStatusFeedback &&
				operationStatusFeedback.status === "in_progress" && (
					<div className="border-b" style={{ backgroundColor: "#a8dadc" }}>
						<div className="p-4 max-w-[1800px] mx-auto">
							<div className="flex items-center justify-between">
								<div className="flex items-center gap-3">
									<Loader2
										className="h-5 w-5 animate-spin"
										style={{ color: "#1d3557" }}
									/>
									<div>
										<p className="font-semibold" style={{ color: "#1d3557" }}>
											Feedback generation in progress
										</p>
										<p className="text-sm" style={{ color: "#1d3557" }}>
											{operationStatusFeedback.stats
												?.total_interactions_processed || 0}{" "}
											interactions processed
											{operationStatusFeedback.progress_percentage !==
												undefined &&
												` (${operationStatusFeedback.progress_percentage.toFixed(0)}%)`}
										</p>
									</div>
								</div>
								<Button
									variant="outline"
									size="sm"
									onClick={async () => {
										try {
											const result = await cancelOperation(
												"feedback_generation",
											);
											if (
												result.success &&
												result.cancelled_services.length > 0
											) {
												// Hide banner (triggers useEffect cleanup which stops polling)
												setShowOperationBannerFeedback(false);
												setMessageModalConfig({
													title: "Feedback Generation Cancelled",
													message: `Cancellation requested. The current user will finish processing, then the operation will stop.`,
													type: "success",
												});
												setShowMessageModal(true);
												// Refresh data
												const [rawResponse, feedbackResponse] =
													await Promise.all([
														getRawFeedbacks({ limit: 10000 }),
														getFeedbacks({ limit: 1000 }),
													]);
												if (rawResponse.success) {
													const allRaw = rawResponse.raw_feedbacks.sort(
														(a, b) => b.created_at - a.created_at,
													);
													setRawFeedbacks(allRaw);
													setRawFeedbackCounts({
														current: allRaw.filter(
															(f) =>
																f.status === null || f.status === undefined,
														).length,
														pending: allRaw.filter(
															(f) => f.status === "pending",
														).length,
														archived: allRaw.filter(
															(f) => f.status === "archived",
														).length,
													});
												}
												if (feedbackResponse.success) {
													setFeedbacks(
														feedbackResponse.feedbacks.sort(
															(a, b) => b.created_at - a.created_at,
														),
													);
												}
											}
										} catch (err) {
											console.error("Failed to cancel operation:", err);
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
					{/* Error Message */}
					{error && (
						<Card className="border-red-200 bg-red-50">
							<CardContent className="pt-6">
								<div className="flex items-center gap-3">
									<AlertCircle className="h-5 w-5 text-red-500" />
									<div>
										<p className="font-semibold text-red-600">
											Error Loading Feedbacks
										</p>
										<p className="text-sm text-slate-600">{error}</p>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={handleRefresh}
										className="ml-auto border-red-200 hover:bg-red-100"
									>
										<RefreshCw className="h-4 w-4 mr-2" />
										Retry
									</Button>
								</div>
							</CardContent>
						</Card>
					)}

					{isLoading ? (
						<Card className="border-slate-200 bg-white">
							<CardContent className="pt-6">
								<div className="flex items-center justify-center py-12">
									<div className="animate-spin rounded-full h-10 w-10 border-2 border-transparent border-t-orange-500 border-r-orange-500"></div>
									<p className="ml-3 text-slate-500">Loading feedbacks...</p>
								</div>
							</CardContent>
						</Card>
					) : (
						<>
							{/* Performance Overview */}
							<Card className="border-slate-200 bg-white hover:shadow-lg transition-all duration-300">
								<CardHeader className="pb-4">
									<div className="flex items-center gap-3">
										<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center shadow-lg shadow-orange-500/25">
											<BarChart3 className="h-5 w-5 text-white" />
										</div>
										<div>
											<CardTitle className="text-lg font-semibold text-slate-800">
												Feedback Overview
											</CardTitle>
											<CardDescription className="text-xs mt-0.5 text-slate-500">
												{totalRaw} raw feedback{totalRaw !== 1 ? "s" : ""}{" "}
												collected
											</CardDescription>
										</div>
									</div>
								</CardHeader>
								<CardContent>
									<div className="grid grid-cols-2 gap-4 md:flex md:gap-0 md:divide-x md:divide-slate-200">
										{/* Raw Feedbacks */}
										<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
											<div className="flex items-center gap-1.5 mb-1">
												<FileText className="h-3.5 w-3.5 text-orange-500" />
												<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
													Raw
												</span>
											</div>
											<span className="text-2xl font-bold text-slate-800">
												{totalRaw}
											</span>
											<span className="text-xs text-slate-400 mt-0.5">
												individual items
											</span>
										</div>

										{/* Aggregated */}
										<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
											<div className="flex items-center gap-1.5 mb-1">
												<Layers className="h-3.5 w-3.5 text-purple-500" />
												<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
													Aggregated
												</span>
											</div>
											<span className="text-2xl font-bold text-slate-800">
												{totalAggregated}
											</span>
											<span className="text-xs text-slate-400 mt-0.5">
												processed summaries
											</span>
										</div>

										{/* Pending Review */}
										<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
											<div className="flex items-center gap-1.5 mb-1">
												<Clock className="h-3.5 w-3.5 text-amber-500" />
												<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
													Pending
												</span>
											</div>
											<span className="text-2xl font-bold text-slate-800">
												{pending}
											</span>
											<span className="text-xs text-slate-400 mt-0.5">
												awaiting approval
											</span>
										</div>

										{/* Approved */}
										<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
											<div className="flex items-center gap-1.5 mb-1">
												<CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
												<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
													Approved
												</span>
											</div>
											<span className="text-2xl font-bold text-slate-800">
												{approved}
											</span>
											<span className="text-xs text-slate-400 mt-0.5">
												validated feedbacks
											</span>
										</div>

										{/* Recent (1h) */}
										<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
											<div className="flex items-center gap-1.5 mb-1">
												<BarChart3 className="h-3.5 w-3.5 text-blue-500" />
												<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
													Recent (1h)
												</span>
											</div>
											<span className="text-2xl font-bold text-slate-800">
												{recentRaw}
											</span>
											<span className="text-xs text-slate-400 mt-0.5">
												new raw feedbacks
											</span>
										</div>
									</div>
								</CardContent>
							</Card>

							{/* Tabs */}
							<div className="flex gap-2 border-b border-slate-200 overflow-x-auto pb-px -mb-px">
								<Button
									variant={activeTab === "aggregated" ? "default" : "ghost"}
									onClick={() => setActiveTab("aggregated")}
									className={`rounded-b-none transition-colors flex-shrink-0 ${
										activeTab === "aggregated"
											? "bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 border-0"
											: "text-slate-600 hover:bg-slate-100"
									}`}
								>
									<Layers className="h-4 w-4 mr-2" />
									Aggregated
									<Badge
										className={`ml-2 ${activeTab === "aggregated" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}
									>
										{totalAggregated}
									</Badge>
								</Button>
								<Button
									variant={activeTab === "current" ? "default" : "ghost"}
									onClick={() => setActiveTab("current")}
									className={`rounded-b-none transition-colors flex-shrink-0 ${
										activeTab === "current"
											? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 border-0"
											: "text-slate-600 hover:bg-slate-100"
									}`}
								>
									<CheckCircle2 className="h-4 w-4 mr-2" />
									Current Raw
									<Badge
										className={`ml-2 ${activeTab === "current" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}
									>
										{rawFeedbackCounts.current}
									</Badge>
								</Button>
								<Button
									variant={activeTab === "pending" ? "default" : "ghost"}
									onClick={() => setActiveTab("pending")}
									className={`rounded-b-none transition-colors flex-shrink-0 ${
										activeTab === "pending"
											? "bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 border-0"
											: "text-slate-600 hover:bg-slate-100"
									}`}
								>
									<Clock className="h-4 w-4 mr-2" />
									Pending Raw
									<Badge
										className={`ml-2 ${activeTab === "pending" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}
									>
										{rawFeedbackCounts.pending}
									</Badge>
								</Button>
								<Button
									variant={activeTab === "archived" ? "default" : "ghost"}
									onClick={() => setActiveTab("archived")}
									className={`rounded-b-none transition-colors flex-shrink-0 ${
										activeTab === "archived"
											? "bg-gradient-to-r from-slate-500 to-slate-600 hover:from-slate-600 hover:to-slate-700 border-0"
											: "text-slate-600 hover:bg-slate-100"
									}`}
								>
									<Archive className="h-4 w-4 mr-2" />
									Archived Raw
									<Badge
										className={`ml-2 ${activeTab === "archived" ? "bg-white/20 text-white hover:bg-white/20" : "bg-slate-100 text-slate-600 hover:bg-slate-100"}`}
									>
										{rawFeedbackCounts.archived}
									</Badge>
								</Button>
							</div>

							{/* Run Feedback Aggregation Action Card - Only show in aggregated tab */}
							{activeTab === "aggregated" && (
								<Card className="border-purple-200 bg-gradient-to-br from-purple-50 to-pink-50">
									<CardContent className="pt-6">
										<div className="flex items-center justify-between">
											<div className="flex items-center gap-3">
												<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg">
													<Layers className="h-5 w-5 text-white" />
												</div>
												<div>
													<h3 className="font-semibold text-slate-800">
														Run Feedback Aggregation
													</h3>
													<p className="text-sm text-slate-500">
														Aggregate raw feedbacks into consolidated insights
														for a specific agent version and feedback type.
													</p>
												</div>
											</div>
											<Button
												onClick={() => setShowRunAggregationModal(true)}
												disabled={runningAggregation}
												className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white border-0"
											>
												{runningAggregation ? (
													<>
														<Loader2 className="h-4 w-4 mr-2 animate-spin" />
														Running...
													</>
												) : (
													<>
														<Layers className="h-4 w-4 mr-2" />
														Run Aggregation
													</>
												)}
											</Button>
										</div>
									</CardContent>
								</Card>
							)}

							{/* Rerun Feedback Action Card - Only show in current raw tab */}
							{activeTab === "current" && (
								<Card className="border-blue-200 bg-gradient-to-br from-blue-50 to-cyan-50">
									<CardContent className="pt-6">
										<div className="flex items-center justify-between">
											<div className="flex items-center gap-3">
												<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-lg">
													<RefreshCw className="h-5 w-5 text-white" />
												</div>
												<div>
													<h3 className="font-semibold text-slate-800">
														Rerun Feedback Generation
													</h3>
													<p className="text-sm text-slate-500">
														Generate new feedbacks from interactions with
														optional filters.
													</p>
												</div>
											</div>
											<Button
												onClick={() => setShowRerunFeedbackModal(true)}
												disabled={
													operationStatusFeedback?.status === "in_progress"
												}
												className="bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white border-0"
											>
												{operationStatusFeedback?.status === "in_progress" ? (
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

							{/* Adopt Pending Raw Feedbacks Action Card - Only show on pending tab with pending feedbacks */}
							{activeTab === "pending" && rawFeedbackCounts.pending > 0 && (
								<Card className="border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50">
									<CardContent className="pt-6">
										<div className="flex items-center justify-between">
											<div className="flex items-center gap-3">
												<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center shadow-lg">
													<CheckCircle className="h-5 w-5 text-white" />
												</div>
												<div>
													<h3 className="font-semibold text-slate-800">
														Adopt Pending Raw Feedbacks
													</h3>
													<p className="text-sm text-slate-500">
														Promote {rawFeedbackCounts.pending} pending raw
														feedbacks to current status with optional filtering
														and archive control.
													</p>
												</div>
											</div>
											<Button
												onClick={confirmUpgradeAllRawFeedbacks}
												disabled={upgrading}
												className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white border-0"
											>
												{upgrading ? (
													<>
														<Loader2 className="h-4 w-4 mr-2 animate-spin" />
														Adopting...
													</>
												) : (
													<>
														<CheckCircle className="h-4 w-4 mr-2" />
														Adopt Pending Raw Feedbacks
													</>
												)}
											</Button>
										</div>
									</CardContent>
								</Card>
							)}

							{/* Restore Archived Raw Feedbacks Action Card - Only show on archived tab with archived feedbacks */}
							{activeTab === "archived" && rawFeedbackCounts.archived > 0 && (
								<Card className="border-indigo-200 bg-gradient-to-br from-indigo-50 to-purple-50">
									<CardContent className="pt-6">
										<div className="flex items-center justify-between">
											<div className="flex items-center gap-3">
												<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg">
													<RotateCcw className="h-5 w-5 text-white" />
												</div>
												<div>
													<h3 className="font-semibold text-slate-800">
														Restore All Archived Raw Feedbacks to Current
													</h3>
													<p className="text-sm text-slate-500">
														Restore {rawFeedbackCounts.archived} archived raw
														feedbacks to current status, archiving existing
														current raw feedbacks.
													</p>
												</div>
											</div>
											<Button
												onClick={confirmDowngradeAllRawFeedbacks}
												disabled={downgrading}
												className="bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white border-0"
											>
												{downgrading ? (
													<>
														<Loader2 className="h-4 w-4 mr-2 animate-spin" />
														Restoring...
													</>
												) : (
													<>
														<RotateCcw className="h-4 w-4 mr-2" />
														Restore Archived Raw Feedbacks
													</>
												)}
											</Button>
										</div>
									</CardContent>
								</Card>
							)}

							{/* Filters */}
							<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
								<CardHeader className="pb-4">
									<div className="flex items-center gap-3">
										<Filter className="h-4 w-4 text-slate-400" />
										<div>
											<CardTitle className="text-lg font-semibold text-slate-800">
												Filters
											</CardTitle>
											<CardDescription className="text-xs mt-1 text-slate-500">
												Refine feedback results
											</CardDescription>
										</div>
									</div>
								</CardHeader>
								<CardContent>
									<div
										className={`grid gap-4 ${!isRawTab ? "md:grid-cols-4" : "md:grid-cols-3"}`}
									>
										{/* Search */}
										<div>
											<label className="text-sm font-medium mb-2 block text-slate-700">
												Search
											</label>
											<div className="relative">
												<Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
												<Input
													placeholder="Content or metadata..."
													value={searchQuery}
													onChange={(e) => setSearchQuery(e.target.value)}
													className="pl-9 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
												/>
											</div>
										</div>

										{/* Agent Version Filter */}
										<div>
											<label className="text-sm font-medium mb-2 block text-slate-700">
												Agent Version
											</label>
											<select
												value={selectedAgent}
												onChange={(e) => setSelectedAgent(e.target.value)}
												className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
											>
												<option value="all">All Agents</option>
												{uniqueAgents.map((agent) => (
													<option key={agent} value={agent}>
														{agent}
													</option>
												))}
											</select>
										</div>

										{/* Feedback Type Filter */}
										<div>
											<label className="text-sm font-medium mb-2 block text-slate-700">
												Feedback Type
											</label>
											<select
												value={selectedFeedbackName}
												onChange={(e) =>
													setSelectedFeedbackName(e.target.value)
												}
												className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
											>
												<option value="all">All Types</option>
												{uniqueFeedbackNames.map((name) => (
													<option key={name} value={name}>
														{formatFeedbackName(name)}
													</option>
												))}
											</select>
										</div>

										{/* Status Filter (only for aggregated) */}
										{!isRawTab && (
											<div>
												<label className="text-sm font-medium mb-2 block text-slate-700">
													Status
												</label>
												<select
													value={selectedStatus}
													onChange={(e) => setSelectedStatus(e.target.value)}
													className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
												>
													<option value="all">All Statuses</option>
													<option value="pending">Pending</option>
													<option value="approved">Approved</option>
													<option value="rejected">Rejected</option>
												</select>
											</div>
										)}
									</div>

									{/* Active filters indicator */}
									{(searchQuery ||
										selectedAgent !== "all" ||
										selectedFeedbackName !== "all" ||
										selectedStatus !== "all") && (
										<div className="mt-4 flex items-center gap-2">
											<span className="text-sm text-slate-500">
												Active filters:
											</span>
											{searchQuery && (
												<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
													Search: {searchQuery}
												</Badge>
											)}
											{selectedAgent !== "all" && (
												<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
													Agent: {selectedAgent}
												</Badge>
											)}
											{selectedFeedbackName !== "all" && (
												<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
													Type: {formatFeedbackName(selectedFeedbackName)}
												</Badge>
											)}
											{selectedStatus !== "all" && (
												<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
													Status: {selectedStatus}
												</Badge>
											)}
											<Button
												variant="ghost"
												size="sm"
												className="h-6 text-xs text-slate-500 hover:text-slate-700"
												onClick={() => {
													setSearchQuery("");
													setSelectedAgent("all");
													setSelectedFeedbackName("all");
													setSelectedStatus("all");
												}}
											>
												Clear all
											</Button>
										</div>
									)}
								</CardContent>
							</Card>

							{/* Results */}
							<div>
								<div className="mb-4 flex items-center justify-between">
									<div>
										<h2 className="text-lg font-semibold text-slate-800">
											{activeTab === "aggregated"
												? "Aggregated"
												: activeTab === "current"
													? "Current Raw"
													: activeTab === "pending"
														? "Pending Raw"
														: "Archived Raw"}{" "}
											Feedback Results
										</h2>
										<p className="text-xs mt-1 text-slate-500">
											Showing{" "}
											{isRawTab
												? filteredRawFeedbacks.length
												: filteredFeedbacks.length}{" "}
											of{" "}
											{isRawTab
												? rawFeedbackCounts[
														activeTab as "current" | "pending" | "archived"
													]
												: totalAggregated}{" "}
											feedbacks
										</p>
									</div>
									<div className="flex gap-2">
										<Button
											variant="outline"
											size="sm"
											onClick={handleRefresh}
											disabled={isLoading}
											className="border-slate-200 hover:bg-slate-50 text-slate-700"
										>
											<RefreshCw
												className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`}
											/>
											Refresh
										</Button>
									</div>
								</div>
								{isRawTab ? (
									filteredRawFeedbacks.length === 0 ? (
										<div className="text-center py-12">
											<Calendar className="h-12 w-12 text-slate-300 mx-auto mb-4" />
											<h3 className="text-lg font-semibold text-slate-800 mb-2">
												No {activeTab} raw feedbacks found
											</h3>
											<p className="text-sm text-slate-500">
												Try adjusting your search or filter criteria
											</p>
										</div>
									) : (
										<div className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100">
											{filteredRawFeedbacks.map((feedback) => (
												<RawFeedbackRow
													key={feedback.raw_feedback_id}
													feedback={feedback}
													onDelete={handleDeleteRawFeedbackClick}
												/>
											))}
										</div>
									)
								) : filteredFeedbacks.length === 0 ? (
									<div className="text-center py-12">
										<Calendar className="h-12 w-12 text-slate-300 mx-auto mb-4" />
										<h3 className="text-lg font-semibold text-slate-800 mb-2">
											No aggregated feedbacks found
										</h3>
										<p className="text-sm text-slate-500">
											Try adjusting your search or filter criteria
										</p>
									</div>
								) : (
									<div className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100">
										{filteredFeedbacks.map((feedback) => (
											<FeedbackRow
												key={feedback.feedback_id}
												feedback={feedback}
												onUpdateStatus={updateFeedbackStatus}
												onDelete={handleDeleteFeedbackClick}
												isUpdating={updatingFeedbackId === feedback.feedback_id}
											/>
										))}
									</div>
								)}
							</div>
						</>
					)}
				</div>
			</div>

			{/* Rerun Feedback Generation Modal */}
			<Dialog
				open={showRerunFeedbackModal}
				onOpenChange={setShowRerunFeedbackModal}
			>
				<DialogContent className="sm:max-w-[550px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-50 to-amber-50 flex items-center justify-center flex-shrink-0 border border-orange-200">
								<RefreshCw className="h-5 w-5 text-orange-600" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								Rerun Feedback Generation
							</DialogTitle>
						</div>
						<DialogDescription className="text-slate-600">
							Generate new feedbacks from interactions with optional filters.
							All fields except agent version are optional.
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-5 py-4">
						{/* Agent Version */}
						<div className="space-y-2">
							<Label htmlFor="rerun-agent-version" className="font-medium">
								Agent Version <span className="text-destructive">*</span>
							</Label>
							<Input
								id="rerun-agent-version"
								type="text"
								placeholder="e.g., v1.0"
								value={rerunAgentVersion}
								onChange={(e) => setRerunAgentVersion(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Required: The agent version to generate feedbacks for
							</p>
						</div>

						{/* Feedback Name */}
						<div className="space-y-2">
							<Label htmlFor="rerun-feedback-name" className="font-medium">
								Feedback Name
							</Label>
							<Input
								id="rerun-feedback-name"
								type="text"
								placeholder="e.g., task_success"
								value={rerunFeedbackName}
								onChange={(e) => setRerunFeedbackName(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Optional: Filter to specific feedback type (leave empty for all
								types)
							</p>
						</div>

						{/* Source Filter */}
						<div className="space-y-2">
							<Label htmlFor="rerun-source" className="font-medium">
								Source Filter
							</Label>
							<Input
								id="rerun-source"
								type="text"
								placeholder="e.g., web_app, mobile_app"
								value={rerunSource}
								onChange={(e) => setRerunSource(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Optional: Only generate feedbacks from this source
							</p>
						</div>

						{/* Start Date & Time */}
						<div className="space-y-2">
							<Label htmlFor="rerun-start-date" className="font-medium">
								Start Date & Time
							</Label>
							<Input
								id="rerun-start-date"
								type="datetime-local"
								value={rerunStartDate}
								onChange={(e) => setRerunStartDate(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Optional: Only process interactions after this time
							</p>
						</div>

						{/* End Date & Time */}
						<div className="space-y-2">
							<Label htmlFor="rerun-end-date" className="font-medium">
								End Date & Time
							</Label>
							<Input
								id="rerun-end-date"
								type="datetime-local"
								value={rerunEndDate}
								onChange={(e) => setRerunEndDate(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Optional: Only process interactions before this time
							</p>
						</div>
					</div>

					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => {
								setShowRerunFeedbackModal(false);
								setRerunAgentVersion("");
								setRerunFeedbackName("");
								setRerunStartDate("");
								setRerunEndDate("");
							}}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleRerunFeedbackGeneration}
							disabled={rerunningFeedback}
							className="min-w-[180px] bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white border-0 shadow-md shadow-orange-500/25"
						>
							{rerunningFeedback ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Starting...
								</>
							) : (
								<>
									<RefreshCw className="mr-2 h-4 w-4" />
									Rerun Feedback Generation
								</>
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Run Feedback Aggregation Modal */}
			<Dialog
				open={showRunAggregationModal}
				onOpenChange={setShowRunAggregationModal}
			>
				<DialogContent className="sm:max-w-[500px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-50 to-pink-50 flex items-center justify-center flex-shrink-0 border border-purple-200">
								<Layers className="h-5 w-5 text-purple-600" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								Run Feedback Aggregation
							</DialogTitle>
						</div>
						<DialogDescription className="text-slate-600">
							Aggregate raw feedbacks into consolidated insights. Both agent
							version and feedback name are required.
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-5 py-4">
						{/* Agent Version */}
						<div className="space-y-2">
							<Label
								htmlFor="aggregation-agent-version"
								className="font-medium"
							>
								Agent Version <span className="text-destructive">*</span>
							</Label>
							<Input
								id="aggregation-agent-version"
								type="text"
								placeholder="e.g., v1.0"
								value={aggregationAgentVersion}
								onChange={(e) => setAggregationAgentVersion(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Required: The agent version to aggregate feedbacks for
							</p>
						</div>

						{/* Feedback Name */}
						<div className="space-y-2">
							<Label
								htmlFor="aggregation-feedback-name"
								className="font-medium"
							>
								Feedback Name <span className="text-destructive">*</span>
							</Label>
							<Input
								id="aggregation-feedback-name"
								type="text"
								placeholder="e.g., task_success"
								value={aggregationFeedbackName}
								onChange={(e) => setAggregationFeedbackName(e.target.value)}
								className="h-10"
							/>
							<p className="text-xs text-muted-foreground">
								Required: The feedback type to aggregate
							</p>
						</div>
					</div>

					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => {
								setShowRunAggregationModal(false);
								setAggregationAgentVersion("");
								setAggregationFeedbackName("");
							}}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleRunFeedbackAggregation}
							disabled={runningAggregation}
							className="min-w-[180px] bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white border-0 shadow-md shadow-purple-500/25"
						>
							{runningAggregation ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Running...
								</>
							) : (
								<>
									<Layers className="mr-2 h-4 w-4" />
									Run Aggregation
								</>
							)}
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

			{/* Confirmation Modal for Downgrade */}
			<Dialog open={showConfirmModal} onOpenChange={setShowConfirmModal}>
				<DialogContent className="sm:max-w-[500px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-50 to-cyan-50 flex items-center justify-center flex-shrink-0 border border-blue-200">
								<RotateCcw className="h-5 w-5 text-blue-600" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								{confirmModalConfig?.title}
							</DialogTitle>
						</div>
						<DialogDescription className="pt-2 text-slate-600">
							{confirmModalConfig?.description}
						</DialogDescription>
					</DialogHeader>
					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => setShowConfirmModal(false)}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleDowngradeAllRawFeedbacks}
							className="bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white border-0 shadow-md shadow-blue-500/25"
						>
							<RotateCcw className="h-4 w-4 mr-2" />
							Restore Archived
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Adopt Pending Raw Feedbacks Modal */}
			<Dialog open={showAdoptModal} onOpenChange={setShowAdoptModal}>
				<DialogContent className="sm:max-w-[540px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 flex items-center justify-center flex-shrink-0 border border-emerald-200">
								<CheckCircle className="h-5 w-5 text-emerald-600" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								Adopt Pending Raw Feedbacks
							</DialogTitle>
						</div>
						<DialogDescription className="pt-2 text-slate-600">
							Promote pending raw feedbacks to current status. Choose how to
							handle existing current feedbacks and optionally filter which
							pending feedbacks to adopt.
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-5 py-2">
						{/* Adoption Mode */}
						<div>
							<label className="text-sm font-medium mb-3 block text-slate-700">
								Adoption Mode
							</label>
							<div className="space-y-2">
								<label className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 cursor-pointer hover:bg-slate-50 transition-colors has-[:checked]:border-emerald-300 has-[:checked]:bg-emerald-50/50">
									<input
										type="radio"
										name="adoptMode"
										checked={adoptArchiveCurrent}
										onChange={() => setAdoptArchiveCurrent(true)}
										className="mt-0.5 accent-emerald-600"
									/>
									<div>
										<div className="font-medium text-sm text-slate-800">
											Adopt & Archive Current
										</div>
										<div className="text-xs text-slate-500 mt-0.5">
											Archive all current raw feedbacks and replace them with
											pending ones. Previously archived feedbacks will be
											deleted.
										</div>
									</div>
								</label>
								<label className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 cursor-pointer hover:bg-slate-50 transition-colors has-[:checked]:border-emerald-300 has-[:checked]:bg-emerald-50/50">
									<input
										type="radio"
										name="adoptMode"
										checked={!adoptArchiveCurrent}
										onChange={() => setAdoptArchiveCurrent(false)}
										className="mt-0.5 accent-emerald-600"
									/>
									<div>
										<div className="font-medium text-sm text-slate-800">
											Adopt Only
										</div>
										<div className="text-xs text-slate-500 mt-0.5">
											Promote pending feedbacks to current without archiving
											existing ones. Current feedbacks remain unchanged.
										</div>
									</div>
								</label>
							</div>
						</div>

						{/* Filters */}
						<div className="grid grid-cols-2 gap-4">
							<div>
								<label className="text-sm font-medium mb-2 block text-slate-700">
									Feedback Name
								</label>
								<select
									value={adoptFeedbackName}
									onChange={(e) => setAdoptFeedbackName(e.target.value)}
									className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-200 focus:border-emerald-300"
								>
									<option value="all">All Types</option>
									{pendingFeedbackNames.map((name) => (
										<option key={name} value={name}>
											{formatFeedbackName(name)}
										</option>
									))}
								</select>
							</div>
							<div>
								<label className="text-sm font-medium mb-2 block text-slate-700">
									Agent Version
								</label>
								<select
									value={adoptAgentVersion}
									onChange={(e) => setAdoptAgentVersion(e.target.value)}
									className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-200 focus:border-emerald-300"
								>
									<option value="all">All Versions</option>
									{pendingAgentVersions.map((version) => (
										<option key={version} value={version}>
											{version}
										</option>
									))}
								</select>
							</div>
						</div>

						{/* Summary */}
						<div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
							<div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
								Summary
							</div>
							<ul className="space-y-1 text-sm text-slate-700">
								<li className="flex items-center gap-2">
									<CheckCircle className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
									Promote{" "}
									{adoptFeedbackName === "all" && adoptAgentVersion === "all"
										? `${rawFeedbackCounts.pending} pending`
										: "matching pending"}{" "}
									feedbacks to current
								</li>
								{adoptArchiveCurrent ? (
									<>
										<li className="flex items-center gap-2">
											<Archive className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
											Archive {rawFeedbackCounts.current} current feedbacks
										</li>
										<li className="flex items-center gap-2">
											<Trash2 className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
											Delete {rawFeedbackCounts.archived} previously archived
											feedbacks
										</li>
									</>
								) : (
									<li className="flex items-center gap-2">
										<CheckCircle2 className="h-3.5 w-3.5 text-slate-400 flex-shrink-0" />
										Keep {rawFeedbackCounts.current} current feedbacks unchanged
									</li>
								)}
							</ul>
						</div>
					</div>

					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => setShowAdoptModal(false)}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleUpgradeAllRawFeedbacks}
							className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white border-0 shadow-md shadow-emerald-500/25"
						>
							<CheckCircle className="h-4 w-4 mr-2" />
							Adopt Pending
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Delete Confirmation Dialog for Raw Feedbacks */}
			<DeleteConfirmDialog
				open={!!rawFeedbackToDelete}
				onOpenChange={(open) => {
					if (!open) setRawFeedbackToDelete(null);
				}}
				onConfirm={confirmDeleteRawFeedback}
				title="Delete Raw Feedback"
				description="Are you sure you want to delete this raw feedback?"
				itemDetails={
					rawFeedbackToDelete && (
						<>
							<div className="flex justify-between">
								<span className="text-muted-foreground">Feedback ID:</span>
								<span className="font-mono text-xs">
									#{rawFeedbackToDelete.raw_feedback_id}
								</span>
							</div>
							<div className="flex justify-between">
								<span className="text-muted-foreground">Feedback Name:</span>
								<span>
									{formatFeedbackName(rawFeedbackToDelete.feedback_name)}
								</span>
							</div>
							<div>
								<span className="text-muted-foreground">Content:</span>
								<p className="text-sm mt-1 line-clamp-2">
									{rawFeedbackToDelete.feedback_content}
								</p>
							</div>
						</>
					)
				}
				loading={deletingRawFeedback}
				confirmButtonText="Delete Raw Feedback"
			/>

			{/* Delete Confirmation Dialog for Aggregated Feedbacks */}
			<DeleteConfirmDialog
				open={!!feedbackToDelete}
				onOpenChange={(open) => {
					if (!open) setFeedbackToDelete(null);
				}}
				onConfirm={confirmDeleteFeedback}
				title="Delete Aggregated Feedback"
				description="Are you sure you want to delete this aggregated feedback?"
				itemDetails={
					feedbackToDelete && (
						<>
							<div className="flex justify-between">
								<span className="text-muted-foreground">Feedback ID:</span>
								<span className="font-mono text-xs">
									#{feedbackToDelete.feedback_id}
								</span>
							</div>
							<div className="flex justify-between">
								<span className="text-muted-foreground">Feedback Name:</span>
								<span>
									{formatFeedbackName(feedbackToDelete.feedback_name)}
								</span>
							</div>
							<div>
								<span className="text-muted-foreground">Content:</span>
								<p className="text-sm mt-1 line-clamp-2">
									{feedbackToDelete.feedback_content}
								</p>
							</div>
						</>
					)
				}
				loading={deletingFeedback}
				confirmButtonText="Delete Feedback"
			/>
		</div>
	);
}

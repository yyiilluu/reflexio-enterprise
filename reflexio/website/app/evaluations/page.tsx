"use client";

import {
	Activity,
	AlertTriangle,
	ArrowUpRight,
	Calendar,
	CheckCircle,
	ChevronDown,
	ChevronUp,
	Filter,
	GitCompare,
	Loader2,
	MessageSquare,
	RefreshCw,
	RotateCcw,
	Search,
	XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
	type AgentSuccessEvaluationResult,
	getAgentSuccessEvaluationResults,
	getRequests,
	type Interaction,
	type RegularVsShadow,
} from "@/lib/api";

// Helper function to format timestamp
const formatDate = (timestamp: number): string => {
	const date = new Date(timestamp * 1000);
	return date.toLocaleString("en-US", {
		month: "short",
		day: "numeric",
		year: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
};

// Helper function to get relative time
const getRelativeTime = (timestamp: number): string => {
	const now = Date.now() / 1000;
	const diff = now - timestamp;

	if (diff < 60) return "Just now";
	if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
	if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
	return `${Math.floor(diff / 86400)}d ago`;
};

// Helper function to get comparison badge styling
const getComparisonBadgeStyle = (comparison: RegularVsShadow | null | undefined) => {
	if (!comparison) return null;
	switch (comparison) {
		case "regular_is_better":
			return {
				bg: "bg-emerald-100",
				text: "text-emerald-700",
				label: "Regular Better",
			};
		case "regular_is_slightly_better":
			return {
				bg: "bg-emerald-50",
				text: "text-emerald-600",
				label: "Regular Slightly Better",
			};
		case "shadow_is_better":
			return {
				bg: "bg-violet-100",
				text: "text-violet-700",
				label: "Shadow Better",
			};
		case "shadow_is_slightly_better":
			return {
				bg: "bg-violet-50",
				text: "text-violet-600",
				label: "Shadow Slightly Better",
			};
		case "tied":
			return { bg: "bg-slate-100", text: "text-slate-600", label: "Tied" };
		default:
			return null;
	}
};

// Conversation row component for side-by-side comparison
interface ConversationRowProps {
	interaction: Interaction;
}

function ConversationRow({ interaction }: ConversationRowProps) {
	const isUser = interaction.role === "User";
	const hasRegular = interaction.content && interaction.content.trim() !== "";
	const hasShadow = interaction.shadow_content && interaction.shadow_content.trim() !== "";

	// For user messages, show spanning both columns (same content)
	if (isUser) {
		return (
			<div className="col-span-2">
				<div className="flex items-center gap-2 mb-1">
					<Badge className="text-xs bg-blue-100 text-blue-700">User</Badge>
				</div>
				<div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
					<p className="text-sm text-slate-700 whitespace-pre-wrap">{interaction.content}</p>
				</div>
			</div>
		);
	}

	// For assistant messages, show side-by-side
	return (
		<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
			{/* Regular Response */}
			<div>
				<div className="flex items-center gap-2 mb-1">
					<Badge className="text-xs bg-slate-100 text-slate-600">Assistant (Regular)</Badge>
				</div>
				<div className="bg-white border border-emerald-200 rounded-lg p-3 h-full">
					{hasRegular ? (
						<p className="text-sm text-slate-700 whitespace-pre-wrap">{interaction.content}</p>
					) : (
						<p className="text-sm text-slate-400 italic">No content</p>
					)}
				</div>
			</div>

			{/* Shadow Response */}
			<div>
				<div className="flex items-center gap-2 mb-1">
					<Badge className="text-xs bg-slate-100 text-slate-600">Assistant (Shadow)</Badge>
				</div>
				<div className="bg-white border border-violet-200 rounded-lg p-3 h-full">
					{hasShadow ? (
						<p className="text-sm text-slate-700 whitespace-pre-wrap">
							{interaction.shadow_content}
						</p>
					) : (
						<p className="text-sm text-slate-400 italic">No shadow content</p>
					)}
				</div>
			</div>
		</div>
	);
}

// Comparison section component
interface ComparisonSectionProps {
	interactions: Interaction[] | null;
	loading: boolean;
	error: string | null;
	onRetry: () => void;
}

function ComparisonSection({ interactions, loading, error, onRetry }: ComparisonSectionProps) {
	// Loading state
	if (loading) {
		return (
			<div className="flex items-center justify-center py-8">
				<Loader2 className="h-6 w-6 animate-spin text-indigo-500 mr-2" />
				<span className="text-sm text-slate-500">Loading comparison data...</span>
			</div>
		);
	}

	// Error state
	if (error) {
		return (
			<div className="bg-red-50 border border-red-200 rounded-lg p-4">
				<div className="flex items-center gap-2">
					<AlertTriangle className="h-4 w-4 text-red-500" />
					<span className="text-sm text-red-600">{error}</span>
				</div>
				<Button
					variant="outline"
					size="sm"
					onClick={onRetry}
					className="mt-2 border-red-200 text-red-600 hover:bg-red-100"
				>
					<RefreshCw className="h-4 w-4 mr-2" />
					Retry
				</Button>
			</div>
		);
	}

	// No data state
	if (!interactions || interactions.length === 0) {
		return (
			<div className="text-center py-8">
				<GitCompare className="h-8 w-8 text-slate-300 mx-auto mb-2" />
				<p className="text-sm text-slate-500">No comparison data available</p>
			</div>
		);
	}

	// Comparison view
	return (
		<div className="space-y-4">
			<div className="flex items-center gap-2 mb-4">
				<GitCompare className="h-4 w-4 text-indigo-600" />
				<span className="text-sm font-semibold text-slate-800">Side-by-Side Comparison</span>
			</div>

			{/* Header row */}
			<div className="grid grid-cols-2 gap-4">
				<div className="text-center">
					<Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 cursor-default">
						Regular Response
					</Badge>
				</div>
				<div className="text-center">
					<Badge className="bg-violet-100 text-violet-700 hover:bg-violet-100 cursor-default">
						Shadow Response
					</Badge>
				</div>
			</div>

			{/* Conversation messages */}
			<div className="space-y-4">
				{interactions.map((interaction, index) => (
					<ConversationRow key={interaction.interaction_id || index} interaction={interaction} />
				))}
			</div>
		</div>
	);
}

// Failure details section component
interface FailureDetailsSectionProps {
	result: AgentSuccessEvaluationResult;
}

function FailureDetailsSection({ result }: FailureDetailsSectionProps) {
	return (
		<div className="space-y-4">
			{/* Failure Reason */}
			{result.failure_reason && (
				<div>
					<div className="flex items-center gap-2 mb-2">
						<AlertTriangle className="h-4 w-4 text-red-500" />
						<span className="text-sm font-semibold text-slate-800">Failure Reason</span>
					</div>
					<p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
						{result.failure_reason}
					</p>
				</div>
			)}
		</div>
	);
}

// Evaluation result row component
interface EvaluationRowProps {
	result: AgentSuccessEvaluationResult;
}

function EvaluationRow({ result }: EvaluationRowProps) {
	const [expanded, setExpanded] = useState(false);
	const [activeTab, setActiveTab] = useState<"failure" | "comparison">("failure");
	const [comparisonData, setComparisonData] = useState<Interaction[] | null>(null);
	const [comparisonLoading, setComparisonLoading] = useState(false);
	const [comparisonError, setComparisonError] = useState<string | null>(null);

	// Determine if row should be expandable
	const hasFailure = !result.is_success;
	const hasComparison = result.regular_vs_shadow != null;
	const isExpandable = hasFailure || hasComparison;

	// Get comparison badge style
	const comparisonStyle = getComparisonBadgeStyle(result.regular_vs_shadow);

	// Fetch comparison data when expanding for the first time
	const fetchComparisonData = async () => {
		if (comparisonData || comparisonLoading) return;

		setComparisonLoading(true);
		setComparisonError(null);

		try {
			const response = await getRequests({ session_id: result.session_id });
			if (response.success && response.sessions.length > 0) {
				// Get all interactions from the request
				const allInteractions = response.sessions
					.flatMap((group) => group.requests)
					.flatMap((rd) => rd.interactions)
					.sort((a, b) => a.created_at - b.created_at);
				setComparisonData(allInteractions);
			} else {
				setComparisonError("No interactions found for this request");
			}
		} catch (err) {
			setComparisonError(err instanceof Error ? err.message : "Failed to load comparison data");
		} finally {
			setComparisonLoading(false);
		}
	};

	// Handle expand/collapse
	const handleExpand = async () => {
		const newExpanded = !expanded;
		setExpanded(newExpanded);

		// Set default active tab based on what's available
		if (newExpanded) {
			if (hasComparison && !hasFailure) {
				setActiveTab("comparison");
			} else if (hasFailure) {
				setActiveTab("failure");
			}

			// Fetch comparison data if needed
			if (hasComparison && !comparisonData && !comparisonLoading) {
				fetchComparisonData();
			}
		}
	};

	return (
		<div className="hover:bg-slate-50/50 transition-colors">
			<div
				className={`p-4 ${isExpandable ? "cursor-pointer hover:bg-slate-50" : ""} transition-colors`}
				onClick={isExpandable ? handleExpand : undefined}
			>
				<div className="flex items-center justify-between gap-4">
					<div className="flex items-center gap-3 flex-1 min-w-0">
						{/* Success/Failure Icon */}
						<div className="flex-shrink-0">
							{result.is_success ? (
								<div className="h-8 w-8 rounded-lg bg-emerald-100 flex items-center justify-center">
									<CheckCircle className="h-4 w-4 text-emerald-600" />
								</div>
							) : (
								<div className="h-8 w-8 rounded-lg bg-red-100 flex items-center justify-center">
									<XCircle className="h-4 w-4 text-red-600" />
								</div>
							)}
						</div>

						{/* Main Info */}
						<div className="flex-1 min-w-0">
							<div className="flex items-center gap-2 flex-wrap">
								<span className="font-semibold text-slate-800 truncate">
									Session: {result.session_id}
								</span>
								<Badge
									className={`text-xs ${result.is_success ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-100" : "bg-red-100 text-red-700 hover:bg-red-100"}`}
								>
									{result.is_success ? "Success" : "Failed"}
								</Badge>
								{!result.is_success && result.failure_type && (
									<Badge variant="outline" className="text-xs border-slate-200 text-slate-600">
										{result.failure_type}
									</Badge>
								)}
								{/* Escalation badge */}
								{result.is_escalated && (
									<Badge className="text-xs bg-amber-100 text-amber-700 hover:bg-amber-100">
										<ArrowUpRight className="h-3 w-3 mr-1" />
										Escalated
									</Badge>
								)}
								{/* Comparison badge */}
								{comparisonStyle && (
									<Badge
										className={`text-xs ${comparisonStyle.bg} ${comparisonStyle.text} hover:${comparisonStyle.bg}`}
									>
										{comparisonStyle.label}
									</Badge>
								)}
							</div>
							<div className="flex items-center gap-2 text-sm text-slate-500 mt-1">
								{result.evaluation_name && (
									<Badge
										variant="outline"
										className="text-xs border-slate-200 text-slate-500 font-normal"
									>
										{result.evaluation_name}
									</Badge>
								)}
								<span className="truncate">Version: {result.agent_version}</span>
								{result.number_of_correction_per_session > 0 && (
									<span className="flex items-center gap-1 text-slate-500">
										<RotateCcw className="h-3 w-3" />
										{result.number_of_correction_per_session} correction
										{result.number_of_correction_per_session !== 1 ? "s" : ""}
									</span>
								)}
								{result.is_success && result.user_turns_to_resolution != null && (
									<span className="flex items-center gap-1 text-slate-500">
										<MessageSquare className="h-3 w-3" />
										{result.user_turns_to_resolution} turn
										{result.user_turns_to_resolution !== 1 ? "s" : ""} to resolve
									</span>
								)}
							</div>
						</div>
					</div>

					{/* Right side: time and expand button */}
					<div className="flex items-center gap-3 flex-shrink-0">
						<div className="text-right">
							<p className="text-xs text-slate-500">{getRelativeTime(result.created_at)}</p>
							<p className="text-xs text-slate-400">{formatDate(result.created_at)}</p>
						</div>
						{isExpandable && (
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
							>
								{expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
							</Button>
						)}
					</div>
				</div>
			</div>

			{/* Expanded Details Section */}
			{expanded && isExpandable && (
				<div className="border-t border-slate-100 p-4">
					{/* Tab Navigation - only show if both failure and comparison exist */}
					{hasFailure && hasComparison && (
						<div className="flex gap-2 mb-4 border-b border-slate-200 pb-2">
							<Button
								variant={activeTab === "failure" ? "default" : "ghost"}
								size="sm"
								onClick={(e) => {
									e.stopPropagation();
									setActiveTab("failure");
								}}
								className={
									activeTab === "failure"
										? "bg-red-500 hover:bg-red-600 text-white"
										: "text-slate-600"
								}
							>
								<AlertTriangle className="h-4 w-4 mr-2" />
								Failure Details
							</Button>
							<Button
								variant={activeTab === "comparison" ? "default" : "ghost"}
								size="sm"
								onClick={(e) => {
									e.stopPropagation();
									setActiveTab("comparison");
									if (!comparisonData && !comparisonLoading) fetchComparisonData();
								}}
								className={
									activeTab === "comparison"
										? "bg-indigo-500 hover:bg-indigo-600 text-white"
										: "text-slate-600"
								}
							>
								<GitCompare className="h-4 w-4 mr-2" />
								Shadow Comparison
							</Button>
						</div>
					)}

					{/* Failure Details Tab Content */}
					{(activeTab === "failure" || !hasComparison) && hasFailure && (
						<FailureDetailsSection result={result} />
					)}

					{/* Comparison Tab Content */}
					{(activeTab === "comparison" || !hasFailure) && hasComparison && (
						<ComparisonSection
							interactions={comparisonData}
							loading={comparisonLoading}
							error={comparisonError}
							onRetry={fetchComparisonData}
						/>
					)}
				</div>
			)}
		</div>
	);
}

export default function EvaluationsPage() {
	const [evaluations, setEvaluations] = useState<AgentSuccessEvaluationResult[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [searchQuery, setSearchQuery] = useState("");
	const [selectedVersion, setSelectedVersion] = useState<string>("all");
	const [selectedStatus, setSelectedStatus] = useState<string>("all");
	const [limit] = useState(100);

	// Fetch evaluations from API
	const fetchEvaluations = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const data = await getAgentSuccessEvaluationResults({
				limit: limit,
				agent_version: null,
			});

			if (data.success) {
				setEvaluations(data.agent_success_evaluation_results);
			} else {
				setError(data.msg || "Failed to fetch evaluations");
			}
		} catch (err) {
			setError(err instanceof Error ? err.message : "An error occurred while fetching evaluations");
		} finally {
			setLoading(false);
		}
	}, [limit]);

	// Fetch on component mount
	useEffect(() => {
		fetchEvaluations();
	}, [fetchEvaluations]);

	// Calculate statistics
	const totalEvaluations = evaluations.length;
	const successCount = evaluations.filter((e) => e.is_success).length;
	const successRate =
		totalEvaluations > 0 ? ((successCount / totalEvaluations) * 100).toFixed(1) : "0";

	// Calculate Regular vs Shadow win rate
	const evaluationsWithComparison = evaluations.filter((e) => e.regular_vs_shadow != null);
	const regularBetter = evaluationsWithComparison.filter(
		(e) => e.regular_vs_shadow === "regular_is_better",
	).length;
	const regularSlightlyBetter = evaluationsWithComparison.filter(
		(e) => e.regular_vs_shadow === "regular_is_slightly_better",
	).length;
	const shadowBetter = evaluationsWithComparison.filter(
		(e) => e.regular_vs_shadow === "shadow_is_better",
	).length;
	const shadowSlightlyBetter = evaluationsWithComparison.filter(
		(e) => e.regular_vs_shadow === "shadow_is_slightly_better",
	).length;
	const regularVsShadowWinRate =
		evaluationsWithComparison.length > 0
			? (
					((regularBetter + regularSlightlyBetter - shadowBetter - shadowSlightlyBetter) /
						evaluationsWithComparison.length) *
					100
				).toFixed(1)
			: "0";

	// Calculate avg corrections per session
	const avgCorrections =
		totalEvaluations > 0
			? (
					evaluations.reduce((sum, e) => sum + (e.number_of_correction_per_session || 0), 0) /
					totalEvaluations
				).toFixed(1)
			: "0";

	// Calculate avg turns to resolution (only for successful evals that have the field)
	const successfulWithTurns = evaluations.filter(
		(e) => e.is_success && e.user_turns_to_resolution != null,
	);
	const avgTurnsToResolution =
		successfulWithTurns.length > 0
			? (
					successfulWithTurns.reduce((sum, e) => sum + (e.user_turns_to_resolution || 0), 0) /
					successfulWithTurns.length
				).toFixed(1)
			: null;

	// Calculate escalation rate
	const escalatedCount = evaluations.filter((e) => e.is_escalated).length;
	const escalationRate =
		totalEvaluations > 0 ? ((escalatedCount / totalEvaluations) * 100).toFixed(1) : "0";

	// Get unique agent versions
	const agentVersions = Array.from(new Set(evaluations.map((e) => e.agent_version))).sort();

	// Filter evaluations
	const filteredEvaluations = evaluations.filter((evaluation) => {
		const matchesSearch =
			searchQuery === "" ||
			evaluation.session_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
			evaluation.agent_version.toLowerCase().includes(searchQuery.toLowerCase()) ||
			evaluation.failure_type.toLowerCase().includes(searchQuery.toLowerCase());

		const matchesVersion =
			selectedVersion === "all" || evaluation.agent_version === selectedVersion;

		const matchesStatus =
			selectedStatus === "all" ||
			(selectedStatus === "success" && evaluation.is_success) ||
			(selectedStatus === "failure" && !evaluation.is_success);

		return matchesSearch && matchesVersion && matchesStatus;
	});

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
			{/* Header */}
			<div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
				<div className="p-8">
					<div className="max-w-[1800px] mx-auto">
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center shadow-lg shadow-emerald-500/25">
								<CheckCircle className="h-5 w-5 text-white" />
							</div>
							<h1 className="text-3xl font-bold tracking-tight text-slate-800">Evaluations</h1>
						</div>
						<p className="text-slate-500 mt-1 ml-13">
							Monitor agent performance and identify improvement opportunities
						</p>
					</div>
				</div>
			</div>

			<div className="p-8">
				<div className="max-w-[1800px] mx-auto space-y-6">
					{/* Loading and Error States */}
					{loading && (
						<div className="flex flex-col items-center justify-center py-12">
							<div className="animate-spin rounded-full h-10 w-10 border-2 border-transparent border-t-emerald-500 border-r-emerald-500 mb-4"></div>
							<p className="text-sm text-slate-500">Loading evaluations...</p>
						</div>
					)}

					{error && (
						<Card className="border-red-200 bg-red-50">
							<CardContent className="py-6">
								<div className="flex items-start gap-3">
									<AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
									<div className="flex-1">
										<h3 className="font-semibold text-red-600 mb-1">Error Loading Evaluations</h3>
										<p className="text-sm text-slate-600">{error}</p>
										<Button
											variant="outline"
											size="sm"
											className="mt-3 border-red-200 hover:bg-red-100"
											onClick={fetchEvaluations}
										>
											<RefreshCw className="h-4 w-4 mr-2" />
											Retry
										</Button>
									</div>
								</div>
							</CardContent>
						</Card>
					)}

					{/* Performance Overview */}
					{!loading && !error && (
						<Card className="border-slate-200 bg-white hover:shadow-lg transition-all duration-300">
							<CardHeader className="pb-4">
								<div className="flex items-center gap-3">
									<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/25">
										<Activity className="h-5 w-5 text-white" />
									</div>
									<div>
										<CardTitle className="text-lg font-semibold text-slate-800">
											Performance Overview
										</CardTitle>
										<CardDescription className="text-xs mt-0.5 text-slate-500">
											{totalEvaluations} evaluation
											{totalEvaluations !== 1 ? "s" : ""} analyzed
										</CardDescription>
									</div>
								</div>
							</CardHeader>
							<CardContent>
								<div className="grid grid-cols-2 gap-4 md:flex md:gap-0 md:divide-x md:divide-slate-200">
									{/* Success Rate */}
									<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
										<div className="flex items-center gap-1.5 mb-1">
											<CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
											<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
												Success Rate
											</span>
										</div>
										<span className="text-2xl font-bold text-slate-800">{successRate}%</span>
										<span className="text-xs text-slate-400 mt-0.5">
											{successCount} of {totalEvaluations}
										</span>
									</div>

									{/* Avg Corrections */}
									<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
										<div className="flex items-center gap-1.5 mb-1">
											<RotateCcw className="h-3.5 w-3.5 text-amber-500" />
											<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
												Avg Corrections
											</span>
										</div>
										<span className="text-2xl font-bold text-slate-800">{avgCorrections}</span>
										<span className="text-xs text-slate-400 mt-0.5">per session</span>
									</div>

									{/* Avg Turns to Resolve */}
									<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
										<div className="flex items-center gap-1.5 mb-1">
											<MessageSquare className="h-3.5 w-3.5 text-blue-500" />
											<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
												Avg Turns to Resolve
											</span>
										</div>
										<span className="text-2xl font-bold text-slate-800">
											{avgTurnsToResolution ?? "N/A"}
										</span>
										<span className="text-xs text-slate-400 mt-0.5">
											across {successfulWithTurns.length} session
											{successfulWithTurns.length !== 1 ? "s" : ""}
										</span>
									</div>

									{/* Escalation Rate */}
									<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
										<div className="flex items-center gap-1.5 mb-1">
											<ArrowUpRight className="h-3.5 w-3.5 text-red-500" />
											<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
												Escalation Rate
											</span>
										</div>
										<span className="text-2xl font-bold text-slate-800">{escalationRate}%</span>
										<span className="text-xs text-slate-400 mt-0.5">
											{escalatedCount} escalated
										</span>
									</div>

									{/* Regular vs Shadow */}
									<div className="flex flex-col items-center text-center flex-1 md:px-4 py-2">
										<div className="flex items-center gap-1.5 mb-1">
											<GitCompare className="h-3.5 w-3.5 text-indigo-500" />
											<span className="text-xs font-medium uppercase tracking-wider text-slate-500">
												Regular vs Shadow
											</span>
										</div>
										<span className="text-2xl font-bold text-slate-800">
											{regularVsShadowWinRate}%
										</span>
										<span className="text-xs text-slate-400 mt-0.5">
											{evaluationsWithComparison.length} compared
										</span>
									</div>
								</div>
							</CardContent>
						</Card>
					)}

					{/* Filters */}
					{!loading && !error && (
						<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
							<CardHeader className="pb-4">
								<div className="flex items-center gap-3">
									<Filter className="h-4 w-4 text-slate-400" />
									<div>
										<CardTitle className="text-lg font-semibold text-slate-800">Filters</CardTitle>
										<CardDescription className="text-xs mt-1 text-slate-500">
											Refine evaluation results
										</CardDescription>
									</div>
								</div>
							</CardHeader>
							<CardContent>
								<div className="grid gap-4 md:grid-cols-3">
									{/* Search */}
									<div>
										<label className="text-sm font-medium mb-2 block text-slate-700">Search</label>
										<div className="relative">
											<Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
											<Input
												placeholder="Request ID, version, or failure type..."
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
											value={selectedVersion}
											onChange={(e) => setSelectedVersion(e.target.value)}
											className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
										>
											<option value="all">All Versions</option>
											{agentVersions.map((version) => (
												<option key={version} value={version}>
													{version}
												</option>
											))}
										</select>
									</div>

									{/* Status Filter */}
									<div>
										<label className="text-sm font-medium mb-2 block text-slate-700">Status</label>
										<select
											value={selectedStatus}
											onChange={(e) => setSelectedStatus(e.target.value)}
											className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
										>
											<option value="all">All Status</option>
											<option value="success">Success Only</option>
											<option value="failure">Failures Only</option>
										</select>
									</div>
								</div>

								{/* Active filters indicator */}
								{(searchQuery || selectedVersion !== "all" || selectedStatus !== "all") && (
									<div className="mt-4 flex items-center gap-2">
										<span className="text-sm text-slate-500">Active filters:</span>
										{searchQuery && (
											<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
												Search: {searchQuery}
											</Badge>
										)}
										{selectedVersion !== "all" && (
											<Badge className="text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
												Version: {selectedVersion}
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
												setSelectedVersion("all");
												setSelectedStatus("all");
											}}
										>
											Clear all
										</Button>
									</div>
								)}
							</CardContent>
						</Card>
					)}

					{/* Results */}
					{!loading && !error && (
						<div>
							<div className="mb-4 flex items-center justify-between">
								<div>
									<h2 className="text-lg font-semibold text-slate-800">Evaluation Results</h2>
									<p className="text-xs mt-1 text-slate-500">
										Showing {filteredEvaluations.length} of {totalEvaluations} evaluations
									</p>
								</div>
								<Button
									variant="outline"
									size="sm"
									onClick={fetchEvaluations}
									disabled={loading}
									className="border-slate-200 hover:bg-slate-50 text-slate-700"
								>
									<RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
									Refresh
								</Button>
							</div>
							{filteredEvaluations.length === 0 ? (
								<div className="text-center py-12">
									<Calendar className="h-12 w-12 text-slate-300 mx-auto mb-4" />
									<h3 className="text-lg font-semibold text-slate-800 mb-2">
										No evaluations found
									</h3>
									<p className="text-sm text-slate-500">
										Try adjusting your filters or search query
									</p>
								</div>
							) : (
								<div className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100">
									{filteredEvaluations.map((result) => (
										<EvaluationRow key={result.result_id} result={result} />
									))}
								</div>
							)}
						</div>
					)}
				</div>
			</div>
		</div>
	);
}

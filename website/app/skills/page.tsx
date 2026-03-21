"use client";

import {
	AlertCircle,
	AlertTriangle,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	Download,
	FileText,
	Loader2,
	Lock,
	RefreshCw,
	Search,
	Sparkles,
	Trash2,
	X,
	XCircle,
	Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
	deleteSkill as deleteSkillAPI,
	getSkills,
	runSkillGeneration,
	type Skill,
	type SkillStatus,
	updateSkillStatus as updateSkillStatusAPI,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

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

const getStatusGradient = (status: SkillStatus) => {
	switch (status) {
		case "published":
			return "bg-gradient-to-br from-teal-500 to-cyan-500";
		case "draft":
			return "bg-gradient-to-br from-amber-500 to-orange-500";
		case "deprecated":
			return "bg-gradient-to-br from-slate-400 to-slate-500";
	}
};

const getStatusBadgeClass = (status: SkillStatus) => {
	switch (status) {
		case "published":
			return "bg-emerald-100 text-emerald-700 hover:bg-emerald-100";
		case "draft":
			return "bg-amber-100 text-amber-700 hover:bg-amber-100";
		case "deprecated":
			return "bg-slate-100 text-slate-600 hover:bg-slate-100";
	}
};

// Generate Anthropic SKILL.md format
const generateSkillMarkdown = (skill: Skill): string => {
	const lines: string[] = [];

	// YAML frontmatter
	lines.push("---");
	lines.push(`name: ${skill.skill_name}`);
	lines.push(`description: ${skill.description}`);
	if (skill.allowed_tools.length > 0) {
		lines.push(`allowed-tools: ${skill.allowed_tools.join(", ")}`);
	}
	lines.push("---");
	lines.push("");

	// If instructions exist, they are the primary body.
	// Only append Do/Don't/When/Examples if instructions are absent,
	// since the LLM-generated instructions already incorporate them.
	if (skill.instructions) {
		lines.push(skill.instructions);
		lines.push("");
	}

	return lines.join("\n");
};

const downloadSkillMarkdown = (skill: Skill) => {
	const markdown = generateSkillMarkdown(skill);
	const blob = new Blob([markdown], { type: "text/markdown" });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = `${skill.skill_name}.md`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
};

// Skill Row Component
interface SkillRowProps {
	skill: Skill;
	onUpdateStatus: (skillId: number, status: SkillStatus) => void;
	onDelete: (skill: Skill) => void;
	isUpdating?: boolean;
}

function SkillRow({ skill, onUpdateStatus, onDelete, isUpdating = false }: SkillRowProps) {
	const [expanded, setExpanded] = useState(false);

	return (
		<div className="border border-slate-200 rounded-xl overflow-hidden hover:shadow-lg transition-all duration-300 bg-white">
			<div
				className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
				onClick={() => setExpanded(!expanded)}
			>
				<div className="flex items-center justify-between gap-4">
					<div className="flex items-center gap-3 flex-1 min-w-0">
						{/* Status Icon */}
						<div className="flex-shrink-0">
							<div
								className={`h-9 w-9 rounded-xl ${getStatusGradient(skill.skill_status)} flex items-center justify-center shadow-lg`}
							>
								<Sparkles className="h-5 w-5 text-white" />
							</div>
						</div>

						{/* Main Info */}
						<div className="flex-1 min-w-0">
							<div className="flex items-center gap-2 flex-wrap">
								<span className="font-semibold text-slate-800 text-sm">{skill.skill_name}</span>
								<Badge variant="outline" className="text-xs border-slate-200 text-slate-600">
									v{skill.version}
								</Badge>
								<Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
									{skill.feedback_name}
								</Badge>
								<Badge className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100">
									{skill.agent_version}
								</Badge>
								<Badge className={`text-xs ${getStatusBadgeClass(skill.skill_status)}`}>
									{skill.skill_status.charAt(0).toUpperCase() + skill.skill_status.slice(1)}
								</Badge>
							</div>
							<p className="text-sm text-slate-500 mt-1 truncate">
								{skill.description || "No description"}
							</p>
						</div>
					</div>

					{/* Right side */}
					<div className="flex items-center gap-3 flex-shrink-0">
						<div className="text-right">
							<p className="text-xs text-slate-500">{getRelativeTime(skill.updated_at)}</p>
							<p className="text-xs text-slate-400">
								{new Date(skill.updated_at * 1000).toLocaleDateString("en-US", {
									month: "short",
									day: "numeric",
								})}
							</p>
						</div>
						<div className="flex items-center gap-1">
							{skill.skill_status === "draft" && (
								<Button
									variant="ghost"
									size="sm"
									className="h-8 w-8 p-0 text-emerald-500 hover:text-emerald-700 hover:bg-emerald-50"
									title="Publish"
									onClick={(e) => {
										e.stopPropagation();
										onUpdateStatus(skill.skill_id, "published");
									}}
									disabled={isUpdating}
								>
									<CheckCircle2 className="h-4 w-4" />
								</Button>
							)}
							{skill.skill_status === "published" && (
								<Button
									variant="ghost"
									size="sm"
									className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600 hover:bg-slate-100"
									title="Deprecate"
									onClick={(e) => {
										e.stopPropagation();
										onUpdateStatus(skill.skill_id, "deprecated");
									}}
									disabled={isUpdating}
								>
									<XCircle className="h-4 w-4" />
								</Button>
							)}
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-red-400 hover:text-red-600 hover:bg-red-50"
								onClick={(e) => {
									e.stopPropagation();
									onDelete(skill);
								}}
							>
								<Trash2 className="h-4 w-4" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className="h-8 w-8 p-0 text-slate-400 hover:text-slate-600"
							>
								{expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
							</Button>
						</div>
					</div>
				</div>
			</div>

			{/* Expanded Details */}
			{expanded && (
				<div className="border-t border-slate-100 bg-slate-50 p-4 space-y-4">
					<div className="grid gap-6 md:grid-cols-2">
						{/* Left Column */}
						<div className="space-y-4">
							{skill.instructions && (
								<div>
									<h4 className="text-sm font-semibold mb-2 text-slate-800">Instructions</h4>
									<div className="text-sm text-slate-600 leading-relaxed bg-white p-3 rounded-lg border border-slate-200 prose prose-sm prose-slate max-w-none prose-headings:text-slate-800 prose-headings:font-semibold prose-headings:mt-3 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-code:text-teal-700 prose-code:bg-teal-50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-pre:rounded-lg">
										<ReactMarkdown>{skill.instructions}</ReactMarkdown>
									</div>
								</div>
							)}

							{skill.blocking_issues.length > 0 && (
								<div>
									<h4 className="text-sm font-semibold mb-2 text-slate-800">Blocking Issues</h4>
									<div className="bg-white p-3 rounded-lg border border-slate-200 space-y-2">
										{skill.blocking_issues.map((issue, i) => (
											<div key={i} className="flex items-start gap-2 text-sm">
												<AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0 mt-0.5" />
												<span className="text-slate-600">
													<span className="font-medium">[{issue.kind}]</span> {issue.details}
												</span>
											</div>
										))}
									</div>
								</div>
							)}
						</div>

						{/* Right Column */}
						<div className="space-y-4">
							<div>
								<h4 className="text-sm font-semibold mb-3 text-slate-800">Details</h4>
								<div className="space-y-2 bg-white p-3 rounded-lg border border-slate-200">
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Skill ID:</span>
										<span className="font-mono text-slate-700">#{skill.skill_id}</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Version:</span>
										<span className="text-slate-700">{skill.version}</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Agent Version:</span>
										<span className="text-slate-700">{skill.agent_version}</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Feedback Name:</span>
										<span className="text-slate-700">{skill.feedback_name}</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Status:</span>
										<Badge className={`text-xs ${getStatusBadgeClass(skill.skill_status)}`}>
											{skill.skill_status}
										</Badge>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Created:</span>
										<span className="text-xs text-slate-700">
											{formatTimestamp(skill.created_at)}
										</span>
									</div>
									<div className="flex justify-between text-sm">
										<span className="text-slate-500">Updated:</span>
										<span className="text-xs text-slate-700">
											{formatTimestamp(skill.updated_at)}
										</span>
									</div>
								</div>
							</div>

							{skill.allowed_tools.length > 0 && (
								<div>
									<h4 className="text-sm font-semibold mb-2 text-slate-800">Allowed Tools</h4>
									<div className="flex flex-wrap gap-1.5">
										{skill.allowed_tools.map((tool, i) => (
											<Badge
												key={i}
												variant="outline"
												className="text-xs border-slate-200 text-slate-600"
											>
												{tool}
											</Badge>
										))}
									</div>
								</div>
							)}

							{skill.raw_feedback_ids.length > 0 && (
								<div>
									<h4 className="text-sm font-semibold mb-2 text-slate-800">Raw Feedback IDs</h4>
									<div className="flex flex-wrap gap-1.5">
										{skill.raw_feedback_ids.map((id, i) => (
											<Badge
												key={i}
												className="text-xs bg-slate-100 text-slate-600 hover:bg-slate-100"
											>
												#{id}
											</Badge>
										))}
									</div>
								</div>
							)}

							<div>
								<h4 className="text-sm font-semibold mb-2 text-slate-800">Export</h4>
								<Button
									size="sm"
									variant="outline"
									onClick={(e) => {
										e.stopPropagation();
										downloadSkillMarkdown(skill);
									}}
									className="w-full border-slate-200 text-slate-700 hover:bg-slate-50"
								>
									<Download className="h-4 w-4 mr-2" />
									Download SKILL.md
								</Button>
							</div>

							<div>
								<h4 className="text-sm font-semibold mb-2 text-slate-800">Status Management</h4>
								<div className="flex gap-2">
									<Button
										size="sm"
										onClick={(e) => {
											e.stopPropagation();
											onUpdateStatus(skill.skill_id, "draft");
										}}
										disabled={isUpdating}
										className={`flex-1 ${skill.skill_status === "draft" ? "bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 border-0" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
										variant={skill.skill_status === "draft" ? "default" : "outline"}
									>
										{isUpdating ? (
											<RefreshCw className="h-4 w-4 mr-1 animate-spin" />
										) : (
											<FileText className="h-4 w-4 mr-1" />
										)}
										Draft
									</Button>
									<Button
										size="sm"
										onClick={(e) => {
											e.stopPropagation();
											onUpdateStatus(skill.skill_id, "published");
										}}
										disabled={isUpdating}
										className={`flex-1 ${skill.skill_status === "published" ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 border-0" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
										variant={skill.skill_status === "published" ? "default" : "outline"}
									>
										{isUpdating ? (
											<RefreshCw className="h-4 w-4 mr-1 animate-spin" />
										) : (
											<CheckCircle2 className="h-4 w-4 mr-1" />
										)}
										Publish
									</Button>
									<Button
										size="sm"
										onClick={(e) => {
											e.stopPropagation();
											onUpdateStatus(skill.skill_id, "deprecated");
										}}
										disabled={isUpdating}
										className={`flex-1 ${skill.skill_status === "deprecated" ? "bg-gradient-to-r from-slate-500 to-slate-600 hover:from-slate-600 hover:to-slate-700 border-0" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
										variant={skill.skill_status === "deprecated" ? "default" : "outline"}
									>
										{isUpdating ? (
											<RefreshCw className="h-4 w-4 mr-1 animate-spin" />
										) : (
											<XCircle className="h-4 w-4 mr-1" />
										)}
										Deprecate
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

export default function SkillsPage() {
	const { isFeatureEnabled } = useAuth();
	const skillsEnabled = isFeatureEnabled("skill_generation");

	const [skills, setSkills] = useState<Skill[]>([]);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [updatingSkillId, setUpdatingSkillId] = useState<number | null>(null);

	// Filter state
	const [searchQuery, setSearchQuery] = useState("");
	const [selectedAgent, setSelectedAgent] = useState<string>("all");
	const [selectedFeedbackName, setSelectedFeedbackName] = useState<string>("all");
	const [selectedStatus, setSelectedStatus] = useState<string>("all");

	// Delete confirmation state
	const [skillToDelete, setSkillToDelete] = useState<Skill | null>(null);
	const [deletingSkill, setDeletingSkill] = useState(false);

	// Generate skills modal state
	const [showGenerateModal, setShowGenerateModal] = useState(false);
	const [generateAgentVersion, setGenerateAgentVersion] = useState("");
	const [generateFeedbackName, setGenerateFeedbackName] = useState("");
	const [generatingSkills, setGeneratingSkills] = useState(false);

	// Message modal state
	const [showMessageModal, setShowMessageModal] = useState(false);
	const [messageModalConfig, setMessageModalConfig] = useState<{
		title: string;
		message: string;
		type: "success" | "error";
	} | null>(null);

	const fetchSkills = useCallback(async () => {
		setIsLoading(true);
		setError(null);
		try {
			const response = await getSkills({ limit: 1000 });
			if (response.success) {
				setSkills(response.skills.sort((a, b) => b.updated_at - a.updated_at));
			} else {
				setError(response.msg || "Failed to load skills");
			}
		} catch (err) {
			console.error("Error fetching skills:", err);
			setError("Failed to load skills. Please try again.");
		} finally {
			setIsLoading(false);
		}
	}, []);

	// Fetch data (skip if feature is disabled to avoid a 403)
	useEffect(() => {
		if (skillsEnabled) {
			fetchSkills();
		} else {
			setIsLoading(false);
		}
	}, [skillsEnabled, fetchSkills]);

	// Get unique values for filters
	const uniqueAgents = useMemo(() => {
		return Array.from(new Set(skills.map((s) => s.agent_version))).sort();
	}, [skills]);

	const uniqueFeedbackNames = useMemo(() => {
		return Array.from(new Set(skills.map((s) => s.feedback_name))).sort();
	}, [skills]);

	// Filter skills
	const filteredSkills = useMemo(() => {
		return skills.filter((skill) => {
			const query = searchQuery.toLowerCase();
			const matchesSearch =
				searchQuery === "" ||
				skill.skill_name.toLowerCase().includes(query) ||
				skill.description.toLowerCase().includes(query) ||
				skill.instructions.toLowerCase().includes(query);

			const matchesAgent = selectedAgent === "all" || skill.agent_version === selectedAgent;
			const matchesFeedbackName =
				selectedFeedbackName === "all" || skill.feedback_name === selectedFeedbackName;
			const matchesStatus = selectedStatus === "all" || skill.skill_status === selectedStatus;

			return matchesSearch && matchesAgent && matchesFeedbackName && matchesStatus;
		});
	}, [skills, searchQuery, selectedAgent, selectedFeedbackName, selectedStatus]);

	// Statistics
	const totalSkills = skills.length;
	const publishedCount = skills.filter((s) => s.skill_status === "published").length;
	const draftCount = skills.filter((s) => s.skill_status === "draft").length;

	// Active filters
	const activeFilters = useMemo(() => {
		const filters: { key: string; label: string; value: string }[] = [];
		if (searchQuery) filters.push({ key: "search", label: "Search", value: searchQuery });
		if (selectedAgent !== "all")
			filters.push({ key: "agent", label: "Agent", value: selectedAgent });
		if (selectedFeedbackName !== "all")
			filters.push({
				key: "feedbackName",
				label: "Feedback",
				value: selectedFeedbackName,
			});
		if (selectedStatus !== "all")
			filters.push({ key: "status", label: "Status", value: selectedStatus });
		return filters;
	}, [searchQuery, selectedAgent, selectedFeedbackName, selectedStatus]);

	const clearFilter = (key: string) => {
		switch (key) {
			case "search":
				setSearchQuery("");
				break;
			case "agent":
				setSelectedAgent("all");
				break;
			case "feedbackName":
				setSelectedFeedbackName("all");
				break;
			case "status":
				setSelectedStatus("all");
				break;
		}
	};

	const clearAllFilters = () => {
		setSearchQuery("");
		setSelectedAgent("all");
		setSelectedFeedbackName("all");
		setSelectedStatus("all");
	};

	// Update skill status
	const handleUpdateStatus = async (skillId: number, status: SkillStatus) => {
		// Optimistic update
		setSkills(skills.map((s) => (s.skill_id === skillId ? { ...s, skill_status: status } : s)));
		setUpdatingSkillId(skillId);

		try {
			const response = await updateSkillStatusAPI({
				skill_id: skillId,
				skill_status: status,
			});
			if (!response.success) {
				setError(`Failed to update skill status: ${response.message || "Unknown error"}`);
				await fetchSkills();
			}
		} catch (err) {
			console.error("Error updating skill status:", err);
			setError("Failed to update skill status. Please try again.");
			await fetchSkills();
		} finally {
			setUpdatingSkillId(null);
		}
	};

	// Delete skill
	const handleDeleteClick = (skill: Skill) => {
		setSkillToDelete(skill);
	};

	const confirmDeleteSkill = async () => {
		if (!skillToDelete) return;

		setDeletingSkill(true);
		try {
			const response = await deleteSkillAPI({
				skill_id: skillToDelete.skill_id,
			});
			if (response.success) {
				setSkills(skills.filter((s) => s.skill_id !== skillToDelete.skill_id));
				setSkillToDelete(null);
			} else {
				setMessageModalConfig({
					title: "Delete Failed",
					message: response.message || "Failed to delete skill",
					type: "error",
				});
				setShowMessageModal(true);
			}
		} catch (err) {
			console.error("Error deleting skill:", err);
			setMessageModalConfig({
				title: "Delete Failed",
				message: err instanceof Error ? err.message : "An error occurred while deleting the skill",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setDeletingSkill(false);
		}
	};

	// Generate skills
	const handleGenerateSkills = async () => {
		if (!generateAgentVersion.trim()) {
			setMessageModalConfig({
				title: "Validation Error",
				message: "Agent version is required",
				type: "error",
			});
			setShowMessageModal(true);
			return;
		}

		if (!generateFeedbackName.trim()) {
			setMessageModalConfig({
				title: "Validation Error",
				message: "Feedback name is required",
				type: "error",
			});
			setShowMessageModal(true);
			return;
		}

		setGeneratingSkills(true);
		try {
			const response = await runSkillGeneration({
				agent_version: generateAgentVersion.trim(),
				feedback_name: generateFeedbackName.trim(),
			});

			setShowGenerateModal(false);

			if (response.success) {
				setMessageModalConfig({
					title: "Skill Generation Completed",
					message:
						response.message ||
						`Generated ${response.skills_generated} skills, updated ${response.skills_updated} skills.`,
					type: "success",
				});
				setShowMessageModal(true);
				await fetchSkills();
			} else {
				setMessageModalConfig({
					title: "Skill Generation Failed",
					message: response.message || "Failed to generate skills",
					type: "error",
				});
				setShowMessageModal(true);
			}

			setGenerateAgentVersion("");
			setGenerateFeedbackName("");
		} catch (err: unknown) {
			console.error("Error generating skills:", err);
			setMessageModalConfig({
				title: "Error Generating Skills",
				message: err instanceof Error ? err.message : "An unexpected error occurred",
				type: "error",
			});
			setShowMessageModal(true);
		} finally {
			setGeneratingSkills(false);
		}
	};

	if (!skillsEnabled) {
		return (
			<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50 flex items-center justify-center">
				<div className="text-center max-w-md">
					<div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center mx-auto mb-6 shadow-lg">
						<Lock className="h-8 w-8 text-slate-500" />
					</div>
					<h2 className="text-2xl font-bold text-slate-800 mb-3">Skills Not Available</h2>
					<p className="text-slate-500">
						The Skills feature is not enabled for your organization. Please contact support if you
						believe this is an error.
					</p>
				</div>
			</div>
		);
	}

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
			{/* Header */}
			<div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
				<div className="p-8">
					<div className="max-w-[1800px] mx-auto">
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-teal-500/25">
								<Sparkles className="h-5 w-5 text-white" />
							</div>
							<h1 className="text-3xl font-bold tracking-tight text-slate-800">Skills</h1>
						</div>
						<p className="text-slate-500 mt-1 ml-13">
							Manage AI-generated skills derived from feedback patterns
						</p>
					</div>
				</div>
			</div>

			<div className="p-8">
				<div className="max-w-[1800px] mx-auto space-y-6">
					{/* Error Message */}
					{error && (
						<Card className="border-red-200 bg-red-50">
							<CardContent className="pt-6">
								<div className="flex items-center gap-3">
									<AlertCircle className="h-5 w-5 text-red-500" />
									<div>
										<p className="font-semibold text-red-600">Error Loading Skills</p>
										<p className="text-sm text-slate-600">{error}</p>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={fetchSkills}
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
									<div className="animate-spin rounded-full h-10 w-10 border-2 border-transparent border-t-teal-500 border-r-teal-500"></div>
									<p className="ml-3 text-slate-500">Loading skills...</p>
								</div>
							</CardContent>
						</Card>
					) : (
						<>
							{/* Statistics Cards */}
							<div className="grid gap-5 md:grid-cols-3">
								<Card className="border bg-gradient-to-br from-teal-50 to-cyan-50 border-teal-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
									<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
										<CardTitle className="text-sm font-semibold text-slate-600">
											Total Skills
										</CardTitle>
										<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center shadow-lg">
											<Sparkles className="h-5 w-5 text-white" />
										</div>
									</CardHeader>
									<CardContent>
										<div className="text-3xl font-bold text-slate-800">{totalSkills}</div>
										<p className="text-xs text-slate-500 mt-1">All skills across versions</p>
									</CardContent>
								</Card>

								<Card className="border bg-gradient-to-br from-emerald-50 to-teal-50 border-emerald-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
									<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
										<CardTitle className="text-sm font-semibold text-slate-600">
											Published
										</CardTitle>
										<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center shadow-lg">
											<CheckCircle2 className="h-5 w-5 text-white" />
										</div>
									</CardHeader>
									<CardContent>
										<div className="text-3xl font-bold text-slate-800">{publishedCount}</div>
										<p className="text-xs text-slate-500 mt-1">Active published skills</p>
									</CardContent>
								</Card>

								<Card className="border bg-gradient-to-br from-amber-50 to-orange-50 border-amber-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
									<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
										<CardTitle className="text-sm font-semibold text-slate-600">Draft</CardTitle>
										<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center shadow-lg">
											<FileText className="h-5 w-5 text-white" />
										</div>
									</CardHeader>
									<CardContent>
										<div className="text-3xl font-bold text-slate-800">{draftCount}</div>
										<p className="text-xs text-slate-500 mt-1">Skills awaiting review</p>
									</CardContent>
								</Card>
							</div>

							{/* Action Buttons */}
							<div className="flex gap-3">
								<Button
									onClick={() => setShowGenerateModal(true)}
									className="bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-600 hover:to-cyan-600 text-white border-0 shadow-md"
								>
									<Zap className="h-4 w-4 mr-2" />
									Generate Skills
								</Button>
								<Button
									variant="outline"
									onClick={fetchSkills}
									className="border-slate-200 text-slate-700 hover:bg-slate-50"
								>
									<RefreshCw className="h-4 w-4 mr-2" />
									Refresh
								</Button>
							</div>

							{/* Filters */}
							<Card className="border-slate-200 bg-white">
								<CardContent className="pt-6">
									<div className="grid gap-4 md:grid-cols-4">
										<div>
											<Label className="text-xs font-medium text-slate-500 mb-1.5 block">
												Search
											</Label>
											<div className="relative">
												<Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
												<Input
													placeholder="Search skills..."
													value={searchQuery}
													onChange={(e) => setSearchQuery(e.target.value)}
													className="pl-9 border-slate-200 focus:border-teal-300 focus:ring-teal-200"
												/>
											</div>
										</div>

										<div>
											<Label className="text-xs font-medium text-slate-500 mb-1.5 block">
												Agent Version
											</Label>
											<select
												value={selectedAgent}
												onChange={(e) => setSelectedAgent(e.target.value)}
												className="w-full h-10 rounded-md border border-slate-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-300"
											>
												<option value="all">All Versions</option>
												{uniqueAgents.map((agent) => (
													<option key={agent} value={agent}>
														{agent}
													</option>
												))}
											</select>
										</div>

										<div>
											<Label className="text-xs font-medium text-slate-500 mb-1.5 block">
												Feedback Name
											</Label>
											<select
												value={selectedFeedbackName}
												onChange={(e) => setSelectedFeedbackName(e.target.value)}
												className="w-full h-10 rounded-md border border-slate-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-300"
											>
												<option value="all">All Names</option>
												{uniqueFeedbackNames.map((name) => (
													<option key={name} value={name}>
														{name}
													</option>
												))}
											</select>
										</div>

										<div>
											<Label className="text-xs font-medium text-slate-500 mb-1.5 block">
												Status
											</Label>
											<select
												value={selectedStatus}
												onChange={(e) => setSelectedStatus(e.target.value)}
												className="w-full h-10 rounded-md border border-slate-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-300"
											>
												<option value="all">All Statuses</option>
												<option value="draft">Draft</option>
												<option value="published">Published</option>
												<option value="deprecated">Deprecated</option>
											</select>
										</div>
									</div>

									{/* Active Filter Badges */}
									{activeFilters.length > 0 && (
										<div className="flex items-center gap-2 mt-4 pt-4 border-t border-slate-100">
											<span className="text-xs text-slate-500">Active filters:</span>
											{activeFilters.map((filter) => (
												<Badge
													key={filter.key}
													variant="outline"
													className="text-xs border-teal-200 text-teal-700 bg-teal-50 cursor-pointer hover:bg-teal-100"
													onClick={() => clearFilter(filter.key)}
												>
													{filter.label}: {filter.value}
													<X className="h-3 w-3 ml-1" />
												</Badge>
											))}
											<button
												onClick={clearAllFilters}
												className="text-xs text-slate-500 hover:text-slate-700 underline"
											>
												Clear all
											</button>
										</div>
									)}
								</CardContent>
							</Card>

							{/* Skills List */}
							<div className="space-y-3">
								<div className="flex items-center justify-between">
									<h3 className="text-sm font-semibold text-slate-600">
										{filteredSkills.length} skill
										{filteredSkills.length !== 1 ? "s" : ""}
										{activeFilters.length > 0 ? " (filtered)" : ""}
									</h3>
								</div>

								{filteredSkills.length === 0 ? (
									<Card className="border-slate-200 bg-white">
										<CardContent className="pt-6">
											<div className="flex flex-col items-center justify-center py-12 text-center">
												<div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-teal-100 to-cyan-100 flex items-center justify-center mb-4">
													<Sparkles className="h-8 w-8 text-teal-500" />
												</div>
												<h3 className="text-lg font-semibold text-slate-700 mb-1">
													No skills found
												</h3>
												<p className="text-sm text-slate-500 max-w-sm">
													{activeFilters.length > 0
														? "Try adjusting your filters to see more results."
														: "Generate skills from feedback patterns to get started."}
												</p>
												{activeFilters.length > 0 && (
													<Button
														variant="outline"
														size="sm"
														className="mt-4 border-slate-200"
														onClick={clearAllFilters}
													>
														Clear Filters
													</Button>
												)}
											</div>
										</CardContent>
									</Card>
								) : (
									filteredSkills.map((skill) => (
										<SkillRow
											key={skill.skill_id}
											skill={skill}
											onUpdateStatus={handleUpdateStatus}
											onDelete={handleDeleteClick}
											isUpdating={updatingSkillId === skill.skill_id}
										/>
									))
								)}
							</div>
						</>
					)}
				</div>
			</div>

			{/* Delete Confirmation Dialog */}
			<DeleteConfirmDialog
				open={!!skillToDelete}
				onOpenChange={(open) => !open && setSkillToDelete(null)}
				onConfirm={confirmDeleteSkill}
				title="Delete Skill"
				description="Are you sure you want to delete this skill? This action cannot be undone."
				itemDetails={
					skillToDelete && (
						<>
							<div className="flex justify-between">
								<span className="text-slate-500">Skill Name:</span>
								<span className="font-medium">{skillToDelete.skill_name}</span>
							</div>
							<div className="flex justify-between">
								<span className="text-slate-500">Skill ID:</span>
								<span className="font-mono">#{skillToDelete.skill_id}</span>
							</div>
							<div className="flex justify-between">
								<span className="text-slate-500">Status:</span>
								<span>{skillToDelete.skill_status}</span>
							</div>
						</>
					)
				}
				loading={deletingSkill}
			/>

			{/* Generate Skills Modal */}
			<Dialog open={showGenerateModal} onOpenChange={setShowGenerateModal}>
				<DialogContent className="sm:max-w-[500px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-teal-500/25">
								<Zap className="h-5 w-5 text-white" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								Generate Skills
							</DialogTitle>
						</div>
						<DialogDescription className="text-sm text-slate-600 pt-2">
							Generate skills from aggregated feedback patterns. This will analyze existing
							feedbacks and create new skills.
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-4 py-4">
						<div>
							<Label className="text-sm font-medium text-slate-700">Agent Version *</Label>
							<Input
								placeholder="e.g., v1.0.0"
								value={generateAgentVersion}
								onChange={(e) => setGenerateAgentVersion(e.target.value)}
								className="mt-1.5 border-slate-200"
							/>
						</div>
						<div>
							<Label className="text-sm font-medium text-slate-700">Feedback Name *</Label>
							<Input
								placeholder="e.g., agent_feedback"
								value={generateFeedbackName}
								onChange={(e) => setGenerateFeedbackName(e.target.value)}
								className="mt-1.5 border-slate-200"
							/>
						</div>
					</div>

					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => setShowGenerateModal(false)}
							disabled={generatingSkills}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleGenerateSkills}
							disabled={generatingSkills}
							className="bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-600 hover:to-cyan-600 text-white border-0"
						>
							{generatingSkills ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Generating...
								</>
							) : (
								<>
									<Zap className="h-4 w-4 mr-2" />
									Generate
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
							<div
								className={`h-10 w-10 rounded-xl flex items-center justify-center shadow-lg ${
									messageModalConfig?.type === "success"
										? "bg-gradient-to-br from-emerald-500 to-teal-500"
										: "bg-gradient-to-br from-red-500 to-rose-500"
								}`}
							>
								{messageModalConfig?.type === "success" ? (
									<CheckCircle2 className="h-5 w-5 text-white" />
								) : (
									<AlertCircle className="h-5 w-5 text-white" />
								)}
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								{messageModalConfig?.title}
							</DialogTitle>
						</div>
					</DialogHeader>
					<p className="text-sm text-slate-600 whitespace-pre-wrap">
						{messageModalConfig?.message}
					</p>
					<DialogFooter>
						<Button
							onClick={() => setShowMessageModal(false)}
							className={
								messageModalConfig?.type === "success"
									? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white border-0"
									: "bg-gradient-to-r from-red-500 to-rose-500 hover:from-red-600 hover:to-rose-600 text-white border-0"
							}
						>
							OK
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}

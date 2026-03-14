"use client";

import {
	AlertCircle,
	CheckCircle,
	Save,
	Settings,
	Undo2,
	Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import { AdvancedSettingsSection } from "@/components/settings/sections/AdvancedSettingsSection";
import { AgentContextSection } from "@/components/settings/sections/AgentContextSection";
import { AgentFeedbackSection } from "@/components/settings/sections/AgentFeedbackSection";
import { AgentSuccessSection } from "@/components/settings/sections/AgentSuccessSection";
import { ExtractionParamsSection } from "@/components/settings/sections/ExtractionParamsSection";
import { ProfileExtractorsSection } from "@/components/settings/sections/ProfileExtractorsSection";

// Section components
import { StorageConfigSection } from "@/components/settings/sections/StorageConfigSection";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import WorkflowVisualization from "@/components/workflow/WorkflowVisualization";
import { getConfig, setConfig as setConfigAPI } from "@/lib/api";

// Types and helpers
import type {
	AgentFeedbackConfig,
	AgentSuccessConfig,
	AnthropicConfig,
	AzureOpenAIConfig,
	BackendConfig,
	Config,
	CustomEndpointConfig,
	LLMConfig,
	MiniMaxConfig,
	OpenAIConfig,
	OpenRouterConfig,
	ProfileExtractorConfig,
	StorageConfig,
	StorageType,
	ToolUseConfig,
} from "./types";
import {
	backendToFrontendConfig,
	configsAreEqual,
	frontendToBackendConfig,
	generateId,
	getDefaultConfig,
} from "./types";

export default function SettingsPage() {
	const [config, setConfig] = useState<Config>(getDefaultConfig());
	const [originalConfig, setOriginalConfig] = useState<Config>(
		getDefaultConfig(),
	);
	const [saveStatus, setSaveStatus] = useState<
		"idle" | "saving" | "success" | "error"
	>("idle");
	const [loading, setLoading] = useState(true);
	const [errorMessage, setErrorMessage] = useState<string>("");
	const [openaiMode, setOpenaiMode] = useState<"direct" | "azure">("direct");
	const [discardDialogOpen, setDiscardDialogOpen] = useState(false);

	const hasUnsavedChanges =
		!loading && !configsAreEqual(config, originalConfig);

	// Fetch config from backend on mount
	useEffect(() => {
		const fetchConfigData = async () => {
			try {
				const backendConfig = await getConfig();
				const frontendConfig = backendToFrontendConfig(
					backendConfig as BackendConfig,
				);
				setConfig(frontendConfig);
				setOriginalConfig(frontendConfig);
				if (frontendConfig.api_key_config?.openai?.azure_config) {
					setOpenaiMode("azure");
				}
			} catch (error) {
				console.error("Error fetching config:", error);
				setErrorMessage(
					error instanceof Error
						? error.message
						: "Failed to load configuration",
				);
			} finally {
				setLoading(false);
			}
		};
		fetchConfigData();
	}, []);

	// --- API key config helpers ---
	const updateCustomEndpointConfig = (
		updates: Partial<CustomEndpointConfig>,
	) => {
		const current = config.api_key_config?.custom_endpoint;
		const merged = {
			model: current?.model || "",
			api_key: current?.api_key || "",
			api_base: current?.api_base || "",
			...updates,
		};
		// Clear custom_endpoint entirely when all fields are empty
		const customEndpoint =
			merged.model || merged.api_key || merged.api_base ? merged : undefined;
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				custom_endpoint: customEndpoint,
			},
		});
	};

	const updateOpenAIConfig = (updates: Partial<OpenAIConfig>) => {
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				openai: { ...config.api_key_config?.openai, ...updates },
			},
		});
	};

	const updateAzureOpenAIConfig = (updates: Partial<AzureOpenAIConfig>) => {
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				openai: {
					...config.api_key_config?.openai,
					azure_config: {
						api_key: config.api_key_config?.openai?.azure_config?.api_key || "",
						endpoint:
							config.api_key_config?.openai?.azure_config?.endpoint || "",
						api_version:
							config.api_key_config?.openai?.azure_config?.api_version ||
							"2024-02-15-preview",
						...config.api_key_config?.openai?.azure_config,
						...updates,
					},
				},
			},
		});
	};

	const updateAnthropicConfig = (updates: Partial<AnthropicConfig>) => {
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				anthropic: {
					api_key: config.api_key_config?.anthropic?.api_key || "",
					...config.api_key_config?.anthropic,
					...updates,
				},
			},
		});
	};

	const updateOpenRouterConfig = (updates: Partial<OpenRouterConfig>) => {
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				openrouter: {
					api_key: config.api_key_config?.openrouter?.api_key || "",
					...config.api_key_config?.openrouter,
					...updates,
				},
			},
		});
	};

	const updateMiniMaxConfig = (updates: Partial<MiniMaxConfig>) => {
		setConfig({
			...config,
			api_key_config: {
				...config.api_key_config,
				minimax: {
					api_key: "",
					...(config.api_key_config?.minimax || {}),
					...updates,
				},
			},
		});
	};

	const updateLLMConfig = (updates: Partial<LLMConfig>) => {
		setConfig({ ...config, llm_config: { ...config.llm_config, ...updates } });
	};

	const handleOpenAIModeChange = (mode: "direct" | "azure") => {
		setOpenaiMode(mode);
		if (mode === "direct") {
			updateOpenAIConfig({ azure_config: undefined });
		} else {
			updateOpenAIConfig({
				api_key: undefined,
				azure_config: {
					api_key: "",
					endpoint: "",
					api_version: "2024-02-15-preview",
				},
			});
		}
	};

	// --- Save / Discard ---
	const handleSave = async () => {
		setSaveStatus("saving");
		setErrorMessage("");

		if (config.storage_config.type === "supabase") {
			const sc = config.storage_config;
			if (!sc.url || !sc.key || !sc.db_url) {
				const missing = [
					!sc.url && "Supabase URL",
					!sc.key && "Supabase Key",
					!sc.db_url && "Database URL",
				].filter(Boolean);
				setErrorMessage(`Required fields missing: ${missing.join(", ")}`);
				setSaveStatus("error");
				setTimeout(() => setSaveStatus("idle"), 3000);
				return;
			}
		}

		try {
			const backendConfig = frontendToBackendConfig(config);
			const result = await setConfigAPI(backendConfig as any);
			if (!result.success) {
				setErrorMessage(result.msg || "Failed to save configuration");
				setSaveStatus("error");
				setTimeout(() => setSaveStatus("idle"), 3000);
				return;
			}
			setOriginalConfig(config);
			setSaveStatus("success");
			setTimeout(() => setSaveStatus("idle"), 3000);
		} catch (error) {
			console.error("Error saving config:", error);
			setErrorMessage(
				error instanceof Error ? error.message : "Failed to save configuration",
			);
			setSaveStatus("error");
			setTimeout(() => setSaveStatus("idle"), 3000);
		}
	};

	const handleDiscard = () => {
		setConfig(originalConfig);
		setDiscardDialogOpen(false);
	};

	// --- Storage ---
	const updateStorageConfig = (updates: Partial<StorageConfig>) => {
		setConfig({
			...config,
			storage_config: { ...config.storage_config, ...updates } as StorageConfig,
		});
	};

	const changeStorageType = (type: StorageType) => {
		if (originalConfig.storage_config.type === type) {
			setConfig({ ...config, storage_config: originalConfig.storage_config });
		} else {
			const newSC: StorageConfig =
				type === "local"
					? { type: "local", dir_path: "./data" }
					: { type: "supabase", url: "", key: "", db_url: "" };
			setConfig({ ...config, storage_config: newSC });
		}
	};

	// --- Profile Extractors ---
	const addProfileExtractor = () => {
		setConfig({
			...config,
			profile_extractor_configs: [
				...config.profile_extractor_configs,
				{
					id: generateId(),
					extractor_name: "",
					profile_content_definition_prompt: "",
					context_prompt: "",
					metadata_definition_prompt: "",
					manual_trigger: false,
				},
			],
		});
	};

	const updateProfileExtractor = (
		id: string,
		updates: Partial<ProfileExtractorConfig>,
	) => {
		setConfig({
			...config,
			profile_extractor_configs: config.profile_extractor_configs.map((pec) =>
				pec.id === id ? { ...pec, ...updates } : pec,
			),
		});
	};

	const removeProfileExtractor = (id: string) => {
		setConfig({
			...config,
			profile_extractor_configs: config.profile_extractor_configs.filter(
				(pec) => pec.id !== id,
			),
		});
	};

	const addRequestSourceToExtractor = (extractorId: string, source: string) => {
		const ext = config.profile_extractor_configs.find(
			(pec) => pec.id === extractorId,
		);
		if (ext)
			updateProfileExtractor(extractorId, {
				request_sources_enabled: [
					...(ext.request_sources_enabled || []),
					source,
				],
			});
	};

	const removeRequestSourceFromExtractor = (
		extractorId: string,
		sourceIndex: number,
	) => {
		const ext = config.profile_extractor_configs.find(
			(pec) => pec.id === extractorId,
		);
		if (ext?.request_sources_enabled)
			updateProfileExtractor(extractorId, {
				request_sources_enabled: ext.request_sources_enabled.filter(
					(_, idx) => idx !== sourceIndex,
				),
			});
	};

	// --- Agent Feedback ---
	const addAgentFeedback = () => {
		setConfig({
			...config,
			agent_feedback_configs: [
				...config.agent_feedback_configs,
				{
					id: generateId(),
					feedback_name: "",
					feedback_definition_prompt: "",
					feedback_aggregator_config: {
						min_feedback_threshold: 2,
						refresh_count: 2,
					},
				},
			],
		});
	};

	const updateAgentFeedback = (
		id: string,
		updates: Partial<AgentFeedbackConfig>,
	) => {
		setConfig({
			...config,
			agent_feedback_configs: config.agent_feedback_configs.map((afc) =>
				afc.id === id ? { ...afc, ...updates } : afc,
			),
		});
	};

	const removeAgentFeedback = (id: string) => {
		setConfig({
			...config,
			agent_feedback_configs: config.agent_feedback_configs.filter(
				(afc) => afc.id !== id,
			),
		});
	};

	const addRequestSourceToFeedback = (feedbackId: string, source: string) => {
		const fb = config.agent_feedback_configs.find(
			(afc) => afc.id === feedbackId,
		);
		if (fb)
			updateAgentFeedback(feedbackId, {
				request_sources_enabled: [
					...(fb.request_sources_enabled || []),
					source,
				],
			});
	};

	const removeRequestSourceFromFeedback = (
		feedbackId: string,
		sourceIndex: number,
	) => {
		const fb = config.agent_feedback_configs.find(
			(afc) => afc.id === feedbackId,
		);
		if (fb?.request_sources_enabled)
			updateAgentFeedback(feedbackId, {
				request_sources_enabled: fb.request_sources_enabled.filter(
					(_, idx) => idx !== sourceIndex,
				),
			});
	};

	// --- Agent Success ---
	const addAgentSuccess = () => {
		setConfig({
			...config,
			agent_success_configs: [
				...config.agent_success_configs,
				{
					id: generateId(),
					evaluation_name: "",
					success_definition_prompt: "",
				},
			],
		});
	};

	const updateAgentSuccess = (
		id: string,
		updates: Partial<AgentSuccessConfig>,
	) => {
		setConfig({
			...config,
			agent_success_configs: config.agent_success_configs.map((asc) =>
				asc.id === id ? { ...asc, ...updates } : asc,
			),
		});
	};

	const removeAgentSuccess = (id: string) => {
		setConfig({
			...config,
			agent_success_configs: config.agent_success_configs.filter(
				(asc) => asc.id !== id,
			),
		});
	};

	// --- Tools ---
	const addTool = () => {
		setConfig({
			...config,
			tool_can_use: [
				...(config.tool_can_use || []),
				{ tool_name: "", tool_description: "" },
			],
		});
	};

	const updateTool = (toolIndex: number, updates: Partial<ToolUseConfig>) => {
		if (config.tool_can_use) {
			setConfig({
				...config,
				tool_can_use: config.tool_can_use.map((tool, idx) =>
					idx === toolIndex ? { ...tool, ...updates } : tool,
				),
			});
		}
	};

	const removeTool = (toolIndex: number) => {
		if (config.tool_can_use) {
			setConfig({
				...config,
				tool_can_use: config.tool_can_use.filter((_, idx) => idx !== toolIndex),
			});
		}
	};

	// --- Loading state ---
	if (loading) {
		return (
			<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50 flex items-center justify-center">
				<div className="flex flex-col items-center gap-4">
					<div className="animate-spin rounded-full h-10 w-10 border-2 border-transparent border-t-indigo-500 border-r-indigo-500"></div>
					<p className="text-slate-500">Loading configuration...</p>
				</div>
			</div>
		);
	}

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
			{/* Header */}
			<div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
				<div className="p-8">
					<div className="max-w-[1800px] mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
						<div>
							<div className="flex items-center gap-3 mb-2">
								<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
									<Settings className="h-5 w-5 text-white" />
								</div>
								<h1 className="text-3xl font-bold tracking-tight text-slate-800">
									Settings
								</h1>
							</div>
							<p className="text-slate-500 mt-1 ml-13">
								Configure storage, extractors, and evaluation criteria
							</p>
						</div>
						<div className="flex items-center gap-3">
							{hasUnsavedChanges && (
								<span className="text-xs text-amber-600 font-medium flex items-center gap-1.5 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-200">
									<span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
									Unsaved changes
								</span>
							)}
							{hasUnsavedChanges && (
								<Button
									variant="outline"
									onClick={() => setDiscardDialogOpen(true)}
									className="border-slate-300 text-slate-700 hover:bg-slate-50"
								>
									<Undo2 className="h-4 w-4 mr-2" />
									Discard
								</Button>
							)}
							<Button
								onClick={handleSave}
								disabled={saveStatus === "saving"}
								size="lg"
								className={`shadow-lg border-0 ${
									hasUnsavedChanges
										? "shadow-amber-500/25 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600"
										: "shadow-indigo-500/25 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700"
								}`}
							>
								<Save className="h-4 w-4 mr-2" />
								{saveStatus === "saving" ? "Saving..." : "Save Configuration"}
							</Button>
						</div>
					</div>
				</div>
			</div>

			<div className="p-8">
				<div className="max-w-[1800px] mx-auto">
					{/* Status Banners */}
					{hasUnsavedChanges && saveStatus !== "saving" && (
						<div
							className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-3 shadow-sm"
							role="status"
							aria-live="polite"
						>
							<div className="h-8 w-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
								<AlertCircle className="h-5 w-5 text-amber-600" />
							</div>
							<div>
								<p className="text-sm text-amber-800 font-semibold">
									You have unsaved changes
								</p>
								<p className="text-xs text-amber-600 mt-0.5">
									Your configuration has been modified. Don&apos;t forget to
									save before leaving.
								</p>
							</div>
						</div>
					)}

					{errorMessage && (
						<div
							className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-center gap-3 shadow-sm"
							role="alert"
						>
							<AlertCircle className="h-5 w-5 text-red-500" />
							<p className="text-sm text-red-600 font-medium">{errorMessage}</p>
						</div>
					)}

					{saveStatus === "success" && (
						<div
							className="mb-6 p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-3 shadow-sm"
							role="status"
							aria-live="polite"
						>
							<CheckCircle className="h-5 w-5 text-emerald-500" />
							<p className="text-sm text-emerald-700 font-medium">
								Configuration saved successfully!
							</p>
						</div>
					)}

					{saveStatus === "error" && !errorMessage && (
						<div
							className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-center gap-3 shadow-sm"
							role="alert"
						>
							<AlertCircle className="h-5 w-5 text-red-500" />
							<p className="text-sm text-red-600 font-medium">
								Failed to save configuration. Please try again.
							</p>
						</div>
					)}

					{/* Tabs */}
					<Tabs defaultValue="general" className="w-full">
						<TabsList className="bg-transparent border-b border-slate-200 rounded-none w-full justify-start h-auto p-0 gap-1">
							<TabsTrigger
								value="general"
								className="rounded-none border-b-2 border-transparent data-[state=active]:border-indigo-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:text-indigo-600 text-slate-500 hover:text-slate-700 px-6 py-3 text-sm font-medium"
							>
								General Settings
							</TabsTrigger>
							<TabsTrigger
								value="extractors"
								className="rounded-none border-b-2 border-transparent data-[state=active]:border-indigo-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:text-indigo-600 text-slate-500 hover:text-slate-700 px-6 py-3 text-sm font-medium"
							>
								Extractor Settings
							</TabsTrigger>
							<TabsTrigger
								value="workflow"
								className="rounded-none border-b-2 border-transparent data-[state=active]:border-indigo-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:text-indigo-600 text-slate-500 hover:text-slate-700 px-6 py-3 text-sm font-medium flex items-center gap-2"
							>
								<Workflow className="h-4 w-4" />
								Workflow Visualization
							</TabsTrigger>
						</TabsList>

						<TabsContent value="general" className="mt-6">
							<div className="space-y-6">
								<StorageConfigSection
									config={config}
									onStorageUpdate={updateStorageConfig}
									onStorageTypeChange={changeStorageType}
								/>
								<AgentContextSection
									config={config}
									onContextChange={(v) =>
										setConfig({ ...config, agent_context_prompt: v })
									}
									onAddTool={addTool}
									onUpdateTool={updateTool}
									onRemoveTool={removeTool}
								/>
								<ExtractionParamsSection
									config={config}
									onWindowSizeChange={(v) =>
										setConfig({ ...config, extraction_window_size: v })
									}
									onWindowStrideChange={(v) =>
										setConfig({ ...config, extraction_window_stride: v })
									}
								/>
								<AdvancedSettingsSection
									config={config}
									openaiMode={openaiMode}
									onOpenAIModeChange={handleOpenAIModeChange}
									onUpdateCustomEndpoint={updateCustomEndpointConfig}
									onUpdateOpenAI={updateOpenAIConfig}
									onUpdateAzureOpenAI={updateAzureOpenAIConfig}
									onUpdateAnthropic={updateAnthropicConfig}
									onUpdateOpenRouter={updateOpenRouterConfig}
									onUpdateMiniMax={updateMiniMaxConfig}
									onUpdateLLM={updateLLMConfig}
								/>
							</div>
						</TabsContent>

						<TabsContent value="extractors" className="mt-6">
							<div className="space-y-6">
								<ProfileExtractorsSection
									config={config}
									onAdd={addProfileExtractor}
									onUpdate={updateProfileExtractor}
									onRemove={removeProfileExtractor}
									onAddRequestSource={addRequestSourceToExtractor}
									onRemoveRequestSource={removeRequestSourceFromExtractor}
								/>
								<AgentFeedbackSection
									config={config}
									onAdd={addAgentFeedback}
									onUpdate={updateAgentFeedback}
									onRemove={removeAgentFeedback}
									onAddRequestSource={addRequestSourceToFeedback}
									onRemoveRequestSource={removeRequestSourceFromFeedback}
								/>
								<AgentSuccessSection
									config={config}
									onAdd={addAgentSuccess}
									onUpdate={updateAgentSuccess}
									onRemove={removeAgentSuccess}
								/>
							</div>
						</TabsContent>

						<TabsContent value="workflow" className="mt-6">
							<div className="space-y-6">
								<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
									<CardHeader className="pb-4">
										<div className="flex items-center gap-3">
											<Workflow className="h-4 w-4 text-slate-400" />
											<div>
												<CardTitle className="text-lg font-semibold text-slate-800">
													Reflexio Workflow
												</CardTitle>
												<CardDescription className="text-xs mt-1 text-slate-500">
													Visual representation of how your configuration
													processes data
												</CardDescription>
											</div>
										</div>
									</CardHeader>
									<CardContent>
										<div className="mb-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
											<p className="text-sm text-slate-600">
												This diagram shows how requests flow through the
												Reflexio system based on your current configuration.
												Click on nodes to view detailed information about each
												component.
											</p>
										</div>
										<WorkflowVisualization config={config} />
									</CardContent>
								</Card>
							</div>
						</TabsContent>
					</Tabs>

					{/* Bottom Save Button */}
					<div className="mt-8 flex justify-end items-center gap-3">
						{hasUnsavedChanges && (
							<>
								<span className="text-xs text-amber-600 font-medium flex items-center gap-1.5 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-200">
									<span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
									Unsaved changes
								</span>
								<Button
									variant="outline"
									onClick={() => setDiscardDialogOpen(true)}
									className="border-slate-300 text-slate-700 hover:bg-slate-50"
								>
									<Undo2 className="h-4 w-4 mr-2" />
									Discard
								</Button>
							</>
						)}
						<Button
							onClick={handleSave}
							disabled={saveStatus === "saving"}
							size="lg"
							className={`shadow-lg border-0 ${
								hasUnsavedChanges
									? "shadow-amber-500/25 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600"
									: "shadow-indigo-500/25 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700"
							}`}
						>
							<Save className="h-4 w-4 mr-2" />
							{saveStatus === "saving" ? "Saving..." : "Save Configuration"}
						</Button>
					</div>
				</div>
			</div>

			{/* Discard Changes Dialog */}
			<Dialog open={discardDialogOpen} onOpenChange={setDiscardDialogOpen}>
				<DialogContent className="sm:max-w-[425px]">
					<DialogHeader>
						<div className="flex items-center gap-3 mb-2">
							<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-amber-50 to-amber-100 flex items-center justify-center flex-shrink-0 border border-amber-200">
								<Undo2 className="h-5 w-5 text-amber-600" />
							</div>
							<DialogTitle className="text-xl font-semibold text-slate-800">
								Discard Changes
							</DialogTitle>
						</div>
						<DialogDescription className="text-sm text-slate-600 pt-2">
							Are you sure you want to discard all unsaved changes? This will
							revert the configuration to the last saved state.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="outline"
							onClick={() => setDiscardDialogOpen(false)}
							className="border-slate-300 text-slate-700 hover:bg-slate-50"
						>
							Cancel
						</Button>
						<Button
							onClick={handleDiscard}
							className="bg-amber-500 hover:bg-amber-600 text-white border-0"
						>
							<Undo2 className="h-4 w-4 mr-2" />
							Discard Changes
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}

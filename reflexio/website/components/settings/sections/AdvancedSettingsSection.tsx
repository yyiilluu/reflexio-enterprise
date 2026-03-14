"use client";

import {
	Bot,
	ChevronDown,
	ChevronUp,
	Circle,
	Cpu,
	Globe,
	Key,
	Layers,
	Router,
	Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type {
	AnthropicConfig,
	AzureOpenAIConfig,
	Config,
	CustomEndpointConfig,
	LLMConfig,
	MiniMaxConfig,
	OpenAIConfig,
	OpenRouterConfig,
} from "@/app/settings/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { FieldLabel } from "../FieldLabel";
import { PasswordInput } from "../PasswordInput";

const PROVIDERS = [
	{ id: "custom_endpoint", label: "Custom Endpoint", abbreviation: "CE" },
	{ id: "openai", label: "OpenAI", abbreviation: "AI" },
	{ id: "anthropic", label: "Anthropic", abbreviation: "A" },
	{ id: "openrouter", label: "OpenRouter", abbreviation: "OR" },
	{ id: "minimax", label: "MiniMax", abbreviation: "MM" },
] as const;

type ProviderId = (typeof PROVIDERS)[number]["id"];

function isProviderConfigured(providerId: ProviderId, config: Config): boolean {
	switch (providerId) {
		case "custom_endpoint":
			return !!(
				config.api_key_config?.custom_endpoint?.api_key ||
				config.api_key_config?.custom_endpoint?.api_base ||
				config.api_key_config?.custom_endpoint?.model
			);
		case "openai":
			return !!(
				config.api_key_config?.openai?.api_key ||
				config.api_key_config?.openai?.azure_config?.api_key
			);
		case "anthropic":
			return !!config.api_key_config?.anthropic?.api_key;
		case "openrouter":
			return !!config.api_key_config?.openrouter?.api_key;
		case "minimax":
			return !!config.api_key_config?.minimax?.api_key;
		default:
			return false;
	}
}

interface AdvancedSettingsSectionProps {
	config: Config;
	openaiMode: "direct" | "azure";
	onOpenAIModeChange: (mode: "direct" | "azure") => void;
	onUpdateCustomEndpoint: (updates: Partial<CustomEndpointConfig>) => void;
	onUpdateOpenAI: (updates: Partial<OpenAIConfig>) => void;
	onUpdateAzureOpenAI: (updates: Partial<AzureOpenAIConfig>) => void;
	onUpdateAnthropic: (updates: Partial<AnthropicConfig>) => void;
	onUpdateOpenRouter: (updates: Partial<OpenRouterConfig>) => void;
	onUpdateMiniMax: (updates: Partial<MiniMaxConfig>) => void;
	onUpdateLLM: (updates: Partial<LLMConfig>) => void;
}

export function AdvancedSettingsSection({
	config,
	openaiMode,
	onOpenAIModeChange,
	onUpdateCustomEndpoint,
	onUpdateOpenAI,
	onUpdateAzureOpenAI,
	onUpdateAnthropic,
	onUpdateOpenRouter,
	onUpdateMiniMax,
	onUpdateLLM,
}: AdvancedSettingsSectionProps) {
	const [expanded, setExpanded] = useState(false);

	const defaultProvider = useMemo<ProviderId>(() => {
		const firstConfigured = PROVIDERS.find((p) =>
			isProviderConfigured(p.id, config),
		);
		return firstConfigured?.id ?? "custom_endpoint";
	}, [config]);

	const [selectedProvider, setSelectedProvider] =
		useState<ProviderId>(defaultProvider);

	// Sync selectedProvider when config loads asynchronously
	useEffect(() => {
		setSelectedProvider(defaultProvider);
	}, [defaultProvider]);

	const configuredProviders = useMemo(
		() => PROVIDERS.filter((p) => isProviderConfigured(p.id, config)),
		[config],
	);

	const hasConfig = !!(
		configuredProviders.length > 0 ||
		config.llm_config?.should_run_model_name ||
		config.llm_config?.generation_model_name ||
		config.llm_config?.embedding_model_name
	);

	return (
		<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
			<CardHeader
				className="pb-4 cursor-pointer select-none"
				onClick={() => setExpanded(!expanded)}
			>
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-3">
						<Key className="h-4 w-4 text-slate-400" />
						<div>
							<CardTitle className="text-lg font-semibold text-slate-800">
								Advanced Settings
							</CardTitle>
							<CardDescription className="text-xs mt-1 text-muted-foreground">
								API keys and provider configuration
							</CardDescription>
						</div>
					</div>
					<div className="flex items-center gap-2">
						{hasConfig && (
							<Badge className="text-xs bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
								Configured
							</Badge>
						)}
						<Button
							variant="ghost"
							size="sm"
							className="h-8 w-8 p-0"
							aria-label={expanded ? "Collapse" : "Expand"}
						>
							{expanded ? (
								<ChevronUp className="h-5 w-5 text-slate-500" />
							) : (
								<ChevronDown className="h-5 w-5 text-slate-500" />
							)}
						</Button>
					</div>
				</div>
			</CardHeader>

			{expanded && (
				<CardContent className="space-y-6 pt-0">
					{/* Provider selector */}
					<div className="space-y-3">
						{/* Configured provider pills */}
						{configuredProviders.length > 0 && (
							<div className="flex items-center gap-2 flex-wrap">
								<span className="text-xs text-muted-foreground">
									Configured:
								</span>
								{configuredProviders.map((p) => (
									<button
										key={p.id}
										type="button"
										onClick={() => setSelectedProvider(p.id)}
										className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all border ${
											selectedProvider === p.id
												? "bg-indigo-50 text-indigo-700 border-indigo-200"
												: "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
										}`}
									>
										<Circle className="h-2 w-2 fill-emerald-500 text-emerald-500" />
										{p.label}
									</button>
								))}
							</div>
						)}

						{/* Provider dropdown */}
						<select
							value={selectedProvider}
							onChange={(e) =>
								setSelectedProvider(e.target.value as ProviderId)
							}
							className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
						>
							{PROVIDERS.map((p) => {
								const configured = isProviderConfigured(p.id, config);
								return (
									<option key={p.id} value={p.id}>
										{configured ? `● ${p.label}` : p.label}
									</option>
								);
							})}
						</select>
					</div>

					{/* Selected provider config panel */}
					{selectedProvider === "custom_endpoint" && (
						<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
							<div className="flex items-center gap-2">
								<Globe className="h-4 w-4 text-slate-400" />
								<span className="text-sm font-semibold text-slate-800">
									Custom Endpoint
								</span>
							</div>
							<p className="text-xs text-muted-foreground">
								Connect to any OpenAI-compatible endpoint (e.g., vLLM, LiteLLM
								proxy, Ollama). When configured, this takes priority over all
								other providers for LLM completion calls.
							</p>
							<div className="grid gap-4 sm:grid-cols-3">
								<div>
									<FieldLabel>Model Name</FieldLabel>
									<Input
										type="text"
										value={config.api_key_config?.custom_endpoint?.model || ""}
										onChange={(e) =>
											onUpdateCustomEndpoint({ model: e.target.value })
										}
										placeholder="e.g., openai/mistral"
										className="h-10"
									/>
									<p className="text-xs text-muted-foreground mt-1">
										Model identifier passed to LiteLLM
									</p>
								</div>
								<div>
									<FieldLabel>Endpoint URL</FieldLabel>
									<Input
										type="text"
										value={
											config.api_key_config?.custom_endpoint?.api_base || ""
										}
										onChange={(e) =>
											onUpdateCustomEndpoint({ api_base: e.target.value })
										}
										placeholder="http://localhost:8000/v1"
										className="h-10"
									/>
									<p className="text-xs text-muted-foreground mt-1">
										Base URL of the API
									</p>
								</div>
								<div>
									<FieldLabel>API Key</FieldLabel>
									<PasswordInput
										value={
											config.api_key_config?.custom_endpoint?.api_key || ""
										}
										onChange={(value) =>
											onUpdateCustomEndpoint({ api_key: value })
										}
										placeholder="API key (if required)"
									/>
									<p className="text-xs text-muted-foreground mt-1">
										Authentication key for the endpoint
									</p>
								</div>
							</div>
						</div>
					)}

					{selectedProvider === "openai" && (
						<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
							<div className="flex items-center gap-2">
								<Cpu className="h-4 w-4 text-slate-400" />
								<span className="text-sm font-semibold text-slate-800">
									OpenAI Configuration
								</span>
							</div>

							<div>
								<FieldLabel>Provider Mode</FieldLabel>
								<div className="flex gap-2">
									<button
										type="button"
										onClick={() => onOpenAIModeChange("direct")}
										className={`flex-1 h-10 px-4 rounded-lg text-sm font-medium transition-all border ${
											openaiMode === "direct"
												? "bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm"
												: "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
										}`}
									>
										Direct OpenAI
									</button>
									<button
										type="button"
										onClick={() => onOpenAIModeChange("azure")}
										className={`flex-1 h-10 px-4 rounded-lg text-sm font-medium transition-all border ${
											openaiMode === "azure"
												? "bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm"
												: "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
										}`}
									>
										Azure OpenAI
									</button>
								</div>
							</div>

							{openaiMode === "direct" ? (
								<div>
									<FieldLabel>OpenAI API Key</FieldLabel>
									<PasswordInput
										value={config.api_key_config?.openai?.api_key || ""}
										onChange={(value) => onUpdateOpenAI({ api_key: value })}
										placeholder="sk-..."
									/>
									<p className="text-xs text-muted-foreground mt-2">
										Your OpenAI API key for direct API access
									</p>
								</div>
							) : (
								<div className="space-y-4">
									<div className="grid gap-4 sm:grid-cols-2">
										<div>
											<FieldLabel>Azure API Key</FieldLabel>
											<PasswordInput
												value={
													config.api_key_config?.openai?.azure_config
														?.api_key || ""
												}
												onChange={(value) =>
													onUpdateAzureOpenAI({ api_key: value })
												}
												placeholder="Azure OpenAI API Key"
											/>
										</div>
										<div>
											<FieldLabel>Endpoint</FieldLabel>
											<Input
												type="text"
												value={
													config.api_key_config?.openai?.azure_config
														?.endpoint || ""
												}
												onChange={(e) =>
													onUpdateAzureOpenAI({ endpoint: e.target.value })
												}
												placeholder="https://your-resource.openai.azure.com/"
												className="h-10"
											/>
										</div>
									</div>
									<div className="grid gap-4 sm:grid-cols-2">
										<div>
											<FieldLabel>API Version</FieldLabel>
											<Input
												type="text"
												value={
													config.api_key_config?.openai?.azure_config
														?.api_version || "2024-02-15-preview"
												}
												onChange={(e) =>
													onUpdateAzureOpenAI({ api_version: e.target.value })
												}
												placeholder="2024-02-15-preview"
												className="h-10"
											/>
										</div>
										<div>
											<FieldLabel>Deployment Name (Optional)</FieldLabel>
											<Input
												type="text"
												value={
													config.api_key_config?.openai?.azure_config
														?.deployment_name || ""
												}
												onChange={(e) =>
													onUpdateAzureOpenAI({
														deployment_name: e.target.value || undefined,
													})
												}
												placeholder="gpt-4"
												className="h-10"
											/>
										</div>
									</div>
									<p className="text-xs text-muted-foreground">
										Configure Azure OpenAI Service credentials for enterprise
										deployments
									</p>
								</div>
							)}
						</div>
					)}

					{selectedProvider === "anthropic" && (
						<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
							<div className="flex items-center gap-2">
								<Bot className="h-4 w-4 text-slate-400" />
								<span className="text-sm font-semibold text-slate-800">
									Anthropic Configuration
								</span>
							</div>
							<div>
								<FieldLabel>Anthropic API Key</FieldLabel>
								<PasswordInput
									value={config.api_key_config?.anthropic?.api_key || ""}
									onChange={(value) => onUpdateAnthropic({ api_key: value })}
									placeholder="sk-ant-..."
								/>
								<p className="text-xs text-muted-foreground mt-2">
									Your Anthropic API key for Claude models
								</p>
							</div>
						</div>
					)}

					{selectedProvider === "openrouter" && (
						<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
							<div className="flex items-center gap-2">
								<Router className="h-4 w-4 text-slate-400" />
								<span className="text-sm font-semibold text-slate-800">
									OpenRouter Configuration
								</span>
							</div>
							<div>
								<FieldLabel>OpenRouter API Key</FieldLabel>
								<PasswordInput
									value={config.api_key_config?.openrouter?.api_key || ""}
									onChange={(value) => onUpdateOpenRouter({ api_key: value })}
									placeholder="sk-or-..."
								/>
								<p className="text-xs text-muted-foreground mt-2">
									Your OpenRouter API key for accessing multiple providers
								</p>
							</div>
						</div>
					)}

					{selectedProvider === "minimax" && (
						<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
							<div className="flex items-center gap-2">
								<Sparkles className="h-4 w-4 text-slate-400" />
								<span className="text-sm font-semibold text-slate-800">
									MiniMax Configuration
								</span>
							</div>
							<div>
								<FieldLabel>MiniMax API Key</FieldLabel>
								<PasswordInput
									value={config.api_key_config?.minimax?.api_key || ""}
									onChange={(value) => onUpdateMiniMax({ api_key: value })}
									placeholder="eyJ..."
								/>
								<p className="text-xs text-muted-foreground mt-2">
									Your MiniMax API key. Use model prefix &quot;minimax/&quot;
									(e.g., minimax/MiniMax-Text-01)
								</p>
							</div>
						</div>
					)}

					<Separator />

					{/* LLM Model Configuration - always visible */}
					<div className="p-5 border border-slate-200 rounded-lg space-y-4 bg-slate-50">
						<div className="flex items-center gap-2">
							<Layers className="h-4 w-4 text-slate-400" />
							<span className="text-sm font-semibold text-slate-800">
								LLM Model Configuration
							</span>
						</div>
						<p className="text-xs text-muted-foreground">
							Override default model names. Leave empty to use system defaults
							from site configuration.
						</p>

						<div className="grid gap-4 sm:grid-cols-3">
							<div>
								<FieldLabel tooltip="Lightweight model used to check if extraction should run on a given batch">
									Should Run Model
								</FieldLabel>
								<Input
									type="text"
									value={config.llm_config?.should_run_model_name || ""}
									onChange={(e) =>
										onUpdateLLM({
											should_run_model_name: e.target.value || undefined,
										})
									}
									placeholder="e.g., gpt-5-nano"
									className="h-10"
								/>
								<p className="text-xs text-muted-foreground mt-1">
									Model for extraction checks
								</p>
							</div>
							<div>
								<FieldLabel>Generation Model</FieldLabel>
								<Input
									type="text"
									value={config.llm_config?.generation_model_name || ""}
									onChange={(e) =>
										onUpdateLLM({
											generation_model_name: e.target.value || undefined,
										})
									}
									placeholder="e.g., gpt-5"
									className="h-10"
								/>
								<p className="text-xs text-muted-foreground mt-1">
									Model for generation & evaluation
								</p>
							</div>
							<div>
								<FieldLabel>Embedding Model</FieldLabel>
								<Input
									type="text"
									value={config.llm_config?.embedding_model_name || ""}
									onChange={(e) =>
										onUpdateLLM({
											embedding_model_name: e.target.value || undefined,
										})
									}
									placeholder="e.g., text-embedding-3-small"
									className="h-10"
								/>
								<p className="text-xs text-muted-foreground mt-1">
									Model for embeddings
								</p>
							</div>
						</div>
					</div>
				</CardContent>
			)}
		</Card>
	);
}

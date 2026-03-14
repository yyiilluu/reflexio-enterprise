// Types matching the config schema
export type StorageType = "local" | "supabase";

export interface StorageConfigLocal {
	type: "local";
	dir_path: string;
}

export interface StorageConfigSupabase {
	type: "supabase";
	url: string;
	key: string;
	db_url: string;
}

export type StorageConfig = StorageConfigLocal | StorageConfigSupabase;

// Frontend config types (with id for UI management)
export interface ProfileExtractorConfig {
	id: string;
	extractor_name: string;
	profile_content_definition_prompt: string;
	context_prompt?: string;
	metadata_definition_prompt?: string;
	should_extract_profile_prompt_override?: string;
	request_sources_enabled?: string[];
	manual_trigger?: boolean;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

export interface FeedbackAggregatorConfig {
	min_feedback_threshold: number;
	refresh_count: number;
}

export interface AgentFeedbackConfig {
	id: string;
	feedback_name: string;
	feedback_definition_prompt: string;
	metadata_definition_prompt?: string;
	request_sources_enabled?: string[];
	feedback_aggregator_config?: FeedbackAggregatorConfig;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

export interface ToolUseConfig {
	tool_name: string;
	tool_description: string;
}

export interface AgentSuccessConfig {
	id: string;
	evaluation_name: string;
	success_definition_prompt: string;
	metadata_definition_prompt?: string;
	sampling_rate?: number;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

// API Key configuration types
export interface AzureOpenAIConfig {
	api_key: string;
	endpoint: string;
	api_version: string;
	deployment_name?: string;
}

export interface OpenAIConfig {
	api_key?: string;
	azure_config?: AzureOpenAIConfig;
}

export interface AnthropicConfig {
	api_key: string;
}

export interface OpenRouterConfig {
	api_key: string;
}

export interface MiniMaxConfig {
	api_key: string;
}

export interface CustomEndpointConfig {
	model: string;
	api_key: string;
	api_base: string;
}

export interface APIKeyConfig {
	custom_endpoint?: CustomEndpointConfig;
	openai?: OpenAIConfig;
	anthropic?: AnthropicConfig;
	openrouter?: OpenRouterConfig;
	minimax?: MiniMaxConfig;
}

// LLM model configuration overrides
export interface LLMConfig {
	should_run_model_name?: string;
	generation_model_name?: string;
	embedding_model_name?: string;
}

export interface Config {
	storage_config: StorageConfig;
	agent_context_prompt?: string;
	tool_can_use?: ToolUseConfig[];
	profile_extractor_configs: ProfileExtractorConfig[];
	agent_feedback_configs: AgentFeedbackConfig[];
	agent_success_configs: AgentSuccessConfig[];
	extraction_window_size?: number;
	extraction_window_stride?: number;
	api_key_config?: APIKeyConfig;
	llm_config?: LLMConfig;
}

// Backend config types (without id, matches Python schema)
export interface BackendProfileExtractorConfig {
	extractor_name: string;
	profile_content_definition_prompt: string;
	context_prompt?: string;
	metadata_definition_prompt?: string;
	should_extract_profile_prompt_override?: string;
	request_sources_enabled?: string[];
	manual_trigger?: boolean;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

export interface BackendAgentFeedbackConfig {
	feedback_name: string;
	feedback_definition_prompt: string;
	metadata_definition_prompt?: string;
	request_sources_enabled?: string[];
	feedback_aggregator_config?: FeedbackAggregatorConfig;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

export interface BackendAgentSuccessConfig {
	evaluation_name: string;
	success_definition_prompt: string;
	metadata_definition_prompt?: string;
	sampling_rate?: number;
	extraction_window_size_override?: number;
	extraction_window_stride_override?: number;
}

export interface BackendConfig {
	storage_config: StorageConfig;
	agent_context_prompt?: string;
	tool_can_use?: ToolUseConfig[];
	profile_extractor_configs?: BackendProfileExtractorConfig[];
	agent_feedback_configs?: BackendAgentFeedbackConfig[];
	agent_success_configs?: BackendAgentSuccessConfig[];
	extraction_window_size?: number;
	extraction_window_stride?: number;
	api_key_config?: APIKeyConfig;
	llm_config?: LLMConfig;
}

// Helper function to generate unique IDs
export const generateId = () => Math.random().toString(36).substring(2, 9);

// Helper function to infer storage type and add type field
export const inferStorageConfig = (storageConfig: any): StorageConfig => {
	if (!storageConfig) {
		return { type: "local", dir_path: "" };
	}
	if ("dir_path" in storageConfig) {
		return { type: "local", dir_path: storageConfig.dir_path };
	} else if ("url" in storageConfig && "key" in storageConfig) {
		return {
			type: "supabase",
			url: storageConfig.url,
			key: storageConfig.key,
			db_url: storageConfig.db_url,
		};
	}
	return { type: "local", dir_path: "" };
};

// Helper function to deep compare configs for unsaved changes detection
export const configsAreEqual = (config1: Config, config2: Config): boolean => {
	if (
		JSON.stringify(config1.storage_config) !==
		JSON.stringify(config2.storage_config)
	)
		return false;
	if (
		(config1.agent_context_prompt || "") !==
		(config2.agent_context_prompt || "")
	)
		return false;
	if (
		JSON.stringify(config1.tool_can_use || []) !==
		JSON.stringify(config2.tool_can_use || [])
	)
		return false;
	if (
		config1.extraction_window_size !== config2.extraction_window_size ||
		config1.extraction_window_stride !== config2.extraction_window_stride
	)
		return false;
	if (
		JSON.stringify(config1.api_key_config || {}) !==
		JSON.stringify(config2.api_key_config || {})
	)
		return false;
	if (
		JSON.stringify(config1.llm_config || {}) !==
		JSON.stringify(config2.llm_config || {})
	)
		return false;

	const extractors1 = config1.profile_extractor_configs.map(
		({ id, ...rest }) => rest,
	);
	const extractors2 = config2.profile_extractor_configs.map(
		({ id, ...rest }) => rest,
	);
	if (JSON.stringify(extractors1) !== JSON.stringify(extractors2)) return false;

	const feedback1 = config1.agent_feedback_configs.map(
		({ id, ...rest }) => rest,
	);
	const feedback2 = config2.agent_feedback_configs.map(
		({ id, ...rest }) => rest,
	);
	if (JSON.stringify(feedback1) !== JSON.stringify(feedback2)) return false;

	const success1 = config1.agent_success_configs.map(({ id, ...rest }) => rest);
	const success2 = config2.agent_success_configs.map(({ id, ...rest }) => rest);
	if (JSON.stringify(success1) !== JSON.stringify(success2)) return false;

	return true;
};

// Helper functions to convert between backend and frontend configs
export const backendToFrontendConfig = (
	backendConfig: BackendConfig,
): Config => {
	return {
		storage_config: inferStorageConfig(backendConfig.storage_config),
		agent_context_prompt: backendConfig.agent_context_prompt,
		tool_can_use: backendConfig.tool_can_use,
		profile_extractor_configs: (
			backendConfig.profile_extractor_configs || []
		).map((config) => ({
			id: generateId(),
			...config,
		})),
		agent_feedback_configs: (backendConfig.agent_feedback_configs || []).map(
			(config) => ({
				id: generateId(),
				...config,
			}),
		),
		agent_success_configs: (backendConfig.agent_success_configs || []).map(
			(config) => ({
				id: generateId(),
				...config,
			}),
		),
		extraction_window_size: backendConfig.extraction_window_size,
		extraction_window_stride: backendConfig.extraction_window_stride,
		api_key_config: backendConfig.api_key_config,
		llm_config: backendConfig.llm_config,
	};
};

export const frontendToBackendConfig = (config: Config): BackendConfig => {
	const { type, ...storageConfigWithoutType } = config.storage_config;

	return {
		storage_config: storageConfigWithoutType as any,
		agent_context_prompt: config.agent_context_prompt,
		tool_can_use: config.tool_can_use,
		profile_extractor_configs: config.profile_extractor_configs.map(
			({ id, ...rest }) => rest,
		),
		agent_feedback_configs: config.agent_feedback_configs.map(
			({ id, ...rest }) => rest,
		),
		agent_success_configs: config.agent_success_configs.map(
			({ id, ...rest }) => rest,
		),
		extraction_window_size: config.extraction_window_size,
		extraction_window_stride: config.extraction_window_stride,
		api_key_config: config.api_key_config,
		llm_config: config.llm_config,
	};
};

// Default configuration
export const getDefaultConfig = (): Config => ({
	storage_config: { type: "local", dir_path: "./data" },
	agent_context_prompt: "",
	profile_extractor_configs: [],
	agent_feedback_configs: [],
	agent_success_configs: [],
	extraction_window_size: 10,
	extraction_window_stride: 5,
});

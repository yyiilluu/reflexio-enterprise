"use client";

import {
	Background,
	BackgroundVariant,
	Controls,
	type Edge,
	MarkerType,
	type Node,
	ReactFlow,
} from "@xyflow/react";
import { useMemo } from "react";
import "@xyflow/react/dist/style.css";
import CustomStorageEdge from "./edges/CustomStorageEdge";
import { AggregatorNode } from "./nodes/AggregatorNode";
import { ExtractorNode } from "./nodes/ExtractorNode";
import { RequestNode } from "./nodes/RequestNode";
import { SlidingWindowNode } from "./nodes/SlidingWindowNode";
import { StorageNode } from "./nodes/StorageNode";

// Define custom node types
const nodeTypes = {
	requestNode: RequestNode,
	slidingWindowNode: SlidingWindowNode,
	extractorNode: ExtractorNode,
	aggregatorNode: AggregatorNode,
	storageNode: StorageNode,
};

// Define custom edge types
const edgeTypes = {
	customStorage: CustomStorageEdge,
};

// Config types matching settings page
interface ProfileExtractorConfig {
	id: string;
	profile_content_definition_prompt: string;
	context_prompt?: string;
	metadata_definition_prompt?: string;
	should_extract_profile_prompt_override?: string;
	request_sources_enabled?: string[];
}

interface FeedbackAggregatorConfig {
	min_feedback_threshold: number;
	refresh_count: number;
}

interface AgentFeedbackConfig {
	id: string;
	feedback_name: string;
	feedback_definition_prompt: string;
	metadata_definition_prompt?: string;
	feedback_aggregator_config?: FeedbackAggregatorConfig;
}

interface ToolUseConfig {
	tool_name: string;
	tool_description: string;
}

interface AgentSuccessConfig {
	id: string;
	evaluation_name: string;
	success_definition_prompt: string;
	tool_can_use?: ToolUseConfig[];
	action_space?: string[];
	metadata_definition_prompt?: string;
	sampling_rate?: number;
}

interface StorageConfig {
	type: "local" | "s3" | "supabase";
	[key: string]: any;
}

interface Config {
	storage_config: StorageConfig;
	profile_extractor_configs: ProfileExtractorConfig[];
	agent_feedback_configs: AgentFeedbackConfig[];
	agent_success_configs: AgentSuccessConfig[];
	extraction_window_size?: number;
	extraction_window_stride?: number;
}

interface WorkflowVisualizationProps {
	config: Config;
}

export default function WorkflowVisualization({
	config,
}: WorkflowVisualizationProps) {
	const { nodes, edges } = useMemo(() => {
		const generatedNodes: Node[] = [];
		const generatedEdges: Edge[] = [];

		// Layout configuration - Horizontal flow (left to right)
		const horizontalSpacing = 500;
		const verticalNodeSpacing = 200;
		const centerY = 400;

		let currentX = 100;

		// Node dimensions (measured widths and heights for centering)
		const requestNodeHeight = 160;
		const _requestNodeWidth = 280;
		const slidingWindowNodeHeight = 480; // Tall due to SVG visualization, stats, and button
		const slidingWindowNodeWidth = 380; // Wide because of animation
		const extractorNodeWidth = 250;
		const _storageNodeWidth = 300;

		// 1. Request Entry Node (leftmost) - center aligned with sliding window
		const requestNodeY = centerY - requestNodeHeight / 2;
		generatedNodes.push({
			id: "request",
			type: "requestNode",
			position: { x: currentX, y: requestNodeY },
			data: { label: "Request Entry" },
		});
		const _requestNodeX = currentX;
		currentX += horizontalSpacing;

		// 2. Sliding Window Node - center aligned with request entry
		const slidingWindowNodeY = centerY - slidingWindowNodeHeight / 2;
		const slidingWindowNodeX = currentX;
		generatedNodes.push({
			id: "window",
			type: "slidingWindowNode",
			position: { x: slidingWindowNodeX, y: slidingWindowNodeY },
			data: {
				label: "Sliding Window Processor",
				windowSize: config.extraction_window_size,
				windowStride: config.extraction_window_stride,
			},
		});
		generatedEdges.push({
			id: "e-request-window",
			source: "request",
			target: "window",
			type: "default",
			animated: false,
			style: { stroke: "#457b9d", strokeWidth: 3 },
			markerEnd: { type: MarkerType.ArrowClosed, color: "#457b9d" },
		});
		currentX += horizontalSpacing;

		// 3. Collect all extractors with their metadata and config
		const allExtractors: Array<{
			id: string;
			type: "profile" | "feedback" | "success";
			name: string;
			prompt: string;
			metadata?: string;
			samplingRate?: number;
			tableName: string;
			config: ProfileExtractorConfig | AgentFeedbackConfig | AgentSuccessConfig;
		}> = [];

		// Profile Extractors
		config.profile_extractor_configs.forEach((ext, idx) => {
			allExtractors.push({
				id: `profile-${idx}`,
				type: "profile",
				name: `Profile #${idx + 1}`,
				prompt: ext.profile_content_definition_prompt,
				metadata: ext.metadata_definition_prompt,
				tableName: "profiles",
				config: ext,
			});
		});

		// Feedback Extractors
		config.agent_feedback_configs.forEach((ext, idx) => {
			allExtractors.push({
				id: `feedback-${idx}`,
				type: "feedback",
				name: ext.feedback_name || `Feedback #${idx + 1}`,
				prompt: ext.feedback_definition_prompt,
				metadata: ext.metadata_definition_prompt,
				tableName: "feedbacks",
				config: ext,
			});
		});

		// Success Evaluators
		config.agent_success_configs.forEach((ext, idx) => {
			allExtractors.push({
				id: `success-${idx}`,
				type: "success",
				name: ext.evaluation_name || `Success #${idx + 1}`,
				prompt: ext.success_definition_prompt,
				metadata: ext.metadata_definition_prompt,
				samplingRate: ext.sampling_rate,
				tableName: "agent_success_results",
				config: ext,
			});
		});

		const totalExtractors = allExtractors.length;

		// Calculate positions for extractors, aggregators, and storage
		const slidingWindowRightEdge = slidingWindowNodeX + slidingWindowNodeWidth;
		const gapBetweenNodes = 300; // Gap between each stage

		// Position extractors after sliding window
		const extractorX = slidingWindowRightEdge + gapBetweenNodes;

		// Position aggregators after extractors (same width as extractors)
		const aggregatorX = extractorX + extractorNodeWidth + gapBetweenNodes;
		const aggregatorNodeWidth = 250; // Same as extractor

		// Position storage after aggregators
		const storageX = aggregatorX + aggregatorNodeWidth + gapBetweenNodes;

		// Calculate vertical centering for extractors
		const totalExtractorHeight = (totalExtractors - 1) * verticalNodeSpacing;
		const startY = centerY - totalExtractorHeight / 2;

		// Create all extractors in a single vertical column with even spacing
		allExtractors.forEach((extractor, idx) => {
			const y = startY + idx * verticalNodeSpacing;

			generatedNodes.push({
				id: extractor.id,
				type: "extractorNode",
				position: { x: extractorX, y },
				data: {
					label: extractor.name,
					type: extractor.type,
					name: extractor.name,
					prompt: extractor.prompt,
					metadata: extractor.metadata,
					samplingRate: extractor.samplingRate,
					tableName: extractor.tableName,
				},
			});

			// Edge from sliding window to this extractor
			const edgeColor =
				extractor.type === "profile"
					? "#9c27b0"
					: extractor.type === "feedback"
						? "#ff9800"
						: "#588157";

			// Generate edge label based on trigger conditions
			let edgeLabel = "";
			if (extractor.type === "profile") {
				const profileConfig = extractor.config as ProfileExtractorConfig;
				if (
					profileConfig.request_sources_enabled &&
					profileConfig.request_sources_enabled.length > 0
				) {
					edgeLabel = `Sources: ${profileConfig.request_sources_enabled.join(", ")}`;
				} else {
					edgeLabel = "All Sources";
				}
			} else if (extractor.type === "feedback") {
				edgeLabel = "Always Active";
			} else if (extractor.type === "success") {
				const successConfig = extractor.config as AgentSuccessConfig;
				const samplingRate = successConfig.sampling_rate ?? 1.0;
				if (samplingRate < 1.0) {
					edgeLabel = `Sample: ${Math.round(samplingRate * 100)}%`;
				} else {
					edgeLabel = "Full Evaluation";
				}
			}

			generatedEdges.push({
				id: `e-window-${extractor.id}`,
				source: "window",
				target: extractor.id,
				type: "default",
				animated: false,
				style: { stroke: edgeColor, strokeWidth: 3 },
				markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
				label: edgeLabel,
				labelStyle: {
					fontSize: 12,
					fontWeight: 700,
					fill: "#1d3557",
				},
				labelBgStyle: {
					fill: "white",
					fillOpacity: 0.95,
					stroke: edgeColor,
					strokeWidth: 2,
				},
				labelBgPadding: [10, 14] as [number, number],
				labelBgBorderRadius: 6,
				labelShowBg: true,
			});

			// Create aggregator node for feedback extractors
			if (extractor.type === "feedback") {
				const feedbackConfig = extractor.config as AgentFeedbackConfig;
				const aggregatorId = `aggregator-${extractor.id}`;
				const minThreshold =
					feedbackConfig.feedback_aggregator_config?.min_feedback_threshold ??
					2;
				const refreshCount =
					feedbackConfig.feedback_aggregator_config?.refresh_count ?? 2;

				// Create aggregator node positioned lower than the extractor for better edge visibility
				const aggregatorY = y + 80; // Offset downward by 80px
				generatedNodes.push({
					id: aggregatorId,
					type: "aggregatorNode",
					position: { x: aggregatorX, y: aggregatorY },
					data: {
						label: `${extractor.name} Aggregator`,
						feedbackName: extractor.name,
						minFeedbackThreshold: minThreshold,
						refreshCount: refreshCount,
						tableName: "aggregated_feedbacks",
					},
				});

				// Edge from feedback extractor to aggregator - curved connection
				generatedEdges.push({
					id: `e-${extractor.id}-${aggregatorId}`,
					source: extractor.id,
					target: aggregatorId,
					type: "default",
					animated: false,
					style: { stroke: edgeColor, strokeWidth: 3 },
					markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
					label: `Min: ${minThreshold} | Cluster: ${refreshCount}`,
					labelStyle: {
						fontSize: 12,
						fontWeight: 700,
						fill: "#1d3557",
					},
					labelBgStyle: {
						fill: "white",
						fillOpacity: 0.95,
						stroke: edgeColor,
						strokeWidth: 2,
					},
					labelBgPadding: [10, 14] as [number, number],
					labelBgBorderRadius: 6,
					labelShowBg: true,
				});

				// Also add edge from feedback extractor directly to storage for raw feedback
				// Use custom edge type with label positioned closer to source
				generatedEdges.push({
					id: `e-${extractor.id}-storage-raw`,
					source: extractor.id,
					target: "storage",
					type: "customStorage",
					style: { stroke: "#d84315", strokeWidth: 2.5 },
					markerEnd: { type: MarkerType.ArrowClosed, color: "#d84315" },
					label: `Raw: ${extractor.tableName}`,
					data: {
						labelStyle: {
							fontSize: 12,
							fontWeight: 700,
							fill: "#1d3557",
						},
						labelBgStyle: {
							fill: "white",
							fillOpacity: 0.95,
							stroke: "#d84315",
							strokeWidth: 2,
						},
					},
				});
			}
		});

		// 4. Storage Node (rightmost) - positioned to the right
		generatedNodes.push({
			id: "storage",
			type: "storageNode",
			position: { x: storageX, y: centerY - 80 },
			data: {
				label: "Supabase Storage",
				storageType: config.storage_config.type,
			},
		});

		// Connect aggregators and non-feedback extractors to storage
		allExtractors.forEach((extractor, idx) => {
			const edgeColor =
				extractor.type === "profile"
					? "#9c27b0"
					: extractor.type === "feedback"
						? "#ff9800"
						: "#588157";

			// Calculate y position for this extractor (same as in the loop above)
			const extractorY = startY + idx * verticalNodeSpacing;

			if (extractor.type === "feedback") {
				// For feedback extractors, connect the aggregator to storage
				// (raw feedback to storage edge is already created above)
				const aggregatorId = `aggregator-${extractor.id}`;
				const _aggregatorY = extractorY + 80; // Same offset as when creating the aggregator node
				generatedEdges.push({
					id: `e-${aggregatorId}-storage`,
					source: aggregatorId,
					target: "storage",
					type: "customStorage",
					style: { stroke: edgeColor, strokeWidth: 3 },
					markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
					label: "aggregated_feedbacks",
					data: {
						labelStyle: {
							fontSize: 12,
							fontWeight: 700,
							fill: "#1d3557",
						},
						labelBgStyle: {
							fill: "white",
							fillOpacity: 0.95,
							stroke: edgeColor,
							strokeWidth: 2,
						},
					},
				});
			} else {
				// For profile and success extractors, connect directly to storage
				generatedEdges.push({
					id: `e-${extractor.id}-storage`,
					source: extractor.id,
					target: "storage",
					type: "customStorage",
					style: { stroke: edgeColor, strokeWidth: 2.5 },
					markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
					label: extractor.tableName,
					data: {
						labelStyle: {
							fontSize: 12,
							fontWeight: 700,
							fill: "#1d3557",
						},
						labelBgStyle: {
							fill: "white",
							fillOpacity: 0.95,
							stroke: edgeColor,
							strokeWidth: 2,
						},
					},
				});
			}
		});

		// If no extractors, add a placeholder message
		if (totalExtractors === 0) {
			generatedNodes.push({
				id: "no-extractors",
				type: "default",
				position: { x: extractorX, y: centerY - 50 },
				data: {
					label:
						"No extractors configured\nAdd extractors in the Extractor Settings tab",
				},
				style: {
					background: "#f1faee",
					border: "2px dashed #457b9d",
					borderRadius: 16,
					padding: 20,
					textAlign: "center",
					color: "#457b9d",
					fontSize: 14,
					fontWeight: 500,
					whiteSpace: "pre-line",
					width: 300,
				},
			});
		}

		return { nodes: generatedNodes, edges: generatedEdges };
	}, [config]);

	// Calculate dynamic height based on content (horizontal layout)
	const calculatedHeight = useMemo(() => {
		const totalExtractors =
			config.profile_extractor_configs.length +
			config.agent_feedback_configs.length +
			config.agent_success_configs.length;

		// Base height + additional height for each extractor vertically
		const baseHeight = 600;
		const verticalNodeSpacing = 200;
		const additionalHeight =
			totalExtractors > 0 ? totalExtractors * verticalNodeSpacing : 0;

		return Math.min(baseHeight + additionalHeight, 1600); // Cap at 1600px for vertical space
	}, [config]);

	return (
		<div
			className="w-full border-2 border-gray-200 rounded-2xl bg-gradient-to-br from-[#f1faee] to-[#e8f4f8] shadow-xl"
			style={{ height: `${calculatedHeight}px` }}
		>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				nodeTypes={nodeTypes}
				edgeTypes={edgeTypes}
				fitView
				minZoom={0.2}
				maxZoom={1.5}
				defaultEdgeOptions={{
					type: "default",
				}}
				proOptions={{ hideAttribution: true }}
			>
				<Controls className="!bg-white !border-2 !border-gray-300 !rounded-xl !shadow-lg" />
				<Background
					variant={BackgroundVariant.Dots}
					gap={20}
					size={1.5}
					color="#457b9d"
					style={{ opacity: 0.3 }}
				/>
			</ReactFlow>
		</div>
	);
}

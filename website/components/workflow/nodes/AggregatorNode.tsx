import { Handle, Position } from "@xyflow/react";
import { Database, Info } from "lucide-react";
import { useRef, useState } from "react";
import { Tooltip } from "../Tooltip";

interface AggregatorNodeProps {
	data: {
		label: string;
		feedbackName: string;
		minFeedbackThreshold: number;
		refreshCount: number;
		tableName: string;
	};
}

const colors = {
	bg: "#fff8e1",
	border: "#f57c00",
	text: "#e65100",
	glow: "rgba(245, 124, 0, 0.2)",
};

export function AggregatorNode({ data }: AggregatorNodeProps) {
	const [showTooltip, setShowTooltip] = useState(false);
	const nodeRef = useRef<HTMLDivElement>(null);

	return (
		<>
			<div className="relative group" ref={nodeRef}>
				<div
					className="px-5 py-4 rounded-xl border-2 shadow-lg hover:shadow-xl transition-all duration-300 min-w-[220px] max-w-[280px]"
					style={{
						backgroundColor: colors.bg,
						borderColor: colors.border,
						boxShadow: `0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06), 0 0 0 3px ${colors.glow}`,
					}}
					onMouseEnter={() => setShowTooltip(true)}
					onMouseLeave={() => setShowTooltip(false)}
				>
					<Handle
						type="target"
						position={Position.Left}
						className="!w-3 !h-3 !border-2"
						style={{ backgroundColor: colors.border, borderColor: "white" }}
					/>

					<div className="space-y-2">
						{/* Type Badge */}
						<div
							className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide"
							style={{
								backgroundColor: colors.border,
								color: "white",
							}}
						>
							<Database className="h-3 w-3" />
							Feedback Aggregator
						</div>

						{/* Aggregator Name */}
						<div className="font-semibold text-sm" style={{ color: colors.text }}>
							{data.feedbackName}
						</div>

						{/* Table Destination */}
						<div className="flex items-center gap-1.5 text-xs" style={{ color: colors.text }}>
							<div
								className="w-1.5 h-1.5 rounded-full"
								style={{ backgroundColor: colors.border }}
							></div>
							<span className="font-medium">→ {data.tableName}</span>
						</div>

						{/* Info Button */}
						<button
							className="flex items-center gap-1 text-xs mt-2 opacity-70 hover:opacity-100 transition-opacity"
							style={{ color: colors.text }}
						>
							<Info className="h-3.5 w-3.5" />
							<span>View details</span>
						</button>
					</div>

					<Handle
						type="source"
						position={Position.Right}
						className="!w-3 !h-3 !border-2"
						style={{ backgroundColor: colors.border, borderColor: "white" }}
					/>
				</div>
			</div>

			{/* Enhanced Tooltip with Portal */}
			<Tooltip
				isVisible={showTooltip}
				anchorRef={nodeRef}
				borderColor={colors.border}
				onMouseEnter={() => setShowTooltip(true)}
				onMouseLeave={() => setShowTooltip(false)}
			>
				{/* Header */}
				<div className="mb-4 pb-3 border-b-2" style={{ borderColor: colors.border }}>
					<div className="font-bold text-base mb-1" style={{ color: colors.text }}>
						{data.feedbackName} - Aggregator
					</div>
					<div className="text-xs text-gray-600">
						Saves aggregated feedback to:{" "}
						<span className="font-semibold" style={{ color: colors.text }}>
							{data.tableName}
						</span>
					</div>
				</div>

				{/* Configuration Details */}
				<div className="space-y-3">
					<div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
						<div className="font-semibold mb-2" style={{ color: colors.text }}>
							⚙️ Aggregation Configuration
						</div>
						<div className="space-y-2 text-sm text-gray-700">
							<div className="flex justify-between">
								<span className="font-medium">Min Feedback Threshold:</span>
								<span className="font-semibold" style={{ color: colors.text }}>
									{data.minFeedbackThreshold}
								</span>
							</div>
							<div className="text-xs text-gray-600">
								Minimum number of feedbacks required per cluster
							</div>
						</div>
					</div>

					<div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
						<div className="space-y-2 text-sm text-gray-700">
							<div className="flex justify-between">
								<span className="font-medium">Refresh Count:</span>
								<span className="font-semibold" style={{ color: colors.text }}>
									{data.refreshCount}
								</span>
							</div>
							<div className="text-xs text-gray-600">
								Number of new feedbacks to trigger re-aggregation
							</div>
						</div>
					</div>
				</div>
			</Tooltip>
		</>
	);
}

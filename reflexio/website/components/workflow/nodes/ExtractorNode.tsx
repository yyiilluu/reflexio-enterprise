import { Handle, Position } from "@xyflow/react";
import { Info } from "lucide-react";
import { useRef, useState } from "react";
import { Tooltip } from "../Tooltip";

interface ExtractorNodeProps {
	data: {
		label: string;
		type: "profile" | "feedback" | "success";
		name?: string;
		prompt?: string;
		metadata?: string;
		samplingRate?: number;
		tableName: string;
	};
}

const getColorByType = (type: string) => {
	switch (type) {
		case "profile":
			return {
				bg: "#f3e5f5",
				border: "#9c27b0",
				text: "#4a148c",
				glow: "rgba(156, 39, 176, 0.2)",
			};
		case "feedback":
			return {
				bg: "#fff3e0",
				border: "#ff9800",
				text: "#e65100",
				glow: "rgba(255, 152, 0, 0.2)",
			};
		case "success":
			return {
				bg: "#e8f5e9",
				border: "#588157",
				text: "#1b5e20",
				glow: "rgba(88, 129, 87, 0.2)",
			};
		default:
			return {
				bg: "#f1faee",
				border: "#457b9d",
				text: "#1d3557",
				glow: "rgba(69, 123, 157, 0.2)",
			};
	}
};

const getTypeLabel = (type: string) => {
	switch (type) {
		case "profile":
			return "Profile Extractor";
		case "feedback":
			return "Feedback Extractor";
		case "success":
			return "Success Evaluator";
		default:
			return "Extractor";
	}
};

export function ExtractorNode({ data }: ExtractorNodeProps) {
	const [showTooltip, setShowTooltip] = useState(false);
	const nodeRef = useRef<HTMLDivElement>(null);
	const colors = getColorByType(data.type);

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
							{getTypeLabel(data.type)}
						</div>

						{/* Extractor Name */}
						{data.name && (
							<div className="font-semibold text-sm" style={{ color: colors.text }}>
								{data.name}
							</div>
						)}

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
						{data.name || getTypeLabel(data.type)}
					</div>
					<div className="text-xs text-gray-600">
						Saves to:{" "}
						<span className="font-semibold" style={{ color: colors.text }}>
							{data.tableName}
						</span>
					</div>
				</div>

				{/* Prompt */}
				{data.prompt && (
					<div className="mb-4">
						<div className="font-semibold mb-2" style={{ color: colors.text }}>
							📝 Definition Prompt
						</div>
						<div className="p-3 bg-gray-50 rounded-lg border border-gray-200 text-gray-700 leading-relaxed">
							{data.prompt.length > 300 ? `${data.prompt.substring(0, 300)}...` : data.prompt}
						</div>
					</div>
				)}

				{/* Metadata */}
				{data.metadata && (
					<div className="mb-4">
						<div className="font-semibold mb-2" style={{ color: colors.text }}>
							🏷️ Metadata Definition
						</div>
						<div className="p-3 bg-gray-50 rounded-lg border border-gray-200 text-gray-700 leading-relaxed">
							{data.metadata.length > 200 ? `${data.metadata.substring(0, 200)}...` : data.metadata}
						</div>
					</div>
				)}

				{/* Sampling Rate */}
				{data.samplingRate !== undefined && (
					<div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
						<span className="font-semibold" style={{ color: colors.text }}>
							📊 Sampling Rate:
						</span>
						<span className="text-gray-700 font-medium">
							{(data.samplingRate * 100).toFixed(0)}%
						</span>
					</div>
				)}
			</Tooltip>
		</>
	);
}

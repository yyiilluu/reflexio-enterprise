import { Handle, Position } from "@xyflow/react";
import { ChevronDown, ChevronUp, Database } from "lucide-react";
import { useRef, useState } from "react";
import { Tooltip } from "../Tooltip";

interface StorageNodeProps {
	data: {
		label: string;
		storageType: string;
	};
}

const tables = [
	{
		name: "profiles",
		description: "User profile data extracted from interactions",
		icon: "👤",
		color: "#9c27b0",
	},
	{
		name: "interactions",
		description: "Raw user interactions and request data",
		icon: "💬",
		color: "#457b9d",
	},
	{
		name: "feedbacks",
		description: "Agent feedback and improvement suggestions",
		icon: "📝",
		color: "#ff9800",
	},
	{
		name: "agent_success_results",
		description: "Agent performance evaluation results",
		icon: "✅",
		color: "#588157",
	},
	{
		name: "requests",
		description: "Request metadata and grouping information",
		icon: "📨",
		color: "#a8dadc",
	},
];

export function StorageNode({ data }: StorageNodeProps) {
	const [expanded, setExpanded] = useState(false);
	const nodeRef = useRef<HTMLDivElement>(null);

	return (
		<>
			<div className="relative" ref={nodeRef}>
				<div className="px-8 py-6 rounded-2xl border-3 shadow-xl bg-gradient-to-br from-[#588157] to-[#3d5a3d] border-[#3d5a3d] min-w-[300px]">
					<Handle
						type="target"
						position={Position.Left}
						className="!w-4 !h-4 !border-2 !border-white"
						style={{ backgroundColor: "#588157" }}
					/>

					<div className="flex flex-col items-center gap-3">
						<div className="p-3 bg-white/90 rounded-xl shadow-md">
							<Database className="h-8 w-8 text-[#588157]" />
						</div>

						<div className="text-center">
							<div className="font-bold text-lg text-white drop-shadow-md mb-1">
								{data.label}
							</div>
							<div className="bg-white/90 px-4 py-1.5 rounded-full shadow-sm">
								<span className="text-xs font-semibold text-gray-600">
									Type:
								</span>
								<span className="text-xs font-bold text-[#588157] ml-1 uppercase">
									{data.storageType}
								</span>
							</div>
						</div>

						<button
							onClick={() => setExpanded(!expanded)}
							onMouseEnter={() => setExpanded(true)}
							className="flex items-center gap-1.5 text-xs text-white/90 hover:text-white transition-colors bg-white/20 px-4 py-2 rounded-full shadow-md hover:shadow-lg"
						>
							<span className="font-semibold">View {tables.length} Tables</span>
							{expanded ? (
								<ChevronUp className="h-3.5 w-3.5" />
							) : (
								<ChevronDown className="h-3.5 w-3.5" />
							)}
						</button>
					</div>
				</div>
			</div>

			{/* Tooltip with Portal */}
			<Tooltip
				isVisible={expanded}
				anchorRef={nodeRef}
				borderColor="#588157"
				onMouseEnter={() => setExpanded(true)}
				onMouseLeave={() => setExpanded(false)}
			>
				<div className="font-bold text-lg mb-4 text-[#588157] flex items-center gap-2">
					<Database className="h-5 w-5" />
					Database Tables
				</div>
				<div className="space-y-3">
					{tables.map((table) => (
						<div
							key={table.name}
							className="p-4 bg-gradient-to-r from-gray-50 to-white rounded-lg border-l-4 shadow-sm hover:shadow-md transition-shadow"
							style={{ borderLeftColor: table.color }}
						>
							<div className="flex items-start gap-3">
								<div className="text-2xl">{table.icon}</div>
								<div className="flex-1">
									<div className="font-bold text-gray-800 mb-1">
										{table.name}
									</div>
									<div className="text-xs text-gray-600 leading-relaxed">
										{table.description}
									</div>
								</div>
							</div>
						</div>
					))}
				</div>
				<div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
					<div className="text-xs text-gray-700">
						<strong>Storage Type:</strong> {data.storageType}
					</div>
				</div>
			</Tooltip>
		</>
	);
}

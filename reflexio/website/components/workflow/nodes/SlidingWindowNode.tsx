import { Handle, Position } from "@xyflow/react";
import { Grid3x3, Info } from "lucide-react";
import { useRef, useState } from "react";
import { Tooltip } from "../Tooltip";

interface SlidingWindowNodeProps {
	data: {
		label: string;
		windowSize?: number;
		windowStride?: number;
	};
}

export function SlidingWindowNode({ data }: SlidingWindowNodeProps) {
	const [showTooltip, setShowTooltip] = useState(false);
	const nodeRef = useRef<HTMLDivElement>(null);

	// Get window parameters with defaults
	const windowSize = data.windowSize || 5;
	const windowStride = data.windowStride || 3;

	return (
		<>
			<div className="relative" ref={nodeRef}>
				<div
					className="px-8 py-6 rounded-2xl border-3 shadow-xl bg-gradient-to-br from-[#ffb703] to-[#fb8500] border-[#fb8500] min-w-[320px]"
					onMouseEnter={() => setShowTooltip(true)}
					onMouseLeave={() => setShowTooltip(false)}
				>
					<Handle
						type="target"
						position={Position.Left}
						className="!w-4 !h-4 !border-2 !border-white"
						style={{ backgroundColor: "#fb8500" }}
					/>

					<div className="flex flex-col items-center gap-3">
						<div className="p-3 bg-white/90 rounded-xl shadow-md">
							<Grid3x3 className="h-8 w-8 text-[#fb8500]" />
						</div>

						<div className="text-center">
							<div className="font-bold text-lg text-white drop-shadow-md mb-2">
								{data.label}
							</div>

							<div className="flex items-center justify-center gap-4">
								<div className="bg-white/90 px-4 py-2 rounded-lg shadow-md">
									<div className="text-xs text-gray-600 font-semibold">
										Window Size
									</div>
									<div className="text-lg font-bold text-[#fb8500]">
										{data.windowSize || "—"}
									</div>
								</div>

								<div className="bg-white/90 px-4 py-2 rounded-lg shadow-md">
									<div className="text-xs text-gray-600 font-semibold">
										Stride
									</div>
									<div className="text-lg font-bold text-[#fb8500]">
										{data.windowStride || "—"}
									</div>
								</div>
							</div>
						</div>

						{/* Static Sliding Window Visualization */}
						<div className="bg-white/90 px-4 py-3 rounded-lg shadow-md w-full">
							<div className="mb-3 space-y-1">
								<p className="text-xs text-gray-600">
									<strong className="text-[#fb8500]">
										Window Size ({windowSize}):
									</strong>{" "}
									Number of interactions processed in each batch
								</p>
								<p className="text-xs text-gray-600">
									<strong className="text-[#fb8500]">
										Stride ({windowStride}):
									</strong>{" "}
									Distance between start of consecutive windows
								</p>
							</div>
							<svg
								width="100%"
								height="110"
								viewBox="0 0 280 110"
								className="overflow-visible"
							>
								{(() => {
									// Scaling to fit visualization
									const timelineStart = 20;
									const maxTimelineWidth = 240;

									// Calculate scale factor to fit both windows plus gap/overlap
									const totalSpan = windowStride + windowSize;
									const scale = Math.min(maxTimelineWidth / totalSpan, 12);

									// Calculate actual pixel dimensions
									const scaledWindowSize = windowSize * scale;
									const scaledStride = windowStride * scale;

									// Position windows
									const window1Start = timelineStart;
									const _window1End = window1Start + scaledWindowSize;
									const window2Start = window1Start + scaledStride;
									const window2End = window2Start + scaledWindowSize;

									// Determine relationship
									let relationship = "";
									if (windowSize > windowStride) {
										const overlap = windowSize - windowStride;
										relationship = `Overlap: ${overlap} interactions`;
									} else if (windowSize === windowStride) {
										relationship = "No gap, no overlap";
									} else {
										const gap = windowStride - windowSize;
										relationship = `Gap: ${gap} interactions`;
									}

									// Draw timeline to cover both windows
									const timelineEnd = Math.max(
										window2End + 20,
										timelineStart + maxTimelineWidth * 0.7,
									);

									return (
										<>
											{/* Timeline */}
											<line
												x1={timelineStart}
												y1="55"
												x2={timelineEnd}
												y2="55"
												stroke="#457b9d"
												strokeWidth="2"
												strokeLinecap="round"
											/>

											{/* Data points along timeline */}
											{[
												...Array(
													Math.floor((timelineEnd - timelineStart) / 12) + 1,
												),
											].map((_, i) => (
												<circle
													key={`dot-${i}`}
													cx={timelineStart + i * 12}
													cy="55"
													r="2"
													fill="#457b9d"
													opacity="0.4"
												/>
											))}

											{/* Window 1 */}
											<rect
												x={window1Start}
												y="30"
												width={scaledWindowSize}
												height="50"
												fill="#ffb703"
												stroke="#fb8500"
												strokeWidth="2.5"
												rx="6"
												opacity="0.7"
											/>
											<text
												x={window1Start + scaledWindowSize / 2}
												y="22"
												fontSize="11"
												fill="#fb8500"
												fontWeight="700"
												textAnchor="middle"
											>
												W1
											</text>

											{/* Window 2 */}
											<rect
												x={window2Start}
												y="30"
												width={scaledWindowSize}
												height="50"
												fill="#ffb703"
												stroke="#fb8500"
												strokeWidth="2.5"
												rx="6"
												opacity="0.7"
											/>
											<text
												x={window2Start + scaledWindowSize / 2}
												y="22"
												fontSize="11"
												fill="#fb8500"
												fontWeight="700"
												textAnchor="middle"
											>
												W2
											</text>

											{/* Annotations */}
											{/* Stride arrow */}
											<line
												x1={window1Start}
												y1="92"
												x2={window2Start}
												y2="92"
												stroke="#1d3557"
												strokeWidth="1.5"
												markerEnd="url(#arrowhead)"
											/>
											<text
												x={(window1Start + window2Start) / 2}
												y="88"
												fontSize="9"
												fill="#1d3557"
												fontWeight="600"
												textAnchor="middle"
											>
												Stride: {windowStride}
											</text>

											{/* Arrow marker definition */}
											<defs>
												<marker
													id="arrowhead"
													markerWidth="10"
													markerHeight="10"
													refX="9"
													refY="3"
													orient="auto"
												>
													<polygon points="0 0, 10 3, 0 6" fill="#1d3557" />
												</marker>
											</defs>

											{/* Relationship label */}
											<text
												x="20"
												y="106"
												fontSize="9"
												fill="#666"
												fontWeight="600"
											>
												{relationship}
											</text>
											<text x="160" y="106" fontSize="8" fill="#999">
												(scaled for illustration)
											</text>
										</>
									);
								})()}
							</svg>
						</div>

						<button className="flex items-center gap-1.5 text-xs text-white/90 hover:text-white transition-colors bg-white/20 px-3 py-1.5 rounded-full">
							<Info className="h-3.5 w-3.5" />
							<span>How it works</span>
						</button>
					</div>

					<Handle
						type="source"
						position={Position.Right}
						className="!w-4 !h-4 !border-2 !border-white"
						style={{ backgroundColor: "#fb8500" }}
					/>
				</div>
			</div>

			{/* Tooltip with Portal */}
			<Tooltip
				isVisible={showTooltip}
				anchorRef={nodeRef}
				borderColor="#fb8500"
				onMouseEnter={() => setShowTooltip(true)}
				onMouseLeave={() => setShowTooltip(false)}
			>
				<div className="font-bold text-base mb-2 text-[#fb8500]">
					🔄 Sliding Window Processing
				</div>
				<div className="space-y-2 text-gray-700 leading-relaxed">
					<p>
						<strong>Window Size:</strong> Maximum number of interactions to
						process in one batch.
					</p>
					<p>
						<strong>Stride:</strong> Number of new interactions needed before
						triggering extraction.
					</p>
					<p className="pt-2 border-t border-gray-200 text-xs">
						When new interaction count ≥ stride, all extractors are triggered to
						process the batch.
					</p>
				</div>
			</Tooltip>
		</>
	);
}

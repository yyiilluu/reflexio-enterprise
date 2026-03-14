import {
	BaseEdge,
	EdgeLabelRenderer,
	type EdgeProps,
	getBezierPath,
	Position,
} from "@xyflow/react";

// Calculate a point on a cubic Bezier curve at parameter t (0 to 1)
function getPointOnBezier(
	sourceX: number,
	sourceY: number,
	targetX: number,
	targetY: number,
	sourcePosition: Position,
	targetPosition: Position,
	t: number,
) {
	// Calculate control points for the Bezier curve
	const distance = Math.sqrt(
		(targetX - sourceX) ** 2 + (targetY - sourceY) ** 2,
	);
	const offset = distance * 0.25;

	let cp1x = sourceX;
	let cp1y = sourceY;
	let cp2x = targetX;
	let cp2y = targetY;

	if (sourcePosition === Position.Right) cp1x += offset;
	if (sourcePosition === Position.Left) cp1x -= offset;
	if (sourcePosition === Position.Top) cp1y -= offset;
	if (sourcePosition === Position.Bottom) cp1y += offset;

	if (targetPosition === Position.Right) cp2x += offset;
	if (targetPosition === Position.Left) cp2x -= offset;
	if (targetPosition === Position.Top) cp2y -= offset;
	if (targetPosition === Position.Bottom) cp2y += offset;

	// Cubic Bezier formula: B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
	const mt = 1 - t;
	const mt2 = mt * mt;
	const mt3 = mt2 * mt;
	const t2 = t * t;
	const t3 = t2 * t;

	const x =
		mt3 * sourceX + 3 * mt2 * t * cp1x + 3 * mt * t2 * cp2x + t3 * targetX;
	const y =
		mt3 * sourceY + 3 * mt2 * t * cp1y + 3 * mt * t2 * cp2y + t3 * targetY;

	return { x, y };
}

export default function CustomStorageEdge({
	id,
	sourceX,
	sourceY,
	targetX,
	targetY,
	sourcePosition,
	targetPosition,
	style = {},
	markerEnd,
	label,
	data,
}: EdgeProps) {
	const [edgePath] = getBezierPath({
		sourceX,
		sourceY,
		sourcePosition,
		targetX,
		targetY,
		targetPosition,
	});

	// Calculate position at 25% along the Bezier curve
	const labelPos = getPointOnBezier(
		sourceX,
		sourceY,
		targetX,
		targetY,
		sourcePosition,
		targetPosition,
		0.25,
	);

	const labelStyle = (
		data as {
			labelStyle?: { fontSize: number; fontWeight: number; fill: string };
		}
	)?.labelStyle || {
		fontSize: 12,
		fontWeight: 700,
		fill: "#1d3557",
	};

	const labelBgStyle = (
		data as {
			labelBgStyle?: {
				fill: string;
				fillOpacity: number;
				stroke: string;
				strokeWidth: number;
			};
		}
	)?.labelBgStyle || {
		fill: "white",
		fillOpacity: 0.95,
		stroke: (style.stroke as string) || "#457b9d",
		strokeWidth: 2,
	};

	return (
		<>
			<BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
			<EdgeLabelRenderer>
				<div
					style={{
						position: "absolute",
						transform: `translate(-50%, -50%) translate(${labelPos.x}px,${labelPos.y}px)`,
						fontSize: labelStyle.fontSize,
						fontWeight: labelStyle.fontWeight,
						color: labelStyle.fill,
						background: labelBgStyle.fill,
						padding: "10px 14px",
						borderRadius: 6,
						border: `${labelBgStyle.strokeWidth}px solid ${labelBgStyle.stroke}`,
						pointerEvents: "all",
						zIndex: 1000,
					}}
					className="nodrag nopan"
				>
					{label}
				</div>
			</EdgeLabelRenderer>
		</>
	);
}

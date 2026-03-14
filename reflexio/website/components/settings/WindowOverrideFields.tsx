"use client";

import { Input } from "@/components/ui/input";
import { FieldLabel } from "./FieldLabel";

interface WindowOverrideFieldsProps {
	windowSize?: number;
	windowStride?: number;
	onWindowSizeChange: (value: number | undefined) => void;
	onWindowStrideChange: (value: number | undefined) => void;
}

export function WindowOverrideFields({
	windowSize,
	windowStride,
	onWindowSizeChange,
	onWindowStrideChange,
}: WindowOverrideFieldsProps) {
	return (
		<div>
			<FieldLabel tooltip="Override the global extraction window settings for this item. Leave empty to use global settings.">
				Extraction Window Overrides (Optional)
			</FieldLabel>
			<div className="grid gap-4 sm:grid-cols-2 mt-1">
				<div>
					<label className="text-sm font-medium mb-2 block">
						Window Size Override
					</label>
					<Input
						type="number"
						min="1"
						value={windowSize ?? ""}
						onChange={(e) =>
							onWindowSizeChange(
								e.target.value ? parseInt(e.target.value, 10) : undefined,
							)
						}
						placeholder="Use global setting"
						className="h-10 text-sm"
					/>
				</div>
				<div>
					<label className="text-sm font-medium mb-2 block">
						Window Stride Override
					</label>
					<Input
						type="number"
						min="1"
						value={windowStride ?? ""}
						onChange={(e) =>
							onWindowStrideChange(
								e.target.value ? parseInt(e.target.value, 10) : undefined,
							)
						}
						placeholder="Use global setting"
						className="h-10 text-sm"
					/>
				</div>
			</div>
		</div>
	);
}

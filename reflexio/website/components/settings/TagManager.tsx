"use client";

import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface TagManagerProps {
	tags: string[];
	onAdd: (tag: string) => void;
	onRemove: (index: number) => void;
	placeholder?: string;
	emptyText?: string;
}

export function TagManager({
	tags,
	onAdd,
	onRemove,
	placeholder = "Add source name (e.g., api, webhook, manual)",
	emptyText = "All sources enabled (default)",
}: TagManagerProps) {
	return (
		<div>
			<div className="flex gap-3 mb-3">
				<Input
					placeholder={placeholder}
					className="h-10 text-sm"
					onKeyDown={(e) => {
						if (e.key === "Enter" && e.currentTarget.value.trim()) {
							onAdd(e.currentTarget.value.trim());
							e.currentTarget.value = "";
						}
					}}
				/>
				<Button
					variant="outline"
					size="sm"
					onClick={(e) => {
						const input = e.currentTarget
							.previousElementSibling as HTMLInputElement;
						if (input?.value.trim()) {
							onAdd(input.value.trim());
							input.value = "";
						}
					}}
					className="h-10 w-10 p-0"
					aria-label="Add tag"
				>
					<Plus className="h-4 w-4" />
				</Button>
			</div>
			<div className="flex flex-wrap gap-2">
				{tags.length > 0 ? (
					tags.map((tag, index) => (
						<Badge key={index} variant="secondary" className="text-sm h-7 px-3">
							{tag}
							<button
								onClick={() => onRemove(index)}
								className="ml-2 hover:text-destructive"
								aria-label={`Remove ${tag}`}
							>
								&times;
							</button>
						</Badge>
					))
				) : (
					<p className="text-xs text-muted-foreground italic">{emptyText}</p>
				)}
			</div>
		</div>
	);
}

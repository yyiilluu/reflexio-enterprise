"use client";

import { Brain, Plus, Trash2 } from "lucide-react";
import type { Config, ToolUseConfig } from "@/app/settings/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FieldLabel } from "../FieldLabel";

interface AgentContextSectionProps {
	config: Config;
	onContextChange: (value: string) => void;
	onAddTool: () => void;
	onUpdateTool: (index: number, updates: Partial<ToolUseConfig>) => void;
	onRemoveTool: (index: number) => void;
}

export function AgentContextSection({
	config,
	onContextChange,
	onAddTool,
	onUpdateTool,
	onRemoveTool,
}: AgentContextSectionProps) {
	return (
		<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
			<CardHeader className="pb-4">
				<div className="flex items-center gap-3">
					<Brain className="h-4 w-4 text-slate-400" />
					<div>
						<CardTitle className="text-lg font-semibold text-slate-800">Agent Context</CardTitle>
						<CardDescription className="text-xs mt-1 text-muted-foreground">
							Define agent working environment
						</CardDescription>
					</div>
				</div>
			</CardHeader>
			<CardContent>
				<div>
					<FieldLabel htmlFor="agent-context">Agent Context Prompt</FieldLabel>
					<textarea
						id="agent-context"
						value={config.agent_context_prompt || ""}
						onChange={(e) => onContextChange(e.target.value)}
						className="flex min-h-[200px] w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300 resize-y"
						placeholder="Define agent working environment, tools available, and action space..."
						rows={8}
					/>
					<p className="text-xs text-muted-foreground mt-2">
						Define the agent's working environment and context
					</p>
				</div>

				<div className="mt-6">
					<div className="flex items-center justify-between mb-3">
						<FieldLabel>Available Tools</FieldLabel>
						<Button variant="ghost" size="sm" onClick={onAddTool} className="h-8 text-sm">
							<Plus className="h-4 w-4 mr-1" />
							Add Tool
						</Button>
					</div>
					<p className="text-xs text-muted-foreground mb-3">
						Define tools the agent can use. These are shared across success evaluation and feedback
						extraction.
					</p>
					<div className="space-y-3">
						{config.tool_can_use?.map((tool, toolIndex) => (
							<div
								key={toolIndex}
								className="flex gap-3 items-center p-3 border border-slate-200 rounded-lg bg-slate-50"
							>
								<div className="flex-1 grid grid-cols-2 gap-3">
									<Input
										value={tool.tool_name}
										onChange={(e) => onUpdateTool(toolIndex, { tool_name: e.target.value })}
										placeholder="Tool name"
										className="h-10 text-sm"
									/>
									<Input
										value={tool.tool_description}
										onChange={(e) =>
											onUpdateTool(toolIndex, {
												tool_description: e.target.value,
											})
										}
										placeholder="Description"
										className="h-10 text-sm"
									/>
								</div>
								<Button
									variant="ghost"
									size="sm"
									onClick={() => onRemoveTool(toolIndex)}
									className="h-8 w-8 p-0"
									aria-label="Remove tool"
								>
									<Trash2 className="h-4 w-4 text-destructive" />
								</Button>
							</div>
						))}
					</div>
				</div>
			</CardContent>
		</Card>
	);
}

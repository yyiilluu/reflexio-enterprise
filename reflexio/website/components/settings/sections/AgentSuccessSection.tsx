"use client";

import { CheckCircle, ChevronDown, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { AgentSuccessConfig, Config } from "@/app/settings/types";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { FieldLabel } from "../FieldLabel";
import { WindowOverrideFields } from "../WindowOverrideFields";

interface AgentSuccessSectionProps {
	config: Config;
	onAdd: () => void;
	onUpdate: (id: string, updates: Partial<AgentSuccessConfig>) => void;
	onRemove: (id: string) => void;
}

export function AgentSuccessSection({
	config,
	onAdd,
	onUpdate,
	onRemove,
}: AgentSuccessSectionProps) {
	const [deleteTarget, setDeleteTarget] = useState<{
		id: string;
		name: string;
	} | null>(null);

	const successes = config.agent_success_configs;

	return (
		<>
			<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
				<CardHeader className="pb-4">
					<div className="flex items-center gap-3">
						<CheckCircle className="h-4 w-4 text-slate-400" />
						<div>
							<CardTitle className="flex items-center gap-2 text-lg font-semibold text-slate-800">
								Agent Success Evaluations
								{successes.length > 0 && (
									<Badge className="text-xs bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
										{successes.length}
									</Badge>
								)}
							</CardTitle>
							<CardDescription className="text-xs mt-1 text-muted-foreground">
								Define success criteria
							</CardDescription>
						</div>
					</div>
				</CardHeader>
				<CardContent>
					{successes.length > 0 ? (
						<Accordion
							type="single"
							collapsible
							className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100"
						>
							{successes.map((success) => (
								<AccordionItem key={success.id} value={success.id} className="border-b-0 px-5">
									<div
										className="flex items-center py-3 gap-3 cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg"
										onClick={(e) => {
											const trigger = (e.currentTarget as HTMLElement).querySelector(
												"[data-radix-collection-item]",
											) as HTMLElement;
											if (trigger && !trigger.contains(e.target as Node)) {
												trigger.click();
											}
										}}
									>
										<AccordionTrigger className="hover:no-underline py-0 gap-3 flex-1 min-w-0">
											<span className="text-sm font-semibold text-slate-800 truncate">
												{success.evaluation_name || "Unnamed evaluation"}
											</span>
											<Badge variant="secondary" className="text-xs shrink-0">
												Success
											</Badge>
											{success.sampling_rate !== undefined && success.sampling_rate < 1 && (
												<span className="text-xs text-slate-500 shrink-0">
													{(success.sampling_rate * 100).toFixed(0)}% sampling
												</span>
											)}
										</AccordionTrigger>
										<Button
											variant="ghost"
											size="sm"
											onClick={(e) => {
												e.stopPropagation();
												setDeleteTarget({
													id: success.id,
													name: success.evaluation_name || "Unnamed evaluation",
												});
											}}
											className="h-8 w-8 p-0 shrink-0"
											aria-label={`Delete ${success.evaluation_name}`}
										>
											<Trash2 className="h-4 w-4 text-destructive" />
										</Button>
									</div>
									<AccordionContent className="pt-2 pb-5 space-y-4">
										{/* Primary fields */}
										<div>
											<FieldLabel htmlFor={`suc-name-${success.id}`}>Evaluation Name</FieldLabel>
											<Input
												id={`suc-name-${success.id}`}
												value={success.evaluation_name}
												onChange={(e) =>
													onUpdate(success.id, {
														evaluation_name: e.target.value,
													})
												}
												placeholder="e.g., task_success"
												className="h-10 text-sm"
												aria-required="true"
											/>
										</div>

										<div>
											<FieldLabel htmlFor={`suc-def-${success.id}`}>Success Definition</FieldLabel>
											<textarea
												id={`suc-def-${success.id}`}
												value={success.success_definition_prompt}
												onChange={(e) =>
													onUpdate(success.id, {
														success_definition_prompt: e.target.value,
													})
												}
												className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
												placeholder="Define what success looks like for the agent..."
												rows={6}
												aria-required="true"
											/>
										</div>

										{/* Sampling Rate */}
										<div>
											<FieldLabel tooltip="Percentage of interaction batches to evaluate for success">
												Sampling Rate
											</FieldLabel>
											<div className="grid grid-cols-3 gap-3 items-center">
												<div className="col-span-2">
													<input
														type="range"
														min="0"
														max="100"
														value={((success.sampling_rate ?? 1.0) * 100).toFixed(0)}
														onChange={(e) =>
															onUpdate(success.id, {
																sampling_rate: parseFloat(e.target.value) / 100,
															})
														}
														className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:cursor-pointer"
														aria-label="Sampling rate"
													/>
												</div>
												<div className="relative">
													<Input
														type="number"
														min="0"
														max="100"
														step="1"
														value={((success.sampling_rate ?? 1.0) * 100).toFixed(0)}
														onChange={(e) => {
															const value = parseFloat(e.target.value);
															if (!Number.isNaN(value) && value >= 0 && value <= 100) {
																onUpdate(success.id, {
																	sampling_rate: value / 100,
																});
															}
														}}
														className="h-10 text-sm pr-8"
													/>
													<span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground pointer-events-none">
														%
													</span>
												</div>
											</div>
										</div>

										{/* Advanced options */}
										<Collapsible>
											<CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-800 transition-colors group">
												<ChevronDown className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180" />
												Advanced Options
											</CollapsibleTrigger>
											<CollapsibleContent className="space-y-4 pt-4">
												<div>
													<FieldLabel>Metadata (Optional)</FieldLabel>
													<textarea
														value={success.metadata_definition_prompt || ""}
														onChange={(e) =>
															onUpdate(success.id, {
																metadata_definition_prompt: e.target.value,
															})
														}
														className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
														placeholder="Metadata structure..."
														rows={5}
													/>
												</div>

												<WindowOverrideFields
													windowSize={success.extraction_window_size_override}
													windowStride={success.extraction_window_stride_override}
													onWindowSizeChange={(v) =>
														onUpdate(success.id, {
															extraction_window_size_override: v,
														})
													}
													onWindowStrideChange={(v) =>
														onUpdate(success.id, {
															extraction_window_stride_override: v,
														})
													}
												/>
											</CollapsibleContent>
										</Collapsible>
									</AccordionContent>
								</AccordionItem>
							))}
						</Accordion>
					) : null}

					<Button
						onClick={onAdd}
						variant="outline"
						className={`w-full h-9 text-sm ${successes.length > 0 ? "mt-4" : ""}`}
					>
						<Plus className="h-3.5 w-3.5 mr-2" />
						Add Success Evaluation
					</Button>
				</CardContent>
			</Card>

			<DeleteConfirmDialog
				open={!!deleteTarget}
				onOpenChange={(open) => !open && setDeleteTarget(null)}
				onConfirm={() => {
					if (deleteTarget) {
						onRemove(deleteTarget.id);
						setDeleteTarget(null);
					}
				}}
				title="Delete Success Evaluation"
				description={`Are you sure you want to delete the success evaluation "${deleteTarget?.name}"?`}
				itemDetails={
					deleteTarget && (
						<div className="flex items-center gap-2">
							<Badge variant="secondary" className="text-xs">
								Success
							</Badge>
							<span className="font-medium">{deleteTarget.name}</span>
						</div>
					)
				}
			/>
		</>
	);
}

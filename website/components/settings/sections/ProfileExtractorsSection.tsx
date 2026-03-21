"use client";

import { ChevronDown, Plus, Settings, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Config, ProfileExtractorConfig } from "@/app/settings/types";
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
import { Switch } from "@/components/ui/switch";
import { FieldLabel } from "../FieldLabel";
import { TagManager } from "../TagManager";
import { WindowOverrideFields } from "../WindowOverrideFields";

interface ProfileExtractorsSectionProps {
	config: Config;
	onAdd: () => void;
	onUpdate: (id: string, updates: Partial<ProfileExtractorConfig>) => void;
	onRemove: (id: string) => void;
	onAddRequestSource: (id: string, source: string) => void;
	onRemoveRequestSource: (id: string, sourceIndex: number) => void;
}

export function ProfileExtractorsSection({
	config,
	onAdd,
	onUpdate,
	onRemove,
	onAddRequestSource,
	onRemoveRequestSource,
}: ProfileExtractorsSectionProps) {
	const [deleteTarget, setDeleteTarget] = useState<{
		id: string;
		name: string;
	} | null>(null);

	const extractors = config.profile_extractor_configs;

	return (
		<>
			<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
				<CardHeader className="pb-4">
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-3">
							<Settings className="h-4 w-4 text-slate-400" />
							<div>
								<CardTitle className="flex items-center gap-2 text-lg font-semibold text-slate-800">
									Profile Extractors
									{extractors.length > 0 && (
										<Badge className="text-xs bg-purple-100 text-purple-700 hover:bg-purple-100">
											{extractors.length}
										</Badge>
									)}
								</CardTitle>
								<CardDescription className="text-xs mt-1 text-muted-foreground">
									Define profile extraction rules
								</CardDescription>
							</div>
						</div>
					</div>
				</CardHeader>
				<CardContent>
					{extractors.length > 0 ? (
						<Accordion
							type="single"
							collapsible
							className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100"
						>
							{extractors.map((extractor) => (
								<AccordionItem key={extractor.id} value={extractor.id} className="border-b-0 px-5">
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
												{extractor.extractor_name || "Unnamed extractor"}
											</span>
											<Badge variant="secondary" className="text-xs shrink-0">
												Profile
											</Badge>
										</AccordionTrigger>
										<div
											className="flex items-center gap-1.5 shrink-0"
											onClick={(e) => e.stopPropagation()}
										>
											<span
												className={`text-xs font-medium ${extractor.manual_trigger ? "text-amber-600" : "text-emerald-600"}`}
											>
												{extractor.manual_trigger ? "Manual" : "Auto"}
											</span>
											<Switch
												checked={!extractor.manual_trigger}
												onCheckedChange={(checked) =>
													onUpdate(extractor.id, { manual_trigger: !checked })
												}
												className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-amber-400 scale-75"
												aria-label={`Toggle ${extractor.extractor_name} auto mode`}
											/>
										</div>
										<Button
											variant="ghost"
											size="sm"
											onClick={(e) => {
												e.stopPropagation();
												setDeleteTarget({
													id: extractor.id,
													name: extractor.extractor_name || "Unnamed extractor",
												});
											}}
											className="h-8 w-8 p-0 shrink-0"
											aria-label={`Delete ${extractor.extractor_name}`}
										>
											<Trash2 className="h-4 w-4 text-destructive" />
										</Button>
									</div>
									<AccordionContent className="pt-2 pb-5 space-y-4">
										{/* Primary fields */}
										<div>
											<FieldLabel htmlFor={`ext-name-${extractor.id}`}>Extractor Name</FieldLabel>
											<Input
												id={`ext-name-${extractor.id}`}
												value={extractor.extractor_name}
												onChange={(e) =>
													onUpdate(extractor.id, {
														extractor_name: e.target.value,
													})
												}
												placeholder="e.g., user_preferences"
												className="h-10 text-sm"
												aria-required="true"
											/>
										</div>

										<div>
											<FieldLabel htmlFor={`ext-def-${extractor.id}`}>
												Profile Content Definition
											</FieldLabel>
											<textarea
												id={`ext-def-${extractor.id}`}
												value={extractor.profile_content_definition_prompt}
												onChange={(e) =>
													onUpdate(extractor.id, {
														profile_content_definition_prompt: e.target.value,
													})
												}
												className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
												placeholder="Define what the profile should contain..."
												rows={6}
												aria-required="true"
											/>
										</div>

										{/* Advanced options */}
										<Collapsible>
											<CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-800 transition-colors group">
												<ChevronDown className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180" />
												Advanced Options
											</CollapsibleTrigger>
											<CollapsibleContent className="space-y-4 pt-4">
												<div className="grid gap-4 sm:grid-cols-2">
													<div>
														<FieldLabel>Context (Optional)</FieldLabel>
														<textarea
															value={extractor.context_prompt || ""}
															onChange={(e) =>
																onUpdate(extractor.id, {
																	context_prompt: e.target.value,
																})
															}
															className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
															placeholder="Additional context..."
															rows={5}
														/>
													</div>
													<div>
														<FieldLabel>Metadata (Optional)</FieldLabel>
														<textarea
															value={extractor.metadata_definition_prompt || ""}
															onChange={(e) =>
																onUpdate(extractor.id, {
																	metadata_definition_prompt: e.target.value,
																})
															}
															className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
															placeholder="Metadata structure..."
															rows={5}
														/>
													</div>
												</div>

												<div>
													<FieldLabel>Enabled Request Sources (Optional)</FieldLabel>
													<p className="text-xs text-muted-foreground mb-3">
														Specify which request sources should trigger profile extraction. Leave
														empty to enable all sources.
													</p>
													<TagManager
														tags={extractor.request_sources_enabled || []}
														onAdd={(source) => onAddRequestSource(extractor.id, source)}
														onRemove={(idx) => onRemoveRequestSource(extractor.id, idx)}
													/>
												</div>

												<WindowOverrideFields
													windowSize={extractor.extraction_window_size_override}
													windowStride={extractor.extraction_window_stride_override}
													onWindowSizeChange={(v) =>
														onUpdate(extractor.id, {
															extraction_window_size_override: v,
														})
													}
													onWindowStrideChange={(v) =>
														onUpdate(extractor.id, {
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
						className={`w-full h-9 text-sm ${extractors.length > 0 ? "mt-4" : ""}`}
					>
						<Plus className="h-3.5 w-3.5 mr-2" />
						Add Profile Extractor
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
				title="Delete Profile Extractor"
				description={`Are you sure you want to delete the profile extractor "${deleteTarget?.name}"?`}
				itemDetails={
					deleteTarget && (
						<div className="flex items-center gap-2">
							<Badge variant="secondary" className="text-xs">
								Profile
							</Badge>
							<span className="font-medium">{deleteTarget.name}</span>
						</div>
					)
				}
			/>
		</>
	);
}

"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { MessageSquare, Plus, Trash2, ChevronDown } from "lucide-react"
import { FieldLabel } from "../FieldLabel"
import { TagManager } from "../TagManager"
import { WindowOverrideFields } from "../WindowOverrideFields"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import type { Config, AgentFeedbackConfig } from "@/app/settings/types"

interface AgentFeedbackSectionProps {
  config: Config
  onAdd: () => void
  onUpdate: (id: string, updates: Partial<AgentFeedbackConfig>) => void
  onRemove: (id: string) => void
  onAddRequestSource: (id: string, source: string) => void
  onRemoveRequestSource: (id: string, sourceIndex: number) => void
}

export function AgentFeedbackSection({
  config,
  onAdd,
  onUpdate,
  onRemove,
  onAddRequestSource,
  onRemoveRequestSource,
}: AgentFeedbackSectionProps) {
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)

  const feedbacks = config.agent_feedback_configs

  return (
    <>
      <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <MessageSquare className="h-4 w-4 text-slate-400" />
            <div>
              <CardTitle className="flex items-center gap-2 text-lg font-semibold text-slate-800">
                Agent Feedback
                {feedbacks.length > 0 && (
                  <Badge className="text-xs bg-orange-100 text-orange-700 hover:bg-orange-100">
                    {feedbacks.length}
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-xs mt-1 text-muted-foreground">Configure feedback collection</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {feedbacks.length > 0 ? (
            <Accordion
              type="single"
              collapsible

              className="border border-slate-200 rounded-xl bg-white overflow-hidden divide-y divide-slate-100"
            >
              {feedbacks.map((feedback) => (
                <AccordionItem
                  key={feedback.id}
                  value={feedback.id}
                  className="border-b-0 px-5"
                >
                  <div
                    className="flex items-center py-3 gap-3 cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg"
                    onClick={(e) => {
                      const trigger = (e.currentTarget as HTMLElement).querySelector('[data-radix-collection-item]') as HTMLElement
                      if (trigger && !trigger.contains(e.target as Node)) {
                        trigger.click()
                      }
                    }}
                  >
                    <AccordionTrigger className="hover:no-underline py-0 gap-3 flex-1 min-w-0">
                      <span className="text-sm font-semibold text-slate-800 truncate">
                        {feedback.feedback_name || "Unnamed feedback"}
                      </span>
                      <Badge variant="secondary" className="text-xs shrink-0">
                        Feedback
                      </Badge>
                    </AccordionTrigger>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteTarget({ id: feedback.id, name: feedback.feedback_name || "Unnamed feedback" })
                      }}
                      className="h-8 w-8 p-0 shrink-0"
                      aria-label={`Delete ${feedback.feedback_name}`}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                  <AccordionContent className="pt-2 pb-5 space-y-4">
                    {/* Primary fields */}
                    <div>
                      <FieldLabel htmlFor={`fb-name-${feedback.id}`}>Feedback Name</FieldLabel>
                      <Input
                        id={`fb-name-${feedback.id}`}
                        value={feedback.feedback_name}
                        onChange={(e) => onUpdate(feedback.id, { feedback_name: e.target.value })}
                        placeholder="e.g., task_completion"
                        className="h-10 text-sm"
                        aria-required="true"
                      />
                    </div>

                    <div>
                      <FieldLabel htmlFor={`fb-def-${feedback.id}`}>Feedback Definition</FieldLabel>
                      <textarea
                        id={`fb-def-${feedback.id}`}
                        value={feedback.feedback_definition_prompt}
                        onChange={(e) => onUpdate(feedback.id, { feedback_definition_prompt: e.target.value })}
                        className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
                        placeholder="Define what feedback to collect..."
                        rows={6}
                        aria-required="true"
                      />
                    </div>

                    {/* Aggregator config (always visible since it's important) */}
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <FieldLabel
                          htmlFor={`fb-threshold-${feedback.id}`}
                          tooltip="Minimum number of feedbacks needed before clustering can begin"
                        >
                          Min Feedback Threshold
                        </FieldLabel>
                        <Input
                          id={`fb-threshold-${feedback.id}`}
                          type="number"
                          min="1"
                          value={feedback.feedback_aggregator_config?.min_feedback_threshold || 2}
                          onChange={(e) => onUpdate(feedback.id, {
                            feedback_aggregator_config: {
                              min_feedback_threshold: parseInt(e.target.value) || 2,
                              refresh_count: feedback.feedback_aggregator_config?.refresh_count ?? 2,
                            },
                          })}
                          className="h-10 text-sm"
                        />
                        <p className="text-xs text-muted-foreground mt-1">Min number of feedbacks per cluster</p>
                      </div>
                      <div>
                        <FieldLabel
                          htmlFor={`fb-refresh-${feedback.id}`}
                          tooltip="Number of new feedbacks needed to trigger re-aggregation"
                        >
                          Refresh Count
                        </FieldLabel>
                        <Input
                          id={`fb-refresh-${feedback.id}`}
                          type="number"
                          min="1"
                          value={feedback.feedback_aggregator_config?.refresh_count || 2}
                          onChange={(e) => onUpdate(feedback.id, {
                            feedback_aggregator_config: {
                              min_feedback_threshold: feedback.feedback_aggregator_config?.min_feedback_threshold ?? 2,
                              refresh_count: parseInt(e.target.value) || 2,
                            },
                          })}
                          className="h-10 text-sm"
                        />
                        <p className="text-xs text-muted-foreground mt-1">New feedbacks to trigger feedback aggregation</p>
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
                            value={feedback.metadata_definition_prompt || ""}
                            onChange={(e) => onUpdate(feedback.id, { metadata_definition_prompt: e.target.value })}
                            className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
                            placeholder="Metadata structure..."
                            rows={5}
                          />
                        </div>

                        <div>
                          <FieldLabel>Enabled Request Sources (Optional)</FieldLabel>
                          <p className="text-xs text-muted-foreground mb-3">
                            Specify which request sources should trigger feedback extraction. Leave empty to enable all sources.
                          </p>
                          <TagManager
                            tags={feedback.request_sources_enabled || []}
                            onAdd={(source) => onAddRequestSource(feedback.id, source)}
                            onRemove={(idx) => onRemoveRequestSource(feedback.id, idx)}
                          />
                        </div>

                        <WindowOverrideFields
                          windowSize={feedback.extraction_window_size_override}
                          windowStride={feedback.extraction_window_stride_override}
                          onWindowSizeChange={(v) => onUpdate(feedback.id, { extraction_window_size_override: v })}
                          onWindowStrideChange={(v) => onUpdate(feedback.id, { extraction_window_stride_override: v })}
                        />
                      </CollapsibleContent>
                    </Collapsible>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          ) : null}

          <Button onClick={onAdd} variant="outline" className={`w-full h-9 text-sm ${feedbacks.length > 0 ? "mt-4" : ""}`}>
            <Plus className="h-3.5 w-3.5 mr-2" />
            Add Agent Feedback
          </Button>
        </CardContent>
      </Card>

      <DeleteConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            onRemove(deleteTarget.id)
            setDeleteTarget(null)
          }
        }}
        title="Delete Agent Feedback"
        description={`Are you sure you want to delete the feedback config "${deleteTarget?.name}"?`}
        itemDetails={
          deleteTarget && (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">Feedback</Badge>
              <span className="font-medium">{deleteTarget.name}</span>
            </div>
          )
        }
      />
    </>
  )
}

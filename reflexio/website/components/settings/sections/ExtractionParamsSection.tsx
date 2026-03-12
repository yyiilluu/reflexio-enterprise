"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Sliders } from "lucide-react"
import { FieldLabel } from "../FieldLabel"
import type { Config } from "@/app/settings/types"

interface ExtractionParamsSectionProps {
  config: Config
  onWindowSizeChange: (value: number | undefined) => void
  onWindowStrideChange: (value: number | undefined) => void
}

export function ExtractionParamsSection({
  config,
  onWindowSizeChange,
  onWindowStrideChange,
}: ExtractionParamsSectionProps) {
  return (
    <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <Sliders className="h-4 w-4 text-slate-400" />
          <div>
            <CardTitle className="text-lg font-semibold text-slate-800">Extraction Parameters</CardTitle>
            <CardDescription className="text-xs mt-1 text-muted-foreground">Configure extraction window settings</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <FieldLabel htmlFor="window-size" tooltip="Number of interactions analyzed per extraction batch">
              Window Size
            </FieldLabel>
            <Input
              id="window-size"
              type="number"
              min="1"
              value={config.extraction_window_size ?? ""}
              onChange={(e) => onWindowSizeChange(e.target.value ? parseInt(e.target.value) : undefined)}
              placeholder="10"
            />
            <p className="text-xs text-muted-foreground mt-1">Interactions per window</p>
          </div>

          <div>
            <FieldLabel htmlFor="window-stride" tooltip="Number of interactions to skip between extraction batches">
              Window Stride
            </FieldLabel>
            <Input
              id="window-stride"
              type="number"
              min="1"
              value={config.extraction_window_stride ?? ""}
              onChange={(e) => onWindowStrideChange(e.target.value ? parseInt(e.target.value) : undefined)}
              placeholder="5"
            />
            <p className="text-xs text-muted-foreground mt-1">Skip between windows</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

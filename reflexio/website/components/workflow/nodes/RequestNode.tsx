import React from "react"
import { Handle, Position } from "@xyflow/react"
import { Inbox } from "lucide-react"

interface RequestNodeProps {
  data: {
    label: string
  }
}

export function RequestNode({ data }: RequestNodeProps) {
  return (
    <div className="relative">
      <div className="px-8 py-6 rounded-2xl border-3 shadow-xl bg-gradient-to-br from-[#a8dadc] to-[#85c1c5] border-[#457b9d] min-w-[280px]">
        <div className="flex flex-col items-center gap-3">
          <div className="p-3 bg-white/80 rounded-xl shadow-md">
            <Inbox className="h-8 w-8 text-[#457b9d]" />
          </div>
          <div className="text-center">
            <div className="font-bold text-lg text-[#1d3557] mb-1">{data.label}</div>
            <div className="text-sm text-[#1d3557]/80 font-medium">
              Sessions & Interactions
            </div>
          </div>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          className="!w-4 !h-4 !border-2 !border-white"
          style={{ backgroundColor: "#457b9d" }}
        />
      </div>
    </div>
  )
}

"use client";

import { HelpCircle } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface FieldLabelProps {
	htmlFor?: string;
	children: React.ReactNode;
	tooltip?: string;
	required?: boolean;
	className?: string;
}

export function FieldLabel({ htmlFor, children, tooltip, required, className }: FieldLabelProps) {
	return (
		<div className={`flex items-center gap-1.5 mb-2 ${className ?? ""}`}>
			<Label htmlFor={htmlFor} className="text-sm font-medium text-slate-700">
				{children}
				{required && <span className="text-red-500 ml-0.5">*</span>}
			</Label>
			{tooltip && (
				<TooltipProvider delayDuration={200}>
					<Tooltip>
						<TooltipTrigger asChild>
							<HelpCircle className="h-3.5 w-3.5 text-slate-400 cursor-help" />
						</TooltipTrigger>
						<TooltipContent side="top" className="max-w-[250px]">
							<p className="text-xs">{tooltip}</p>
						</TooltipContent>
					</Tooltip>
				</TooltipProvider>
			)}
		</div>
	);
}

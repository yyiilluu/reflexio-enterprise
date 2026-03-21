"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface PasswordInputProps {
	value: string;
	onChange: (value: string) => void;
	placeholder?: string;
	className?: string;
}

export function PasswordInput({ value, onChange, placeholder, className }: PasswordInputProps) {
	const [visible, setVisible] = useState(false);

	return (
		<div className="relative">
			<Input
				type={visible ? "text" : "password"}
				value={value}
				onChange={(e) => onChange(e.target.value)}
				placeholder={placeholder}
				className={`h-10 pr-10 ${className ?? ""}`}
			/>
			<Button
				type="button"
				variant="ghost"
				size="sm"
				onClick={() => setVisible(!visible)}
				className="absolute right-0 top-0 h-10 w-10 p-0 hover:bg-transparent"
				aria-label={visible ? "Hide value" : "Show value"}
			>
				{visible ? (
					<EyeOff className="h-4 w-4 text-slate-400" />
				) : (
					<Eye className="h-4 w-4 text-slate-400" />
				)}
			</Button>
		</div>
	);
}

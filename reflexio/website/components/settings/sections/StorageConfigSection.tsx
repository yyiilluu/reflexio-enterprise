"use client";

import { Database } from "lucide-react";
import type { Config, StorageConfig, StorageType } from "@/app/settings/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FieldLabel } from "../FieldLabel";
import { PasswordInput } from "../PasswordInput";

interface StorageConfigSectionProps {
	config: Config;
	onStorageUpdate: (updates: Partial<StorageConfig>) => void;
	onStorageTypeChange: (type: StorageType) => void;
}

export function StorageConfigSection({
	config,
	onStorageUpdate,
	onStorageTypeChange,
}: StorageConfigSectionProps) {
	return (
		<Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
			<CardHeader className="pb-4">
				<div className="flex items-center gap-3">
					<Database className="h-4 w-4 text-slate-400" />
					<div>
						<CardTitle className="text-lg font-semibold text-slate-800">
							Storage Configuration
						</CardTitle>
						<CardDescription className="text-xs mt-1 text-muted-foreground">
							Configure data storage backend
						</CardDescription>
					</div>
				</div>
			</CardHeader>
			<CardContent className="space-y-4">
				<div>
					<FieldLabel htmlFor="storage-type">Storage Type</FieldLabel>
					<select
						id="storage-type"
						value={config.storage_config.type}
						onChange={(e) => onStorageTypeChange(e.target.value as StorageType)}
						className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
					>
						<option value="local">Local Storage</option>
						<option value="supabase">Supabase</option>
					</select>
				</div>

				{config.storage_config.type === "local" && (
					<div>
						<FieldLabel htmlFor="dir-path">Directory Path</FieldLabel>
						<Input
							id="dir-path"
							value={config.storage_config.dir_path}
							onChange={(e) => onStorageUpdate({ dir_path: e.target.value })}
							placeholder="/path/to/storage"
						/>
						<p className="text-xs text-muted-foreground mt-1">
							Local directory path for storing data
						</p>
					</div>
				)}

				{config.storage_config.type === "supabase" && (
					<div className="space-y-3">
						<div>
							<FieldLabel htmlFor="supabase-url" required>
								Supabase URL
							</FieldLabel>
							<Input
								id="supabase-url"
								value={config.storage_config.url}
								onChange={(e) => onStorageUpdate({ url: e.target.value })}
								placeholder="https://xxx.supabase.co"
								aria-required="true"
							/>
						</div>
						<div>
							<FieldLabel htmlFor="supabase-key" required>
								Supabase Key
							</FieldLabel>
							<PasswordInput
								value={config.storage_config.key}
								onChange={(value) => onStorageUpdate({ key: value })}
								placeholder="Supabase API Key"
							/>
						</div>
						<div>
							<FieldLabel htmlFor="db-url" required>
								Database URL
							</FieldLabel>
							<Input
								id="db-url"
								value={config.storage_config.db_url}
								onChange={(e) => onStorageUpdate({ db_url: e.target.value })}
								placeholder="postgresql://..."
								aria-required="true"
							/>
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

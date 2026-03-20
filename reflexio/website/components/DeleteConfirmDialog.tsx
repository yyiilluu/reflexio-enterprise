import { AlertCircle, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";

interface DeleteConfirmDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onConfirm: () => void;
	title: string;
	description: string;
	itemDetails?: React.ReactNode;
	loading?: boolean;
	confirmButtonText?: string;
}

export function DeleteConfirmDialog({
	open,
	onOpenChange,
	onConfirm,
	title,
	description,
	itemDetails,
	loading = false,
	confirmButtonText = "Delete",
}: DeleteConfirmDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-[500px]">
				<DialogHeader>
					<div className="flex items-center gap-3 mb-2">
						<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-red-50 to-red-100 flex items-center justify-center flex-shrink-0 border border-red-200">
							<AlertCircle className="h-5 w-5 text-red-500" />
						</div>
						<DialogTitle className="text-xl font-semibold text-slate-800">{title}</DialogTitle>
					</div>
					<DialogDescription className="text-sm text-slate-600 pt-2">
						{description}
					</DialogDescription>
				</DialogHeader>

				{itemDetails && (
					<div className="bg-slate-50 border border-slate-200 rounded-lg p-4 my-2">
						<div className="text-sm space-y-1.5 text-slate-700">{itemDetails}</div>
					</div>
				)}

				<div className="bg-gradient-to-r from-red-50 to-red-50/50 border border-red-200 rounded-lg p-3 flex items-start gap-2">
					<AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
					<p className="text-sm text-red-600">This action cannot be undone.</p>
				</div>

				<DialogFooter className="gap-2 sm:gap-0">
					<Button
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={loading}
						className="border-slate-300 text-slate-700 hover:bg-slate-50"
					>
						Cancel
					</Button>
					<Button
						onClick={onConfirm}
						disabled={loading}
						className="bg-red-500 hover:bg-red-600 text-white border-0"
					>
						{loading ? (
							<>
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								Deleting...
							</>
						) : (
							<>
								<Trash2 className="h-4 w-4 mr-2" />
								{confirmButtonText}
							</>
						)}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

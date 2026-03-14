"use client";

import { Menu } from "lucide-react";
import { useState } from "react";
import { MobileSidebar } from "@/components/mobile-sidebar";
import { Sidebar } from "@/components/sidebar";
import {
	Sheet,
	SheetContent,
	SheetTitle,
	SheetTrigger,
} from "@/components/ui/sheet";

export function ResponsiveSidebar() {
	const [open, setOpen] = useState(false);

	return (
		<>
			{/* Mobile: Hamburger menu + Sheet drawer */}
			<div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-background shadow-[0_4px_12px_-2px_rgba(29,53,87,0.08)]">
				<Sheet open={open} onOpenChange={setOpen}>
					<SheetTrigger asChild>
						<button className="p-4 hover:bg-accent transition-colors">
							<Menu className="h-6 w-6" />
							<span className="sr-only">Toggle navigation menu</span>
						</button>
					</SheetTrigger>
					<SheetContent side="left" className="p-0 w-64">
						<SheetTitle className="sr-only">Navigation menu</SheetTitle>
						<div onClick={() => setOpen(false)}>
							<MobileSidebar />
						</div>
					</SheetContent>
				</Sheet>
			</div>

			{/* Desktop: Regular sidebar */}
			<div className="hidden md:block">
				<Sidebar />
			</div>
		</>
	);
}

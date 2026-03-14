"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

export function LandingNav() {
	const [isOpen, setIsOpen] = useState(false);
	const [scrolled, setScrolled] = useState(false);

	useEffect(() => {
		const handleScroll = () => {
			setScrolled(window.scrollY > 20);
		};
		window.addEventListener("scroll", handleScroll);
		return () => window.removeEventListener("scroll", handleScroll);
	}, []);

	const navLinks = [
		{ href: "#features", label: "Features" },
		{ href: "#how-it-works", label: "How It Works" },
	];

	return (
		<nav
			className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
				scrolled
					? "bg-white/80 backdrop-blur-lg border-b border-slate-200/50 shadow-sm"
					: "bg-transparent"
			}`}
		>
			<div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
				<div className="flex items-center justify-between h-16">
					{/* Logo */}
					<Link href="/" className="flex items-center gap-2 group">
						<div className="h-9 w-9 rounded-xl bg-white flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-shadow p-1">
							<Image src="/reflexio_fav.svg" alt="Reflexio" width={28} height={28} />
						</div>
						<span className="font-bold text-xl text-slate-800">Reflexio</span>
					</Link>

					{/* Desktop Navigation */}
					<div className="hidden md:flex items-center gap-8">
						{navLinks.map((link) => (
							<a
								key={link.href}
								href={link.href}
								className="text-sm font-medium text-slate-600 hover:text-indigo-600 transition-colors"
							>
								{link.label}
							</a>
						))}
					</div>

					{/* Desktop CTA */}
					<div className="hidden md:flex items-center">
						<Button
							asChild
							className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 shadow-lg shadow-indigo-500/25 border-0"
						>
							<Link href="/login">Get Started</Link>
						</Button>
					</div>

					{/* Mobile Menu */}
					<Sheet open={isOpen} onOpenChange={setIsOpen}>
						<SheetTrigger asChild className="md:hidden">
							<Button variant="ghost" size="icon" className="text-slate-600">
								<Menu className="h-5 w-5" />
							</Button>
						</SheetTrigger>
						<SheetContent side="right" className="w-[280px] bg-white">
							<div className="flex flex-col gap-6 mt-6">
								{/* Mobile Logo */}
								<div className="flex items-center gap-2 pb-4 border-b border-slate-100">
									<div className="h-9 w-9 rounded-xl bg-white flex items-center justify-center shadow-sm p-1">
										<Image src="/reflexio_fav.svg" alt="Reflexio" width={28} height={28} />
									</div>
									<span className="font-bold text-xl text-slate-800">Reflexio</span>
								</div>

								{/* Mobile Navigation Links */}
								<div className="flex flex-col gap-4">
									{navLinks.map((link) => (
										<a
											key={link.href}
											href={link.href}
											onClick={() => setIsOpen(false)}
											className="text-base font-medium text-slate-600 hover:text-indigo-600 transition-colors py-2"
										>
											{link.label}
										</a>
									))}
								</div>

								{/* Mobile CTA */}
								<div className="flex flex-col gap-3 pt-4 border-t border-slate-100">
									<Button asChild className="w-full bg-gradient-to-r from-indigo-600 to-purple-600">
										<Link href="/login" onClick={() => setIsOpen(false)}>
											Get Started
										</Link>
									</Button>
								</div>
							</div>
						</SheetContent>
					</Sheet>
				</div>
			</div>
		</nav>
	);
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const phrases = [
	"Self-Correct From User Interactions",
	"Remember User Preferences",
	"Improve Autonomously",
];

export function Hero() {
	const [currentIndex, setCurrentIndex] = useState(0);
	const [isVisible, setIsVisible] = useState(true);

	useEffect(() => {
		const interval = setInterval(() => {
			setIsVisible(false);
			setTimeout(() => {
				setCurrentIndex((prev) => (prev + 1) % phrases.length);
				setIsVisible(true);
			}, 500);
		}, 3000);
		return () => clearInterval(interval);
	}, []);

	return (
		<section className="relative pt-32 pb-24 px-4 sm:px-6 lg:px-8 overflow-hidden">
			{/* Animated gradient background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-gradient-to-br from-blue-400/20 via-purple-400/20 to-pink-400/20 rounded-full blur-3xl" />
				<div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-gradient-to-tr from-emerald-400/15 via-cyan-400/15 to-blue-400/15 rounded-full blur-3xl" />
				<div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-r from-indigo-200/10 via-purple-200/10 to-pink-200/10 rounded-full blur-3xl" />
			</div>

			<div className="max-w-4xl mx-auto text-center">
				<h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight mb-6">
					<span className="block text-slate-400 text-3xl sm:text-4xl lg:text-5xl font-medium mb-2">
						Beyond Memory.
					</span>
					<span className="block bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">
						Toward Evolution.
					</span>
					<span className="block mt-4 text-2xl sm:text-3xl lg:text-4xl">
						<span
							className={`bg-gradient-to-r from-slate-600 to-slate-800 bg-clip-text text-transparent transition-opacity duration-500 ${isVisible ? "opacity-100" : "opacity-0"}`}
						>
							{phrases[currentIndex]}
						</span>
					</span>
				</h1>

				<p className="text-lg sm:text-xl text-slate-600 max-w-2xl mx-auto mb-10 leading-relaxed">
					Reflexio adds a learning loop that turns user corrections and feedback into permanent
					behavioral improvements for AI agents.
				</p>

				<div className="flex flex-col sm:flex-row gap-4 justify-center">
					<Button
						size="lg"
						asChild
						className="text-base px-8 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 shadow-lg shadow-indigo-500/25 border-0"
					>
						<Link href="/login">Get Started Free</Link>
					</Button>
					<Button
						variant="outline"
						size="lg"
						asChild
						className="text-base px-8 border-slate-300 hover:bg-slate-50 text-slate-700"
					>
						<a href="/docs/" target="_blank" rel="noopener noreferrer">
							View Documentation
						</a>
					</Button>
				</div>

				{/* Trust indicators */}
				<div className="mt-16 flex flex-wrap items-center justify-center gap-8 text-sm text-slate-500">
					<div className="flex items-center gap-2">
						<div className="w-2 h-2 rounded-full bg-emerald-500"></div>
						<span>3-line SDK integration</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-2 h-2 rounded-full bg-emerald-500"></div>
						<span>100% data ownership</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-2 h-2 rounded-full bg-emerald-500"></div>
						<span>Safe behavioral versioning</span>
					</div>
				</div>
			</div>
		</section>
	);
}

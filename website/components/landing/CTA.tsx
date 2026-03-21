"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export function CTA() {
	return (
		<section className="py-24 px-4 sm:px-6 lg:px-8">
			<div className="max-w-4xl mx-auto">
				<div className="relative overflow-hidden rounded-3xl">
					{/* Background gradient */}
					<div className="absolute inset-0 bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-600"></div>

					{/* Decorative elements */}
					<div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full blur-3xl"></div>
					<div className="absolute bottom-0 left-0 w-48 h-48 bg-white/10 rounded-full blur-3xl"></div>

					{/* Content */}
					<div className="relative p-10 md:p-14 text-center">
						<div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 backdrop-blur-sm text-white/90 text-sm font-medium mb-6">
							<Sparkles className="w-4 h-4" />
							Free to get started
						</div>

						<h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
							Stop Fixing the Same Agent Mistakes
						</h2>
						<p className="text-white/80 text-lg mb-8 max-w-xl mx-auto">
							Add a learning loop to your agents in minutes. Free to start, scales with the value
							created.
						</p>

						<div className="flex flex-col sm:flex-row gap-4 justify-center">
							<Button
								size="lg"
								asChild
								className="text-base px-8 bg-white text-indigo-700 hover:bg-white/90 shadow-lg border-0"
							>
								<Link href="/login">
									Get Started Free
									<ArrowRight className="ml-2 h-4 w-4" />
								</Link>
							</Button>
						</div>
					</div>
				</div>
			</div>
		</section>
	);
}

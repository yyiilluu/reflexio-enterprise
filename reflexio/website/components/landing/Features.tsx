"use client";

import { BarChart3, Brain, TrendingUp } from "lucide-react";

const features = [
	{
		title: "Personalization Signals",
		description:
			"Go beyond remembering that 'John likes blue.' Reflexio learns that 'When John asks for a report, he expects a 7-day rolling average' — extracting preferences, constraints, and habits that shape how your agent actually behaves.",
		icon: Brain,
		gradient: "from-violet-500 to-purple-600",
		bgGradient: "from-violet-50 to-purple-50",
		iconBg: "bg-gradient-to-br from-violet-500 to-purple-600",
	},
	{
		title: "Self-Correction Loop",
		description:
			"When a user undoes an action or corrects your agent, Reflexio extracts specific do/don't rules with triggering conditions — turning one-time fixes into permanent behavioral changes.",
		icon: TrendingUp,
		gradient: "from-emerald-500 to-teal-600",
		bgGradient: "from-emerald-50 to-teal-50",
		iconBg: "bg-gradient-to-br from-emerald-500 to-teal-600",
	},
	{
		title: "Observation & Measurement",
		description:
			"Test new learned behaviors in parallel with current ones using shadow deployment. Measure whether your agent is actually getting smarter, not just different.",
		icon: BarChart3,
		gradient: "from-orange-500 to-amber-600",
		bgGradient: "from-orange-50 to-amber-50",
		iconBg: "bg-gradient-to-br from-orange-500 to-amber-600",
	},
];

export function Features() {
	return (
		<section
			id="features"
			className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-50/50 to-white"
		>
			<div className="max-w-6xl mx-auto">
				<div className="text-center mb-16">
					<p className="text-sm font-semibold text-indigo-600 uppercase tracking-wider mb-3">
						Core Capabilities
					</p>
					<h2 className="text-3xl sm:text-4xl font-bold text-slate-800 mb-4">
						From Static Agents to Self-Improving Systems
					</h2>
					<p className="text-slate-600 text-lg max-w-2xl mx-auto">
						Your agents interact with users thousands of times, but the lessons
						from those interactions are trapped in logs. Reflexio closes that
						loop.
					</p>
				</div>

				<div className="grid md:grid-cols-3 gap-8">
					{features.map((feature) => (
						<div
							key={feature.title}
							className={`relative group rounded-2xl p-8 bg-gradient-to-br ${feature.bgGradient} border border-white/50 shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1`}
						>
							{/* Icon */}
							<div
								className={`${feature.iconBg} w-14 h-14 rounded-xl flex items-center justify-center mb-6 shadow-lg`}
							>
								<feature.icon className="h-7 w-7 text-white" />
							</div>

							{/* Content */}
							<h3 className="text-xl font-semibold text-slate-800 mb-3">
								{feature.title}
							</h3>
							<p className="text-slate-600 leading-relaxed">
								{feature.description}
							</p>

							{/* Decorative gradient line */}
							<div
								className={`absolute bottom-0 left-8 right-8 h-1 bg-gradient-to-r ${feature.gradient} rounded-full opacity-0 group-hover:opacity-100 transition-opacity`}
							></div>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

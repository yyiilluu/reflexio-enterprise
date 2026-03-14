"use client";

import {
	CheckCircle2,
	Cpu,
	GitCompare,
	RefreshCw,
	Shield,
	Sliders,
} from "lucide-react";

const comparisonData = [
	{
		traditional: "Stores what users said",
		reflexio: "Learns how agents should act",
		reflexioHighlight: "",
	},
	{
		traditional: "Remembers user facts",
		reflexio: "Builds actionable behavioral rules",
		reflexioHighlight: "",
	},
	{
		traditional: "Static memory records",
		reflexio: "Self-evolving learned behaviors",
		reflexioHighlight: "",
	},
	{
		traditional: "No validation",
		reflexio: "Shadow deployment testing",
		reflexioHighlight: "",
	},
	{
		traditional: "Passive retrieval",
		reflexio: "Active learning loop",
		reflexioHighlight: "",
	},
	{
		traditional: "Generic conversation context",
		reflexio: "Domain-specific signal extraction",
		reflexioHighlight: "",
	},
	{
		traditional: '"What did the user say?"',
		reflexio: '"How should the agent behave differently next time?"',
		reflexioHighlight: "",
		isPhilosophy: true,
	},
];

const valueProps = [
	{
		title: "Autonomy Through Reflection",
		description:
			"Agents 'think back' on their performance and optimize their own logic — not just retrieve stored facts.",
		icon: CheckCircle2,
		color: "text-emerald-600",
		bgColor: "bg-emerald-100",
		borderColor: "border-emerald-200",
	},
	{
		title: "Full Extraction Control",
		description:
			"Tunable extractors that look for business-specific signals — a churn signal in customer service, a syntax error in a coding agent.",
		icon: Sliders,
		color: "text-purple-600",
		bgColor: "bg-purple-100",
		borderColor: "border-purple-200",
	},
	{
		title: "Safe Behavioral Evolution",
		description:
			"Treat agent learning like software deployments. Version behaviors, test with shadow deployment, and roll back bad learning like a git commit.",
		icon: GitCompare,
		color: "text-blue-600",
		bgColor: "bg-blue-100",
		borderColor: "border-blue-200",
	},
	{
		title: "Low-Cost Skill Acquisition",
		description:
			"When a user corrects your agent's tool usage or process, Reflexio extracts that as a learned skill for all future similar scenarios.",
		icon: Cpu,
		color: "text-orange-600",
		bgColor: "bg-orange-100",
		borderColor: "border-orange-200",
	},
	{
		title: "Conflict Resolution",
		description:
			"A background process de-duplicates and resolves conflicting learning signals, preventing behavioral drift and learning rot.",
		icon: RefreshCw,
		color: "text-pink-600",
		bgColor: "bg-pink-100",
		borderColor: "border-pink-200",
	},
	{
		title: "Data Privacy",
		description:
			"Bring your own storage. Your users' learning data never stays on our servers. 100% data ownership guaranteed.",
		icon: Shield,
		color: "text-indigo-600",
		bgColor: "bg-indigo-100",
		borderColor: "border-indigo-200",
	},
];

export function ValuePropositions() {
	return (
		<section className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-white via-slate-50/50 to-white">
			<div className="max-w-6xl mx-auto">
				<div className="text-center mb-16">
					<p className="text-sm font-semibold text-indigo-600 uppercase tracking-wider mb-3">
						Why Choose Us
					</p>
					<h2 className="text-3xl sm:text-4xl font-bold text-slate-800 mb-4">
						Why Reflexio?
					</h2>
					<p className="text-slate-600 text-lg max-w-2xl mx-auto">
						Built different from the ground up to create agents that actually
						learn
					</p>
				</div>

				<div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
					{valueProps.map((prop) => (
						<div
							key={prop.title}
							className="p-6 rounded-2xl bg-white border border-slate-200 hover:border-slate-300 shadow-sm hover:shadow-md transition-all duration-300 group"
						>
							<div className="flex items-start gap-4">
								<div
									className={`${prop.bgColor} ${prop.borderColor} border w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform`}
								>
									<prop.icon className={`h-6 w-6 ${prop.color}`} />
								</div>
								<div>
									<h3 className="font-semibold text-slate-800 mb-2">
										{prop.title}
									</h3>
									<p className="text-sm text-slate-600 leading-relaxed">
										{prop.description}
									</p>
								</div>
							</div>
						</div>
					))}
				</div>

				{/* Comparison Table */}
				<div className="mt-24">
					<div className="text-center mb-12">
						<p className="text-sm font-semibold text-emerald-600 uppercase tracking-wider mb-3">
							The Difference
						</p>
						<h2 className="text-3xl sm:text-4xl font-bold text-slate-800 mb-4">
							Not Just Another Memory Layer
						</h2>
						<p className="text-slate-600 text-lg max-w-2xl mx-auto">
							See how Reflexio fundamentally differs from traditional approaches
						</p>
					</div>

					<div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg">
						{/* Table Header */}
						<div className="grid grid-cols-2">
							<div className="bg-slate-50 border-b border-r border-slate-200 p-5 sm:p-6">
								<h3 className="font-semibold text-slate-500 text-sm uppercase tracking-wide">
									Traditional Memory
								</h3>
								<p className="text-xs text-slate-400 mt-1">
									Vector DBs, Mem0, Zep
								</p>
							</div>
							<div className="bg-emerald-50 border-b border-slate-200 p-5 sm:p-6">
								<h3 className="font-semibold text-emerald-700 text-sm uppercase tracking-wide">
									Reflexio
								</h3>
								<p className="text-xs text-emerald-600/70 mt-1">
									Behavioral learning layer
								</p>
							</div>
						</div>

						{/* Table Rows */}
						{comparisonData.map((row, index) => (
							<div
								key={index}
								className={`grid grid-cols-2 ${
									index !== comparisonData.length - 1
										? "border-b border-slate-100"
										: ""
								} ${row.isPhilosophy ? "bg-slate-50/50" : ""} hover:bg-slate-50/30 transition-colors`}
							>
								{/* Traditional Column */}
								<div className="border-r border-slate-100 p-4 sm:p-5 flex items-center">
									<p
										className={`text-slate-500 text-sm ${row.isPhilosophy ? "italic" : ""}`}
									>
										{row.traditional}
									</p>
								</div>

								{/* Reflexio Column */}
								<div className="p-4 sm:p-5 flex items-center">
									<div className="flex items-start gap-2.5">
										<CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
										<p
											className={`text-sm ${row.isPhilosophy ? "italic" : ""}`}
										>
											<span className="font-medium text-slate-800">
												{row.reflexio}
											</span>
											{row.reflexioHighlight && (
												<span className="text-slate-500">
													{" "}
													{row.reflexioHighlight}
												</span>
											)}
										</p>
									</div>
								</div>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}

"use client";

import {
	CheckCircle,
	LayoutDashboard,
	MessageSquare,
	ThumbsUp,
	TrendingDown,
	TrendingUp,
	Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
	CartesianGrid,
	Line,
	LineChart,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type DashboardStats, getDashboardStats, type TimeSeriesDataPoint } from "@/lib/api";

// Helper function to format timestamps into readable time labels
const formatTimeLabel = (timestamp: number, granularity: string): string => {
	const date = new Date(timestamp * 1000);

	if (granularity === "daily") {
		const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
		return days[date.getDay()];
	} else if (granularity === "weekly") {
		// Calculate week number
		const startOfYear = new Date(date.getFullYear(), 0, 1);
		const days = Math.floor((date.getTime() - startOfYear.getTime()) / (24 * 60 * 60 * 1000));
		const weekNumber = Math.ceil((days + startOfYear.getDay() + 1) / 7);
		return `Week ${weekNumber}`;
	} else {
		// Monthly
		const months = [
			"Jan",
			"Feb",
			"Mar",
			"Apr",
			"May",
			"Jun",
			"Jul",
			"Aug",
			"Sep",
			"Oct",
			"Nov",
			"Dec",
		];
		return months[date.getMonth()];
	}
};

// Group time series data by granularity
const groupTimeSeriesData = (
	data: TimeSeriesDataPoint[],
	granularity: string,
	aggregationType: "sum" | "average" = "sum",
): { time: string; value: number }[] => {
	if (data.length === 0) return [];

	// Group data points by time bucket
	const grouped = new Map<number, { sum: number; count: number }>();

	data.forEach((point) => {
		const bucket = getTimeBucket(point.timestamp, granularity);
		const existing = grouped.get(bucket) || { sum: 0, count: 0 };
		grouped.set(bucket, {
			sum: existing.sum + point.value,
			count: existing.count + 1,
		});
	});

	// Convert to array and format labels
	return Array.from(grouped.entries())
		.sort((a, b) => a[0] - b[0])
		.map(([timestamp, { sum, count }]) => ({
			time: formatTimeLabel(timestamp, granularity),
			value: aggregationType === "average" ? sum / count : sum,
		}));
};

// Get time bucket for grouping
const getTimeBucket = (timestamp: number, granularity: string): number => {
	const date = new Date(timestamp * 1000);

	if (granularity === "daily") {
		// Start of day
		return Math.floor(
			new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() / 1000,
		);
	} else if (granularity === "weekly") {
		// Start of week (Monday)
		const dayOfWeek = date.getDay();
		const diff = dayOfWeek === 0 ? 6 : dayOfWeek - 1; // Adjust for Monday start
		const monday = new Date(date);
		monday.setDate(date.getDate() - diff);
		return Math.floor(
			new Date(monday.getFullYear(), monday.getMonth(), monday.getDate()).getTime() / 1000,
		);
	} else {
		// Start of month
		return Math.floor(new Date(date.getFullYear(), date.getMonth(), 1).getTime() / 1000);
	}
};

// Calculate trend percentage
const calculateTrend = (
	current: number,
	previous: number,
): { text: string; isPositive: boolean } => {
	if (previous === 0) {
		return { text: current > 0 ? "+100%" : "0%", isPositive: current > 0 };
	}
	const percentage = (((current - previous) / previous) * 100).toFixed(1);
	const isPositive = parseFloat(percentage) >= 0;
	const sign = isPositive ? "+" : "";
	return { text: `${sign}${percentage}%`, isPositive };
};

interface ChartCardProps {
	title: string;
	description: string;
	data: { time: string; value: number }[];
	timeGranularity: "daily" | "weekly" | "monthly";
	onGranularityChange: (granularity: "daily" | "weekly" | "monthly") => void;
	color: string;
	gradientFrom: string;
	gradientTo: string;
	dataKey?: string;
	yAxisLabel?: string;
	isLoading?: boolean;
}

function ChartCard({
	title,
	description,
	data,
	timeGranularity,
	onGranularityChange,
	color,
	gradientFrom,
	gradientTo,
	dataKey = "value",
	yAxisLabel,
	isLoading = false,
}: ChartCardProps) {
	return (
		<Card className="overflow-hidden border-slate-200 hover:shadow-lg transition-all duration-300 bg-white">
			<CardHeader className="pb-4">
				<div className="flex items-center justify-between gap-4">
					<div>
						<CardTitle className="text-lg font-semibold text-slate-800">{title}</CardTitle>
						<CardDescription className="mt-1 text-slate-500">{description}</CardDescription>
					</div>
					<div className="flex gap-1 bg-slate-100 p-1 rounded-xl">
						{(["daily", "weekly", "monthly"] as const).map((gran) => (
							<button
								key={gran}
								onClick={() => onGranularityChange(gran)}
								className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
									timeGranularity === gran
										? `bg-gradient-to-r ${gradientFrom} ${gradientTo} text-white shadow-sm`
										: "text-slate-600 hover:text-slate-800 hover:bg-white"
								}`}
							>
								{gran.charAt(0).toUpperCase() + gran.slice(1)}
							</button>
						))}
					</div>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="flex items-center justify-center h-[280px]">
						<div
							className={`animate-spin rounded-full h-10 w-10 border-2 border-transparent`}
							style={{ borderTopColor: color, borderRightColor: color }}
						></div>
					</div>
				) : data.length === 0 ? (
					<div className="flex items-center justify-center h-[280px] text-slate-400">
						No data available
					</div>
				) : (
					<ResponsiveContainer width="100%" height={280}>
						<LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
							<defs>
								<linearGradient
									id={`gradient-${title.replace(/\s/g, "")}`}
									x1="0"
									y1="0"
									x2="0"
									y2="1"
								>
									<stop offset="5%" stopColor={color} stopOpacity={0.2} />
									<stop offset="95%" stopColor={color} stopOpacity={0} />
								</linearGradient>
							</defs>
							<CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
							<XAxis
								dataKey="time"
								tick={{ fill: "#64748b", fontSize: 12 }}
								axisLine={{ stroke: "#e2e8f0" }}
								tickLine={{ stroke: "#e2e8f0" }}
							/>
							<YAxis
								tick={{ fill: "#64748b", fontSize: 12 }}
								axisLine={{ stroke: "#e2e8f0" }}
								tickLine={{ stroke: "#e2e8f0" }}
								label={
									yAxisLabel
										? {
												value: yAxisLabel,
												angle: -90,
												position: "insideLeft",
												fill: "#64748b",
											}
										: undefined
								}
							/>
							<Tooltip
								contentStyle={{
									backgroundColor: "white",
									border: "1px solid #e2e8f0",
									borderRadius: "12px",
									boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
									padding: "12px",
								}}
								labelStyle={{
									color: "#1e293b",
									fontWeight: 600,
									marginBottom: "4px",
								}}
							/>
							<Line
								type="monotone"
								dataKey={dataKey}
								stroke={color}
								strokeWidth={3}
								dot={{ fill: color, strokeWidth: 2, r: 4, stroke: "white" }}
								activeDot={{ r: 6, stroke: "white", strokeWidth: 2 }}
								name={title}
								fill={`url(#gradient-${title.replace(/\s/g, "")})`}
							/>
						</LineChart>
					</ResponsiveContainer>
				)}
			</CardContent>
		</Card>
	);
}

// Stat card configurations with colors
const statConfigs = [
	{
		key: "interactions",
		iconBg: "bg-gradient-to-br from-blue-500 to-cyan-500",
		iconColor: "text-white",
		trendColor: "text-blue-600",
		bgGradient: "from-blue-50 to-cyan-50",
		borderColor: "border-blue-100",
	},
	{
		key: "profiles",
		iconBg: "bg-gradient-to-br from-purple-500 to-pink-500",
		iconColor: "text-white",
		trendColor: "text-purple-600",
		bgGradient: "from-purple-50 to-pink-50",
		borderColor: "border-purple-100",
	},
	{
		key: "feedbacks",
		iconBg: "bg-gradient-to-br from-orange-500 to-amber-500",
		iconColor: "text-white",
		trendColor: "text-orange-600",
		bgGradient: "from-orange-50 to-amber-50",
		borderColor: "border-orange-100",
	},
	{
		key: "success",
		iconBg: "bg-gradient-to-br from-emerald-500 to-teal-500",
		iconColor: "text-white",
		trendColor: "text-emerald-600",
		bgGradient: "from-emerald-50 to-teal-50",
		borderColor: "border-emerald-100",
	},
];

export default function Dashboard() {
	const [interactionsGranularity, setInteractionsGranularity] = useState<
		"daily" | "weekly" | "monthly"
	>("daily");
	const [profilesGranularity, setProfilesGranularity] = useState<"daily" | "weekly" | "monthly">(
		"daily",
	);
	const [feedbacksGranularity, setFeedbacksGranularity] = useState<"daily" | "weekly" | "monthly">(
		"daily",
	);
	const [evaluationsGranularity, setEvaluationsGranularity] = useState<
		"daily" | "weekly" | "monthly"
	>("daily");

	const [dashboardData, setDashboardData] = useState<DashboardStats | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// Fetch dashboard data (only once, no granularity needed)
	const fetchDashboardData = useCallback(async () => {
		setIsLoading(true);
		setError(null);

		try {
			const data = await getDashboardStats({ days_back: 30 });

			if (data.success && data.stats) {
				setDashboardData(data.stats);
			} else {
				setError(data.msg || "Failed to load dashboard data");
			}
		} catch (err) {
			setError("Failed to connect to API");
			console.error("Dashboard API error:", err);
		} finally {
			setIsLoading(false);
		}
	}, []);

	// Initial load only - granularity is handled client-side
	useEffect(() => {
		fetchDashboardData();
	}, [fetchDashboardData]);

	// Calculate stats for display
	const stats = dashboardData
		? [
				{
					title: "User Interactions",
					value: dashboardData.current_period.total_interactions.toLocaleString(),
					description: "Total interactions recorded",
					icon: MessageSquare,
					trend: calculateTrend(
						dashboardData.current_period.total_interactions,
						dashboardData.previous_period.total_interactions,
					),
					...statConfigs[0],
				},
				{
					title: "User Profiles",
					value: dashboardData.current_period.total_profiles.toLocaleString(),
					description: "Active user profiles",
					icon: Users,
					trend: calculateTrend(
						dashboardData.current_period.total_profiles,
						dashboardData.previous_period.total_profiles,
					),
					...statConfigs[1],
				},
				{
					title: "Feedbacks Extracted",
					value: dashboardData.current_period.total_feedbacks.toLocaleString(),
					description: "Total feedbacks collected",
					icon: ThumbsUp,
					trend: calculateTrend(
						dashboardData.current_period.total_feedbacks,
						dashboardData.previous_period.total_feedbacks,
					),
					...statConfigs[2],
				},
				{
					title: "Success Rate",
					value: `${dashboardData.current_period.success_rate.toFixed(1)}%`,
					description: "Agent success rate",
					icon: CheckCircle,
					trend: calculateTrend(
						dashboardData.current_period.success_rate,
						dashboardData.previous_period.success_rate,
					),
					...statConfigs[3],
				},
			]
		: [];

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
			{/* Header */}
			<div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
				<div className="p-8">
					<div className="flex items-center gap-3 mb-2">
						<div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
							<LayoutDashboard className="h-5 w-5 text-white" />
						</div>
						<h1 className="text-3xl font-bold tracking-tight text-slate-800">Dashboard</h1>
					</div>
					<p className="text-slate-500 mt-1 ml-13">
						Monitor and analyze user profiling metrics in real-time
					</p>
				</div>
			</div>

			<div className="p-8">
				{error && (
					<div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl">
						<p className="text-red-600 text-sm font-medium">{error}</p>
					</div>
				)}

				{/* Statistics Cards */}
				<div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4 mb-8">
					{isLoading
						? // Loading skeleton
							Array.from({ length: 4 }).map((_, i) => (
								<Card
									key={i}
									className={`border bg-gradient-to-br ${statConfigs[i].bgGradient} ${statConfigs[i].borderColor}`}
								>
									<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
										<div className="h-4 bg-white/60 rounded w-24 animate-pulse"></div>
										<div
											className={`h-10 w-10 rounded-xl ${statConfigs[i].iconBg} opacity-50 animate-pulse`}
										></div>
									</CardHeader>
									<CardContent>
										<div className="h-9 bg-white/60 rounded w-20 mb-2 animate-pulse"></div>
										<div className="h-3 bg-white/40 rounded w-32 mb-3 animate-pulse"></div>
										<div className="h-4 bg-white/40 rounded w-16 animate-pulse"></div>
									</CardContent>
								</Card>
							))
						: stats.map((stat) => {
								const Icon = stat.icon;
								return (
									<Card
										key={stat.title}
										className={`border bg-gradient-to-br ${stat.bgGradient} ${stat.borderColor} hover:shadow-lg transition-all duration-300 hover:-translate-y-1`}
									>
										<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
											<CardTitle className="text-sm font-semibold text-slate-600">
												{stat.title}
											</CardTitle>
											<div
												className={`h-10 w-10 rounded-xl ${stat.iconBg} flex items-center justify-center shadow-lg`}
											>
												<Icon className={`h-5 w-5 ${stat.iconColor}`} />
											</div>
										</CardHeader>
										<CardContent>
											<div className="text-3xl font-bold text-slate-800">{stat.value}</div>
											<p className="text-xs text-slate-500 mt-1">{stat.description}</p>
											<div
												className={`flex items-center gap-1 mt-3 text-sm font-semibold ${stat.trend.isPositive ? "text-emerald-600" : "text-red-500"}`}
											>
												{stat.trend.isPositive ? (
													<TrendingUp className="h-4 w-4" />
												) : (
													<TrendingDown className="h-4 w-4" />
												)}
												<span>{stat.trend.text}</span>
												<span className="text-slate-400 font-normal text-xs ml-1">
													vs last period
												</span>
											</div>
										</CardContent>
									</Card>
								);
							})}
				</div>

				{/* Interactive Charts Grid */}
				<div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
					<ChartCard
						title="User Interactions"
						description="Track user interactions over time"
						data={
							dashboardData
								? groupTimeSeriesData(
										dashboardData.interactions_time_series,
										interactionsGranularity,
										"average",
									)
								: []
						}
						timeGranularity={interactionsGranularity}
						onGranularityChange={setInteractionsGranularity}
						color="#3b82f6"
						gradientFrom="from-blue-500"
						gradientTo="to-cyan-500"
						isLoading={isLoading}
					/>

					<ChartCard
						title="Profiles Learnt"
						description="Number of user profiles extracted"
						data={
							dashboardData
								? groupTimeSeriesData(
										dashboardData.profiles_time_series,
										profilesGranularity,
										"average",
									)
								: []
						}
						timeGranularity={profilesGranularity}
						onGranularityChange={setProfilesGranularity}
						color="#a855f7"
						gradientFrom="from-purple-500"
						gradientTo="to-pink-500"
						isLoading={isLoading}
					/>

					<ChartCard
						title="Feedbacks Extracted"
						description="Total feedbacks collected from interactions"
						data={
							dashboardData
								? groupTimeSeriesData(
										dashboardData.feedbacks_time_series,
										feedbacksGranularity,
										"average",
									)
								: []
						}
						timeGranularity={feedbacksGranularity}
						onGranularityChange={setFeedbacksGranularity}
						color="#f97316"
						gradientFrom="from-orange-500"
						gradientTo="to-amber-500"
						isLoading={isLoading}
					/>

					<ChartCard
						title="Agent Success Rate"
						description="Agent evaluation success percentage"
						data={
							dashboardData
								? groupTimeSeriesData(
										dashboardData.evaluations_time_series,
										evaluationsGranularity,
										"average",
									)
								: []
						}
						timeGranularity={evaluationsGranularity}
						onGranularityChange={setEvaluationsGranularity}
						color="#10b981"
						gradientFrom="from-emerald-500"
						gradientTo="to-teal-500"
						yAxisLabel="%"
						isLoading={isLoading}
					/>
				</div>
			</div>
		</div>
	);
}

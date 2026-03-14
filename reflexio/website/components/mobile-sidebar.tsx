"use client";

import {
	BarChart3,
	CheckCircle,
	KeyRound,
	LayoutDashboard,
	LogIn,
	LogOut,
	MessageSquare,
	Settings,
	Sparkles,
	User,
	Users,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

interface NavItem {
	title: string;
	href: string;
	icon: React.ComponentType<{ className?: string }>;
	featureFlag?: string;
}

interface NavSection {
	title: string;
	items: NavItem[];
}

const navSections: NavSection[] = [
	{
		title: "Analytics",
		items: [
			{
				title: "Dashboard",
				href: "/dashboard",
				icon: LayoutDashboard,
			},
			{
				title: "Evaluations",
				href: "/evaluations",
				icon: CheckCircle,
			},
		],
	},
	{
		title: "Management",
		items: [
			{
				title: "Interactions",
				href: "/interactions",
				icon: MessageSquare,
			},
			{
				title: "User Profiles",
				href: "/profiles",
				icon: Users,
			},
			{
				title: "Feedback",
				href: "/feedbacks",
				icon: BarChart3,
			},
			{
				title: "Skills",
				href: "/skills",
				icon: Sparkles,
				featureFlag: "skill_generation",
			},
		],
	},
	{
		title: "Settings",
		items: [
			{
				title: "Settings",
				href: "/settings",
				icon: Settings,
			},
			{
				title: "Account",
				href: "/account",
				icon: KeyRound,
			},
		],
	},
];

export function MobileSidebar() {
	const pathname = usePathname();
	const { isAuthenticated, userEmail, logout, isSelfHost, isFeatureEnabled } =
		useAuth();

	return (
		<div className="flex h-screen w-64 flex-col bg-background shadow-[4px_0_12px_-2px_rgba(29,53,87,0.08)] relative z-10">
			{/* Header */}
			<div className="bg-gradient-to-br from-primary/5 to-secondary/10">
				<div className="p-6">
					<div className="flex items-center gap-2 mb-2">
						<div className="h-8 w-8 rounded-lg bg-white flex items-center justify-center flex-shrink-0 shadow-lg shadow-indigo-500/25 p-1">
							<Image
								src="/reflexio_fav.svg"
								alt="Reflexio"
								width={24}
								height={24}
							/>
						</div>
						<div className="overflow-hidden">
							<h1 className="text-xl font-bold text-foreground whitespace-nowrap">
								Reflexio
							</h1>
						</div>
					</div>
					<p className="text-sm text-muted-foreground font-medium">
						User Profiler Portal
					</p>
				</div>
			</div>
			{/* Gradient separator */}
			<div className="h-px bg-gradient-to-r from-transparent via-primary/10 to-transparent mx-3" />

			{/* Navigation */}
			<nav className="flex-1 overflow-y-auto px-3 py-4">
				{navSections.map((section) => (
					<div key={section.title} className="mb-6">
						{/* Section Header */}
						<div className="px-3 mb-2">
							<h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
								{section.title}
							</h2>
						</div>

						{/* Section Items */}
						<div className="space-y-1">
							{section.items
								.filter(
									(item) =>
										!item.featureFlag || isFeatureEnabled(item.featureFlag),
								)
								.map((item) => {
									const Icon = item.icon;
									const isActive = pathname === item.href;

									return (
										<Link
											key={item.title}
											href={item.href}
											className={cn(
												"flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200 relative group",
												isActive
													? "bg-primary/10 text-primary shadow-sm before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:bg-primary before:rounded-r"
													: "text-foreground/70 hover:bg-accent hover:text-accent-foreground hover:shadow-sm hover:scale-105",
											)}
										>
											<Icon className="h-5 w-5 flex-shrink-0" />
											<span className="flex-1">{item.title}</span>
										</Link>
									);
								})}
						</div>
					</div>
				))}
			</nav>

			{/* Gradient separator */}
			<div className="h-px bg-gradient-to-r from-transparent via-primary/10 to-transparent mx-3" />

			{/* Footer */}
			<div className="bg-muted/30">
				{/* Auth Section - Only show if not in self-host mode */}
				{!isSelfHost && (
					<div className="p-4">
						{isAuthenticated ? (
							<div className="space-y-2">
								<div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-background">
									<User className="h-4 w-4 text-muted-foreground" />
									<span
										className="text-xs text-foreground font-medium truncate flex-1"
										title={userEmail || undefined}
									>
										{userEmail}
									</span>
								</div>
								<button
									onClick={() => logout()}
									className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-foreground/70 hover:bg-accent hover:text-accent-foreground rounded-lg transition-all"
								>
									<LogOut className="h-4 w-4" />
									<span>Logout</span>
								</button>
							</div>
						) : (
							<Link
								href="/login"
								className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-foreground/70 hover:bg-accent hover:text-accent-foreground rounded-lg transition-all"
							>
								<LogIn className="h-4 w-4" />
								<span>Login</span>
							</Link>
						)}
					</div>
				)}

				{/* Version Info */}
				<div className="p-4">
					<p className="text-xs text-muted-foreground font-medium">
						Version 1.0.0
					</p>
					<p className="text-xs text-muted-foreground/70 mt-0.5">
						{isSelfHost ? "Self-Hosted" : "Production"}
					</p>
				</div>
			</div>
		</div>
	);
}

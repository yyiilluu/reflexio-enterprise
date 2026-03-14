"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ResponsiveSidebar } from "@/components/responsive-sidebar";
import { useAuth } from "@/lib/auth-context";
import { AUTH_PAGES, PROTECTED_ROUTES } from "@/lib/routes";

export function LayoutContent({ children }: { children: React.ReactNode }) {
	const pathname = usePathname();
	const router = useRouter();
	const { isAuthenticated, isSelfHost } = useAuth();

	const isAuthPage = AUTH_PAGES.includes(
		pathname as (typeof AUTH_PAGES)[number],
	);
	const isLandingPage = pathname === "/";
	const isProtectedRoute = PROTECTED_ROUTES.some(
		(route) => pathname === route || pathname.startsWith(`${route}/`),
	);

	// Redirect to login if not authenticated and accessing a protected route
	useEffect(() => {
		if (isAuthPage || isLandingPage || isSelfHost) {
			return;
		}

		if (!isAuthenticated && isProtectedRoute) {
			if (sessionStorage.getItem("account_deleted")) return;
			router.push("/login");
		}
	}, [
		isAuthenticated,
		isSelfHost,
		isAuthPage,
		isLandingPage,
		isProtectedRoute,
		router,
	]);

	if (isAuthPage || isLandingPage) {
		// Auth pages and landing page get full screen without sidebar
		return <>{children}</>;
	}

	// For unknown routes, let Next.js render the not-found page
	if (!isProtectedRoute) {
		return <>{children}</>;
	}

	// Don't render protected pages until auth check is complete
	// Allow rendering during account deletion flow so success dialog can show
	if (
		!isSelfHost &&
		!isAuthenticated &&
		!sessionStorage.getItem("account_deleted")
	) {
		return null;
	}

	// Regular pages get sidebar layout
	return (
		<div className="flex h-screen overflow-hidden">
			<ResponsiveSidebar />
			<main className="flex-1 overflow-y-auto bg-background pt-16 md:pt-0">
				{children}
			</main>
		</div>
	);
}

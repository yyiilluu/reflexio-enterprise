"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { CTA } from "@/components/landing/CTA";
import { Features } from "@/components/landing/Features";
import { Footer } from "@/components/landing/Footer";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingNav } from "@/components/landing/LandingNav";
import { ValuePropositions } from "@/components/landing/ValuePropositions";
import { useAuth } from "@/lib/auth-context";

export default function LandingPage() {
	const { isAuthenticated, isSelfHost } = useAuth();
	const router = useRouter();

	useEffect(() => {
		// Redirect authenticated users or self-host mode to dashboard
		if (isAuthenticated || isSelfHost) {
			router.push("/dashboard");
		}
	}, [isAuthenticated, isSelfHost, router]);

	// Show nothing while redirecting
	if (isAuthenticated || isSelfHost) {
		return null;
	}

	return (
		<div className="min-h-screen bg-background">
			<LandingNav />
			<main>
				<Hero />
				<Features />
				<HowItWorks />
				<ValuePropositions />
				<CTA />
			</main>
			<Footer />
		</div>
	);
}

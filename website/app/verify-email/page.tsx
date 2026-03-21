"use client";

import { CheckCircle, Loader2, Mail, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

function VerifyEmailContent() {
	const [status, setStatus] = useState<"loading" | "success" | "error" | "already_verified">(
		"loading",
	);
	const [message, setMessage] = useState("");
	const searchParams = useSearchParams();
	const token = searchParams.get("token");

	useEffect(() => {
		if (!token) {
			setStatus("error");
			setMessage("No verification token provided");
			return;
		}

		const verifyEmail = async () => {
			try {
				const response = await fetch(`${API_BASE_URL}/api/verify-email`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
					},
					body: JSON.stringify({ token }),
				});

				const data = await response.json();

				if (response.ok) {
					if (data.message === "Email already verified") {
						setStatus("already_verified");
					} else {
						setStatus("success");
					}
					setMessage(data.message);
				} else {
					setStatus("error");
					setMessage(data.detail || "Verification failed");
				}
			} catch (_error) {
				setStatus("error");
				setMessage("Network error. Please try again.");
			}
		};

		verifyEmail();
	}, [token]);

	const renderContent = () => {
		switch (status) {
			case "loading":
				return (
					<>
						<Loader2 className="h-16 w-16 text-primary animate-spin mx-auto mb-4" />
						<h2 className="text-2xl font-semibold mb-2">Verifying Your Email</h2>
						<p className="text-muted-foreground">
							Please wait while we verify your email address...
						</p>
					</>
				);
			case "success":
				return (
					<>
						<CheckCircle className="h-16 w-16 text-emerald-500 mx-auto mb-4" />
						<h2 className="text-2xl font-semibold mb-2">Email Verified!</h2>
						<p className="text-muted-foreground mb-6">
							Your email has been successfully verified. You can now access all features.
						</p>
						<Button asChild className="w-full">
							<Link href="/login">Continue to Login</Link>
						</Button>
					</>
				);
			case "already_verified":
				return (
					<>
						<CheckCircle className="h-16 w-16 text-primary mx-auto mb-4" />
						<h2 className="text-2xl font-semibold mb-2">Already Verified</h2>
						<p className="text-muted-foreground mb-6">
							Your email address has already been verified.
						</p>
						<Button asChild className="w-full">
							<Link href="/login">Go to Login</Link>
						</Button>
					</>
				);
			case "error":
				return (
					<>
						<XCircle className="h-16 w-16 text-destructive mx-auto mb-4" />
						<h2 className="text-2xl font-semibold mb-2">Verification Failed</h2>
						<p className="text-muted-foreground mb-6">
							{message || "The verification link is invalid or has expired."}
						</p>
						<div className="space-y-3">
							<Button asChild variant="outline" className="w-full">
								<Link href="/login">Go to Login</Link>
							</Button>
							<p className="text-sm text-muted-foreground text-center">
								Need a new verification link?{" "}
								<Link href="/resend-verification" className="text-primary hover:underline">
									Resend verification email
								</Link>
							</p>
						</div>
					</>
				);
		}
	};

	return (
		<div className="flex items-center justify-center min-h-screen p-4 bg-background">
			<div className="w-full max-w-md">
				<Card>
					<CardHeader className="text-center">
						<Mail className="h-8 w-8 text-primary mx-auto mb-2" />
					</CardHeader>
					<CardContent className="text-center">{renderContent()}</CardContent>
				</Card>
			</div>
		</div>
	);
}

export default function VerifyEmailPage() {
	return (
		<Suspense
			fallback={
				<div className="flex items-center justify-center min-h-screen">
					<Loader2 className="h-8 w-8 animate-spin text-primary" />
				</div>
			}
		>
			<VerifyEmailContent />
		</Suspense>
	);
}

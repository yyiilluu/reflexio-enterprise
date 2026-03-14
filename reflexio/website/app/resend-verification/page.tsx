"use client";

import { AlertCircle, CheckCircle, Loader2, Mail } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

export default function ResendVerificationPage() {
	const [email, setEmail] = useState("");
	const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
	const [message, setMessage] = useState("");

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		setStatus("loading");

		try {
			const response = await fetch(`${API_BASE_URL}/api/resend-verification`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ email }),
			});

			const data = await response.json();
			setStatus("success");
			setMessage(data.message);
		} catch (_error) {
			setStatus("error");
			setMessage("Network error. Please try again.");
		}
	};

	return (
		<div className="flex items-center justify-center min-h-screen p-4 bg-background">
			<div className="w-full max-w-md">
				<Card>
					<CardHeader>
						<div className="flex items-center gap-2 mb-2">
							<Mail className="h-6 w-6 text-primary" />
							<CardTitle className="text-2xl">Resend Verification</CardTitle>
						</div>
						<CardDescription>
							Enter your email address and we'll send you a new verification link.
						</CardDescription>
					</CardHeader>
					<CardContent>
						{status === "success" ? (
							<div className="text-center py-4">
								<CheckCircle className="h-12 w-12 text-emerald-500 mx-auto mb-4" />
								<p className="text-sm text-muted-foreground mb-4">{message}</p>
								<Button asChild variant="outline" className="w-full">
									<Link href="/login">Back to Login</Link>
								</Button>
							</div>
						) : (
							<form onSubmit={handleSubmit} className="space-y-4">
								{status === "error" && (
									<div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2">
										<AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
										<p className="text-sm text-destructive">{message}</p>
									</div>
								)}

								<div className="space-y-2">
									<label htmlFor="email" className="block text-sm font-medium">
										Email
									</label>
									<Input
										id="email"
										type="email"
										value={email}
										onChange={(e) => setEmail(e.target.value)}
										required
										disabled={status === "loading"}
										placeholder="you@example.com"
									/>
								</div>

								<Button type="submit" disabled={status === "loading"} className="w-full">
									{status === "loading" ? (
										<>
											<Loader2 className="h-4 w-4 animate-spin mr-2" />
											Sending...
										</>
									) : (
										<>
											<Mail className="h-4 w-4 mr-2" />
											Send Verification Link
										</>
									)}
								</Button>
							</form>
						)}

						<div className="mt-6 text-center">
							<p className="text-sm text-muted-foreground">
								Remember your password?{" "}
								<Link href="/login" className="font-medium text-primary hover:underline">
									Sign in
								</Link>
							</p>
						</div>
					</CardContent>
				</Card>
			</div>
		</div>
	);
}

"use client";

import { AlertCircle, CheckCircle, KeyRound, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

function ResetPasswordForm() {
	const searchParams = useSearchParams();
	const token = searchParams.get("token");

	const [newPassword, setNewPassword] = useState("");
	const [confirmPassword, setConfirmPassword] = useState("");
	const [status, setStatus] = useState<
		"idle" | "loading" | "success" | "error" | "no_token"
	>("idle");
	const [message, setMessage] = useState("");

	useEffect(() => {
		if (!token) {
			setStatus("no_token");
		}
	}, [token]);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		setMessage("");

		// Validate passwords match
		if (newPassword !== confirmPassword) {
			setStatus("error");
			setMessage("Passwords do not match");
			return;
		}

		// Validate password length
		if (newPassword.length < 6) {
			setStatus("error");
			setMessage("Password must be at least 6 characters");
			return;
		}

		setStatus("loading");

		try {
			const response = await fetch(`${API_BASE_URL}/api/reset-password`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ token, new_password: newPassword }),
			});

			const data = await response.json();

			if (response.ok) {
				setStatus("success");
				setMessage(data.message);
			} else {
				setStatus("error");
				setMessage(data.detail || "Failed to reset password");
			}
		} catch (_error) {
			setStatus("error");
			setMessage("Network error. Please try again.");
		}
	};

	if (status === "no_token") {
		return (
			<div className="text-center py-4">
				<AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
				<p className="text-sm text-muted-foreground mb-4">
					Invalid or missing reset token. Please request a new password reset
					link.
				</p>
				<Button asChild variant="outline" className="w-full">
					<Link href="/forgot-password">Request New Link</Link>
				</Button>
			</div>
		);
	}

	if (status === "success") {
		return (
			<div className="text-center py-4">
				<CheckCircle className="h-12 w-12 text-emerald-500 mx-auto mb-4" />
				<p className="text-sm text-muted-foreground mb-4">{message}</p>
				<Button asChild className="w-full">
					<Link href="/login">Sign In</Link>
				</Button>
			</div>
		);
	}

	return (
		<form onSubmit={handleSubmit} className="space-y-4">
			{status === "error" && (
				<div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2">
					<AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
					<p className="text-sm text-destructive">{message}</p>
				</div>
			)}

			<div className="space-y-2">
				<label htmlFor="newPassword" className="block text-sm font-medium">
					New Password
				</label>
				<Input
					id="newPassword"
					type="password"
					value={newPassword}
					onChange={(e) => setNewPassword(e.target.value)}
					required
					disabled={status === "loading"}
					placeholder="Enter new password"
					minLength={6}
				/>
			</div>

			<div className="space-y-2">
				<label htmlFor="confirmPassword" className="block text-sm font-medium">
					Confirm Password
				</label>
				<Input
					id="confirmPassword"
					type="password"
					value={confirmPassword}
					onChange={(e) => setConfirmPassword(e.target.value)}
					required
					disabled={status === "loading"}
					placeholder="Confirm new password"
					minLength={6}
				/>
			</div>

			<Button type="submit" disabled={status === "loading"} className="w-full">
				{status === "loading" ? (
					<>
						<Loader2 className="h-4 w-4 animate-spin mr-2" />
						Resetting...
					</>
				) : (
					<>
						<KeyRound className="h-4 w-4 mr-2" />
						Reset Password
					</>
				)}
			</Button>
		</form>
	);
}

export default function ResetPasswordPage() {
	return (
		<div className="flex items-center justify-center min-h-screen p-4 bg-background">
			<div className="w-full max-w-md">
				<Card>
					<CardHeader>
						<div className="flex items-center gap-2 mb-2">
							<KeyRound className="h-6 w-6 text-primary" />
							<CardTitle className="text-2xl">Reset Password</CardTitle>
						</div>
						<CardDescription>Enter your new password below.</CardDescription>
					</CardHeader>
					<CardContent>
						<Suspense
							fallback={
								<div className="text-center py-4">
									<Loader2 className="h-6 w-6 animate-spin mx-auto" />
								</div>
							}
						>
							<ResetPasswordForm />
						</Suspense>

						<div className="mt-6 text-center">
							<p className="text-sm text-muted-foreground">
								Remember your password?{" "}
								<Link
									href="/login"
									className="font-medium text-primary hover:underline"
								>
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

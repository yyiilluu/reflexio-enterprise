"use client";

import {
	AlertCircle,
	Check,
	CheckCircle,
	Eye,
	EyeOff,
	Github,
	Loader2,
	LogIn,
	Mail,
	UserPlus,
	X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GoogleIcon } from "@/components/icons/oauth-icons";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth-context";

export function AuthPageContent({ defaultTab }: { defaultTab: "login" | "register" }) {
	// Shared state
	const [activeTab, setActiveTab] = useState(defaultTab);
	const [oauthProviders, setOauthProviders] = useState<string[]>([]);
	const [invitationRequired, setInvitationRequired] = useState(false);
	const { login, register, isAuthenticated, isSelfHost } = useAuth();
	const router = useRouter();
	const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

	// Login state
	const [loginEmail, setLoginEmail] = useState("");
	const [loginPassword, setLoginPassword] = useState("");
	const [loginError, setLoginError] = useState("");
	const [loginLoading, setLoginLoading] = useState(false);

	// Register state
	const [regEmail, setRegEmail] = useState("");
	const [regPassword, setRegPassword] = useState("");
	const [confirmPassword, setConfirmPassword] = useState("");
	const [invitationCode, setInvitationCode] = useState("");
	const [regError, setRegError] = useState("");
	const [regLoading, setRegLoading] = useState(false);
	const [showPasswords, setShowPasswords] = useState(false);
	const [showVerificationNotice, setShowVerificationNotice] = useState(false);
	const [showAutoVerifiedNotice, setShowAutoVerifiedNotice] = useState(false);

	// Password strength checks
	const passwordChecks = {
		minLength: regPassword.length >= 12,
		hasUppercase: /[A-Z]/.test(regPassword),
		hasLowercase: /[a-z]/.test(regPassword),
		hasNumber: /[0-9]/.test(regPassword),
		hasSpecial: /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`~]/.test(regPassword),
	};
	const allChecksPassed = Object.values(passwordChecks).every(Boolean);

	// Fetch registration config
	useEffect(() => {
		fetch(`${API_BASE_URL}/api/registration-config`)
			.then((res) => res.json())
			.then((data) => {
				if (data.invitation_code_required) {
					setInvitationRequired(true);
				}
				if (data.oauth_providers) {
					setOauthProviders(data.oauth_providers);
				}
			})
			.catch(() => {});
	}, [API_BASE_URL]);

	// Redirect if already authenticated or in self-host mode
	useEffect(() => {
		if (isSelfHost || isAuthenticated) {
			router.push("/");
		}
	}, [isAuthenticated, isSelfHost, router]);

	// Sync tab with URL
	const handleTabChange = (value: string) => {
		const tab = value === "register" ? "register" : "login";
		setActiveTab(tab);
		router.replace(tab === "register" ? "/register" : "/login");
	};

	const handleLogin = async (e: React.FormEvent) => {
		e.preventDefault();
		setLoginError("");
		setLoginLoading(true);
		try {
			const result = await login(loginEmail, loginPassword);
			if (result.success) {
				router.push("/");
			} else {
				setLoginError(result.error || "Login failed");
			}
		} catch (_err) {
			setLoginError("An unexpected error occurred");
		} finally {
			setLoginLoading(false);
		}
	};

	const handleRegister = async (e: React.FormEvent) => {
		e.preventDefault();
		setRegError("");
		if (regPassword !== confirmPassword) {
			setRegError("Passwords do not match");
			return;
		}
		setRegLoading(true);
		try {
			const result = await register(regEmail, regPassword, invitationCode || undefined);
			if (result.success) {
				if (result.autoVerified) {
					setShowAutoVerifiedNotice(true);
				} else {
					setShowVerificationNotice(true);
				}
			} else {
				setRegError(result.error || "Registration failed");
			}
		} catch (_err) {
			setRegError("An unexpected error occurred");
		} finally {
			setRegLoading(false);
		}
	};

	if (isSelfHost) {
		return null;
	}

	// Auto-verified success notice
	if (showAutoVerifiedNotice) {
		return (
			<div className="flex items-center justify-center min-h-screen p-4 bg-background">
				<div className="w-full max-w-md">
					<Card>
						<div className="p-6 text-center">
							<div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
								<CheckCircle className="h-8 w-8 text-primary" />
							</div>
							<h2 className="text-2xl font-semibold tracking-tight mb-2">Account Created</h2>
							<p className="text-sm text-muted-foreground mb-4">
								Your account has been verified automatically
							</p>
							<p className="font-medium text-lg mb-4">{regEmail}</p>
							<div className="bg-muted/50 rounded-lg p-4 mb-6">
								<div className="flex items-start gap-3 text-left">
									<CheckCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
									<p className="text-sm text-muted-foreground">
										Your account is ready. You can now sign in with your credentials.
									</p>
								</div>
							</div>
							<Button
								className="w-full"
								onClick={() => {
									setShowAutoVerifiedNotice(false);
									setActiveTab("login");
									router.replace("/login");
								}}
							>
								Go to Sign In
							</Button>
						</div>
					</Card>
				</div>
			</div>
		);
	}

	// Verification email notice
	if (showVerificationNotice) {
		return (
			<div className="flex items-center justify-center min-h-screen p-4 bg-background">
				<div className="w-full max-w-md">
					<Card>
						<div className="p-6 text-center">
							<div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
								<Mail className="h-8 w-8 text-primary" />
							</div>
							<h2 className="text-2xl font-semibold tracking-tight mb-2">Check Your Email</h2>
							<p className="text-sm text-muted-foreground mb-4">
								We've sent a verification link to
							</p>
							<p className="font-medium text-lg mb-4">{regEmail}</p>
							<div className="bg-muted/50 rounded-lg p-4 mb-6">
								<div className="flex items-start gap-3 text-left">
									<CheckCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
									<div className="text-sm text-muted-foreground">
										<p className="mb-2">
											Please click the link in the email to verify your account.
										</p>
										<p>
											The link will expire in{" "}
											<span className="font-medium text-foreground">7 days</span>.
										</p>
									</div>
								</div>
							</div>
							<div className="space-y-3">
								<Button
									className="w-full"
									onClick={() => {
										setShowVerificationNotice(false);
										setActiveTab("login");
										router.replace("/login");
									}}
								>
									Go to Sign In
								</Button>
								<p className="text-sm text-muted-foreground">
									Didn't receive the email?{" "}
									<Link href="/resend-verification" className="text-primary hover:underline">
										Resend verification link
									</Link>
								</p>
							</div>
						</div>
					</Card>
				</div>
			</div>
		);
	}

	const isLogin = activeTab === "login";

	return (
		<div className="flex items-start justify-center min-h-screen pt-24 px-4 pb-4 bg-background">
			<div className="w-full max-w-md">
				<div className="flex items-center justify-center gap-3 mb-8">
					<div className="h-12 w-12 rounded-xl bg-white flex items-center justify-center shadow-lg shadow-indigo-500/25 p-1.5">
						<Image src="/reflexio_fav.svg" alt="Reflexio" width={36} height={36} />
					</div>
					<span className="font-bold text-3xl text-slate-800">Reflexio</span>
				</div>
				<Card>
					<CardContent className="pt-6">
						<Tabs value={activeTab} onValueChange={handleTabChange}>
							<TabsList className="w-full grid grid-cols-2 mb-6">
								<TabsTrigger value="login">
									<LogIn className="h-4 w-4 mr-1.5" />
									Sign In
								</TabsTrigger>
								<TabsTrigger value="register">
									<UserPlus className="h-4 w-4 mr-1.5" />
									Create Account
								</TabsTrigger>
							</TabsList>

							{/* Sign In Tab */}
							<TabsContent value="login">
								<form onSubmit={handleLogin} className="space-y-4">
									{loginError && (
										<div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2">
											<AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
											<p className="text-sm text-destructive">{loginError}</p>
										</div>
									)}
									<div className="space-y-2">
										<label htmlFor="login-email" className="block text-sm font-medium">
											Email
										</label>
										<Input
											id="login-email"
											type="text"
											value={loginEmail}
											onChange={(e) => setLoginEmail(e.target.value)}
											required
											autoComplete="username"
											disabled={loginLoading}
											placeholder="you@example.com"
										/>
									</div>
									<div className="space-y-2">
										<label htmlFor="login-password" className="block text-sm font-medium">
											Password
										</label>
										<Input
											id="login-password"
											type="password"
											value={loginPassword}
											onChange={(e) => setLoginPassword(e.target.value)}
											required
											autoComplete="current-password"
											disabled={loginLoading}
											placeholder="••••••••"
										/>
										<div className="text-right">
											<Link
												href="/forgot-password"
												className="text-sm text-primary hover:underline"
											>
												Forgot password?
											</Link>
										</div>
									</div>
									<Button type="submit" disabled={loginLoading} className="w-full">
										{loginLoading ? (
											<>
												<Loader2 className="h-4 w-4 animate-spin mr-2" />
												Signing in...
											</>
										) : (
											<>
												<LogIn className="h-4 w-4 mr-2" />
												Sign In
											</>
										)}
									</Button>
								</form>
							</TabsContent>

							{/* Create Account Tab */}
							<TabsContent value="register">
								{/* Invitation Code (shown at top when required) */}
								{invitationRequired && (
									<div className="space-y-2 mb-4">
										<label htmlFor="invitationCodeTop" className="block text-sm font-medium">
											Invitation Code
										</label>
										<Input
											id="invitationCodeTop"
											type="text"
											value={invitationCode}
											onChange={(e) => {
												const sanitized = e.target.value
													.trimStart()
													.replace(/\s+$/, "")
													.toUpperCase()
													.replace(/[^A-Z0-9-]/g, "");
												setInvitationCode(sanitized);
											}}
											required
											autoComplete="off"
											disabled={regLoading}
											placeholder="REFLEXIO-XXXX-XXXX"
										/>
									</div>
								)}

								<form onSubmit={handleRegister} className="space-y-4">
									{regError && (
										<div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2">
											<AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
											<p className="text-sm text-destructive">{regError}</p>
										</div>
									)}
									<div className="space-y-2">
										<label htmlFor="reg-email" className="block text-sm font-medium">
											Email
										</label>
										<Input
											id="reg-email"
											type="text"
											value={regEmail}
											onChange={(e) => setRegEmail(e.target.value)}
											required
											autoComplete="email"
											disabled={regLoading}
											placeholder="you@example.com"
										/>
									</div>
									<div className="space-y-2">
										<label htmlFor="reg-password" className="block text-sm font-medium">
											Password
										</label>
										<div className="relative">
											<Input
												id="reg-password"
												type={showPasswords ? "text" : "password"}
												value={regPassword}
												onChange={(e) => setRegPassword(e.target.value)}
												required
												autoComplete="new-password"
												disabled={regLoading}
												placeholder="••••••••"
												className="pr-10"
											/>
											<Button
												type="button"
												variant="ghost"
												size="icon"
												className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
												onClick={() => setShowPasswords(!showPasswords)}
												tabIndex={-1}
											>
												{showPasswords ? (
													<EyeOff className="h-4 w-4 text-muted-foreground" />
												) : (
													<Eye className="h-4 w-4 text-muted-foreground" />
												)}
											</Button>
										</div>
										{regPassword.length > 0 && (
											<ul className="space-y-1 text-sm mt-2">
												{(
													[
														[passwordChecks.minLength, "At least 12 characters"],
														[passwordChecks.hasUppercase, "One uppercase letter (A-Z)"],
														[passwordChecks.hasLowercase, "One lowercase letter (a-z)"],
														[passwordChecks.hasNumber, "One number (0-9)"],
														[passwordChecks.hasSpecial, "One special character (!@#$%^&*)"],
													] as [boolean, string][]
												).map(([passed, label]) => (
													<li key={label} className="flex items-center gap-2">
														{passed ? (
															<Check className="h-4 w-4 text-green-500" />
														) : (
															<X className="h-4 w-4 text-muted-foreground" />
														)}
														<span className={passed ? "text-green-600" : "text-muted-foreground"}>
															{label}
														</span>
													</li>
												))}
											</ul>
										)}
									</div>
									<div className="space-y-2">
										<label htmlFor="confirmPassword" className="block text-sm font-medium">
											Confirm Password
										</label>
										<div className="relative">
											<Input
												id="confirmPassword"
												type={showPasswords ? "text" : "password"}
												value={confirmPassword}
												onChange={(e) => setConfirmPassword(e.target.value)}
												required
												autoComplete="new-password"
												disabled={regLoading}
												placeholder="••••••••"
												className="pr-10"
											/>
											<Button
												type="button"
												variant="ghost"
												size="icon"
												className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
												onClick={() => setShowPasswords(!showPasswords)}
												tabIndex={-1}
											>
												{showPasswords ? (
													<EyeOff className="h-4 w-4 text-muted-foreground" />
												) : (
													<Eye className="h-4 w-4 text-muted-foreground" />
												)}
											</Button>
										</div>
									</div>

									{/* Invitation Code (optional, in form) */}
									{!invitationRequired && (
										<div className="space-y-2">
											<label htmlFor="invitationCode" className="block text-sm font-medium">
												Invitation Code{" "}
												<span className="text-muted-foreground font-normal">(optional)</span>
											</label>
											<Input
												id="invitationCode"
												type="text"
												value={invitationCode}
												onChange={(e) => {
													const sanitized = e.target.value
														.trimStart()
														.replace(/\s+$/, "")
														.toUpperCase()
														.replace(/[^A-Z0-9-]/g, "");
													setInvitationCode(sanitized);
												}}
												autoComplete="off"
												disabled={regLoading}
												placeholder="REFLEXIO-XXXX-XXXX"
											/>
										</div>
									)}

									<Button
										type="submit"
										disabled={regLoading || !allChecksPassed}
										className="w-full"
									>
										{regLoading ? (
											<>
												<Loader2 className="h-4 w-4 animate-spin mr-2" />
												Creating account...
											</>
										) : (
											<>
												<UserPlus className="h-4 w-4 mr-2" />
												Create Account
											</>
										)}
									</Button>
								</form>
							</TabsContent>
						</Tabs>

						{/* OAuth Buttons (shared, below tabs) */}
						{oauthProviders.length > 0 && (
							<div className="mt-6 space-y-4">
								<div className="relative">
									<div className="absolute inset-0 flex items-center">
										<Separator className="w-full" />
									</div>
									<div className="relative flex justify-center text-xs uppercase">
										<span className="bg-card px-2 text-muted-foreground">Or continue with</span>
									</div>
								</div>
								<div className="grid gap-2">
									{oauthProviders.includes("google") && (
										<Button
											variant="outline"
											className="w-full"
											disabled={isLogin ? false : invitationRequired && !invitationCode}
											onClick={() => {
												if (isLogin) {
													window.location.href = `${API_BASE_URL}/api/auth/google/login`;
												} else {
													const params = invitationCode
														? `?invitation_code=${encodeURIComponent(invitationCode)}`
														: "";
													window.location.href = `${API_BASE_URL}/api/auth/google/register${params}`;
												}
											}}
										>
											<GoogleIcon className="h-4 w-4 mr-2" />
											{isLogin ? "Sign in with Google" : "Sign up with Google"}
										</Button>
									)}
									{oauthProviders.includes("github") && (
										<Button
											variant="outline"
											className="w-full"
											disabled={isLogin ? false : invitationRequired && !invitationCode}
											onClick={() => {
												if (isLogin) {
													window.location.href = `${API_BASE_URL}/api/auth/github/login`;
												} else {
													const params = invitationCode
														? `?invitation_code=${encodeURIComponent(invitationCode)}`
														: "";
													window.location.href = `${API_BASE_URL}/api/auth/github/register${params}`;
												}
											}}
										>
											<Github className="h-4 w-4 mr-2" />
											{isLogin ? "Sign in with GitHub" : "Sign up with GitHub"}
										</Button>
									)}
								</div>
							</div>
						)}
					</CardContent>
				</Card>
			</div>
		</div>
	);
}

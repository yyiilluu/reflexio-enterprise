"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { GoogleIcon } from "@/components/icons/oauth-icons"
import { UserPlus, Loader2, AlertCircle, Mail, CheckCircle, Eye, EyeOff, Check, X, Github } from "lucide-react"
import Link from "next/link"

export default function RegisterPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [invitationCode, setInvitationCode] = useState("")
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [showVerificationNotice, setShowVerificationNotice] = useState(false)
  const [showAutoVerifiedNotice, setShowAutoVerifiedNotice] = useState(false)
  const [showPasswords, setShowPasswords] = useState(false)
  const [invitationRequired, setInvitationRequired] = useState(false)
  const [oauthProviders, setOauthProviders] = useState<string[]>([])
  const { register, isAuthenticated, isSelfHost } = useAuth()
  const router = useRouter()

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || ""

  // Fetch registration config to determine if invitation code is required and OAuth providers
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/registration-config`)
      .then((res) => res.json())
      .then((data) => {
        if (data.invitation_code_required) {
          setInvitationRequired(true)
        }
        if (data.oauth_providers) {
          setOauthProviders(data.oauth_providers)
        }
      })
      .catch(() => {
        // Default to optional on error
      })
  }, [API_BASE_URL])

  const passwordChecks = {
    minLength: password.length >= 12,
    hasUppercase: /[A-Z]/.test(password),
    hasLowercase: /[a-z]/.test(password),
    hasNumber: /[0-9]/.test(password),
    hasSpecial: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?`~]/.test(password),
  }
  const allChecksPassed = Object.values(passwordChecks).every(Boolean)


  // Redirect if already authenticated or in self-host mode
  useEffect(() => {
    if (isSelfHost) {
      router.push("/")
    } else if (isAuthenticated) {
      router.push("/")
    }
  }, [isAuthenticated, isSelfHost, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    // Validate passwords match
    if (password !== confirmPassword) {
      setError("Passwords do not match")
      return
    }

    setIsLoading(true)

    try {
      const result = await register(email, password, invitationCode || undefined)
      if (result.success) {
        if (result.autoVerified) {
          // Auto-verified via invitation code — show success notice
          setShowAutoVerifiedNotice(true)
        } else {
          // Show verification notice instead of redirecting
          setShowVerificationNotice(true)
        }
      } else {
        setError(result.error || "Registration failed")
      }
    } catch {
      setError("An unexpected error occurred")
    } finally {
      setIsLoading(false)
    }
  }

  // Don't render anything if in self-host mode (will redirect)
  if (isSelfHost) {
    return null
  }

  // Show auto-verified success notice (invitation code flow)
  if (showAutoVerifiedNotice) {
    return (
      <div className="flex items-center justify-center min-h-screen p-4 bg-background">
        <div className="w-full max-w-md">
          <Card>
            <CardHeader className="text-center">
              <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                <CheckCircle className="h-8 w-8 text-primary" />
              </div>
              <CardTitle className="text-2xl">Account Created</CardTitle>
              <CardDescription>
                Your account has been verified automatically
              </CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <p className="font-medium text-lg mb-4">{email}</p>
              <div className="bg-muted/50 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3 text-left">
                  <CheckCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-muted-foreground">
                    Your account is ready. You can now sign in with your credentials.
                  </p>
                </div>
              </div>
              <Button asChild className="w-full">
                <Link href="/login">Go to Login</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  // Show verification notice after successful registration
  if (showVerificationNotice) {
    return (
      <div className="flex items-center justify-center min-h-screen p-4 bg-background">
        <div className="w-full max-w-md">
          <Card>
            <CardHeader className="text-center">
              <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                <Mail className="h-8 w-8 text-primary" />
              </div>
              <CardTitle className="text-2xl">Check Your Email</CardTitle>
              <CardDescription>
                We&apos;ve sent a verification link to
              </CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <p className="font-medium text-lg mb-4">{email}</p>
              <div className="bg-muted/50 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3 text-left">
                  <CheckCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-muted-foreground">
                    <p className="mb-2">
                      Please click the link in the email to verify your account.
                    </p>
                    <p>
                      The link will expire in <span className="font-medium text-foreground">7 days</span>.
                    </p>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <Button asChild className="w-full">
                  <Link href="/login">Go to Login</Link>
                </Button>
                <p className="text-sm text-muted-foreground">
                  Didn&apos;t receive the email?{" "}
                  <Link href="/resend-verification" className="text-primary hover:underline">
                    Resend verification link
                  </Link>
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen p-4 bg-background">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 mb-2">
              <UserPlus className="h-6 w-6 text-primary" />
              <CardTitle className="text-2xl">Create Account</CardTitle>
            </div>
            <CardDescription>
              Sign up to get started with Reflexio
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Error Alert */}
            {error && (
              <div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2 mb-4">
                <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            {/* Invitation Code Field (shown at top when required) */}
            {invitationRequired && (
              <div className="space-y-2 mb-4">
                <label
                  htmlFor="invitationCodeTop"
                  className="block text-sm font-medium"
                >
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
                      .replace(/[^A-Z0-9\-]/g, "")
                    setInvitationCode(sanitized)
                  }}
                  required
                  autoComplete="off"
                  disabled={isLoading}
                  placeholder="REFLEXIO-XXXX-XXXX"
                />
              </div>
            )}

            {/* OAuth Buttons */}
            {oauthProviders.length > 0 && (
              <div className="space-y-3 mb-4">
                <div className="grid gap-2">
                  {oauthProviders.includes("google") && (
                    <Button
                      variant="outline"
                      className="w-full"
                      disabled={invitationRequired && !invitationCode}
                      onClick={() => {
                        const params = invitationCode ? `?invitation_code=${encodeURIComponent(invitationCode)}` : ""
                        window.location.href = `${API_BASE_URL}/api/auth/google/register${params}`
                      }}
                    >
                      <GoogleIcon className="h-4 w-4 mr-2" />
                      Sign up with Google
                    </Button>
                  )}
                  {oauthProviders.includes("github") && (
                    <Button
                      variant="outline"
                      className="w-full"
                      disabled={invitationRequired && !invitationCode}
                      onClick={() => {
                        const params = invitationCode ? `?invitation_code=${encodeURIComponent(invitationCode)}` : ""
                        window.location.href = `${API_BASE_URL}/api/auth/github/register${params}`
                      }}
                    >
                      <Github className="h-4 w-4 mr-2" />
                      Sign up with GitHub
                    </Button>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <Separator className="w-full" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">
                      Or register with email
                    </span>
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email Field */}
              <div className="space-y-2">
                <label
                  htmlFor="email"
                  className="block text-sm font-medium"
                >
                  Email
                </label>
                <Input
                  id="email"
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  disabled={isLoading}
                  placeholder="you@example.com"
                />
              </div>

              {/* Password Field */}
              <div className="space-y-2">
                <label
                  htmlFor="password"
                  className="block text-sm font-medium"
                >
                  Password
                </label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPasswords ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    disabled={isLoading}
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
                {password.length > 0 && (
                  <ul className="space-y-1 text-sm mt-2">
                    {([
                      [passwordChecks.minLength, "At least 12 characters"],
                      [passwordChecks.hasUppercase, "One uppercase letter (A-Z)"],
                      [passwordChecks.hasLowercase, "One lowercase letter (a-z)"],
                      [passwordChecks.hasNumber, "One number (0-9)"],
                      [passwordChecks.hasSpecial, "One special character (!@#$%^&*)"],
                    ] as [boolean, string][]).map(([passed, label]) => (
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

              {/* Confirm Password Field */}
              <div className="space-y-2">
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium"
                >
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
                    disabled={isLoading}
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

              {/* Invitation Code Field (only show in form when optional) */}
              {!invitationRequired && (
                <div className="space-y-2">
                  <label
                    htmlFor="invitationCode"
                    className="block text-sm font-medium"
                  >
                    Invitation Code <span className="text-muted-foreground font-normal">(optional)</span>
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
                        .replace(/[^A-Z0-9\-]/g, "")
                      setInvitationCode(sanitized)
                    }}
                    autoComplete="off"
                    disabled={isLoading}
                    placeholder="REFLEXIO-XXXX-XXXX"
                  />
                </div>
              )}

              {/* Submit Button */}
              <Button
                type="submit"
                disabled={isLoading || !allChecksPassed}
                className="w-full"
              >
                {isLoading ? (
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

            {/* Login Link */}
            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Already have an account?{" "}
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
  )
}

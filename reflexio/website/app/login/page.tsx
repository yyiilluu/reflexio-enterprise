"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { GoogleIcon } from "@/components/icons/oauth-icons"
import { LogIn, Loader2, AlertCircle, Github } from "lucide-react"
import Link from "next/link"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [oauthProviders, setOauthProviders] = useState<string[]>([])
  const { login, isAuthenticated, isSelfHost } = useAuth()
  const router = useRouter()

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || ""

  // Fetch OAuth providers config
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/registration-config`)
      .then((res) => res.json())
      .then((data) => {
        if (data.oauth_providers) {
          setOauthProviders(data.oauth_providers)
        }
      })
      .catch(() => {})
  }, [API_BASE_URL])

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
    setIsLoading(true)

    try {
      const result = await login(email, password)
      if (result.success) {
        router.push("/")
      } else {
        setError(result.error || "Login failed")
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

  return (
    <div className="flex items-center justify-center min-h-screen p-4 bg-background">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 mb-2">
              <LogIn className="h-6 w-6 text-primary" />
              <CardTitle className="text-2xl">Sign In</CardTitle>
            </div>
            <CardDescription>
              Enter your credentials to access your account
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Error Alert */}
              {error && (
                <div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex items-start gap-2">
                  <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-destructive">{error}</p>
                </div>
              )}

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
                  autoComplete="username"
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
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  disabled={isLoading}
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

              {/* Submit Button */}
              <Button
                type="submit"
                disabled={isLoading}
                className="w-full"
              >
                {isLoading ? (
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

            {/* OAuth Buttons */}
            {oauthProviders.length > 0 && (
              <div className="mt-4 space-y-4">
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <Separator className="w-full" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">
                      Or continue with
                    </span>
                  </div>
                </div>
                <div className="grid gap-2">
                  {oauthProviders.includes("google") && (
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => {
                        window.location.href = `${API_BASE_URL}/api/auth/google/login`
                      }}
                    >
                      <GoogleIcon className="h-4 w-4 mr-2" />
                      Sign in with Google
                    </Button>
                  )}
                  {oauthProviders.includes("github") && (
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => {
                        window.location.href = `${API_BASE_URL}/api/auth/github/login`
                      }}
                    >
                      <Github className="h-4 w-4 mr-2" />
                      Sign in with GitHub
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Register Link */}
            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Don&apos;t have an account?{" "}
                <Link
                  href="/register"
                  className="font-medium text-primary hover:underline"
                >
                  Sign up
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

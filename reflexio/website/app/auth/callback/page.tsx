"use client"

import { Suspense, useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { AlertCircle, Loader2 } from "lucide-react"
import Link from "next/link"
import Cookies from "js-cookie"

const TOKEN_COOKIE_NAME = "reflexio_token"
const USER_EMAIL_COOKIE_NAME = "reflexio_user_email"
const FEATURE_FLAGS_KEY = "reflexio_feature_flags"

const ERROR_MESSAGES: Record<string, { message: string; link: string; linkText: string }> = {
  email_exists: {
    message: "An account with this email already exists. Please sign in with your email and password.",
    link: "/login",
    linkText: "Go to Login",
  },
  no_account: {
    message: "No account found with this email. Please create an account first.",
    link: "/register",
    linkText: "Go to Register",
  },
  wrong_provider: {
    message: "This email is registered with a different sign-in method. Please use that method to log in.",
    link: "/login",
    linkText: "Go to Login",
  },
  invalid_invitation: {
    message: "Invalid, expired, or already used invitation code.",
    link: "/register",
    linkText: "Go to Register",
  },
  invitation_required: {
    message: "An invitation code is required to register.",
    link: "/register",
    linkText: "Go to Register",
  },
  oauth_failed: {
    message: "Authentication failed. Please try again.",
    link: "/login",
    linkText: "Try Again",
  },
}

function AuthCallbackContent() {
  const searchParams = useSearchParams()

  const [status] = useState<"loading" | "error">(() => {
    const error = searchParams.get("error")
    if (error) return "error"
    const token = searchParams.get("token")
    const email = searchParams.get("email")
    if (token && email) return "loading"
    return "error"
  })

  const [errorInfo] = useState(() => {
    const error = searchParams.get("error")
    if (error) return ERROR_MESSAGES[error] || ERROR_MESSAGES.oauth_failed
    return ERROR_MESSAGES.oauth_failed
  })

  useEffect(() => {
    const token = searchParams.get("token")
    const email = searchParams.get("email")
    const featureFlags = searchParams.get("feature_flags")

    if (token && email) {
      // Store token and email in cookies (7 days expiry)
      Cookies.set(TOKEN_COOKIE_NAME, token, { expires: 7 })
      Cookies.set(USER_EMAIL_COOKIE_NAME, email, { expires: 7 })

      // Store feature flags in localStorage
      if (featureFlags) {
        try {
          localStorage.setItem(FEATURE_FLAGS_KEY, featureFlags)
        } catch {
          // Ignore localStorage errors
        }
      }

      // Force full page reload to pick up cookies in AuthProvider
      window.location.href = "/"
    }
  }, [searchParams])

  if (status === "loading") {
    return (
      <div className="flex items-center justify-center min-h-screen p-4 bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Completing sign-in...</p>
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
              <AlertCircle className="h-6 w-6 text-destructive" />
              <CardTitle className="text-xl">Authentication Error</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-destructive/10 border border-destructive/20 rounded-md p-3">
              <p className="text-sm text-destructive">{errorInfo.message}</p>
            </div>
            <Button asChild className="w-full">
              <Link href={errorInfo.link}>{errorInfo.linkText}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen p-4 bg-background">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        </div>
      }
    >
      <AuthCallbackContent />
    </Suspense>
  )
}

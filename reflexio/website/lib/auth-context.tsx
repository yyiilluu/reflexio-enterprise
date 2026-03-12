"use client"

import React, { createContext, useContext, useState, useEffect } from "react"
import Cookies from "js-cookie"
import { useRouter } from "next/navigation"

// Use empty string to make requests relative (proxied through Next.js rewrites)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || ""
const SELF_HOST = process.env.NEXT_PUBLIC_SELF_HOST === "true"
const TOKEN_COOKIE_NAME = "reflexio_token"
const USER_EMAIL_COOKIE_NAME = "reflexio_user_email"
const FEATURE_FLAGS_KEY = "reflexio_feature_flags"

interface AuthContextType {
  isAuthenticated: boolean
  userEmail: string | null
  token: string | null
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>
  register: (email: string, password: string, invitationCode?: string) => Promise<{ success: boolean; autoVerified?: boolean; error?: string }>
  logout: () => Promise<void>
  isSelfHost: boolean
  featureFlags: Record<string, boolean>
  isFeatureEnabled: (name: string) => boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()

  // Initialize auth state from cookies/localStorage
  useEffect(() => {
    if (SELF_HOST) {
      // In self-host mode, no authentication needed, all features enabled
      setIsLoading(false)
      return
    }

    const storedToken = Cookies.get(TOKEN_COOKIE_NAME)
    const storedEmail = Cookies.get(USER_EMAIL_COOKIE_NAME)

    if (storedToken) {
      setToken(storedToken)
      setUserEmail(storedEmail || null)
    }

    // Restore feature flags from localStorage
    try {
      const storedFlags = localStorage.getItem(FEATURE_FLAGS_KEY)
      if (storedFlags) {
        setFeatureFlags(JSON.parse(storedFlags))
      }
    } catch {
      // Ignore parse errors
    }

    setIsLoading(false)
  }, [])

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      // Use FormData to match OAuth2PasswordRequestForm format
      const formData = new URLSearchParams()
      formData.append("username", email)
      formData.append("password", password)

      const response = await fetch(`${API_BASE_URL}/token`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Login failed" }))
        return { success: false, error: error.detail || "Login failed" }
      }

      const data = await response.json()
      const apiKey = data.api_key || data.access_token

      if (!apiKey) {
        return { success: false, error: "No token received" }
      }

      // Store token and email in cookies (7 days expiry)
      Cookies.set(TOKEN_COOKIE_NAME, apiKey, { expires: 7 })
      Cookies.set(USER_EMAIL_COOKIE_NAME, email, { expires: 7 })

      // Store feature flags
      const flags = data.feature_flags || {}
      localStorage.setItem(FEATURE_FLAGS_KEY, JSON.stringify(flags))
      setFeatureFlags(flags)

      setToken(apiKey)
      setUserEmail(email)

      return { success: true }
    } catch (error) {
      console.error("Login error:", error)
      return { success: false, error: "Network error" }
    }
  }

  const register = async (email: string, password: string, invitationCode?: string): Promise<{ success: boolean; autoVerified?: boolean; error?: string }> => {
    try {
      // Use FormData to match OAuth2PasswordRequestForm format
      const formData = new URLSearchParams()
      formData.append("username", email)
      formData.append("password", password)
      if (invitationCode) {
        formData.append("invitation_code", invitationCode)
      }

      const response = await fetch(`${API_BASE_URL}/api/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData,
      })

      if (!response.ok) {
        let message = "Registration failed"
        try {
          const error = await response.json()
          if (typeof error.detail === "string") {
            message = error.detail
          } else if (Array.isArray(error.detail)) {
            message = error.detail.map((e: { msg?: string }) => e.msg || String(e)).join("; ")
          }
        } catch {
          if (response.statusText) {
            message = response.statusText
          }
        }
        return { success: false, error: message }
      }

      const data = await response.json()
      return { success: true, autoVerified: data.auto_verified === true }
    } catch (error) {
      console.error("Registration error:", error)
      return { success: false, error: "Network error" }
    }
  }

  const logout = async () => {
    // Call logout API to invalidate server-side cache
    try {
      if (token) {
        await fetch(`${API_BASE_URL}/api/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
      }
    } catch (error) {
      // Don't block logout if API call fails
      console.error('Failed to invalidate cache:', error)
    }

    // Remove cookies and localStorage
    Cookies.remove(TOKEN_COOKIE_NAME)
    Cookies.remove(USER_EMAIL_COOKIE_NAME)
    localStorage.removeItem(FEATURE_FLAGS_KEY)

    setToken(null)
    setUserEmail(null)
    setFeatureFlags({})

    // Redirect to landing page
    router.push("/")
  }

  const isFeatureEnabled = (name: string): boolean => {
    // In self-host mode, all features are enabled
    if (SELF_HOST) return true
    // If flag is not present, default to enabled (fail-open)
    return featureFlags[name] !== false
  }

  const value: AuthContextType = {
    isAuthenticated: SELF_HOST || !!token,
    userEmail,
    token,
    login,
    register,
    logout,
    isSelfHost: SELF_HOST,
    featureFlags,
    isFeatureEnabled,
  }

  // Show loading state while checking cookies
  if (isLoading) {
    return null
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}

// Helper function to get token for API calls
export function getAuthToken(): string | null {
  if (SELF_HOST) {
    return null
  }
  return Cookies.get(TOKEN_COOKIE_NAME) || null
}

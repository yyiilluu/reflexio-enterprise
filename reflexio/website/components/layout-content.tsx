"use client"

import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"
import { useAuth } from "@/lib/auth-context"
import { ResponsiveSidebar } from "@/components/responsive-sidebar"

export function LayoutContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { isAuthenticated, isSelfHost } = useAuth()

  // Hide sidebar on auth-related pages and landing page
  const authPages = ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/resend-verification"]
  const isAuthPage = authPages.includes(pathname)
  const isLandingPage = pathname === "/"

  // Only redirect to login for known protected routes, not unknown routes
  const protectedRoutes = ["/dashboard", "/profiles", "/interactions", "/feedbacks", "/evaluations", "/skills", "/settings"]
  const isProtectedRoute = protectedRoutes.some(route => pathname === route || pathname.startsWith(route + "/"))

  // Redirect to login if not authenticated and accessing a protected route
  useEffect(() => {
    if (isAuthPage || isLandingPage || isSelfHost) {
      return
    }

    if (!isAuthenticated && isProtectedRoute) {
      router.push("/login")
    }
  }, [isAuthenticated, isSelfHost, isAuthPage, isLandingPage, isProtectedRoute, pathname, router])

  if (isAuthPage || isLandingPage) {
    // Auth pages and landing page get full screen without sidebar
    return <>{children}</>
  }

  // For unknown routes, let Next.js render the not-found page
  if (!isProtectedRoute) {
    return <>{children}</>
  }

  // Don't render protected pages until auth check is complete
  if (!isSelfHost && !isAuthenticated) {
    return null
  }

  // Regular pages get sidebar layout
  return (
    <div className="flex h-screen overflow-hidden">
      <ResponsiveSidebar />
      <main className="flex-1 overflow-y-auto bg-background pt-16 md:pt-0">
        {children}
      </main>
    </div>
  )
}

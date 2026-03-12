/**
 * Route constants shared across layout, sidebar, and auth logic.
 */

export const AUTH_PAGES = [
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/resend-verification",
] as const

export const PROTECTED_ROUTES = [
  "/dashboard",
  "/profiles",
  "/interactions",
  "/feedbacks",
  "/evaluations",
  "/skills",
  "/settings",
  "/account",
] as const

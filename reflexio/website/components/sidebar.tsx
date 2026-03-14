"use client"

import Link from "next/link"
import Image from "next/image"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import {
  LayoutDashboard,
  Users,
  MessageSquare,
  CheckCircle,
  Settings,
  ChevronDown,
  ChevronRight,
  LogOut,
  LogIn,
  User,
  PanelLeftClose,
  PanelLeftOpen,
  BarChart3,
  Sparkles,
  KeyRound,
} from "lucide-react"
import { useState } from "react"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Separator } from "@/components/ui/separator"

interface NavItem {
  title: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  children?: NavItem[]
  featureFlag?: string
}

interface NavSection {
  title: string
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    title: "Analytics",
    items: [
      {
        title: "Dashboard",
        href: "/dashboard",
        icon: LayoutDashboard,
      },
      {
        title: "Evaluations",
        href: "/evaluations",
        icon: CheckCircle,
      },
    ],
  },
  {
    title: "Management",
    items: [
      {
        title: "Interactions",
        href: "/interactions",
        icon: MessageSquare,
      },
      {
        title: "User Profiles",
        href: "/profiles",
        icon: Users,
      },
      {
        title: "Feedback",
        href: "/feedbacks",
        icon: BarChart3,
      },
      {
        title: "Skills",
        href: "/skills",
        icon: Sparkles,
        featureFlag: "skill_generation",
      },
    ],
  },
  {
    title: "Settings",
    items: [
      {
        title: "Settings",
        href: "/settings",
        icon: Settings,
      },
      {
        title: "Account",
        href: "/account",
        icon: KeyRound,
      },
    ],
  },
]

export function Sidebar() {
  const pathname = usePathname()
  const [expandedItems, setExpandedItems] = useState<string[]>([])
  const [isCollapsed, setIsCollapsed] = useState(() => {
    if (typeof window === "undefined") return false
    return localStorage.getItem("sidebar-collapsed") === "true"
  })
  const { isAuthenticated, userEmail, logout, isSelfHost, isFeatureEnabled } = useAuth()

  // Save collapsed state to localStorage
  const toggleCollapsed = () => {
    const newState = !isCollapsed
    setIsCollapsed(newState)
    localStorage.setItem("sidebar-collapsed", String(newState))
  }

  const toggleExpanded = (title: string) => {
    setExpandedItems((prev) =>
      prev.includes(title)
        ? prev.filter((item) => item !== title)
        : [...prev, title]
    )
  }

  return (
    <TooltipProvider delayDuration={0}>
      <div
        className={cn(
          "flex h-screen flex-col bg-white border-r border-slate-200/50 shadow-lg shadow-slate-200/50 transition-all duration-300 ease-in-out relative z-10",
          isCollapsed ? "w-20" : "w-64"
        )}
      >
        {/* Header */}
        <div className="bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
          <div className={cn("p-6", isCollapsed && "px-4 py-6")}>
            <div className="flex items-center gap-2 mb-2">
              <div className="h-8 w-8 rounded-lg bg-white flex items-center justify-center flex-shrink-0 shadow-lg shadow-indigo-500/25 p-1">
                <Image src="/reflexio_fav.svg" alt="Reflexio" width={24} height={24} />
              </div>
              {!isCollapsed && (
                <div className="overflow-hidden">
                  <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent whitespace-nowrap">
                    Reflexio
                  </h1>
                </div>
              )}
            </div>
            {!isCollapsed && (
              <p className="text-sm text-slate-500 font-medium">
                User Profiler Portal
              </p>
            )}
          </div>

          {/* Toggle Button */}
          <div className={cn("px-3 pb-3", isCollapsed && "px-2")}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={toggleCollapsed}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 rounded-lg transition-all hover:shadow-sm"
                >
                  {isCollapsed ? (
                    <PanelLeftOpen className="h-4 w-4" />
                  ) : (
                    <>
                      <PanelLeftClose className="h-4 w-4" />
                      <span className="text-xs">Collapse</span>
                    </>
                  )}
                </button>
              </TooltipTrigger>
              {isCollapsed && (
                <TooltipContent side="right">
                  <p>Expand sidebar</p>
                </TooltipContent>
              )}
            </Tooltip>
          </div>
        </div>
        {/* Gradient separator */}
        <div className="h-px bg-gradient-to-r from-transparent via-indigo-200/50 to-transparent mx-3" />

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {navSections.map((section, sectionIndex) => (
            <div key={section.title} className="mb-6">
              {/* Section Header */}
              {!isCollapsed && (
                <div className="px-3 mb-2">
                  <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    {section.title}
                  </h2>
                </div>
              )}
              {isCollapsed && sectionIndex > 0 && (
                <Separator className="my-3 bg-slate-200" />
              )}

              {/* Section Items */}
              <div className="space-y-1">
                {section.items.filter((item) => !item.featureFlag || isFeatureEnabled(item.featureFlag)).map((item) => {
                  const Icon = item.icon
                  const isActive = pathname === item.href
                  const isExpanded = expandedItems.includes(item.title)
                  const hasChildren = item.children && item.children.length > 0

                  const linkContent = (
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 relative group",
                        isActive
                          ? "bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10 text-indigo-700 shadow-sm border border-indigo-200/50 before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:bg-gradient-to-b before:from-indigo-500 before:to-purple-500 before:rounded-r"
                          : "text-slate-600 hover:bg-slate-100 hover:text-slate-800 hover:shadow-sm",
                        isCollapsed && "justify-center px-2"
                      )}
                      onClick={(e) => {
                        if (hasChildren) {
                          e.preventDefault()
                          toggleExpanded(item.title)
                        }
                      }}
                    >
                      <Icon className={cn("h-5 w-5 flex-shrink-0", isActive && "text-indigo-600")} />
                      {!isCollapsed && (
                        <>
                          <span className="flex-1">{item.title}</span>
                          {hasChildren &&
                            (isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            ))}
                        </>
                      )}
                    </Link>
                  )

                  return (
                    <div key={item.title}>
                      {isCollapsed ? (
                        <Tooltip>
                          <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
                          <TooltipContent side="right">
                            <p>{item.title}</p>
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        linkContent
                      )}

                      {/* Children (only show when not collapsed) */}
                      {!isCollapsed && hasChildren && isExpanded && (
                        <div className="ml-6 mt-1 space-y-1">
                          {item.children?.map((child) => {
                            const ChildIcon = child.icon
                            const isChildActive = pathname === child.href
                            return (
                              <Link
                                key={child.title}
                                href={child.href}
                                className={cn(
                                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                                  isChildActive
                                    ? "bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md"
                                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-800"
                                )}
                              >
                                <ChildIcon className="h-4 w-4" />
                                <span>{child.title}</span>
                              </Link>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Gradient separator */}
        <div className="h-px bg-gradient-to-r from-transparent via-indigo-200/50 to-transparent mx-3" />

        {/* Footer */}
        <div className="bg-gradient-to-br from-slate-50 to-white">
          {/* Auth Section - Only show if not in self-host mode */}
          {!isSelfHost && (
            <div className="p-4">
              {isAuthenticated ? (
                <div className="space-y-2">
                  {!isCollapsed && (
                    <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-white border border-slate-200/50 shadow-sm">
                      <User className="h-4 w-4 text-slate-500" />
                      <span
                        className="text-xs text-slate-700 font-medium truncate flex-1"
                        title={userEmail || undefined}
                      >
                        {userEmail}
                      </span>
                    </div>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => logout()}
                        className={cn(
                          "w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 rounded-lg transition-all",
                          isCollapsed && "justify-center"
                        )}
                      >
                        <LogOut className="h-4 w-4" />
                        {!isCollapsed && <span>Logout</span>}
                      </button>
                    </TooltipTrigger>
                    {isCollapsed && (
                      <TooltipContent side="right">
                        <p>Logout</p>
                      </TooltipContent>
                    )}
                  </Tooltip>
                </div>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link
                      href="/login"
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 rounded-lg transition-all",
                        isCollapsed && "justify-center"
                      )}
                    >
                      <LogIn className="h-4 w-4" />
                      {!isCollapsed && <span>Login</span>}
                    </Link>
                  </TooltipTrigger>
                  {isCollapsed && (
                    <TooltipContent side="right">
                      <p>Login</p>
                    </TooltipContent>
                  )}
                </Tooltip>
              )}
            </div>
          )}

          {/* Version Info */}
          {!isCollapsed && (
            <div className="p-4">
              <p className="text-xs text-slate-500 font-medium">
                Version 1.0.0
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                {isSelfHost ? "Self-Hosted" : "Production"}
              </p>
            </div>
          )}
        </div>
      </div>
    </TooltipProvider>
  )
}

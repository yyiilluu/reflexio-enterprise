"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@/lib/auth-context"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Copy, Check, KeyRound, User, Mail, ShieldCheck, Terminal, Plus, Trash2, AlertTriangle, Loader2, Eye, EyeOff } from "lucide-react"
import { getApiTokens, createApiToken, deleteApiToken, revealApiToken, deleteAccount, type ApiToken } from "@/lib/api"
import { useRouter } from "next/navigation"

export default function AccountPage() {
  const { userEmail, token, isSelfHost, logout } = useAuth()
  const router = useRouter()
  const [snippetCopied, setSnippetCopied] = useState(false)
  const [tokens, setTokens] = useState<ApiToken[]>([])
  const [loading, setLoading] = useState(true)

  // Create dialog state
  const [createOpen, setCreateOpen] = useState(false)
  const [newTokenName, setNewTokenName] = useState("")
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [createdTokenCopied, setCreatedTokenCopied] = useState(false)
  const [creating, setCreating] = useState(false)

  // Reveal token state
  const [revealedTokens, setRevealedTokens] = useState<Record<number, string>>({})
  const [revealingTokenId, setRevealingTokenId] = useState<number | null>(null)
  const [copiedTokenId, setCopiedTokenId] = useState<number | null>(null)
  const [copyingTokenId, setCopyingTokenId] = useState<number | null>(null)

  // Delete dialog state
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [tokenToDelete, setTokenToDelete] = useState<ApiToken | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Delete account state
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false)
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("")
  const [deletingAccount, setDeletingAccount] = useState(false)
  const [deleteAccountError, setDeleteAccountError] = useState<string | null>(null)
  const [deleteAccountSuccess, setDeleteAccountSuccess] = useState(false)
  const [countdown, setCountdown] = useState(10)

  const fetchTokens = useCallback(async () => {
    if (isSelfHost || !token) return
    try {
      setLoading(true)
      const response = await getApiTokens()
      setTokens(response.tokens)
    } catch (error) {
      console.error("Failed to fetch tokens:", error)
    } finally {
      setLoading(false)
    }
  }, [isSelfHost, token])

  useEffect(() => {
    fetchTokens()
  }, [fetchTokens])

  const handleCreate = async () => {
    if (!newTokenName.trim()) return
    setCreating(true)
    try {
      const response = await createApiToken(newTokenName.trim())
      setCreatedToken(response.token)
      await fetchTokens()
    } catch (error) {
      console.error("Failed to create token:", error)
    } finally {
      setCreating(false)
    }
  }

  const handleCloseCreate = () => {
    setCreateOpen(false)
    setNewTokenName("")
    setCreatedToken(null)
    setCreatedTokenCopied(false)
  }

  const handleCopyCreatedToken = async () => {
    if (!createdToken) return
    await navigator.clipboard.writeText(createdToken)
    setCreatedTokenCopied(true)
    setTimeout(() => setCreatedTokenCopied(false), 2000)
  }

  const handleDelete = async () => {
    if (!tokenToDelete) return
    setDeleting(true)
    try {
      await deleteApiToken(tokenToDelete.id)
      await fetchTokens()
      setDeleteOpen(false)
      setTokenToDelete(null)
    } catch (error) {
      console.error("Failed to delete token:", error)
    } finally {
      setDeleting(false)
    }
  }

  const firstTokenValue = tokens.length > 0 ? tokens[0].token_masked : "your-api-key"

  const codeSnippet = `from reflexio import ReflexioClient

# Option 1: Pass API key directly
client = ReflexioClient(
    api_key="${firstTokenValue}",
    url_endpoint="https://www.reflexio.com/"
)

# Option 2: Use environment variables
# export REFLEXIO_API_KEY="your-api-key"
# export REFLEXIO_API_URL="https://www.reflexio.com/"
client = ReflexioClient()`

  const handleSnippetCopy = async () => {
    await navigator.clipboard.writeText(codeSnippet)
    setSnippetCopied(true)
    setTimeout(() => setSnippetCopied(false), 2000)
  }

  const handleDeleteAccount = async () => {
    if (!deleteAccountPassword.trim()) return
    setDeletingAccount(true)
    setDeleteAccountError(null)
    try {
      await deleteAccount(deleteAccountPassword)
      setDeleteAccountOpen(false)
      sessionStorage.setItem("account_deleted", "true")
      setDeleteAccountSuccess(true)
      setCountdown(10)
      await logout(true)
    } catch (error) {
      setDeleteAccountError(error instanceof Error ? error.message : "Failed to delete account")
    } finally {
      setDeletingAccount(false)
    }
  }

  useEffect(() => {
    if (!deleteAccountSuccess) return
    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval)
          sessionStorage.removeItem("account_deleted")
          router.push("/register")
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [deleteAccountSuccess, router])

  const handleCloseDeleteAccount = () => {
    setDeleteAccountOpen(false)
    setDeleteAccountPassword("")
    setDeleteAccountError(null)
  }

  const formatDate = (timestamp: number | null) => {
    if (!timestamp) return "—"
    return new Date(timestamp * 1000).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-sm border-b border-slate-200/50">
        <div className="p-8">
          <div className="max-w-[1800px] mx-auto">
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
                <KeyRound className="h-5 w-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-800">Account</h1>
            </div>
            <p className="text-slate-500 mt-1 ml-12">
              Manage your account and API access
            </p>
          </div>
        </div>
      </div>

      <div className="p-8">
        <div className="max-w-[1800px] mx-auto space-y-6">
          {/* User Info Card */}
          <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center border border-slate-200">
                  <User className="h-4 w-4 text-slate-500" />
                </div>
                <div>
                  <CardTitle className="text-lg font-semibold text-slate-800">User Information</CardTitle>
                  <CardDescription className="text-xs mt-1 text-slate-500">
                    Your account details
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-50 border border-slate-100">
                  <div className="h-9 w-9 rounded-lg bg-white flex items-center justify-center border border-slate-200 shadow-sm">
                    <Mail className="h-4 w-4 text-slate-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Email</p>
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {isSelfHost ? "Self-Hosted (no auth)" : userEmail || "Not logged in"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-50 border border-slate-100">
                  <div className="h-9 w-9 rounded-lg bg-white flex items-center justify-center border border-slate-200 shadow-sm">
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Status</p>
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      Active
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Delete Account Dialog */}
          <Dialog open={deleteAccountOpen} onOpenChange={(open) => {
            if (!open) handleCloseDeleteAccount()
            else setDeleteAccountOpen(true)
          }}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="text-red-600">Delete Account</DialogTitle>
                <DialogDescription>
                  This action is permanent and cannot be undone. All your data will be deleted, including:
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
                  <li>All interactions and profiles</li>
                  <li>All feedbacks and skills</li>
                  <li>All API keys</li>
                  <li>Your organization record</li>
                </ul>
                {deleteAccountError && (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200">
                    <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0" />
                    <p className="text-xs text-red-800">{deleteAccountError}</p>
                  </div>
                )}
                <div>
                  <Label htmlFor="delete-password">Enter your password to confirm</Label>
                  <Input
                    id="delete-password"
                    type="password"
                    placeholder="Your password"
                    value={deleteAccountPassword}
                    onChange={(e) => setDeleteAccountPassword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && deleteAccountPassword.trim()) handleDeleteAccount()
                    }}
                    className="mt-2"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseDeleteAccount}>
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleDeleteAccount}
                  disabled={!deleteAccountPassword.trim() || deletingAccount}
                >
                  {deletingAccount ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    "Delete My Account"
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Delete Account Success Dialog */}
          <Dialog open={deleteAccountSuccess}>
            <DialogContent className="[&>button]:hidden" onPointerDownOutside={(e) => e.preventDefault()} onEscapeKeyDown={(e) => e.preventDefault()}>
              <DialogHeader>
                <DialogTitle className="text-emerald-600">Account Deleted</DialogTitle>
                <DialogDescription>
                  Your account has been successfully deleted. All your data has been removed.
                </DialogDescription>
              </DialogHeader>
              <div className="py-2">
                <p className="text-sm text-slate-500 text-center">
                  Redirecting to sign up in {countdown} second{countdown !== 1 ? "s" : ""}...
                </p>
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button variant="outline" onClick={() => { sessionStorage.removeItem("account_deleted"); router.push("/") }}>
                  Go to Home
                </Button>
                <Button onClick={() => { sessionStorage.removeItem("account_deleted"); router.push("/register") }}>
                  Sign Up
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* API Keys Card */}
          <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-amber-50 to-amber-100 flex items-center justify-center border border-amber-200">
                    <KeyRound className="h-4 w-4 text-amber-600" />
                  </div>
                  <div>
                    <CardTitle className="text-lg font-semibold text-slate-800">API Keys</CardTitle>
                    <CardDescription className="text-xs mt-1 text-slate-500">
                      Manage API keys for authenticating with the Reflexio SDK
                    </CardDescription>
                  </div>
                </div>
                {!isSelfHost && token && (
                  <Dialog open={createOpen} onOpenChange={(open) => {
                    if (!open) handleCloseCreate()
                    else setCreateOpen(true)
                  }}>
                    <DialogTrigger asChild>
                      <Button size="sm" className="gap-1.5">
                        <Plus className="h-4 w-4" />
                        Create API Key
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      {!createdToken ? (
                        <>
                          <DialogHeader>
                            <DialogTitle>Create API Key</DialogTitle>
                            <DialogDescription>
                              Give your new API key a name to help you identify it later.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="py-4">
                            <Label htmlFor="token-name">Name</Label>
                            <Input
                              id="token-name"
                              placeholder="e.g., Production, Staging, CI/CD"
                              value={newTokenName}
                              onChange={(e) => setNewTokenName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && newTokenName.trim()) handleCreate()
                              }}
                              className="mt-2"
                            />
                          </div>
                          <DialogFooter>
                            <Button variant="outline" onClick={handleCloseCreate}>
                              Cancel
                            </Button>
                            <Button
                              onClick={handleCreate}
                              disabled={!newTokenName.trim() || creating}
                            >
                              {creating ? "Creating..." : "Create"}
                            </Button>
                          </DialogFooter>
                        </>
                      ) : (
                        <>
                          <DialogHeader>
                            <DialogTitle>API Key Created</DialogTitle>
                            <DialogDescription>
                              Copy your API key now. You won&apos;t be able to see it again.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="py-4 space-y-3">
                            <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
                              <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
                              <p className="text-xs text-amber-800">
                                Save this key securely. It will only be shown once.
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="flex-1 font-mono text-sm text-slate-700 bg-slate-50 rounded-lg border border-slate-200 px-3 py-2.5 select-all break-all">
                                {createdToken}
                              </div>
                              <Button
                                variant="outline"
                                size="icon"
                                onClick={handleCopyCreatedToken}
                                className={`flex-shrink-0 h-10 w-10 transition-colors ${
                                  createdTokenCopied
                                    ? "border-emerald-300 bg-emerald-50 hover:bg-emerald-50"
                                    : "border-slate-200 hover:bg-slate-100"
                                }`}
                              >
                                {createdTokenCopied ? (
                                  <Check className="h-4 w-4 text-emerald-600" />
                                ) : (
                                  <Copy className="h-4 w-4 text-slate-500" />
                                )}
                              </Button>
                            </div>
                          </div>
                          <DialogFooter>
                            <Button onClick={handleCloseCreate}>Done</Button>
                          </DialogFooter>
                        </>
                      )}
                    </DialogContent>
                  </Dialog>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {isSelfHost ? (
                <div className="p-6 rounded-xl bg-slate-50 border border-slate-100 text-center">
                  <div className="h-12 w-12 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <KeyRound className="h-6 w-6 text-slate-400" />
                  </div>
                  <p className="text-sm text-slate-600 font-medium">
                    API key authentication is not required in self-hosted mode.
                  </p>
                </div>
              ) : !token ? (
                <div className="p-6 rounded-xl bg-slate-50 border border-slate-100 text-center">
                  <div className="h-12 w-12 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <KeyRound className="h-6 w-6 text-slate-400" />
                  </div>
                  <p className="text-sm text-slate-600 font-medium">
                    Log in to view your API keys.
                  </p>
                </div>
              ) : loading ? (
                <div className="p-6 rounded-xl bg-slate-50 border border-slate-100 text-center">
                  <p className="text-sm text-slate-500">Loading API keys...</p>
                </div>
              ) : (
                <>
                  {/* Tokens table */}
                  <div className="rounded-xl border border-slate-200 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                          <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase tracking-wider">Name</th>
                          <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase tracking-wider">Key</th>
                          <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase tracking-wider">Created</th>
                          <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase tracking-wider w-20"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {tokens.map((t) => (
                          <tr key={t.id} className="hover:bg-slate-50/50 transition-colors">
                            <td className="px-4 py-3 font-medium text-slate-700">{t.name}</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5">
                                <code className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-1 rounded">
                                  {revealedTokens[t.id] || t.token_masked}
                                </code>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-6 w-6 text-slate-400 hover:text-slate-600"
                                  disabled={revealingTokenId === t.id}
                                  onClick={async () => {
                                    if (revealedTokens[t.id]) {
                                      setRevealedTokens((prev) => {
                                        const next = { ...prev }
                                        delete next[t.id]
                                        return next
                                      })
                                    } else {
                                      setRevealingTokenId(t.id)
                                      try {
                                        const res = await revealApiToken(t.id)
                                        setRevealedTokens((prev) => ({ ...prev, [t.id]: res.token }))
                                      } catch {
                                        // ignore
                                      } finally {
                                        setRevealingTokenId(null)
                                      }
                                    }
                                  }}
                                  title={revealedTokens[t.id] ? "Hide key" : "Reveal key"}
                                >
                                  {revealingTokenId === t.id ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : revealedTokens[t.id] ? (
                                    <EyeOff className="h-3.5 w-3.5" />
                                  ) : (
                                    <Eye className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-slate-400 hover:text-slate-600"
                                    disabled={copyingTokenId === t.id}
                                    onClick={async () => {
                                      let token = revealedTokens[t.id]
                                      if (!token) {
                                        setCopyingTokenId(t.id)
                                        try {
                                          const res = await revealApiToken(t.id)
                                          token = res.token
                                        } catch {
                                          setCopyingTokenId(null)
                                          return
                                        }
                                        setCopyingTokenId(null)
                                      }
                                      navigator.clipboard.writeText(token)
                                      setCopiedTokenId(t.id)
                                      setTimeout(() => setCopiedTokenId(null), 2000)
                                    }}
                                    title="Copy key"
                                  >
                                    {copyingTokenId === t.id ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : copiedTokenId === t.id ? (
                                      <Check className="h-3.5 w-3.5 text-green-500" />
                                    ) : (
                                      <Copy className="h-3.5 w-3.5" />
                                    )}
                                  </Button>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-slate-500 text-xs">{formatDate(t.created_at)}</td>
                            <td className="px-4 py-3 text-right">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-slate-400 hover:text-red-600 hover:bg-red-50"
                                onClick={() => {
                                  setTokenToDelete(t)
                                  setDeleteOpen(true)
                                }}
                                disabled={tokens.length <= 1}
                                title={tokens.length <= 1 ? "Cannot delete the last API key" : "Delete API key"}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </td>
                          </tr>
                        ))}
                        {tokens.length === 0 && (
                          <tr>
                            <td colSpan={4} className="px-4 py-6 text-center text-slate-400 text-sm">
                              No API keys found. Create one to get started.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Delete confirmation dialog */}
                  <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Delete API Key</DialogTitle>
                        <DialogDescription>
                          Are you sure you want to delete the API key &quot;{tokenToDelete?.name}&quot;?
                          Any applications using this key will stop working.
                        </DialogDescription>
                      </DialogHeader>
                      <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteOpen(false)}>
                          Cancel
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={handleDelete}
                          disabled={deleting}
                        >
                          {deleting ? "Deleting..." : "Delete"}
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>

                  {/* Quick Start code snippet */}
                  <div>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
                        <Terminal className="h-4 w-4 text-slate-300" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-800">Quick Start</p>
                        <p className="text-xs text-slate-500">Copy this snippet to start using the SDK</p>
                      </div>
                    </div>
                    <div className="relative group">
                      <pre className="rounded-xl bg-slate-900 p-5 text-sm text-slate-300 overflow-x-auto border border-slate-700/50 shadow-inner leading-relaxed">
                        <code>{codeSnippet}</code>
                      </pre>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleSnippetCopy}
                        className="absolute top-3 right-3 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 hover:bg-slate-700 border border-slate-600"
                        title="Copy snippet"
                      >
                        {snippetCopied ? (
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5 text-slate-400" />
                        )}
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Danger Zone Card — hidden in self-host mode */}
          {!isSelfHost && token && (
            <Card className="border-red-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
              <CardHeader className="pb-4">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-red-50 to-red-100 flex items-center justify-center border border-red-200">
                    <AlertTriangle className="h-4 w-4 text-red-600" />
                  </div>
                  <div>
                    <CardTitle className="text-lg font-semibold text-slate-800">Danger Zone</CardTitle>
                    <CardDescription className="text-xs mt-1 text-slate-500">
                      Irreversible actions for your account
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between p-4 rounded-xl border border-red-100 bg-red-50/50">
                  <div>
                    <p className="text-sm font-medium text-slate-800">Delete Account</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Permanently delete your account and all associated data
                    </p>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setDeleteAccountOpen(true)}
                  >
                    <Trash2 className="h-4 w-4 mr-1.5" />
                    Delete Account
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

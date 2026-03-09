"use client"

import { useState } from "react"
import { useAuth } from "@/lib/auth-context"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Eye, EyeOff, Copy, Check, KeyRound, User, Mail, ShieldCheck, Terminal } from "lucide-react"

export default function AccountPage() {
  const { userEmail, token, isSelfHost } = useAuth()
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [snippetCopied, setSnippetCopied] = useState(false)

  const apiKey = token || ""
  const maskedKey = apiKey
    ? `${apiKey.slice(0, 8)}${"*".repeat(Math.max(0, apiKey.length - 12))}${apiKey.slice(-4)}`
    : ""

  const handleCopy = async () => {
    if (!apiKey) return
    await navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const codeSnippet = `from reflexio import ReflexioClient

# Option 1: Pass API key directly
client = ReflexioClient(
    api_key="${showKey ? apiKey : "your-api-key"}",
    url_endpoint="https://www.reflexio.com/"
)

# Option 2: Use environment variables
# export REFLEXIO_API_KEY="${showKey ? apiKey : "your-api-key"}"
# export REFLEXIO_API_URL="https://www.reflexio.com/"
client = ReflexioClient()`

  const handleSnippetCopy = async () => {
    await navigator.clipboard.writeText(codeSnippet)
    setSnippetCopied(true)
    setTimeout(() => setSnippetCopied(false), 2000)
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

          {/* API Key Card */}
          <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
            <CardHeader className="pb-4">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-amber-50 to-amber-100 flex items-center justify-center border border-amber-200">
                  <KeyRound className="h-4 w-4 text-amber-600" />
                </div>
                <div>
                  <CardTitle className="text-lg font-semibold text-slate-800">API Key</CardTitle>
                  <CardDescription className="text-xs mt-1 text-slate-500">
                    Use this key to authenticate with the Reflexio Python SDK
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {apiKey ? (
                <>
                  {/* Key display */}
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Your API Key</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 font-mono text-sm text-slate-700 bg-white rounded-lg border border-slate-200 px-3 py-2.5 truncate select-all shadow-sm">
                        {showKey ? apiKey : maskedKey}
                      </div>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => setShowKey(!showKey)}
                        className="flex-shrink-0 border-slate-200 hover:bg-slate-100 h-10 w-10"
                        title={showKey ? "Hide API key" : "Reveal API key"}
                      >
                        {showKey ? <EyeOff className="h-4 w-4 text-slate-500" /> : <Eye className="h-4 w-4 text-slate-500" />}
                      </Button>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={handleCopy}
                        className={`flex-shrink-0 h-10 w-10 transition-colors ${copied ? "border-emerald-300 bg-emerald-50 hover:bg-emerald-50" : "border-slate-200 hover:bg-slate-100"}`}
                        title="Copy API key"
                      >
                        {copied ? (
                          <Check className="h-4 w-4 text-emerald-600" />
                        ) : (
                          <Copy className="h-4 w-4 text-slate-500" />
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Code snippet */}
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
              ) : (
                <div className="p-6 rounded-xl bg-slate-50 border border-slate-100 text-center">
                  <div className="h-12 w-12 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <KeyRound className="h-6 w-6 text-slate-400" />
                  </div>
                  <p className="text-sm text-slate-600 font-medium">
                    {isSelfHost
                      ? "API key authentication is not required in self-hosted mode."
                      : "Log in to view your API key."}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

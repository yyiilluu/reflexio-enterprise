"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Key, ChevronDown, ChevronUp } from "lucide-react"
import { FieldLabel } from "../FieldLabel"
import { PasswordInput } from "../PasswordInput"
import type {
  Config,
  CustomEndpointConfig,
  OpenAIConfig,
  AzureOpenAIConfig,
  AnthropicConfig,
  OpenRouterConfig,
  LLMConfig,
} from "@/app/settings/types"

interface AdvancedSettingsSectionProps {
  config: Config
  openaiMode: "direct" | "azure"
  onOpenAIModeChange: (mode: "direct" | "azure") => void
  onUpdateCustomEndpoint: (updates: Partial<CustomEndpointConfig>) => void
  onUpdateOpenAI: (updates: Partial<OpenAIConfig>) => void
  onUpdateAzureOpenAI: (updates: Partial<AzureOpenAIConfig>) => void
  onUpdateAnthropic: (updates: Partial<AnthropicConfig>) => void
  onUpdateOpenRouter: (updates: Partial<OpenRouterConfig>) => void
  onUpdateLLM: (updates: Partial<LLMConfig>) => void
}

export function AdvancedSettingsSection({
  config,
  openaiMode,
  onOpenAIModeChange,
  onUpdateCustomEndpoint,
  onUpdateOpenAI,
  onUpdateAzureOpenAI,
  onUpdateAnthropic,
  onUpdateOpenRouter,
  onUpdateLLM,
}: AdvancedSettingsSectionProps) {
  const [expanded, setExpanded] = useState(false)

  const hasConfig = !!(
    config.api_key_config?.custom_endpoint?.api_key ||
    config.api_key_config?.openai?.api_key ||
    config.api_key_config?.openai?.azure_config?.api_key ||
    config.api_key_config?.anthropic?.api_key ||
    config.api_key_config?.openrouter?.api_key ||
    config.llm_config?.should_run_model_name ||
    config.llm_config?.generation_model_name ||
    config.llm_config?.embedding_model_name
  )

  return (
    <Card className="border-slate-200 bg-white overflow-hidden hover:shadow-lg transition-all duration-300">
      <CardHeader
        className="pb-4 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Key className="h-4 w-4 text-slate-400" />
            <div>
              <CardTitle className="text-lg font-semibold text-slate-800">Advanced Settings</CardTitle>
              <CardDescription className="text-xs mt-1 text-slate-500">API keys and provider configuration</CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasConfig && (
              <Badge className="text-xs bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                Configured
              </Badge>
            )}
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0" aria-label={expanded ? "Collapse" : "Expand"}>
              {expanded ? (
                <ChevronUp className="h-5 w-5 text-slate-500" />
              ) : (
                <ChevronDown className="h-5 w-5 text-slate-500" />
              )}
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-6 pt-0">
          {/* Custom Endpoint Configuration */}
          <div className="p-5 border rounded-lg space-y-4 bg-muted/30">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400">CE</span>
              <span className="text-sm font-semibold text-slate-800">Custom Endpoint</span>
            </div>
            <p className="text-xs text-slate-500">
              Connect to any OpenAI-compatible endpoint (e.g., vLLM, LiteLLM proxy, Ollama). When configured, this takes priority over all other providers for LLM completion calls.
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <FieldLabel>Model Name</FieldLabel>
                <Input
                  type="text"
                  value={config.api_key_config?.custom_endpoint?.model || ""}
                  onChange={(e) => onUpdateCustomEndpoint({ model: e.target.value })}
                  placeholder="e.g., openai/mistral"
                  className="h-10"
                />
                <p className="text-xs text-slate-500 mt-1">Model identifier passed to LiteLLM</p>
              </div>
              <div>
                <FieldLabel>Endpoint URL</FieldLabel>
                <Input
                  type="text"
                  value={config.api_key_config?.custom_endpoint?.api_base || ""}
                  onChange={(e) => onUpdateCustomEndpoint({ api_base: e.target.value })}
                  placeholder="http://localhost:8000/v1"
                  className="h-10"
                />
                <p className="text-xs text-slate-500 mt-1">Base URL of the API</p>
              </div>
              <div>
                <FieldLabel>API Key</FieldLabel>
                <PasswordInput
                  value={config.api_key_config?.custom_endpoint?.api_key || ""}
                  onChange={(value) => onUpdateCustomEndpoint({ api_key: value })}
                  placeholder="API key (if required)"
                />
                <p className="text-xs text-slate-500 mt-1">Authentication key for the endpoint</p>
              </div>
            </div>
          </div>

          <Separator />

          {/* OpenAI Configuration */}
          <div className="p-5 border rounded-lg space-y-4 bg-muted/30">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400">AI</span>
              <span className="text-sm font-semibold text-slate-800">OpenAI Configuration</span>
            </div>

            <div>
              <FieldLabel>Provider Mode</FieldLabel>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onOpenAIModeChange("direct")}
                  className={`flex-1 h-10 px-4 rounded-lg text-sm font-medium transition-all border ${
                    openaiMode === "direct"
                      ? "bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm"
                      : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  Direct OpenAI
                </button>
                <button
                  type="button"
                  onClick={() => onOpenAIModeChange("azure")}
                  className={`flex-1 h-10 px-4 rounded-lg text-sm font-medium transition-all border ${
                    openaiMode === "azure"
                      ? "bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm"
                      : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  Azure OpenAI
                </button>
              </div>
            </div>

            {openaiMode === "direct" ? (
              <div>
                <FieldLabel>OpenAI API Key</FieldLabel>
                <PasswordInput
                  value={config.api_key_config?.openai?.api_key || ""}
                  onChange={(value) => onUpdateOpenAI({ api_key: value })}
                  placeholder="sk-..."
                />
                <p className="text-xs text-slate-500 mt-2">Your OpenAI API key for direct API access</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <FieldLabel>Azure API Key</FieldLabel>
                    <PasswordInput
                      value={config.api_key_config?.openai?.azure_config?.api_key || ""}
                      onChange={(value) => onUpdateAzureOpenAI({ api_key: value })}
                      placeholder="Azure OpenAI API Key"
                    />
                  </div>
                  <div>
                    <FieldLabel>Endpoint</FieldLabel>
                    <Input
                      type="text"
                      value={config.api_key_config?.openai?.azure_config?.endpoint || ""}
                      onChange={(e) => onUpdateAzureOpenAI({ endpoint: e.target.value })}
                      placeholder="https://your-resource.openai.azure.com/"
                      className="h-10"
                    />
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <FieldLabel>API Version</FieldLabel>
                    <Input
                      type="text"
                      value={config.api_key_config?.openai?.azure_config?.api_version || "2024-02-15-preview"}
                      onChange={(e) => onUpdateAzureOpenAI({ api_version: e.target.value })}
                      placeholder="2024-02-15-preview"
                      className="h-10"
                    />
                  </div>
                  <div>
                    <FieldLabel>Deployment Name (Optional)</FieldLabel>
                    <Input
                      type="text"
                      value={config.api_key_config?.openai?.azure_config?.deployment_name || ""}
                      onChange={(e) => onUpdateAzureOpenAI({ deployment_name: e.target.value || undefined })}
                      placeholder="gpt-4"
                      className="h-10"
                    />
                  </div>
                </div>
                <p className="text-xs text-slate-500">
                  Configure Azure OpenAI Service credentials for enterprise deployments
                </p>
              </div>
            )}
          </div>

          <Separator />

          {/* Anthropic Configuration */}
          <div className="p-5 border rounded-lg space-y-4 bg-muted/30">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400">A</span>
              <span className="text-sm font-semibold text-slate-800">Anthropic Configuration</span>
            </div>
            <div>
              <FieldLabel>Anthropic API Key</FieldLabel>
              <PasswordInput
                value={config.api_key_config?.anthropic?.api_key || ""}
                onChange={(value) => onUpdateAnthropic({ api_key: value })}
                placeholder="sk-ant-..."
              />
              <p className="text-xs text-slate-500 mt-2">Your Anthropic API key for Claude models</p>
            </div>
          </div>

          <Separator />

          {/* OpenRouter Configuration */}
          <div className="p-5 border rounded-lg space-y-4 bg-muted/30">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400">OR</span>
              <span className="text-sm font-semibold text-slate-800">OpenRouter Configuration</span>
            </div>
            <div>
              <FieldLabel>OpenRouter API Key</FieldLabel>
              <PasswordInput
                value={config.api_key_config?.openrouter?.api_key || ""}
                onChange={(value) => onUpdateOpenRouter({ api_key: value })}
                placeholder="sk-or-..."
              />
              <p className="text-xs text-slate-500 mt-2">Your OpenRouter API key for accessing multiple providers</p>
            </div>
          </div>

          <Separator />

          {/* LLM Model Configuration */}
          <div className="p-5 border rounded-lg space-y-4 bg-muted/30">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400">M</span>
              <span className="text-sm font-semibold text-slate-800">LLM Model Configuration</span>
            </div>
            <p className="text-xs text-slate-500">
              Override default model names. Leave empty to use system defaults from site configuration.
            </p>

            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <FieldLabel tooltip="Lightweight model used to check if extraction should run on a given batch">
                  Should Run Model
                </FieldLabel>
                <Input
                  type="text"
                  value={config.llm_config?.should_run_model_name || ""}
                  onChange={(e) => onUpdateLLM({ should_run_model_name: e.target.value || undefined })}
                  placeholder="e.g., gpt-5-nano"
                  className="h-10"
                />
                <p className="text-xs text-slate-500 mt-1">Model for extraction checks</p>
              </div>
              <div>
                <FieldLabel>Generation Model</FieldLabel>
                <Input
                  type="text"
                  value={config.llm_config?.generation_model_name || ""}
                  onChange={(e) => onUpdateLLM({ generation_model_name: e.target.value || undefined })}
                  placeholder="e.g., gpt-5"
                  className="h-10"
                />
                <p className="text-xs text-slate-500 mt-1">Model for generation & evaluation</p>
              </div>
              <div>
                <FieldLabel>Embedding Model</FieldLabel>
                <Input
                  type="text"
                  value={config.llm_config?.embedding_model_name || ""}
                  onChange={(e) => onUpdateLLM({ embedding_model_name: e.target.value || undefined })}
                  placeholder="e.g., text-embedding-3-small"
                  className="h-10"
                />
                <p className="text-xs text-slate-500 mt-1">Model for embeddings</p>
              </div>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  )
}

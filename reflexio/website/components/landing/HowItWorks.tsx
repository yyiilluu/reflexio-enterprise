"use client"

import {
  Bot,
  Cloud,
  Database,
  User,
  ThumbsUp,
  Target,
  RefreshCw,
  Plug,
  Sparkles,
  MessageSquarePlus,
  ArrowDown,
} from "lucide-react"

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-50/50 to-white">
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="text-center mb-16">
          <p className="text-sm font-semibold text-indigo-600 uppercase tracking-wider mb-3">
            Simple & Powerful
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-800 mb-4">
            How It Works
          </h2>
          <p className="text-slate-600 text-lg max-w-2xl mx-auto">
            A continuous learning loop that turns every interaction into actionable improvement — no retraining required.
          </p>
        </div>

        {/* Desktop Layout */}
        <div className="hidden lg:block">
          <div className="relative py-12">
            {/* SVG Connection Lines - positioned above nodes */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none z-20"
              viewBox="0 0 1000 340"
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                {/* Agent to Reflexio gradient */}
                <linearGradient id="agentToMem" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#0ea5e9" />
                </linearGradient>
                {/* Reflexio to Memory gradient */}
                <linearGradient id="memToStore" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#0ea5e9" />
                  <stop offset="100%" stopColor="#14b8a6" />
                </linearGradient>
                {/* Memory to Reflexio gradient (return) */}
                <linearGradient id="storeToMem" x1="100%" y1="0%" x2="0%" y2="0%">
                  <stop offset="0%" stopColor="#14b8a6" />
                  <stop offset="100%" stopColor="#0ea5e9" />
                </linearGradient>
                {/* Reflexio to Agent gradient (retrieve) */}
                <linearGradient id="memToAgent" x1="100%" y1="0%" x2="0%" y2="0%">
                  <stop offset="0%" stopColor="#0ea5e9" />
                  <stop offset="100%" stopColor="#6366f1" />
                </linearGradient>
                {/* Arrow markers - pointing right */}
                <marker id="arrowRightSky" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L6,3 z" fill="#0ea5e9" />
                </marker>
                <marker id="arrowRightTeal" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L6,3 z" fill="#14b8a6" />
                </marker>
                <marker id="arrowRightIndigo" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L6,3 z" fill="#6366f1" />
                </marker>
                {/* Arrow markers - pointing left (following path direction) */}
                <marker id="arrowLeftSky" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M6,0 L6,6 L0,3 z" fill="#0ea5e9" />
                </marker>
                <marker id="arrowLeftIndigo" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M6,0 L6,6 L0,3 z" fill="#6366f1" />
                </marker>
                {/* Arrow markers - fixed right direction (for bottom return paths) */}
                <marker id="arrowFixedRightSky" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="0" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L6,3 z" fill="#0ea5e9" />
                </marker>
                <marker id="arrowFixedRightIndigo" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="0" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L6,3 z" fill="#6366f1" />
                </marker>
              </defs>

              {/* 1. Agent → Reflexio (Publish) - Top curved path */}
              <path
                d="M 155 95 Q 255 15, 355 95"
                fill="none"
                stroke="url(#agentToMem)"
                strokeWidth="2"
                strokeDasharray="8 4"
                markerEnd="url(#arrowRightSky)"
                className="animate-flow"
              />
              {/* Label: Publish */}
              <text x="255" y="30" textAnchor="middle" className="fill-indigo-600 text-xs font-medium">Publish</text>

              {/* 2. Reflexio → Learning Store (Write) - Top curved path */}
              <path
                d="M 645 95 Q 745 15, 845 95"
                fill="none"
                stroke="url(#memToStore)"
                strokeWidth="2"
                strokeDasharray="8 4"
                markerEnd="url(#arrowRightTeal)"
                className="animate-flow"
              />
              {/* Label: Write */}
              <text x="745" y="30" textAnchor="middle" className="fill-teal-600 text-xs font-medium">Write</text>

              {/* 3. Learning Store → Reflexio (Read) - Bottom curved path */}
              <path
                d="M 845 195 Q 745 275, 645 195"
                fill="none"
                stroke="url(#storeToMem)"
                strokeWidth="2"
                strokeDasharray="8 4"
                markerEnd="url(#arrowRightSky)"
                className="animate-flow"
              />
              {/* Label: Read */}
              <text x="745" y="295" textAnchor="middle" className="fill-sky-600 text-xs font-medium">Read</text>

              {/* 4. Reflexio → Agent (Retrieve) - Bottom curved path */}
              <path
                d="M 355 195 Q 255 275, 155 195"
                fill="none"
                stroke="url(#memToAgent)"
                strokeWidth="2"
                strokeDasharray="8 4"
                markerEnd="url(#arrowRightIndigo)"
                className="animate-flow"
              />
              {/* Label: Retrieve */}
              <text x="255" y="295" textAnchor="middle" className="fill-indigo-600 text-xs font-medium">Retrieve</text>
            </svg>

            {/* Flow Animation Styles */}
            <style jsx>{`
              @keyframes flow {
                from { stroke-dashoffset: 24; }
                to { stroke-dashoffset: 0; }
              }
              @keyframes flowReverse {
                from { stroke-dashoffset: 0; }
                to { stroke-dashoffset: 24; }
              }
              .animate-flow {
                animation: flow 1.5s linear infinite;
              }
              .animate-flow-reverse {
                animation: flowReverse 1.5s linear infinite;
              }
            `}</style>

            {/* Nodes */}
            <div className="relative z-10 flex items-start justify-between px-8">
              {/* Node 1: Your Agent */}
              <div className="flex flex-col items-center w-48">
                <div className="bg-white rounded-2xl p-6 shadow-lg border border-slate-200 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                  <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center mx-auto mb-4">
                    <Bot className="h-8 w-8 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-800 text-center">Your Agent</h3>
                  <p className="text-sm text-slate-500 text-center mt-1">AI-powered assistant</p>
                </div>

                {/* Badge */}
                <div className="mt-4 flex items-center gap-2 bg-indigo-50 px-3 py-1.5 rounded-full border border-indigo-100">
                  <span className="text-sm font-medium text-indigo-700">Publish & Retrieve</span>
                </div>
              </div>

              {/* Node 2: Reflexio (Central) */}
              <div className="flex flex-col items-center w-72">
                <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-lg border border-slate-200/80 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                  {/* Header */}
                  <div className="flex items-center justify-center gap-2 mb-5">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 flex items-center justify-center">
                      <Cloud className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-xl font-bold text-slate-800">Reflexio</span>
                  </div>

                  {/* Extractors - 2+1 Grid */}
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      {/* Profile Pill */}
                      <div className="flex-1 flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
                        <div className="w-6 h-6 rounded-md bg-violet-100 flex items-center justify-center">
                          <User className="h-3.5 w-3.5 text-violet-600" />
                        </div>
                        <span className="text-sm font-medium text-slate-700">Profile</span>
                      </div>
                      {/* Feedback Pill */}
                      <div className="flex-1 flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
                        <div className="w-6 h-6 rounded-md bg-amber-100 flex items-center justify-center">
                          <ThumbsUp className="h-3.5 w-3.5 text-amber-600" />
                        </div>
                        <span className="text-sm font-medium text-slate-700">Feedback</span>
                      </div>
                    </div>
                    {/* Success Pill */}
                    <div className="flex justify-center">
                      <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-4 py-2 border border-slate-200">
                        <div className="w-6 h-6 rounded-md bg-emerald-100 flex items-center justify-center">
                          <Target className="h-3.5 w-3.5 text-emerald-600" />
                        </div>
                        <span className="text-sm font-medium text-slate-700">Success</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Step Label */}
                <div className="mt-4 flex items-center gap-2 bg-sky-50 px-3 py-1.5 rounded-full border border-sky-100">
                  <span className="text-sm font-medium text-sky-700">Learn & Evaluate</span>
                </div>
              </div>

              {/* Node 3: Learning Store */}
              <div className="flex flex-col items-center w-48">
                <div className="bg-white rounded-2xl p-6 shadow-lg border border-slate-200 hover:shadow-xl hover:-translate-y-1 transition-all duration-300 relative">
                  <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center mx-auto mb-4">
                    <Database className="h-8 w-8 text-white" />
                  </div>
                  {/* Refresh Badge */}
                  <div className="absolute top-4 right-4 w-8 h-8 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center animate-pulse">
                    <RefreshCw className="w-4 h-4 text-teal-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-800 text-center">Learning Store</h3>
                  <p className="text-sm text-slate-500 text-center mt-1">Persistent context</p>
                </div>

                {/* Step Label */}
                <div className="mt-4 flex items-center gap-2 bg-teal-50 px-3 py-1.5 rounded-full border border-teal-100">
                  <span className="text-sm font-medium text-teal-700">Write & Read</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tablet Layout */}
        <div className="hidden md:block lg:hidden">
          <div className="flex flex-col items-center gap-4 py-8">
            {/* Agent */}
            <div className="flex flex-col items-center">
              <div className="bg-white rounded-2xl p-5 shadow-lg border border-slate-200 w-56">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center mx-auto mb-3">
                  <Bot className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-base font-semibold text-slate-800 text-center">Your Agent</h3>
              </div>
            </div>

            {/* Bidirectional Arrow: Agent ↔ Reflexio */}
            <div className="flex flex-col items-center gap-1">
              <div className="flex items-center gap-3">
                <span className="text-xs text-indigo-600 font-medium">Publish</span>
                <ArrowDown className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="flex items-center gap-3">
                <ArrowDown className="w-4 h-4 text-indigo-400 rotate-180" />
                <span className="text-xs text-indigo-600 font-medium">Retrieve</span>
              </div>
            </div>

            {/* Reflexio */}
            <div className="flex flex-col items-center">
              <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-5 shadow-lg border border-slate-200/80 w-64">
                <div className="flex items-center justify-center gap-2 mb-4">
                  <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 flex items-center justify-center">
                    <Cloud className="h-4 w-4 text-white" />
                  </div>
                  <span className="text-lg font-bold text-slate-800">Reflexio</span>
                </div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <div className="flex-1 flex items-center gap-2 bg-slate-50 rounded-lg px-2 py-1.5 border border-slate-200">
                      <div className="w-5 h-5 rounded bg-violet-100 flex items-center justify-center">
                        <User className="h-3 w-3 text-violet-600" />
                      </div>
                      <span className="text-xs font-medium text-slate-700">Profile</span>
                    </div>
                    <div className="flex-1 flex items-center gap-2 bg-slate-50 rounded-lg px-2 py-1.5 border border-slate-200">
                      <div className="w-5 h-5 rounded bg-amber-100 flex items-center justify-center">
                        <ThumbsUp className="h-3 w-3 text-amber-600" />
                      </div>
                      <span className="text-xs font-medium text-slate-700">Feedback</span>
                    </div>
                  </div>
                  <div className="flex justify-center">
                    <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-1.5 border border-slate-200">
                      <div className="w-5 h-5 rounded bg-emerald-100 flex items-center justify-center">
                        <Target className="h-3 w-3 text-emerald-600" />
                      </div>
                      <span className="text-xs font-medium text-slate-700">Success</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-2 text-xs text-sky-600 font-medium">Learn & Evaluate</div>
            </div>

            {/* Bidirectional Arrow: Reflexio ↔ Memory */}
            <div className="flex flex-col items-center gap-1">
              <div className="flex items-center gap-3">
                <span className="text-xs text-teal-600 font-medium">Write</span>
                <ArrowDown className="w-4 h-4 text-teal-400" />
              </div>
              <div className="flex items-center gap-3">
                <ArrowDown className="w-4 h-4 text-teal-400 rotate-180" />
                <span className="text-xs text-teal-600 font-medium">Read</span>
              </div>
            </div>

            {/* Learning Store */}
            <div className="flex flex-col items-center">
              <div className="bg-white rounded-2xl p-5 shadow-lg border border-slate-200 w-56 relative">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center mx-auto mb-3">
                  <Database className="h-7 w-7 text-white" />
                </div>
                <div className="absolute top-3 right-3 w-7 h-7 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center animate-pulse">
                  <RefreshCw className="w-3 h-3 text-teal-600" />
                </div>
                <h3 className="text-base font-semibold text-slate-800 text-center">Learning Store</h3>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile Layout */}
        <div className="md:hidden flex flex-col items-center gap-2 py-6">
          {/* Agent */}
          <div className="w-full max-w-sm bg-white rounded-xl p-4 shadow-md border border-slate-200">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center flex-shrink-0">
                <Bot className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-slate-800">Your Agent</h4>
                <p className="text-xs text-slate-500">AI-powered assistant</p>
              </div>
            </div>
          </div>

          {/* Bidirectional: Agent ↔ Reflexio */}
          <div className="flex items-center gap-4 py-1">
            <div className="flex items-center gap-1">
              <ArrowDown className="w-4 h-4 text-indigo-400" />
              <span className="text-[10px] text-indigo-600 font-medium">Publish</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-indigo-600 font-medium">Retrieve</span>
              <ArrowDown className="w-4 h-4 text-indigo-400 rotate-180" />
            </div>
          </div>

          {/* Reflexio */}
          <div className="w-full max-w-sm bg-white/90 backdrop-blur-sm rounded-xl p-4 shadow-md border border-slate-200/80">
            <div className="flex items-center gap-4 mb-3">
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 flex items-center justify-center flex-shrink-0">
                <Cloud className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-slate-800">Reflexio</h4>
                <p className="text-xs text-slate-500">Learn & Evaluate</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 ml-16">
              <div className="flex items-center gap-1.5 bg-slate-50 rounded px-2 py-1 border border-slate-200">
                <div className="w-4 h-4 rounded bg-violet-100 flex items-center justify-center">
                  <User className="h-2.5 w-2.5 text-violet-600" />
                </div>
                <span className="text-xs text-slate-600">Profile</span>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-50 rounded px-2 py-1 border border-slate-200">
                <div className="w-4 h-4 rounded bg-amber-100 flex items-center justify-center">
                  <ThumbsUp className="h-2.5 w-2.5 text-amber-600" />
                </div>
                <span className="text-xs text-slate-600">Feedback</span>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-50 rounded px-2 py-1 border border-slate-200">
                <div className="w-4 h-4 rounded bg-emerald-100 flex items-center justify-center">
                  <Target className="h-2.5 w-2.5 text-emerald-600" />
                </div>
                <span className="text-xs text-slate-600">Success</span>
              </div>
            </div>
          </div>

          {/* Bidirectional: Reflexio ↔ Memory */}
          <div className="flex items-center gap-4 py-1">
            <div className="flex items-center gap-1">
              <ArrowDown className="w-4 h-4 text-teal-400" />
              <span className="text-[10px] text-teal-600 font-medium">Write</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-teal-600 font-medium">Read</span>
              <ArrowDown className="w-4 h-4 text-teal-400 rotate-180" />
            </div>
          </div>

          {/* Learning Store */}
          <div className="w-full max-w-sm bg-white rounded-xl p-4 shadow-md border border-slate-200">
            <div className="flex items-center gap-4">
              <div className="relative w-12 h-12 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center flex-shrink-0">
                <Database className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-slate-800">Learning Store</h4>
                  <div className="w-5 h-5 rounded-full bg-teal-50 flex items-center justify-center animate-pulse">
                    <RefreshCw className="w-3 h-3 text-teal-500" />
                  </div>
                </div>
                <p className="text-xs text-slate-500">Persistent context</p>
              </div>
            </div>
          </div>
        </div>

        {/* Key Highlights */}
        <div className="grid md:grid-cols-4 gap-6 mt-16">
          <div className="text-center p-5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 mb-3">
              <Plug className="w-5 h-5 text-white" />
            </div>
            <h3 className="font-semibold text-slate-800 mb-2">Simple Integration</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Wrap your existing LLM calls with a lightweight SDK — no agent rewrite needed
            </p>
          </div>
          <div className="text-center p-5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500 mb-3">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <h3 className="font-semibold text-slate-800 mb-2">Actionable Signals</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Automatically extract triggering conditions and do/don&apos;t rules from user corrections
            </p>
          </div>
          <div className="text-center p-5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 mb-3">
              <RefreshCw className="w-5 h-5 text-white" />
            </div>
            <h3 className="font-semibold text-slate-800 mb-2">Evolving Intelligence</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Learned behaviors consolidate and resolve conflicts automatically over time
            </p>
          </div>
          <div className="text-center p-5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 mb-3">
              <MessageSquarePlus className="w-5 h-5 text-white" />
            </div>
            <h3 className="font-semibold text-slate-800 mb-2">Precise Context Injection</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Only inject relevant signals at the moment of inference — reducing token waste
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

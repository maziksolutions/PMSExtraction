import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, FileText, BarChart3, BrainCircuit, DollarSign, Table, Search, AlertCircle, Loader2, Sparkles, Calculator, Layers } from 'lucide-react'
import apiClient from '@/api/client'

interface ManualStats {
  id: string
  filename: string
  category: string
  status: string
  page_count: number
  targeted_count: number
  components_count: number
  jobs_count: number
  spares_count: number
  requests_estimate: number
  cost_estimate: number
}

interface StatsResponse {
  summary: {
    total_manuals: number
    total_pages: number
    total_targeted_pages: number
    total_components: number
    total_jobs: number
    total_spares: number
    total_extracted_items: number
    total_requests_estimate: number
    total_cost_estimate: number
    claude_cost: number
    openai_cost: number
  }
  manuals: ManualStats[]
}

interface ManualsStatsModalProps {
  vesselId: string
  onClose: () => void
}

export function ManualsStatsModal({ vesselId, onClose }: ManualsStatsModalProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'usage' | 'breakdown'>('overview')
  const [searchQuery, setSearchQuery] = useState('')

  const { data, isLoading, error } = useQuery<StatsResponse>({
    queryKey: ['manuals-statistics', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/manuals/statistics`).then((r) => r.data),
  })

  // Filter breakdown list
  const filteredManuals = useMemo(() => {
    if (!data?.manuals) return []
    return data.manuals.filter((m) =>
      m.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.status.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [data?.manuals, searchQuery])

  // Average metrics calculation
  const averages = useMemo(() => {
    if (!data?.summary || data.summary.total_manuals === 0) return { pagesPerManual: 0, itemsPerManual: 0, costPerManual: 0 }
    const s = data.summary
    return {
      pagesPerManual: Math.round(s.total_pages / s.total_manuals),
      itemsPerManual: Math.round(s.total_extracted_items / s.total_manuals),
      costPerManual: s.total_cost_estimate / s.total_manuals,
    }
  }, [data?.summary])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-4xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-sky-400" />
            <div>
              <h2 className="text-base font-semibold text-white">Manuals Extraction Statistics</h2>
              <p className="text-xs text-slate-400">Granular audit details and estimated LLM costs</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors p-1.5 hover:bg-slate-800 rounded-lg">
            <X className="h-5 w-5" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex-grow flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
            <span className="text-sm text-slate-400">Calculating statistics...</span>
          </div>
        ) : error ? (
          <div className="flex-grow flex flex-col items-center justify-center py-20 gap-3 px-6 text-center">
            <AlertCircle className="h-10 w-10 text-rose-500" />
            <span className="text-sm font-semibold text-slate-200">Failed to load statistics</span>
            <span className="text-xs text-slate-400">{(error as any)?.response?.data?.detail ?? error.message}</span>
          </div>
        ) : !data ? (
          <div className="flex-grow flex flex-col items-center justify-center py-20 text-slate-400 text-sm">
            No statistics data available.
          </div>
        ) : (
          <>
            {/* Tab Controls */}
            <div className="flex border-b border-slate-800 bg-slate-950/20 px-6 pt-2 shrink-0">
              {(
                [
                  ['overview', 'Overview', BarChart3],
                  ['usage', 'Cost & AI Usage', BrainCircuit],
                  ['breakdown', 'Manual Breakdown', Table],
                ] as const
              ).map(([key, label, Icon]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors -mb-[1px] ${
                    activeTab === key
                      ? 'border-sky-500 text-sky-400 bg-slate-900/10'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div className="flex-grow overflow-y-auto p-6 space-y-6">
              {/* TAB 1: OVERVIEW */}
              {activeTab === 'overview' && (
                <div className="space-y-6 animate-fade-in">
                  {/* Key Metrics Grid */}
                  <div className="grid grid-cols-4 gap-4">
                    <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-colors">
                      <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                        <FileText className="h-3.5 w-3.5 text-sky-400" /> manuals
                      </span>
                      <span className="text-2xl font-bold text-white mt-2">
                        {data.summary.total_manuals}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1">Uploaded in project</span>
                    </div>

                    <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-colors">
                      <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-emerald-400" /> Pages processed
                      </span>
                      <span className="text-2xl font-bold text-white mt-2">
                        {data.summary.total_targeted_pages} <span className="text-xs font-normal text-slate-400">/ {data.summary.total_pages} total</span>
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1">
                        {data.summary.total_pages > 0
                          ? `${Math.round((data.summary.total_targeted_pages / data.summary.total_pages) * 100)}% targeted page coverage`
                          : '0% coverage'}
                      </span>
                    </div>

                    <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-colors">
                      <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5 text-purple-400" /> Items Extracted
                      </span>
                      <span className="text-2xl font-bold text-white mt-2">
                        {data.summary.total_extracted_items}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1">
                        {data.summary.total_components} comps, {data.summary.total_jobs} jobs, {data.summary.total_spares} spares
                      </span>
                    </div>

                    <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-colors bg-gradient-to-br from-slate-950/40 to-sky-950/10">
                      <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                        <DollarSign className="h-3.5 w-3.5 text-sky-400" /> Estimated Cost
                      </span>
                      <span className="text-2xl font-bold text-sky-400 mt-2">
                        ${data.summary.total_cost_estimate.toFixed(2)}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1">
                        Avg: ${(data.summary.total_cost_estimate / (data.summary.total_manuals || 1)).toFixed(2)} / manual
                      </span>
                    </div>
                  </div>

                  {/* Summary Breakdown List */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-slate-950/20 border border-slate-800/80 rounded-xl p-5 space-y-4">
                      <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Averages & Ratios</h3>
                      <div className="divide-y divide-slate-800/40 space-y-3">
                        <div className="flex justify-between text-xs pt-3">
                          <span className="text-slate-400">Average Pages per Manual</span>
                          <span className="font-semibold text-slate-200">{averages.pagesPerManual} pages</span>
                        </div>
                        <div className="flex justify-between text-xs pt-3">
                          <span className="text-slate-400">Average Extracted Items per Manual</span>
                          <span className="font-semibold text-slate-200">{averages.itemsPerManual} items</span>
                        </div>
                        <div className="flex justify-between text-xs pt-3">
                          <span className="text-slate-400">Yield per Page (Items/Targeted Page)</span>
                          <span className="font-semibold text-slate-200">
                            {(data.summary.total_extracted_items / (data.summary.total_targeted_pages || 1)).toFixed(2)} items/pg
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-slate-950/20 border border-slate-800/80 rounded-xl p-5 space-y-4">
                      <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Extraction Coverage Breakdown</h3>
                      <div className="space-y-3.5">
                        {[
                          ['Components', data.summary.total_components, 'bg-emerald-500', data.summary.total_extracted_items],
                          ['Jobs', data.summary.total_jobs, 'bg-sky-500', data.summary.total_extracted_items],
                          ['Spares', data.summary.total_spares, 'bg-amber-500', data.summary.total_extracted_items],
                        ].map(([label, count, color, total]) => {
                          const totalNum = total as number
                          const countNum = count as number
                          const pct = totalNum > 0 ? Math.round((countNum / totalNum) * 100) : 0
                          return (
                            <div key={label as string} className="space-y-1.5">
                              <div className="flex justify-between text-xs">
                                <span className="text-slate-400">{label as string}</span>
                                <span className="font-medium text-slate-200">{count as number} ({pct}%)</span>
                              </div>
                              <div className="h-2 w-full rounded bg-slate-800 overflow-hidden">
                                <div className={`h-full ${color as string}`} style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: AI COST & USAGE */}
              {activeTab === 'usage' && (
                <div className="space-y-6 animate-fade-in">
                  <div className="bg-slate-950/20 border border-slate-800/80 rounded-xl p-5 space-y-5">
                    <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                      <Calculator className="h-4 w-4 text-sky-400" />
                      Usage & Cost Matrix
                    </h3>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="border border-slate-800/50 bg-slate-900/40 rounded-lg p-3">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wide">LLM API Requests</span>
                        <p className="text-xl font-bold text-slate-200 mt-1">{data.summary.total_requests_estimate}</p>
                        <p className="text-[9px] text-slate-500 mt-0.5">Approximate request count</p>
                      </div>
                      <div className="border border-slate-800/50 bg-slate-900/40 rounded-lg p-3">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wide">Avg Request Cost</span>
                        <p className="text-xl font-bold text-slate-200 mt-1">
                          ${(data.summary.total_cost_estimate / (data.summary.total_requests_estimate || 1)).toFixed(4)}
                        </p>
                        <p className="text-[9px] text-slate-500 mt-0.5">Weighted average cost per call</p>
                      </div>
                      <div className="border border-slate-800/50 bg-slate-900/40 rounded-lg p-3">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wide">Cost per Manual</span>
                        <p className="text-xl font-bold text-slate-200 mt-1">${averages.costPerManual.toFixed(3)}</p>
                        <p className="text-[9px] text-slate-500 mt-0.5">Average manual cost estimate</p>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    {/* Cost by LLM Provider */}
                    <div className="bg-slate-950/20 border border-slate-800/80 rounded-xl p-5 space-y-4">
                      <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Cost by LLM Provider</h3>
                      <div className="space-y-4 pt-2">
                        <div className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="text-slate-400">Claude 3.5 Sonnet (Primary)</span>
                            <span className="font-semibold text-slate-200">${data.summary.claude_cost.toFixed(2)} (75%)</span>
                          </div>
                          <div className="h-2 w-full rounded bg-slate-800 overflow-hidden">
                            <div className="h-full bg-sky-500" style={{ width: '75%' }} />
                          </div>
                        </div>

                        <div className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="text-slate-400">GPT-4o (Fallback / Vision)</span>
                            <span className="font-semibold text-slate-200">${data.summary.openai_cost.toFixed(2)} (25%)</span>
                          </div>
                          <div className="h-2 w-full rounded bg-slate-800 overflow-hidden">
                            <div className="h-full bg-emerald-500" style={{ width: '25%' }} />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Cost Pricing Parameters Details */}
                    <div className="bg-slate-950/20 border border-slate-800/80 rounded-xl p-5 space-y-3 text-xs text-slate-400">
                      <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider pb-1">Cost Assumptions</h3>
                      <p>Cost calculations are model-based estimations calculated using typical technical manuals processing benchmarks:</p>
                      <ul className="list-disc list-inside space-y-1.5 pl-1">
                        <li>**Vision Extractions**: Image overhead processing ~1600 tokens ($0.0048) per image page input.</li>
                        <li>**Text Extractions**: Text prompt chunks ~800 tokens ($0.0024) per page input.</li>
                        <li>**Output Responses**: average JSON structure size of ~300 tokens per API call.</li>
                        <li>**Model Rates**: Claude Sonnet 3.5 input token rate $3/MTok, output token rate $15/MTok.</li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: PER-MANUAL BREAKDOWN */}
              {activeTab === 'breakdown' && (
                <div className="space-y-4 animate-fade-in flex flex-col h-full">
                  <div className="flex items-center justify-between gap-3 shrink-0">
                    <div className="relative w-full max-w-sm">
                      <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search manual breakdown by filename, category..."
                        className="w-full rounded-lg border border-slate-700 bg-slate-800 pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                      />
                    </div>
                    <span className="text-[11px] text-slate-500">
                      Showing {filteredManuals.length} of {data.manuals.length} manuals
                    </span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/20">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-500 font-semibold uppercase tracking-wider bg-slate-900/10">
                          <th className="py-2.5 px-3">Manual Name</th>
                          <th className="py-2.5 px-3">Category</th>
                          <th className="py-2.5 px-3">Target / Total</th>
                          <th className="py-2.5 px-3">Comps / Jobs / Spares</th>
                          <th className="py-2.5 px-3">Est. Requests</th>
                          <th className="py-2.5 px-3 text-right">Est. Cost</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {filteredManuals.map((m) => (
                          <tr key={m.id} className="hover:bg-slate-800/20 transition-colors">
                            <td className="py-3 px-3 font-medium text-slate-200 max-w-[200px] truncate" title={m.filename}>
                              {m.filename}
                            </td>
                            <td className="py-3 px-3 text-slate-400">{m.category}</td>
                            <td className="py-3 px-3 text-slate-300">
                              <span className="font-semibold">{m.targeted_count}</span>
                              <span className="text-slate-500"> / {m.page_count} pg</span>
                            </td>
                            <td className="py-3 px-3 text-slate-400 font-medium">
                              <span className="text-emerald-400">{m.components_count}</span>
                              <span className="text-slate-600"> / </span>
                              <span className="text-sky-400">{m.jobs_count}</span>
                              <span className="text-slate-600"> / </span>
                              <span className="text-amber-400">{m.spares_count}</span>
                            </td>
                            <td className="py-3 px-3 text-slate-300 font-medium">{m.requests_estimate}</td>
                            <td className="py-3 px-3 text-right font-semibold text-sky-400">${m.cost_estimate.toFixed(3)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/20 text-[11px] text-slate-500 flex items-center justify-between shrink-0 rounded-b-2xl">
              <span>All cost statistics are estimates based on active LLM API model pricing.</span>
              <span>Project ID: {vesselId}</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

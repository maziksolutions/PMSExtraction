import React, { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, FileText, BarChart3, BrainCircuit, DollarSign, Table, Search, AlertCircle, Loader2, Sparkles, Calculator, Layers, Calendar, ChevronDown, ChevronRight, HelpCircle, Filter } from 'lucide-react'
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
  created_at: string | null
  updated_at: string | null
  comp_pages: number[]
  job_pages: number[]
  spare_pages: number[]
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
  const [activeTab, setActiveTab] = useState<'overview' | 'datewise' | 'breakdown' | 'calculator'>('overview')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedVesselId, setSelectedVesselId] = useState(vesselId)

  // Fetch all vessels for project switcher
  const { data: vesselsList } = useQuery<{ items: { id: string; name: string; imo_number?: string }[] }>({
    queryKey: ['vessels-list-stats'],
    queryFn: () => apiClient.get('/vessels?page=1&page_size=100').then((r) => r.data),
  })

  // Find active vessel info
  const activeVesselInfo = useMemo(() => {
    return vesselsList?.items?.find((v) => v.id === selectedVesselId)
  }, [vesselsList, selectedVesselId])

  // Calculator states
  const [dailyCostInput, setDailyCostInput] = useState('15.00')
  const [dailyRequestsInput, setDailyRequestsInput] = useState('200')
  const [selectedDateForCalibrate, setSelectedDateForCalibrate] = useState('all')
  const [expandedManualId, setExpandedManualId] = useState<string | null>(null)

  // Date range filters
  const [activityStartDate, setActivityStartDate] = useState('')
  const [activityEndDate, setActivityEndDate] = useState('')

  const { data, isLoading, error } = useQuery<StatsResponse>({
    queryKey: ['manuals-statistics', selectedVesselId],
    queryFn: () => apiClient.get(`/vessels/${selectedVesselId}/manuals/statistics`).then((r) => r.data),
  })

  // Group manual statistics by date
  const dateWiseActivity = useMemo(() => {
    if (!data?.manuals) return []
    const groups: Record<string, {
      date: string
      manualsCount: number
      manualNames: string[]
      pagesProcessed: number
      itemsExtracted: number
      requestsEstimate: number
      costEstimate: number
    }> = {}

    for (const m of data.manuals) {
      const dateStr = m.created_at ? m.created_at.substring(0, 10) : 'Unknown Date'
      if (!groups[dateStr]) {
        groups[dateStr] = {
          date: dateStr,
          manualsCount: 0,
          manualNames: [],
          pagesProcessed: 0,
          itemsExtracted: 0,
          requestsEstimate: 0,
          costEstimate: 0,
        }
      }
      const g = groups[dateStr]
      g.manualsCount++
      g.manualNames.push(m.filename)
      g.pagesProcessed += m.targeted_count
      g.itemsExtracted += m.components_count + m.jobs_count + m.spares_count
      g.requestsEstimate += m.requests_estimate
      g.costEstimate += m.cost_estimate
    }

    return Object.values(groups).sort((a, b) => b.date.localeCompare(a.date))
  }, [data?.manuals])

  // Filtered date-wise activity based on date range inputs
  const filteredDateWiseActivity = useMemo(() => {
    let result = dateWiseActivity
    if (activityStartDate) {
      result = result.filter((day) => day.date >= activityStartDate)
    }
    if (activityEndDate) {
      result = result.filter((day) => day.date <= activityEndDate)
    }
    return result
  }, [dateWiseActivity, activityStartDate, activityEndDate])

  // Sync calculator request input field when calibration target date changes
  useEffect(() => {
    if (!data?.summary) return
    if (selectedDateForCalibrate === 'all') {
      setDailyRequestsInput(data.summary.total_requests_estimate.toString())
    } else {
      const day = dateWiseActivity.find((d) => d.date === selectedDateForCalibrate)
      if (day) {
        setDailyRequestsInput(day.requestsEstimate.toString())
      }
    }
  }, [selectedDateForCalibrate, dateWiseActivity, data?.summary])

  // Filter breakdown list
  const filteredManuals = useMemo(() => {
    if (!data?.manuals) return []
    return data.manuals.filter((m) =>
      m.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.status.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [data?.manuals, searchQuery])

  // Calibrated cost parameters
  const calibrationResult = useMemo(() => {
    const dailyCost = parseFloat(dailyCostInput) || 0
    const dailyRequests = parseInt(dailyRequestsInput, 10) || 1
    const costPerRequest = dailyRequests > 0 ? dailyCost / dailyRequests : 0
    return {
      costPerRequest,
    }
  }, [dailyCostInput, dailyRequestsInput])

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
          <div className="flex items-center gap-3">
            <BarChart3 className="h-5 w-5 text-sky-400 shrink-0" />
            <div>
              <h2 className="text-base font-semibold text-white">Manuals Extraction Statistics</h2>
              <p className="text-xs text-slate-400 flex items-center gap-1">
                <span>Active Vessel Project:</span>
                <span className="font-semibold text-sky-400">{activeVesselInfo?.name ?? 'Loading...'}</span>
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {/* Vessel Filter Selector */}
            <div className="flex items-center gap-1.5 bg-slate-950/40 border border-slate-800 rounded-lg px-2.5 py-1">
              <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Vessel:</span>
              <select
                value={selectedVesselId}
                onChange={(e) => setSelectedVesselId(e.target.value)}
                className="bg-transparent border-0 text-xs font-semibold text-white focus:ring-0 focus:outline-none cursor-pointer max-w-[200px]"
              >
                {vesselsList?.items?.map((v) => (
                  <option key={v.id} value={v.id} className="bg-slate-900 text-white">
                    {v.name} {v.imo_number ? `(IMO: ${v.imo_number})` : ''}
                  </option>
                ))}
              </select>
            </div>

            <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors p-1.5 hover:bg-slate-800 rounded-lg">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex-grow flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
            <span className="text-sm text-slate-400">Calculating project statistics...</span>
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
                  ['datewise', 'Date-wise Activity', Calendar],
                  ['breakdown', 'Manual Breakdown', Table],
                  ['calculator', 'AI Rate Calculator', Calculator],
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
                                <span className="font-medium text-slate-200">{countNum} ({pct}%)</span>
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

              {activeTab === 'datewise' && (
                <div className="space-y-4 animate-fade-in">
                  {/* Date range controls */}
                  <div className="flex items-center gap-3 bg-slate-950/20 border border-slate-800 rounded-xl p-3 shrink-0">
                    <span className="text-xs text-slate-400 font-semibold flex items-center gap-1">
                      <Filter className="h-3.5 w-3.5 text-sky-400" /> Filter by Date Range:
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="date"
                        value={activityStartDate}
                        onChange={(e) => setActivityStartDate(e.target.value)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                      <span className="text-slate-600 text-xs">to</span>
                      <input
                        type="date"
                        value={activityEndDate}
                        onChange={(e) => setActivityEndDate(e.target.value)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                      {(activityStartDate || activityEndDate) && (
                        <button
                          onClick={() => {
                            setActivityStartDate('')
                            setActivityEndDate('')
                          }}
                          className="rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-400 hover:text-white px-2 py-1 text-xs transition-colors"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/20">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-500 font-semibold uppercase tracking-wider bg-slate-900/10">
                          <th className="py-2.5 px-4 w-[15%]">Processing Date</th>
                          <th className="py-2.5 px-4 w-[40%]">Manuals Processed</th>
                          <th className="py-2.5 px-4 w-[15%]">Pages Target</th>
                          <th className="py-2.5 px-4 w-[15%]">Items Extracted</th>
                          <th className="py-2.5 px-4 w-[15%] text-right">Est. Cost</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {filteredDateWiseActivity.map((day) => (
                          <tr key={day.date} className="hover:bg-slate-800/20 transition-colors">
                            <td className="py-3.5 px-4 font-semibold text-slate-200">
                              {day.date}
                            </td>
                            <td className="py-3.5 px-4">
                              <div className="space-y-1">
                                <p className="font-medium text-slate-300">
                                  {day.manualsCount} {day.manualsCount === 1 ? 'manual' : 'manuals'}
                                </p>
                                <p className="text-[10px] text-slate-500 truncate max-w-[320px]" title={day.manualNames.join(', ')}>
                                  {day.manualNames.join(', ')}
                                </p>
                              </div>
                            </td>
                            <td className="py-3.5 px-4 text-slate-300 font-medium">
                              {day.pagesProcessed} pages
                            </td>
                            <td className="py-3.5 px-4 text-slate-300 font-medium">
                              {day.itemsExtracted} items
                            </td>
                            <td className="py-3.5 px-4 text-right font-bold text-sky-400">
                              ${day.costEstimate.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 3: PER-MANUAL BREAKDOWN */}
              {activeTab === 'breakdown' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="flex items-center justify-between gap-3">
                    <div className="relative w-full max-w-sm">
                      <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search manuals by filename, category..."
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
                            <td className="py-3 px-3 font-medium text-slate-200 max-w-[240px] truncate" title={m.filename}>
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

              {/* TAB 4: CALIBRATOR CALCULATOR */}
              {activeTab === 'calculator' && (
                <div className="space-y-6 animate-fade-in">
                  <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-5 space-y-4">
                    <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                      <Calculator className="h-4 w-4 text-sky-400" />
                      LLM Pricing Rate Calibration
                    </h3>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Enter the actual cost recorded on your AI console (e.g., Anthropic or OpenAI API logs) for a specific day or overall, alongside the request count, to calibrate the exact per-request rate and obtain calibrated pricing projections per manual and page.
                    </p>

                    <div className="grid grid-cols-4 gap-4 pt-2">
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                          <Calendar className="h-3 w-3" /> Target Date
                        </label>
                        <select
                          value={selectedDateForCalibrate}
                          onChange={(e) => setSelectedDateForCalibrate(e.target.value)}
                          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white focus:border-sky-500 focus:outline-none"
                        >
                          <option value="all">Entire Project (All Dates)</option>
                          {dateWiseActivity.map((day) => (
                            <option key={day.date} value={day.date}>
                              {day.date} ({day.requestsEstimate} requests)
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                          <DollarSign className="h-3 w-3" /> Actual Console Cost ($)
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          value={dailyCostInput}
                          onChange={(e) => setDailyCostInput(e.target.value)}
                          placeholder="e.g. 15.00"
                          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:border-sky-500 focus:outline-none"
                        />
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                          <Layers className="h-3 w-3" /> Console Request Count
                        </label>
                        <input
                          type="number"
                          value={dailyRequestsInput}
                          onChange={(e) => setDailyRequestsInput(e.target.value)}
                          placeholder="e.g. 200"
                          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:border-sky-500 focus:outline-none"
                        />
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                          Calibrated Unit Rate
                        </label>
                        <div className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-1.5 text-xs font-semibold text-sky-400 h-[34px] flex items-center">
                          ${calibrationResult.costPerRequest.toFixed(5)} <span className="text-[9px] text-slate-500 font-normal ml-1">/ request</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Calibrated Manual & Page breakdown */}
                  <div className="space-y-3">
                    <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      Calibrated Cost Breakdown per Manual & Page
                    </h3>

                    <div className="overflow-hidden border border-slate-800 rounded-xl bg-slate-950/20">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-500 font-semibold uppercase tracking-wider bg-slate-900/10">
                            <th className="py-2.5 px-4 w-[45%]">Manual Name</th>
                            <th className="py-2.5 px-4 w-[15%]">Est. Requests</th>
                            <th className="py-2.5 px-4 w-[25%] text-right font-medium">Original Cost Est.</th>
                            <th className="py-2.5 px-4 w-[15%] text-right text-sky-400 font-bold">Calibrated Cost</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/40">
                          {data.manuals.map((m) => {
                            const isExpanded = expandedManualId === m.id
                            const calibratedManualCost = m.requests_estimate * calibrationResult.costPerRequest

                            // Build unique pages set and their cost
                            const pageCalculations = []
                            const allPages = Array.from(new Set([...m.comp_pages, ...m.job_pages, ...m.spare_pages])).sort((a, b) => a - b)
                            
                            for (const p of allPages) {
                              let pageRequests = 0
                              const types = []
                              if (m.comp_pages.includes(p)) {
                                pageRequests += 1
                                types.push('Component')
                              }
                              if (m.spare_pages.includes(p)) {
                                pageRequests += 4
                                types.push('Spare')
                              }
                              if (m.job_pages.includes(p)) {
                                pageRequests += 0.5
                                types.push('Job')
                              }
                              pageCalculations.push({
                                page: p,
                                requests: pageRequests,
                                types: types.join(' & '),
                                cost: pageRequests * calibrationResult.costPerRequest
                              })
                            }

                            return (
                              <React.Fragment key={m.id}>
                                <tr className="hover:bg-slate-800/20 transition-colors">
                                  <td className="py-3 px-4 font-medium text-slate-200">
                                    <button
                                      onClick={() => setExpandedManualId(isExpanded ? null : m.id)}
                                      className="flex items-center gap-1.5 hover:text-white text-left font-medium min-w-0 w-full"
                                    >
                                      {isExpanded ? (
                                        <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
                                      ) : (
                                        <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" />
                                      )}
                                      <span className="truncate max-w-[280px]" title={m.filename}>{m.filename}</span>
                                    </button>
                                  </td>
                                  <td className="py-3 px-4 text-slate-300 font-medium">{m.requests_estimate}</td>
                                  <td className="py-3 px-4 text-right text-slate-500 font-medium">${m.cost_estimate.toFixed(3)}</td>
                                  <td className="py-3 px-4 text-right font-bold text-sky-400">${calibratedManualCost.toFixed(3)}</td>
                                </tr>

                                {isExpanded && (
                                  <tr>
                                    <td colSpan={4} className="bg-slate-950/30 px-8 py-3 border-b border-slate-800/50">
                                      <div className="space-y-2">
                                        <h4 className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1">
                                          <HelpCircle className="h-3.5 w-3.5 text-slate-500" />
                                          Granular Page Pricing Breakdown
                                        </h4>
                                        {pageCalculations.length === 0 ? (
                                          <p className="text-xs text-slate-500 italic py-1">No pages targeted for extraction in this manual.</p>
                                        ) : (
                                          <div className="grid grid-cols-3 gap-2.5 max-h-[180px] overflow-y-auto pr-2 py-1">
                                            {pageCalculations.map((pc) => (
                                              <div key={pc.page} className="bg-slate-900/60 border border-slate-800/40 rounded-lg p-2 flex items-center justify-between text-xs">
                                                <div>
                                                  <p className="font-semibold text-slate-300">Page {pc.page}</p>
                                                  <p className="text-[9px] text-slate-500 uppercase font-medium">{pc.types}</p>
                                                </div>
                                                <div className="text-right">
                                                  <p className="font-bold text-sky-400">${pc.cost.toFixed(4)}</p>
                                                  <p className="text-[9px] text-slate-500">{pc.requests} req</p>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/20 text-[11px] text-slate-500 flex items-center justify-between shrink-0 rounded-b-2xl">
              <span>All cost statistics are estimates based on active LLM API model pricing.</span>
              <span>Project ID: {selectedVesselId}</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

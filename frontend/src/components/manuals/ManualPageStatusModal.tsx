import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, RefreshCw, Search, CheckCircle2, AlertCircle, Loader2, ChevronDown, ChevronUp, Play, Filter, HelpCircle, FileText, XCircle } from 'lucide-react'
import apiClient from '@/api/client'

// Frontend range parser
export function parsePageTokens(value: string | null | undefined): number[] {
  if (!value) return []
  const pages = new Set<number>()
  const tokens = value.split(',')
  for (const token of tokens) {
    const cleaned = token.trim()
    if (!cleaned) continue
    if (cleaned.includes('-')) {
      const parts = cleaned.split('-')
      if (parts.length === 2) {
        const start = parseInt(parts[0].trim(), 10)
        const end = parseInt(parts[1].trim(), 10)
        if (!isNaN(start) && !isNaN(end)) {
          const minPage = Math.min(start, end)
          const maxPage = Math.max(start, end)
          for (let p = minPage; p <= maxPage; p++) {
            pages.add(p)
          }
        }
      }
    } else {
      const p = parseInt(cleaned, 10)
      if (!isNaN(p)) {
        pages.add(p)
      }
    }
  }
  return Array.from(pages).sort((a, b) => a - b)
}

interface PageItem {
  type: 'component' | 'job' | 'spare'
  name: string
  detail?: string
}

interface PageStatusRow {
  page_number: number
  is_targeted: boolean
  status: 'success' | 'failed' | 'pending' | 'skipped'
  extracted_count: number
  targeted_types: {
    component: boolean
    job: boolean
    spare: boolean
  }
  items: PageItem[]
}

interface PageStatusResponse {
  manual_id: string
  original_filename: string
  page_count: number | null
  status: string
  pages: PageStatusRow[]
}

interface ManualPageStatusModalProps {
  vesselId: string
  manualId: string
  manualTitle: string
  unsavedComponentsPages?: string | null
  unsavedJobsPages?: string | null
  unsavedSparesPages?: string | null
  onClose: () => void
}

export function ManualPageStatusModal({
  vesselId,
  manualId,
  manualTitle,
  unsavedComponentsPages,
  unsavedJobsPages,
  unsavedSparesPages,
  onClose,
}: ManualPageStatusModalProps) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'failed'>('all')
  const [expandedPages, setExpandedPages] = useState<Record<number, boolean>>({})
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // Fetch page statuses, passing unsaved edits as query params to support dynamic page reforming
  const { data, isLoading, error, refetch } = useQuery<PageStatusResponse>({
    queryKey: ['manual-page-status', manualId, unsavedComponentsPages, unsavedJobsPages, unsavedSparesPages],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (unsavedComponentsPages !== undefined && unsavedComponentsPages !== null) {
        params.append('components_pages_unsaved', unsavedComponentsPages)
      }
      if (unsavedJobsPages !== undefined && unsavedJobsPages !== null) {
        params.append('jobs_pages_unsaved', unsavedJobsPages)
      }
      if (unsavedSparesPages !== undefined && unsavedSparesPages !== null) {
        params.append('spares_pages_unsaved', unsavedSparesPages)
      }
      const res = await apiClient.get(
        `/vessels/${vesselId}/manuals/${manualId}/page-status?${params.toString()}`
      )
      return res.data
    },
    refetchInterval: (query) => {
      const manualStatus = query.state.data?.status
      if (
        manualStatus === 'queued' ||
        manualStatus === 'downloading' ||
        manualStatus === 'converting' ||
        manualStatus === 'translating' ||
        manualStatus === 'scanning'
      ) {
        return 3000 // Poll every 3 seconds
      }
      return false
    },
  })

  const isCurrentlyExtracting =
    data?.status === 'queued' ||
    data?.status === 'downloading' ||
    data?.status === 'converting' ||
    data?.status === 'translating' ||
    data?.status === 'scanning'

  // Mutation to trigger page-specific retry
  const retryMutation = useMutation({
    mutationFn: async (vars: { pageNumber: number; entityTypes: string[] }) => {
      const res = await apiClient.post(`/vessels/${vesselId}/manuals/extract-selected`, {
        manual_ids: [manualId],
        page_numbers: [vars.pageNumber],
        entity_types: vars.entityTypes,
      })
      return res.data
    },
    onSuccess: (_, vars) => {
      setNotification({
        message: `Triggered extraction retry for Page ${vars.pageNumber} (${vars.entityTypes.join(', ')}).`,
        type: 'success',
      })
      queryClient.invalidateQueries({ queryKey: ['manual-page-status', manualId] })
      queryClient.invalidateQueries({ queryKey: ['extraction-status', vesselId] })
      setTimeout(() => setNotification(null), 5000)
    },
    onError: (err: any) => {
      setNotification({
        message: `Failed to trigger retry: ${err?.response?.data?.detail ?? err.message}`,
        type: 'error',
      })
      setTimeout(() => setNotification(null), 5000)
    },
  })

  // Mutation to trigger full manual re-extraction
  const retryManualMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/vessels/${vesselId}/manuals/extract-selected`, {
        manual_ids: [manualId],
      })
      return res.data
    },
    onSuccess: () => {
      setNotification({
        message: 'Triggered full re-extraction for this manual.',
        type: 'success',
      })
      queryClient.invalidateQueries({ queryKey: ['manual-page-status', manualId] })
      queryClient.invalidateQueries({ queryKey: ['extraction-status', vesselId] })
      setTimeout(() => setNotification(null), 5000)
    },
    onError: (err: any) => {
      setNotification({
        message: `Failed to trigger full re-extraction: ${err?.response?.data?.detail ?? err.message}`,
        type: 'error',
      })
      setTimeout(() => setNotification(null), 5000)
    },
  })

  // Mutation to stop/cancel active extraction
  const stopMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/vessels/${vesselId}/extract-stop`)
      return res.data
    },
    onSuccess: () => {
      setNotification({
        message: 'Successfully stopped the extraction task.',
        type: 'success',
      })
      queryClient.invalidateQueries({ queryKey: ['manual-page-status', manualId] })
      queryClient.invalidateQueries({ queryKey: ['extraction-status', vesselId] })
      setTimeout(() => setNotification(null), 5000)
    },
    onError: (err: any) => {
      setNotification({
        message: `Failed to stop extraction: ${err?.response?.data?.detail ?? err.message}`,
        type: 'error',
      })
      setTimeout(() => setNotification(null), 5000)
    },
  })

  const togglePageExpand = (pageNo: number) => {
    setExpandedPages((prev) => ({ ...prev, [pageNo]: !prev[pageNo] }))
  }

  // Filter and search logic
  const filteredPages = useMemo(() => {
    if (!data?.pages) return []

    return data.pages.filter((page) => {
      // 1. Status Filter
      if (statusFilter === 'success' && page.status !== 'success') return false
      if (statusFilter === 'failed' && page.status !== 'failed') return false

      // 2. Search query (matches page number or any item name/detail)
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim()
        const pageMatch = `page ${page.page_number}`.includes(query) || `${page.page_number}` === query
        const itemMatch = page.items.some(
          (item) =>
            item.name.toLowerCase().includes(query) ||
            item.detail?.toLowerCase().includes(query) ||
            item.type.toLowerCase().includes(query)
        )
        return pageMatch || itemMatch
      }

      return true
    })
  }, [data?.pages, statusFilter, searchQuery])

  // Count summary
  const summary = useMemo(() => {
    if (!data?.pages) return { components: 0, jobs: 0, spares: 0, totalTargeted: 0 }
    let components = 0
    let jobs = 0
    let spares = 0
    let totalTargeted = 0

    for (const page of data.pages) {
      if (page.is_targeted) totalTargeted++
      for (const item of page.items) {
        if (item.type === 'component') components++
        if (item.type === 'job') jobs++
        if (item.type === 'spare') spares++
      }
    }
    return { components, jobs, spares, totalTargeted }
  }, [data?.pages])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-4xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4 shrink-0">
          <div className="space-y-1.5 min-w-0 flex-1 pr-4">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-5 w-5 text-sky-400 shrink-0" />
              <h2 className="text-base font-semibold text-white truncate max-w-[550px]" title={manualTitle}>
                {manualTitle}
              </h2>
            </div>
            {data && (
              <p className="text-xs text-slate-400 flex items-center gap-2">
                <span>Extraction Status Details</span>
                <span className="text-slate-600">&bull;</span>
                <span>Manual Status:</span>
                <span className="capitalize font-semibold text-slate-300">{data.status}</span>
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors p-1.5 hover:bg-slate-800 rounded-lg shrink-0">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Banner notification */}
        {notification && (
          <div
            className={`px-6 py-3 text-xs flex items-center gap-2 border-b shrink-0 ${
              notification.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-400'
                : 'bg-rose-950/40 border-rose-800/50 text-rose-400'
            }`}
          >
            {notification.type === 'success' ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <AlertCircle className="h-4 w-4 text-rose-400" />}
            <span>{notification.message}</span>
          </div>
        )}

        {/* Content */}
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
            <span className="text-sm text-slate-400">Loading page status details...</span>
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center py-20 gap-3 px-6 text-center">
            <AlertCircle className="h-10 w-10 text-rose-500" />
            <span className="text-sm font-semibold text-slate-200">Failed to load page status</span>
            <span className="text-xs text-slate-400 max-w-md">{(error as any)?.response?.data?.detail ?? error.message}</span>
            <button onClick={() => refetch()} className="mt-2 rounded-lg bg-sky-600 px-3 py-1.5 text-xs text-white hover:bg-sky-500 transition-colors">
              Retry Load
            </button>
          </div>
        ) : (
          <>
            {/* Top Summary Stats Cards */}
            <div className="grid grid-cols-4 gap-3 px-6 pt-4 shrink-0">
              <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
                <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider">Pages Status</span>
                <span className="text-lg font-bold text-white mt-1">
                  {summary.totalTargeted} <span className="text-xs font-normal text-slate-400">/ {data?.page_count ?? 'N/A'} targeted</span>
                </span>
              </div>
              <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
                <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider">Extracted Components</span>
                <span className="text-lg font-bold text-emerald-400 mt-1">{summary.components}</span>
              </div>
              <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
                <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider">Extracted Jobs</span>
                <span className="text-lg font-bold text-sky-400 mt-1">{summary.jobs}</span>
              </div>
              <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
                <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider">Extracted Spares</span>
                <span className="text-lg font-bold text-amber-400 mt-1">{summary.spares}</span>
              </div>
            </div>

            {/* Topbar Search & Filter Controls */}
            <div className="flex items-center justify-between gap-3 px-6 py-4 shrink-0 border-b border-slate-800">
              <div className="flex items-center gap-2 flex-1 max-w-sm">
                <div className="relative w-full">
                  <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by page number, item name..."
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 flex items-center gap-1">
                  <Filter className="h-3 w-3" /> Filters:
                </span>
                <div className="inline-flex rounded-lg border border-slate-800 bg-slate-950/40 p-0.5">
                  {(
                    [
                      ['all', 'All'],
                      ['success', 'Processed'],
                      ['failed', 'Failed'],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={() => setStatusFilter(key)}
                      className={`rounded px-2.5 py-1 text-[10px] font-medium transition-colors ${
                        statusFilter === key
                          ? 'bg-slate-800 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => retryManualMutation.mutate()}
                  disabled={retryManualMutation.isPending || retryMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-sky-800/50 text-xs text-white font-medium px-3 py-1.5 transition-colors shadow-md ml-2"
                  title="Re-run extraction for all targeted pages in this manual"
                >
                  {retryManualMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                  <span>Re-extract Manual</span>
                </button>
                {isCurrentlyExtracting && (
                  <button
                    onClick={() => stopMutation.mutate()}
                    disabled={stopMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800/50 text-xs text-white font-medium px-3 py-1.5 transition-colors shadow-md ml-2"
                    title="Stop/cancel active extraction task for this vessel"
                  >
                    {stopMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5" />
                    )}
                    <span>Stop Extraction</span>
                  </button>
                )}
              </div>
            </div>

            {/* Scrollable Table Area */}
            <div className="flex-1 overflow-y-auto px-6 py-2">
              {filteredPages.length === 0 ? (
                <div className="text-center py-16 text-slate-500 text-xs">
                  No pages match the search query and filters.
                </div>
              ) : (
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 font-semibold uppercase tracking-wider">
                      <th className="py-2.5 px-3 w-[15%]">Page Number</th>
                      <th className="py-2.5 px-3 w-[25%]">Extraction Status</th>
                      <th className="py-2.5 px-3 w-[45%]">Extracted Items</th>
                      <th className="py-2.5 px-3 w-[15%] text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {filteredPages.map((page) => {
                      const isExpanded = !!expandedPages[page.page_number]
                      const targetTypes: string[] = []
                      if (page.targeted_types.component) targetTypes.push('Components')
                      if (page.targeted_types.job) targetTypes.push('Jobs')
                      if (page.targeted_types.spare) targetTypes.push('Spares')

                      const statusColors = {
                        success: 'bg-emerald-950/40 border-emerald-800/50 text-emerald-400',
                        failed: 'bg-rose-950/40 border-rose-800/50 text-rose-400',
                        pending: 'bg-sky-950/40 border-sky-800/50 text-sky-400',
                        skipped: 'bg-slate-950/40 border-slate-800/50 text-slate-400',
                      }[page.status]

                      const statusLabels = {
                        success: 'Processed',
                        failed: 'Failed',
                        pending: 'Extracting...',
                        skipped: 'Not Targeted',
                      }[page.status]

                      const isRetrying = retryMutation.isPending && retryMutation.variables?.pageNumber === page.page_number
                      const retryEntityTypes: string[] = []
                      if (page.targeted_types.component) retryEntityTypes.push('component')
                      if (page.targeted_types.job) retryEntityTypes.push('job')
                      if (page.targeted_types.spare) retryEntityTypes.push('spare')

                      return (
                        <React.Fragment key={page.page_number}>
                          <tr className={`hover:bg-slate-800/20 transition-colors ${page.is_targeted ? 'bg-slate-900/10' : ''}`}>
                            {/* Page # */}
                            <td className="py-3.5 px-3 font-semibold text-slate-200">
                              <div className="flex items-center gap-1.5">
                                <span>p. {page.page_number}</span>
                                {page.is_targeted && (
                                  <span className="inline-flex rounded-full bg-sky-950/50 border border-sky-800/50 px-1.5 py-0.5 text-[9px] font-medium text-sky-400 uppercase tracking-wide">
                                    Targeted
                                  </span>
                                )}
                              </div>
                            </td>

                            {/* Status */}
                            <td className="py-3.5 px-3">
                              <div className="space-y-1.5">
                                <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-[10px] font-medium ${statusColors}`}>
                                  {page.status === 'pending' && <Loader2 className="h-3 w-3 animate-spin shrink-0" />}
                                  {statusLabels}
                                </span>
                                {targetTypes.length > 0 && (
                                  <div className="text-[10px] text-slate-500">
                                    Targeted: <span className="text-slate-400">{targetTypes.join(', ')}</span>
                                  </div>
                                )}
                              </div>
                            </td>

                            {/* Extracted Items */}
                            <td className="py-3.5 px-3">
                              {page.extracted_count > 0 ? (
                                <div className="space-y-1">
                                  <button
                                    onClick={() => togglePageExpand(page.page_number)}
                                    className="text-slate-300 hover:text-white inline-flex items-center gap-1.5 hover:underline"
                                  >
                                    <span className="font-semibold text-slate-200">
                                      {page.extracted_count} {page.extracted_count === 1 ? 'item' : 'items'}
                                    </span>
                                    <span className="text-slate-500 text-[10px]">
                                      ({page.items.filter((i) => i.type === 'component').length} comps,{' '}
                                      {page.items.filter((i) => i.type === 'job').length} jobs,{' '}
                                      {page.items.filter((i) => i.type === 'spare').length} spares)
                                    </span>
                                    {isExpanded ? (
                                      <ChevronUp className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                                    ) : (
                                      <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                                    )}
                                  </button>
                                </div>
                              ) : (
                                <span className="text-slate-500 italic">No items extracted</span>
                              )}
                            </td>

                            {/* Action Button */}
                            <td className="py-3.5 px-3 text-right">
                              {page.is_targeted ? (
                                <button
                                  onClick={() =>
                                    retryMutation.mutate({
                                      pageNumber: page.page_number,
                                      entityTypes: retryEntityTypes.length > 0 ? retryEntityTypes : ['component', 'job', 'spare'],
                                    })
                                  }
                                  disabled={isRetrying || retryMutation.isPending || retryManualMutation.isPending}
                                  className="inline-flex items-center gap-1 rounded bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:border-slate-600 disabled:opacity-50 text-sky-400 disabled:text-sky-700 px-2 py-1 transition-colors"
                                  title={`Re-run extraction specifically for page ${page.page_number}`}
                                >
                                  {isRetrying ? (
                                    <Loader2 className="h-3 w-3 animate-spin shrink-0" />
                                  ) : (
                                    <Play className="h-3 w-3 fill-sky-400 shrink-0" />
                                  )}
                                  <span>Retry Page</span>
                                </button>
                              ) : (
                                <span className="text-slate-600" title="Only targeted pages can be retried">—</span>
                              )}
                            </td>
                          </tr>

                          {/* Expanded items list row */}
                          {isExpanded && page.extracted_count > 0 && (
                            <tr>
                              <td colSpan={4} className="bg-slate-950/20 px-6 py-2 border-b border-slate-800/40">
                                <div className="space-y-1.5 py-1">
                                  {page.items.map((item, index) => {
                                    const badgeColor = {
                                      component: 'bg-emerald-950/30 border-emerald-800/30 text-emerald-400',
                                      job: 'bg-sky-950/30 border-sky-800/30 text-sky-400',
                                      spare: 'bg-amber-950/30 border-amber-800/30 text-amber-400',
                                    }[item.type]

                                    return (
                                      <div key={index} className="flex items-start gap-2 text-xs py-1 border-b border-slate-800/10 last:border-0">
                                        <span className={`inline-flex rounded px-1.5 py-0.5 text-[9px] font-semibold border uppercase shrink-0 ${badgeColor}`}>
                                          {item.type}
                                        </span>
                                        <div className="flex-1">
                                          <span className="font-medium text-slate-200">{item.name}</span>
                                          {item.detail && (
                                            <span className="text-slate-500 text-[10px] ml-1.5 font-normal">
                                              ({item.detail})
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                    )
                                  })}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Footer Summary Info */}
            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/20 text-[11px] text-slate-500 flex items-center justify-between shrink-0 rounded-b-2xl">
              <div className="flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5 text-slate-500" />
                <span>Skipped pages are ignored during manual extraction to conserve credits.</span>
              </div>
              <div>
                Showing {filteredPages.length} of {data?.pages?.length ?? 0} pages
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  X,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertCircle,
  Loader2,
  History,
  RotateCcw,
  Clock,
  Trash2,
  Archive,
  Zap,
  FileText,
  ChevronDown,
  ChevronUp,
  Tag,
  Check,
  FolderArchive,
  Layers,
} from 'lucide-react'
import apiClient from '@/api/client'
import { PageRefHistoryModal } from './PageRefHistoryModal'

export interface DeletedManual {
  id: string
  vessel_id: string
  original_filename: string
  file_extension: string
  file_size_bytes: number
  category?: string | null
  classification_confidence?: number | null
  useful_for_extraction?: string | null
  pages_with_components?: string | null
  pages_with_jobs?: string | null
  pages_with_spares?: string | null
  pages_with_components_physical?: string | null
  pages_with_jobs_physical?: string | null
  pages_with_spares_physical?: string | null
  page_count?: number | null
  created_at: string
  updated_at: string
  manual_extraction_run_count: number
  page_extraction_counts: Record<string, number>
  last_extraction_at?: string | null
  extracted_components_count: number
  extracted_jobs_count: number
  extracted_spares_count: number
  history_snapshot_count: number
}

interface DeletedManualsModalProps {
  vesselId: string
  isOpen: boolean
  onClose: () => void
  onManualRestored?: (manualId: string) => void
}

export function DeletedManualsModal({
  vesselId,
  isOpen,
  onClose,
  onManualRestored,
}: DeletedManualsModalProps) {
  const queryClient = useQueryClient()
  const [searchTerm, setSearchTerm] = useState('')
  const [filterRuns, setFilterRuns] = useState<'all' | 'ran' | 'none'>('all')
  const [expandedPagesManualId, setExpandedPagesManualId] = useState<string | null>(null)
  const [confirmRestoreId, setConfirmRestoreId] = useState<string | null>(null)
  const [selectedManualForHistory, setSelectedManualForHistory] = useState<DeletedManual | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const {
    data: deletedManuals = [],
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery<DeletedManual[]>({
    queryKey: ['deleted-manuals', vesselId],
    queryFn: async () => {
      const res = await apiClient.get<DeletedManual[]>(`/vessels/${vesselId}/manuals/deleted`)
      return res.data
    },
    enabled: isOpen,
    staleTime: 5000,
  })

  const restoreMutation = useMutation({
    mutationFn: async (manualId: string) => {
      const res = await apiClient.post(`/vessels/${vesselId}/manuals/${manualId}/restore-deleted`)
      return res.data
    },
    onSuccess: (data, manualId) => {
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['deleted-manuals', vesselId] })
      setConfirmRestoreId(null)
      setSuccessMsg('Manual and all its extracted records were successfully restored!')
      setTimeout(() => setSuccessMsg(null), 4000)
      if (onManualRestored) {
        onManualRestored(manualId)
      }
    },
  })

  const filteredManuals = useMemo(() => {
    return deletedManuals.filter((m) => {
      if (filterRuns === 'ran' && m.manual_extraction_run_count === 0) return false
      if (filterRuns === 'none' && m.manual_extraction_run_count > 0) return false

      if (!searchTerm) return true
      const term = searchTerm.toLowerCase()
      return (
        m.original_filename.toLowerCase().includes(term) ||
        (m.category && m.category.toLowerCase().includes(term)) ||
        (m.pages_with_components && m.pages_with_components.toLowerCase().includes(term)) ||
        (m.pages_with_jobs && m.pages_with_jobs.toLowerCase().includes(term)) ||
        (m.pages_with_spares && m.pages_with_spares.toLowerCase().includes(term))
      )
    })
  }, [deletedManuals, filterRuns, searchTerm])

  const stats = useMemo(() => {
    let totalRuns = 0
    let totalComps = 0
    let totalJobs = 0
    let totalSpares = 0
    for (const m of deletedManuals) {
      totalRuns += m.manual_extraction_run_count || 0
      totalComps += m.extracted_components_count || 0
      totalJobs += m.extracted_jobs_count || 0
      totalSpares += m.extracted_spares_count || 0
    }
    return {
      count: deletedManuals.length,
      totalRuns,
      totalComps,
      totalJobs,
      totalSpares,
    }
  }, [deletedManuals])

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDateTime = (isoString?: string | null) => {
    if (!isoString) return '-'
    try {
      const d = new Date(isoString)
      return d.toLocaleString(undefined, {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return isoString
    }
  }

  if (!isOpen) return null

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-150">
        <div className="flex flex-col w-full max-w-6xl h-[90vh] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-900/90">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400">
                <Trash2 className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                  Deleted Manuals Archive
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-rose-950/80 border border-rose-800 text-rose-300 font-bold">
                    {deletedManuals.length} Deleted
                  </span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  View full history, extraction runs, and page references for deleted manuals of this vessel.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors disabled:opacity-50"
                title="Refresh deleted manuals"
              >
                <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                title="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Top Summary Banner */}
          <div className="bg-slate-950/70 border-b border-slate-800/80 px-6 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300">
                  <Archive className="h-4 w-4 text-rose-400" />
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Deleted Manuals</div>
                  <div className="text-base font-bold text-slate-100">{stats.count}</div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300">
                  <Zap className="h-4 w-4 text-amber-400" />
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Total Extractions Run</div>
                  <div className="text-base font-bold text-amber-400">{stats.totalRuns} times</div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300">
                  <Layers className="h-4 w-4 text-sky-400" />
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Extracted Records</div>
                  <div className="text-xs font-medium text-slate-300 mt-0.5">
                    <span className="text-sky-300 font-bold">{stats.totalComps}</span> comps •{' '}
                    <span className="text-teal-300 font-bold">{stats.totalJobs}</span> jobs •{' '}
                    <span className="text-amber-300 font-bold">{stats.totalSpares}</span> spares
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300">
                  <RotateCcw className="h-4 w-4 text-emerald-400" />
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Undelete / Restore</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    1-Click Restore available
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Success Banner */}
          {successMsg && (
            <div className="bg-emerald-950/80 border-b border-emerald-800/60 px-6 py-2.5 flex items-center gap-2 text-emerald-300 text-xs animate-in slide-in-from-top-1">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Search & Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-b border-slate-800 bg-slate-900/60">
            <div className="relative flex-1 min-w-[220px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search deleted manuals by filename, category, pages..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Filter Extractions:</span>
              <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-xs">
                {(['all', 'ran', 'none'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setFilterRuns(mode)}
                    className={`px-3 py-1 rounded-md transition-colors ${
                      filterRuns === mode
                        ? 'bg-rose-500/20 text-rose-300 font-semibold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {mode === 'all' ? 'All Deleted' : mode === 'ran' ? 'Ran Extractions' : 'Never Ran'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* List of Deleted Manuals */}
          <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-slate-950/40">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center h-64 gap-3 text-slate-400">
                <Loader2 className="h-7 w-7 animate-spin text-rose-400" />
                <p className="text-xs">Loading deleted manuals archive...</p>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-64 gap-3 text-rose-400">
                <AlertCircle className="h-7 w-7 text-rose-500" />
                <p className="text-xs">Failed to load deleted manuals.</p>
                <button
                  onClick={() => refetch()}
                  className="px-3 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 hover:bg-slate-700"
                >
                  Retry
                </button>
              </div>
            ) : filteredManuals.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 gap-2 text-slate-500">
                <FolderArchive className="h-8 w-8 text-slate-600" />
                <p className="text-sm font-medium text-slate-400">No deleted manuals found</p>
                <p className="text-xs text-slate-500">
                  {searchTerm || filterRuns !== 'all'
                    ? 'No deleted manuals matched your filter criteria.'
                    : 'There are currently no deleted manuals for this vessel.'}
                </p>
              </div>
            ) : (
              filteredManuals.map((m) => {
                const isConfirming = confirmRestoreId === m.id
                const isRestoring = restoreMutation.isPending && confirmRestoreId === m.id
                const isExpanded = expandedPagesManualId === m.id
                const pageRunsEntries = Object.entries(m.page_extraction_counts || {}).sort(
                  ([a], [b]) => Number(a) - Number(b)
                )

                return (
                  <div
                    key={m.id}
                    className="rounded-xl border border-slate-800 bg-slate-900/60 p-4.5 hover:border-slate-700 transition-all space-y-3"
                  >
                    {/* Top Row: Filename, Badges & Actions */}
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 max-w-3xl">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-sm font-semibold text-slate-100 break-all font-mono" title={m.original_filename}>
                            {m.original_filename}
                          </h3>
                          {m.category && (
                            <span className="inline-flex items-center gap-1 rounded bg-slate-800 border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                              <Tag className="h-3 w-3 text-slate-400" />
                              {m.category}
                            </span>
                          )}
                          <span className="text-[11px] text-slate-400">
                            {formatFileSize(m.file_size_bytes)} • {m.page_count ? `${m.page_count} pages` : 'pages unknown'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1">
                          <Clock className="h-3 w-3" />
                          <span>Deleted/Last modified: {formatDateTime(m.updated_at)}</span>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 shrink-0">
                        {/* Page Ref History Button */}
                        <button
                          type="button"
                          onClick={() => setSelectedManualForHistory(m)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs font-medium text-amber-400 hover:bg-slate-750 hover:text-amber-300 transition-colors shadow-sm"
                          title="View complete page references change history snapshots"
                        >
                          <History className="h-3.5 w-3.5" />
                          <span>History ({m.history_snapshot_count})</span>
                        </button>

                        {/* Restore Button */}
                        {isConfirming ? (
                          <div className="flex items-center gap-1.5 animate-in fade-in duration-150">
                            <button
                              type="button"
                              onClick={() => restoreMutation.mutate(m.id)}
                              disabled={isRestoring}
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors disabled:opacity-50 shadow-sm"
                            >
                              {isRestoring ? (
                                <>
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  <span>Restoring...</span>
                                </>
                              ) : (
                                <>
                                  <Check className="h-3.5 w-3.5" />
                                  <span>Confirm Restore</span>
                                </>
                              )}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmRestoreId(null)}
                              disabled={isRestoring}
                              className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setConfirmRestoreId(m.id)}
                            disabled={restoreMutation.isPending}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-700/60 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/60 hover:text-emerald-200 transition-colors shadow-sm"
                            title="Restore this manual and un-delete its components, jobs, and spares"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            <span>Restore Manual</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Middle Row: Extraction Runs & Extracted Items Metric Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 text-xs">
                      {/* Extraction Count */}
                      <div className="rounded-lg bg-slate-950/60 border border-slate-800 p-2.5">
                        <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
                          <span className="font-semibold text-amber-400 flex items-center gap-1">
                            <Zap className="h-3 w-3" />
                            Extractions Run
                          </span>
                          {pageRunsEntries.length > 0 && (
                            <button
                              type="button"
                              onClick={() => setExpandedPagesManualId(isExpanded ? null : m.id)}
                              className="text-[10px] text-amber-400 hover:underline inline-flex items-center gap-0.5"
                            >
                              {isExpanded ? 'Hide pages' : `${pageRunsEntries.length} pages detail`}
                              {isExpanded ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
                            </button>
                          )}
                        </div>
                        <div className="text-sm font-bold text-slate-100 flex items-baseline gap-1.5">
                          {m.manual_extraction_run_count > 0 ? (
                            <span className="text-amber-400 font-mono">{m.manual_extraction_run_count} time{m.manual_extraction_run_count === 1 ? '' : 's'}</span>
                          ) : (
                            <span className="text-slate-500 font-normal">0 runs recorded</span>
                          )}
                        </div>
                        {m.last_extraction_at && (
                          <div className="text-[10px] text-slate-500 mt-1 truncate">
                            Last: {formatDateTime(m.last_extraction_at)}
                          </div>
                        )}
                      </div>

                      {/* Saved References */}
                      <div className="rounded-lg bg-slate-950/60 border border-slate-800 p-2.5">
                        <div className="text-slate-400 text-[11px] font-semibold mb-1">Saved Ref Pages</div>
                        <div className="space-y-0.5 text-[11px] font-mono">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Components:</span>
                            <span className="text-sky-300 font-medium truncate max-w-[120px]">{m.pages_with_components || 'None'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Jobs:</span>
                            <span className="text-teal-300 font-medium truncate max-w-[120px]">{m.pages_with_jobs || 'None'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Spares:</span>
                            <span className="text-amber-300 font-semibold truncate max-w-[120px]">{m.pages_with_spares || 'None'}</span>
                          </div>
                        </div>
                      </div>

                      {/* Extracted Records Count */}
                      <div className="rounded-lg bg-slate-950/60 border border-slate-800 p-2.5">
                        <div className="text-slate-400 text-[11px] font-semibold mb-1">Extracted Items History</div>
                        <div className="space-y-0.5 text-[11px]">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Components:</span>
                            <span className="text-sky-400 font-mono font-semibold">{m.extracted_components_count}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Jobs:</span>
                            <span className="text-teal-400 font-mono font-semibold">{m.extracted_jobs_count}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Spares:</span>
                            <span className="text-amber-400 font-mono font-semibold">{m.extracted_spares_count}</span>
                          </div>
                        </div>
                      </div>

                      {/* Physical Page Refs */}
                      <div className="rounded-lg bg-slate-950/60 border border-slate-800 p-2.5">
                        <div className="text-slate-400 text-[11px] font-semibold mb-1">Physical Page Refs</div>
                        <div className="space-y-0.5 text-[11px] font-mono">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Comp Phys:</span>
                            <span className="text-slate-300 truncate max-w-[120px]">{m.pages_with_components_physical || '-'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Job Phys:</span>
                            <span className="text-slate-300 truncate max-w-[120px]">{m.pages_with_jobs_physical || '-'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Spare Phys:</span>
                            <span className="text-slate-300 truncate max-w-[120px]">{m.pages_with_spares_physical || '-'}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Expandable Per-Page Run Counts Breakdown */}
                    {isExpanded && pageRunsEntries.length > 0 && (
                      <div className="rounded-lg bg-slate-950/80 border border-amber-500/30 p-3 animate-in fade-in duration-150">
                        <div className="text-xs font-semibold text-amber-300 mb-2 flex items-center gap-1.5">
                          <Zap className="h-3.5 w-3.5 text-amber-400" />
                          <span>Page-by-Page Extraction Runs Breakdown:</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {pageRunsEntries.map(([pageNum, count]) => (
                            <div
                              key={pageNum}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-xs font-mono"
                            >
                              <span className="text-slate-300">Page {pageNum}:</span>
                              <span className="px-1.5 py-0.2 rounded bg-amber-950/80 border border-amber-700/80 text-amber-300 font-bold">
                                {count} run{count === 1 ? '' : 's'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-900/90 text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <span className="text-slate-500">Tip:</span>
              <span>Click &quot;Restore Manual&quot; to reinstate any deleted manual and all its extracted records instantly.</span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>

      {/* Sub-modal: Page Reference Change History for Deleted Manual */}
      {selectedManualForHistory && (
        <PageRefHistoryModal
          vesselId={vesselId}
          manualId={selectedManualForHistory.id}
          manualTitle={`[DELETED] ${selectedManualForHistory.original_filename}`}
          currentComponents={selectedManualForHistory.pages_with_components}
          currentJobs={selectedManualForHistory.pages_with_jobs}
          currentSpares={selectedManualForHistory.pages_with_spares}
          onClose={() => setSelectedManualForHistory(null)}
          onRestored={() => {
            refetch()
            queryClient.invalidateQueries({ queryKey: ['deleted-manuals', vesselId] })
          }}
        />
      )}
    </>
  )
}

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
  User as UserIcon,
  Tag,
  ArrowRight,
  SlidersHorizontal,
} from 'lucide-react'
import apiClient from '@/api/client'

export interface PageRefHistoryItem {
  id: string
  tenant_id: string
  vessel_id: string
  manual_id: string
  changed_by_user_id?: string | null
  changed_by_name?: string | null
  change_source: string
  pages_with_components?: string | null
  pages_with_jobs?: string | null
  pages_with_spares?: string | null
  pages_with_components_physical?: string | null
  pages_with_jobs_physical?: string | null
  pages_with_spares_physical?: string | null
  previous_pages_with_components?: string | null
  previous_pages_with_jobs?: string | null
  previous_pages_with_spares?: string | null
  notes?: string | null
  created_at: string
}

interface PageRefHistoryModalProps {
  vesselId: string
  manualId: string
  manualTitle: string
  currentComponents?: string | null
  currentJobs?: string | null
  currentSpares?: string | null
  onClose: () => void
  onRestored?: () => void
}

export function PageRefHistoryModal({
  vesselId,
  manualId,
  manualTitle,
  currentComponents,
  currentJobs,
  currentSpares,
  onClose,
  onRestored,
}: PageRefHistoryModalProps) {
  const queryClient = useQueryClient()
  const [searchTerm, setSearchTerm] = useState('')
  const [sourceFilter, setSourceFilter] = useState<string>('all')
  const [confirmRestoreId, setConfirmRestoreId] = useState<string | null>(null)
  const [restoreSuccessMsg, setRestoreSuccessMsg] = useState<string | null>(null)

  const {
    data: historyList = [],
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery<PageRefHistoryItem[]>({
    queryKey: ['manual-page-ref-history', vesselId, manualId],
    queryFn: async () => {
      const res = await apiClient.get<PageRefHistoryItem[]>(
        `/vessels/${vesselId}/manuals/${manualId}/page-ref-history`
      )
      return res.data
    },
    staleTime: 5000,
  })

  const restoreMutation = useMutation({
    mutationFn: async (historyId: string) => {
      const res = await apiClient.post(
        `/vessels/${vesselId}/manuals/${manualId}/restore-page-ref-snapshot/${historyId}`
      )
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['manual-page-ref-history', vesselId, manualId] })
      setConfirmRestoreId(null)
      setRestoreSuccessMsg('Page references successfully restored from snapshot!')
      setTimeout(() => setRestoreSuccessMsg(null), 4000)
      if (onRestored) {
        onRestored()
      }
    },
  })

  const filteredHistory = useMemo(() => {
    return historyList.filter((item) => {
      if (sourceFilter !== 'all' && item.change_source !== sourceFilter) {
        return false
      }
      if (!searchTerm) return true
      const term = searchTerm.toLowerCase()
      return (
        item.change_source.toLowerCase().includes(term) ||
        (item.changed_by_name && item.changed_by_name.toLowerCase().includes(term)) ||
        (item.notes && item.notes.toLowerCase().includes(term)) ||
        (item.pages_with_components && item.pages_with_components.toLowerCase().includes(term)) ||
        (item.pages_with_jobs && item.pages_with_jobs.toLowerCase().includes(term)) ||
        (item.pages_with_spares && item.pages_with_spares.toLowerCase().includes(term))
      )
    })
  }, [historyList, sourceFilter, searchTerm])

  const renderSourceBadge = (source: string) => {
    switch (source) {
      case 'user_edit':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-blue-900/60 border border-blue-700/60 px-2 py-0.5 text-xs font-medium text-blue-300">
            <UserIcon className="h-3 w-3" />
            User Edit
          </span>
        )
      case 'excel_import':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-emerald-900/60 border border-emerald-700/60 px-2 py-0.5 text-xs font-medium text-emerald-300">
            <Tag className="h-3 w-3" />
            Excel Import
          </span>
        )
      case 'ai_screening':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-purple-900/60 border border-purple-700/60 px-2 py-0.5 text-xs font-medium text-purple-300">
            <SlidersHorizontal className="h-3 w-3" />
            AI Screening
          </span>
        )
      case 'restored':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-900/60 border border-amber-700/60 px-2 py-0.5 text-xs font-medium text-amber-300">
            <RotateCcw className="h-3 w-3" />
            Restored
          </span>
        )
      case 'initial_baseline':
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded bg-slate-800 border border-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300">
            <History className="h-3 w-3" />
            {source.replace('_', ' ')}
          </span>
        )
    }
  }

  const formatDateTime = (isoString: string) => {
    try {
      const date = new Date(isoString)
      return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return isoString
    }
  }

  const isCurrentActive = (item: PageRefHistoryItem) => {
    const curC = (currentComponents || '').trim()
    const curJ = (currentJobs || '').trim()
    const curS = (currentSpares || '').trim()
    const itemC = (item.pages_with_components || '').trim()
    const itemJ = (item.pages_with_jobs || '').trim()
    const itemS = (item.pages_with_spares || '').trim()
    return curC === itemC && curJ === itemJ && curS === itemS
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="flex flex-col w-full max-w-5xl h-[88vh] bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-900/90">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <History className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                Page Reference Change History
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400 font-normal">
                  {historyList.length} snapshot{historyList.length === 1 ? '' : 's'}
                </span>
              </h2>
              <p className="text-xs text-slate-400 truncate max-w-2xl font-mono mt-0.5" title={manualTitle}>
                {manualTitle}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors disabled:opacity-50"
              title="Refresh history"
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

        {/* Current Active References Banner */}
        <div className="bg-slate-950/80 border-b border-slate-800/80 px-6 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium uppercase tracking-wider text-[10px]">
                Current Active References:
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500">Components:</span>
                <span className="font-mono px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-sky-400">
                  {currentComponents || 'None'}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500">Jobs:</span>
                <span className="font-mono px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-teal-400">
                  {currentJobs || 'None'}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500">Spares:</span>
                <span className="font-mono px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-amber-400 font-semibold">
                  {currentSpares || 'None'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Success Alert */}
        {restoreSuccessMsg && (
          <div className="bg-emerald-950/70 border-b border-emerald-800/60 px-6 py-2.5 flex items-center gap-2 text-emerald-300 text-xs animate-in slide-in-from-top-1">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>{restoreSuccessMsg}</span>
          </div>
        )}

        {/* Filter bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-b border-slate-800 bg-slate-900/60">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search snapshots by user, note, or pages..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Filter Source:</span>
            <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-xs">
              {(['all', 'user_edit', 'excel_import', 'ai_screening', 'restored'] as const).map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => setSourceFilter(source)}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    sourceFilter === source
                      ? 'bg-amber-500/20 text-amber-300 font-medium'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {source === 'all'
                    ? 'All'
                    : source === 'user_edit'
                    ? 'User Edit'
                    : source === 'excel_import'
                    ? 'Excel'
                    : source === 'ai_screening'
                    ? 'AI Screening'
                    : 'Restored'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Content list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-slate-950/40">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3 text-slate-400">
              <Loader2 className="h-7 w-7 animate-spin text-amber-400" />
              <p className="text-xs">Loading page reference snapshots...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3 text-rose-400">
              <AlertCircle className="h-7 w-7 text-rose-500" />
              <p className="text-xs">Failed to load change history.</p>
              <button
                onClick={() => refetch()}
                className="px-3 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 hover:bg-slate-700"
              >
                Retry
              </button>
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 gap-2 text-slate-500">
              <History className="h-8 w-8 text-slate-600" />
              <p className="text-sm font-medium text-slate-400">No snapshots found</p>
              <p className="text-xs text-slate-500">
                {searchTerm || sourceFilter !== 'all'
                  ? 'No history entries matched your filter.'
                  : 'Snapshots are automatically captured whenever page references are saved, imported, or screened.'}
              </p>
            </div>
          ) : (
            filteredHistory.map((item, idx) => {
              const active = isCurrentActive(item)
              const isConfirming = confirmRestoreId === item.id
              const isRestoringThis = restoreMutation.isPending && confirmRestoreId === item.id

              return (
                <div
                  key={item.id}
                  className={`rounded-lg border p-4 transition-all ${
                    active
                      ? 'bg-slate-900/90 border-amber-500/40 ring-1 ring-amber-500/30'
                      : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
                        <Clock className="h-3.5 w-3.5 text-slate-500" />
                        <span>{formatDateTime(item.created_at)}</span>
                      </div>
                      {renderSourceBadge(item.change_source)}
                      {item.changed_by_name && (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          by <strong className="text-slate-300 font-medium">{item.changed_by_name}</strong>
                        </span>
                      )}
                      {active && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/80 border border-emerald-700/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                          Active State
                        </span>
                      )}
                      {idx === 0 && !active && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
                          Latest Entry
                        </span>
                      )}
                    </div>

                    {/* Restore Action */}
                    <div>
                      {isConfirming ? (
                        <div className="flex items-center gap-2 animate-in fade-in duration-150">
                          <span className="text-xs text-amber-300 font-medium">Revert to this snapshot?</span>
                          <button
                            type="button"
                            onClick={() => restoreMutation.mutate(item.id)}
                            disabled={isRestoringThis}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
                          >
                            {isRestoringThis ? (
                              <>
                                <Loader2 className="h-3 w-3 animate-spin" />
                                <span>Restoring...</span>
                              </>
                            ) : (
                              <>
                                <RotateCcw className="h-3 w-3" />
                                <span>Confirm Revert</span>
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmRestoreId(null)}
                            disabled={isRestoringThis}
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmRestoreId(item.id)}
                          disabled={active || restoreMutation.isPending}
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                            active
                              ? 'bg-slate-800/40 border-slate-800 text-slate-500 cursor-not-allowed'
                              : 'bg-slate-800 border-slate-700 text-amber-400 hover:bg-amber-950/40 hover:border-amber-700 hover:text-amber-300'
                          }`}
                          title={active ? 'Already the active state' : 'Restore these page references'}
                        >
                          <RotateCcw className="h-3 w-3" />
                          <span>{active ? 'Current Active' : 'Restore This'}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Notes if any */}
                  {item.notes && (
                    <div className="mt-2 text-xs text-slate-400 italic">
                      Note: {item.notes}
                    </div>
                  )}

                  {/* Snapshot Page References Grid */}
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Components */}
                    <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium mb-1">
                        <span className="text-sky-400 font-semibold">Components Ref</span>
                        {item.previous_pages_with_components &&
                          item.previous_pages_with_components !== item.pages_with_components && (
                            <span className="text-[10px] text-slate-500 flex items-center gap-0.5">
                              was: <span className="line-through">{item.previous_pages_with_components}</span>
                            </span>
                          )}
                      </div>
                      <div className="text-xs font-mono text-slate-200 break-all select-all">
                        {item.pages_with_components ? (
                          <span className="text-sky-300">{item.pages_with_components}</span>
                        ) : (
                          <span className="text-slate-600 italic">None specified</span>
                        )}
                      </div>
                    </div>

                    {/* Jobs */}
                    <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium mb-1">
                        <span className="text-teal-400 font-semibold">Jobs Ref</span>
                        {item.previous_pages_with_jobs &&
                          item.previous_pages_with_jobs !== item.pages_with_jobs && (
                            <span className="text-[10px] text-slate-500 flex items-center gap-0.5">
                              was: <span className="line-through">{item.previous_pages_with_jobs}</span>
                            </span>
                          )}
                      </div>
                      <div className="text-xs font-mono text-slate-200 break-all select-all">
                        {item.pages_with_jobs ? (
                          <span className="text-teal-300">{item.pages_with_jobs}</span>
                        ) : (
                          <span className="text-slate-600 italic">None specified</span>
                        )}
                      </div>
                    </div>

                    {/* Spares */}
                    <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium mb-1">
                        <span className="text-amber-400 font-semibold">Spares Ref</span>
                        {item.previous_pages_with_spares &&
                          item.previous_pages_with_spares !== item.pages_with_spares && (
                            <span className="text-[10px] text-amber-500/80 flex items-center gap-0.5">
                              was: <span className="line-through">{item.previous_pages_with_spares}</span>
                            </span>
                          )}
                      </div>
                      <div className="text-xs font-mono text-slate-200 break-all select-all">
                        {item.pages_with_spares ? (
                          <span className="text-amber-300 font-semibold">{item.pages_with_spares}</span>
                        ) : (
                          <span className="text-slate-600 italic">None specified</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-slate-800 bg-slate-900/90 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="text-slate-500">Tip:</span>
            <span>Click &quot;Restore This&quot; to revert page references back to any snapshot instantly.</span>
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
  )
}

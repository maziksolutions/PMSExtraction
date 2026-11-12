import React, { useState, useMemo } from 'react'
import {
  X,
  Layers,
  Search,
  Play,
  FileText,
  Loader2,
  RefreshCw,
  Filter,
  CheckCircle2,
  AlertCircle,
  Eye,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'

export interface UntouchedManualItem {
  id: string
  original_filename: string
  category?: string | null
  target_model?: string | null
  batch_number: number
  sequence_number?: number | null
  created_at?: string | null
  file_size_bytes: number
  useful_for_extraction?: string | null
  status: string
  pages_with_components: string
  pages_with_jobs: string
  pages_with_spares: string
  targeted_components_count: number
  targeted_jobs_count: number
  targeted_spares_count: number
  total_targeted_pages: number
  run_count: number
  extracted_pages_count: number
  is_never_run: boolean
}

interface UntouchedManualsModalProps {
  isOpen: boolean
  onClose: () => void
  vesselId: string
  manuals: UntouchedManualItem[]
  onExtractManuals: (manualIds: string[]) => void
  onFilterMainTable?: (manualIds: string[]) => void
  isExtracting?: boolean
  refetch?: () => void
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export const UntouchedManualsModal: React.FC<UntouchedManualsModalProps> = ({
  isOpen,
  onClose,
  vesselId,
  manuals = [],
  onExtractManuals,
  onFilterMainTable,
  isExtracting = false,
  refetch,
}) => {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'never_run' | 'zero_extracted'>('all')
  const [iterationFilter, setIterationFilter] = useState<number | 'all'>('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loadingManualId, setLoadingManualId] = useState<string | null>(null)
  const token = useAuthStore((s) => s.accessToken)

  // Collect unique iterations/batches
  const iterations = useMemo(() => {
    const set = new Set<number>()
    manuals.forEach((m) => {
      set.add(m.batch_number || 1)
    })
    return Array.from(set).sort((a, b) => a - b)
  }, [manuals])

  // Filtered manuals list
  const filteredManuals = useMemo(() => {
    return manuals.filter((m) => {
      // Search
      if (search.trim()) {
        const q = search.toLowerCase()
        const matchName = m.original_filename.toLowerCase().includes(q)
        const matchCat = (m.category || '').toLowerCase().includes(q)
        const matchModel = (m.target_model || '').toLowerCase().includes(q)
        if (!matchName && !matchCat && !matchModel) return false
      }

      // Status filter
      if (statusFilter === 'never_run' && !m.is_never_run) return false
      if (statusFilter === 'zero_extracted' && m.is_never_run) return false

      // Iteration filter
      if (iterationFilter !== 'all' && (m.batch_number || 1) !== iterationFilter) {
        return false
      }

      return true
    })
  }, [manuals, search, statusFilter, iterationFilter])

  // Selection handlers
  const handleToggleSelect = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const handleSelectAll = () => {
    if (selectedIds.size === filteredManuals.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredManuals.map((m) => m.id)))
    }
  }

  const handleOpenPdf = async (manualId: string) => {
    setLoadingManualId(manualId)
    try {
      const resp = await fetch(`/api/v1/vessels/${vesselId}/manuals/${manualId}/view`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) {
        alert('Could not open file')
        return
      }
      const ct = resp.headers.get('content-type') ?? ''
      if (ct.includes('application/json')) {
        const json = (await resp.json()) as { url: string }
        window.open(json.url, '_blank')
      } else {
        const blob = await resp.blob()
        const blobUrl = URL.createObjectURL(blob)
        window.open(blobUrl, '_blank')
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
      }
    } catch (err: any) {
      alert(`Could not open file: ${err?.message ?? 'Network error'}`)
    } finally {
      setLoadingManualId(null)
    }
  }

  const handleRunSelected = () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return
    onExtractManuals(ids)
    onClose()
  }

  const handleRunAllUntouched = () => {
    const ids = filteredManuals.map((m) => m.id)
    if (ids.length === 0) return
    onExtractManuals(ids)
    onClose()
  }

  const handleApplyFilterToMain = () => {
    if (onFilterMainTable) {
      onFilterMainTable(filteredManuals.map((m) => m.id))
      onClose()
    }
  }

  if (!isOpen) return null

  const neverRunCount = manuals.filter((m) => m.is_never_run).length
  const zeroExtractedCount = manuals.filter((m) => !m.is_never_run && m.extracted_pages_count === 0).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-5xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4 shrink-0">
          <div className="space-y-1 min-w-0 flex-1 pr-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
                <Layers className="h-4 w-4" />
              </div>
              <h2 className="text-base font-semibold text-white">Untouched Manuals (No Single Run)</h2>
              <span className="inline-flex items-center rounded-full bg-amber-950/60 border border-amber-600/50 px-2.5 py-0.5 text-xs font-bold text-amber-300">
                {manuals.length} Manuals
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Manuals that have never been run for extraction, or yielded 0 extracted pages. Select manuals to launch extraction.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="p-4 border-b border-slate-800 bg-slate-900/60 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
            {/* Search */}
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search untouched manuals..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/90 pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-amber-500 focus:outline-none"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-2 text-slate-400 hover:text-white text-xs"
                >
                  &times;
                </button>
              )}
            </div>

            {/* Run Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
            >
              <option value="all">All Untouched ({manuals.length})</option>
              <option value="never_run">Never Run (0 runs) ({neverRunCount})</option>
              <option value="zero_extracted">0 Pages Extracted ({zeroExtractedCount})</option>
            </select>

            {/* Iteration Filter */}
            {iterations.length > 1 && (
              <select
                value={iterationFilter}
                onChange={(e) => setIterationFilter(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
                className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
              >
                <option value="all">All Iterations</option>
                {iterations.map((iter) => (
                  <option key={iter} value={iter}>
                    Iteration #{iter}
                  </option>
                ))}
              </select>
            )}

            {refetch && (
              <button
                onClick={() => refetch()}
                className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:text-white hover:bg-slate-750 transition-colors"
                title="Refresh untouched manuals list"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {onFilterMainTable && (
              <button
                type="button"
                onClick={handleApplyFilterToMain}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-750 hover:text-white transition-colors"
                title="Show only these untouched manuals in the main table"
              >
                <Filter className="h-3.5 w-3.5 text-sky-400" />
                <span>Filter Main Table</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleRunSelected}
              disabled={selectedIds.size === 0 || isExtracting}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-white transition-colors shadow-sm"
            >
              {isExtracting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-white" />
              )}
              <span>Extract Selected ({selectedIds.size})</span>
            </button>
          </div>
        </div>

        {/* Content list */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {filteredManuals.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400 mb-2" />
              <p className="text-sm font-semibold text-slate-200">No Untouched Manuals Found</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                {search || statusFilter !== 'all' || iterationFilter !== 'all'
                  ? 'No manuals match the current search or filter criteria.'
                  : 'All targeted manuals in this vessel have already undergone extraction.'}
              </p>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-900 border-b border-slate-800 text-slate-500 font-semibold uppercase tracking-wider z-10">
                <tr>
                  <th className="py-2.5 px-3 w-[4%]">
                    <input
                      type="checkbox"
                      checked={filteredManuals.length > 0 && selectedIds.size === filteredManuals.length}
                      onChange={handleSelectAll}
                      className="rounded border-slate-700 bg-slate-800 text-emerald-500"
                    />
                  </th>
                  <th className="py-2.5 px-3 w-[8%]">#</th>
                  <th className="py-2.5 px-3 w-[36%]">Manual Name</th>
                  <th className="py-2.5 px-3 w-[16%]">Category / Model</th>
                  <th className="py-2.5 px-3 w-[18%]">Targeted Pages</th>
                  <th className="py-2.5 px-3 w-[14%] text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {filteredManuals.map((m) => {
                  const isSelected = selectedIds.has(m.id)
                  const isLoading = loadingManualId === m.id

                  return (
                    <tr
                      key={m.id}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        isSelected ? 'bg-emerald-950/20' : ''
                      }`}
                    >
                      <td className="py-3 px-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleToggleSelect(m.id)}
                          className="rounded border-slate-700 bg-slate-800 text-emerald-500"
                        />
                      </td>

                      {/* Sequence Number Badge */}
                      <td className="py-3 px-3">
                        <span
                          className="inline-flex items-center justify-center rounded bg-sky-950/60 border border-sky-700/50 px-2 py-0.5 text-xs font-bold font-mono text-sky-300 shadow-xs"
                          title={`Manual Sequence #${m.sequence_number ?? 1}`}
                        >
                          #{m.sequence_number ?? 1}
                        </span>
                      </td>

                      {/* File Name */}
                      <td className="py-3 px-3 min-w-0">
                        <div className="flex items-start gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleOpenPdf(m.id)}
                            className="inline-flex items-center gap-1.5 text-left text-slate-200 hover:text-sky-400 font-medium group transition-colors truncate max-w-[340px]"
                            title="Click to view manual PDF"
                          >
                            {isLoading ? (
                              <RefreshCw className="h-3.5 w-3.5 animate-spin text-sky-400 shrink-0" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 text-slate-500 group-hover:text-sky-400 shrink-0" />
                            )}
                            <span className="truncate">{m.original_filename}</span>
                          </button>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-500">
                          <span>{formatBytes(m.file_size_bytes)}</span>
                          <span>&bull;</span>
                          {m.is_never_run ? (
                            <span className="text-amber-400 font-semibold bg-amber-950/40 border border-amber-800/50 px-1.5 py-0.2 rounded">
                              Never Run (0 runs)
                            </span>
                          ) : (
                            <span className="text-slate-400 font-medium bg-slate-800/80 px-1.5 py-0.2 rounded">
                              {m.run_count} run(s) &bull; 0 extracted
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Category / Model */}
                      <td className="py-3 px-3">
                        <div className="font-medium text-slate-300 truncate max-w-[140px]">
                          {m.category || '—'}
                        </div>
                        {m.target_model && (
                          <div className="text-[10px] text-sky-400 truncate max-w-[140px]" title={m.target_model}>
                            {m.target_model}
                          </div>
                        )}
                      </td>

                      {/* Targeted Pages Summary */}
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1 flex-wrap text-[10px]">
                          {m.targeted_components_count > 0 && (
                            <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 bg-emerald-950/50 border border-emerald-800/40 text-emerald-400 font-semibold">
                              C: {m.targeted_components_count}
                            </span>
                          )}
                          {m.targeted_jobs_count > 0 && (
                            <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 bg-sky-950/50 border border-sky-800/40 text-sky-400 font-semibold">
                              J: {m.targeted_jobs_count}
                            </span>
                          )}
                          {m.targeted_spares_count > 0 && (
                            <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 bg-amber-950/50 border border-amber-800/40 text-amber-400 font-semibold">
                              S: {m.targeted_spares_count}
                            </span>
                          )}
                          {m.total_targeted_pages === 0 && (
                            <span className="text-slate-500 italic">No targeted pages</span>
                          )}
                        </div>
                      </td>

                      {/* Single Action */}
                      <td className="py-3 px-3 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            onExtractManuals([m.id])
                            onClose()
                          }}
                          disabled={isExtracting}
                          className="inline-flex items-center gap-1 rounded bg-slate-800 border border-slate-700 hover:bg-emerald-900/40 hover:border-emerald-600/50 text-emerald-400 px-2 py-1 transition-colors text-xs font-medium"
                          title={`Launch extraction for ${m.original_filename}`}
                        >
                          <Play className="h-3 w-3 fill-emerald-400" />
                          <span>Extract</span>
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/40 text-xs text-slate-400 flex items-center justify-between shrink-0 rounded-b-2xl">
          <div>
            Showing <span className="font-semibold text-slate-200">{filteredManuals.length}</span> of{' '}
            <span className="font-semibold text-slate-200">{manuals.length}</span> untouched manuals
            {selectedIds.size > 0 && (
              <span className="ml-2 text-emerald-400 font-semibold">
                ({selectedIds.size} selected)
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunAllUntouched}
              disabled={filteredManuals.length === 0 || isExtracting}
              className="flex items-center gap-1.5 rounded-lg border border-amber-600/50 bg-amber-950/40 hover:bg-amber-900/50 text-amber-300 px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-amber-300" />
              <span>Extract All ({filteredManuals.length})</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-750 hover:text-white transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

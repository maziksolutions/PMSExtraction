import React, { useState, useMemo, useEffect } from 'react'
import { X, Search, Zap, Layers, FileText, Filter, CheckSquare, Square, CheckCircle2, Clock, RotateCcw } from 'lucide-react'

export interface ManualItem {
  id: string
  original_filename: string
  category?: string | null
  page_count?: number | null
  pages_with_components?: string | null
  pages_with_components_physical?: string | null
  pages_with_jobs?: string | null
  pages_with_jobs_physical?: string | null
  pages_with_spares?: string | null
  pages_with_spares_physical?: string | null
}

export interface ManualSummaryItem {
  has_target_pages?: boolean
  total_target_pages?: number
  is_complete?: boolean
  total_missing_pages_count?: number
  missing_components_count?: number
  missing_jobs_count?: number
  missing_spares_count?: number
  missing_components_pages?: number[]
  missing_jobs_pages?: number[]
  missing_spares_pages?: number[]
  extracted_components_pages?: number[]
  extracted_jobs_pages?: number[]
  extracted_spares_pages?: number[]
  extracted_components_count?: number
  extracted_jobs_count?: number
  extracted_spares_count?: number
  total_extracted_pages_count?: number
}

interface ExtractionConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  manuals: ManualItem[]
  initialSelectedIds: Set<string> | string[]
  initialExtractionType: 'general' | 'jobs' | 'spares'
  onConfirm: (
    finalSelectedIds: string[],
    extractionType: 'general' | 'jobs' | 'spares',
    scope: 'pending' | 'full',
    manualPagesMap?: Record<string, number[]>
  ) => void
  isExtractAll?: boolean
  isPending?: boolean
  noExtractedSummary?: Record<string, ManualSummaryItem>
  edits?: Record<string, any>
}

function parsePageTokens(str?: string | null): number[] {
  if (!str) return []
  const pages: number[] = []
  const parts = str.split(/[,\s]+/)
  for (const part of parts) {
    if (part.includes('-')) {
      const [start, end] = part.split('-').map(Number)
      if (!isNaN(start) && !isNaN(end)) {
        for (let i = Math.min(start, end); i <= Math.max(start, end); i++) {
          if (i > 0) pages.push(i)
        }
      }
    } else {
      const n = Number(part)
      if (!isNaN(n) && n > 0) pages.push(n)
    }
  }
  return Array.from(new Set(pages)).sort((a, b) => a - b)
}

export function ExtractionConfirmationModal({
  isOpen,
  onClose,
  manuals,
  initialSelectedIds,
  initialExtractionType,
  onConfirm,
  isExtractAll = false,
  isPending = false,
  noExtractedSummary,
  edits,
}: ExtractionConfirmationModalProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [extractionType, setExtractionType] = useState<'general' | 'jobs' | 'spares'>('general')
  const [scope, setScope] = useState<'pending' | 'full'>('pending')
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [selectionFilter, setSelectionFilter] = useState<'all' | 'selected' | 'unselected'>('all')

  const getTargetPagesForManual = (manualId: string, type: 'general' | 'jobs' | 'spares'): number[] => {
    const edit = edits?.[manualId]
    const m = manuals.find((x) => x.id === manualId)

    if (type === 'spares') {
      const spareRefStr = (edit?.pages_with_spares_physical as string | undefined) ??
                          (edit?.pages_with_spares as string | undefined) ??
                          m?.pages_with_spares_physical ??
                          m?.pages_with_spares
      return parsePageTokens(spareRefStr)
    }
    if (type === 'jobs') {
      const jobRefStr = (edit?.pages_with_jobs_physical as string | undefined) ??
                        (edit?.pages_with_jobs as string | undefined) ??
                        m?.pages_with_jobs_physical ??
                        m?.pages_with_jobs
      return parsePageTokens(jobRefStr)
    }
    const compRefStr = (edit?.pages_with_components_physical as string | undefined) ??
                       (edit?.pages_with_components as string | undefined) ??
                       m?.pages_with_components_physical ??
                       m?.pages_with_components
    const jobRefStr = (edit?.pages_with_jobs_physical as string | undefined) ??
                      (edit?.pages_with_jobs as string | undefined) ??
                      m?.pages_with_jobs_physical ??
                      m?.pages_with_jobs
    const spareRefStr = (edit?.pages_with_spares_physical as string | undefined) ??
                        (edit?.pages_with_spares as string | undefined) ??
                        m?.pages_with_spares_physical ??
                        m?.pages_with_spares
    const set = new Set<number>([
      ...parsePageTokens(compRefStr),
      ...parsePageTokens(jobRefStr),
      ...parsePageTokens(spareRefStr),
    ])
    return Array.from(set).sort((a, b) => a - b)
  }

  // Helper to extract pending pages for a manual given the extraction type
  const getPendingPagesForManual = (manualId: string, type: 'general' | 'jobs' | 'spares'): number[] => {
    const summary = noExtractedSummary?.[manualId]
    const edit = edits?.[manualId]
    const m = manuals.find((x) => x.id === manualId)

    if (type === 'spares') {
      const spareRefStr = (edit?.pages_with_spares_physical as string | undefined) ??
                          (edit?.pages_with_spares as string | undefined) ??
                          m?.pages_with_spares_physical ??
                          m?.pages_with_spares
      if (spareRefStr !== undefined && spareRefStr.trim() !== '') {
        const targetPages = parsePageTokens(spareRefStr)
        const extracted = new Set(summary?.extracted_spares_pages || [])
        return targetPages.filter((p) => !extracted.has(p))
      }
      return summary?.missing_spares_pages || []
    }
    if (type === 'jobs') {
      const jobRefStr = (edit?.pages_with_jobs_physical as string | undefined) ??
                        (edit?.pages_with_jobs as string | undefined) ??
                        m?.pages_with_jobs_physical ??
                        m?.pages_with_jobs
      if (jobRefStr !== undefined && jobRefStr.trim() !== '') {
        const targetPages = parsePageTokens(jobRefStr)
        const extracted = new Set(summary?.extracted_jobs_pages || [])
        return targetPages.filter((p) => !extracted.has(p))
      }
      return summary?.missing_jobs_pages || []
    }
    // general: union of missing components, jobs, spares
    const compRefStr = (edit?.pages_with_components_physical as string | undefined) ??
                       (edit?.pages_with_components as string | undefined) ??
                       m?.pages_with_components_physical ??
                       m?.pages_with_components
    const jobRefStr = (edit?.pages_with_jobs_physical as string | undefined) ??
                      (edit?.pages_with_jobs as string | undefined) ??
                      m?.pages_with_jobs_physical ??
                      m?.pages_with_jobs
    const spareRefStr = (edit?.pages_with_spares_physical as string | undefined) ??
                        (edit?.pages_with_spares as string | undefined) ??
                        m?.pages_with_spares_physical ??
                        m?.pages_with_spares

    const compPending = (compRefStr !== undefined && compRefStr.trim() !== '')
      ? parsePageTokens(compRefStr).filter((p) => !(new Set(summary?.extracted_components_pages || [])).has(p))
      : (summary?.missing_components_pages || [])
    const jobPending = (jobRefStr !== undefined && jobRefStr.trim() !== '')
      ? parsePageTokens(jobRefStr).filter((p) => !(new Set(summary?.extracted_jobs_pages || [])).has(p))
      : (summary?.missing_jobs_pages || [])
    const sparePending = (spareRefStr !== undefined && spareRefStr.trim() !== '')
      ? parsePageTokens(spareRefStr).filter((p) => !(new Set(summary?.extracted_spares_pages || [])).has(p))
      : (summary?.missing_spares_pages || [])

    const set = new Set<number>([...compPending, ...jobPending, ...sparePending])
    return Array.from(set).sort((a, b) => a - b)
  }

  // Reset state when modal opens or manuals load
  useEffect(() => {
    if (isOpen) {
      const initialSet = new Set<string>()
      if (isExtractAll) {
        manuals.forEach((m) => {
          if (m.category !== null && m.category !== '') {
            initialSet.add(m.id)
          }
        })
      } else {
        if (initialSelectedIds instanceof Set) {
          initialSelectedIds.forEach((id) => initialSet.add(id))
        } else if (Array.isArray(initialSelectedIds)) {
          initialSelectedIds.forEach((id) => initialSet.add(id))
        }
      }
      setSelectedIds(initialSet)
      setExtractionType(initialExtractionType)
      setScope('pending') // Default to pending pages as requested
      setSearchQuery('')
      setCategoryFilter('all')
      setSelectionFilter('all')
    }
  }, [isOpen, initialSelectedIds, initialExtractionType, isExtractAll, manuals])

  // Extract unique categories dynamically from the manuals list
  const availableCategories = useMemo(() => {
    const set = new Set<string>()
    manuals.forEach((m) => {
      if (m.category) set.add(m.category)
    })
    return Array.from(set).sort()
  }, [manuals])

  // Aggregate pending pages count across currently selected manuals
  const totalPendingPages = useMemo(() => {
    let count = 0
    selectedIds.forEach((id) => {
      const pgs = getPendingPagesForManual(id, extractionType)
      count += pgs.length
    })
    return count
  }, [selectedIds, extractionType, noExtractedSummary])

  // Aggregate total configured reference pages across selected manuals
  const totalConfiguredPages = useMemo(() => {
    let count = 0
    selectedIds.forEach((id) => {
      const targetPgs = getTargetPagesForManual(id, extractionType)
      if (targetPgs.length > 0) {
        count += targetPgs.length
      } else {
        const summary = noExtractedSummary?.[id]
        if (summary) {
          if (extractionType === 'spares') {
            count += (summary.missing_spares_pages?.length || 0) + (summary.extracted_spares_pages?.length || 0)
          } else if (extractionType === 'jobs') {
            count += (summary.missing_jobs_pages?.length || 0) + (summary.extracted_jobs_pages?.length || 0)
          } else {
            count += summary.total_target_pages || 0
          }
        }
      }
    })
    return count
  }, [selectedIds, extractionType, noExtractedSummary, edits, manuals])

  // Count how many selected manuals actually have pending pages
  const manualsWithPendingCount = useMemo(() => {
    let count = 0
    selectedIds.forEach((id) => {
      if (getPendingPagesForManual(id, extractionType).length > 0) {
        count += 1
      }
    })
    return count
  }, [selectedIds, extractionType, noExtractedSummary])

  // Filter and sort manuals: Selected manuals are pinned to the TOP
  const filteredAndSortedManuals = useMemo(() => {
    let list = manuals

    // 1. Text Search Filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      list = list.filter(
        (m) =>
          m.original_filename.toLowerCase().includes(query) ||
          (m.category || '').toLowerCase().includes(query)
      )
    }

    // 2. Category Filter
    if (categoryFilter !== 'all') {
      if (categoryFilter === '__uncategorized__') {
        list = list.filter((m) => !m.category)
      } else {
        list = list.filter((m) => m.category === categoryFilter)
      }
    }

    // 3. Selection Status Filter
    if (selectionFilter === 'selected') {
      list = list.filter((m) => selectedIds.has(m.id))
    } else if (selectionFilter === 'unselected') {
      list = list.filter((m) => !selectedIds.has(m.id))
    }

    // 4. Sort: Checked/Selected manuals placed at the TOP
    return [...list].sort((a, b) => {
      const aSelected = selectedIds.has(a.id) ? 1 : 0
      const bSelected = selectedIds.has(b.id) ? 1 : 0
      if (aSelected !== bSelected) {
        return bSelected - aSelected // Selected first
      }
      return a.original_filename.localeCompare(b.original_filename)
    })
  }, [manuals, searchQuery, categoryFilter, selectionFilter, selectedIds])

  if (!isOpen) return null

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleSelectAllFiltered = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      filteredAndSortedManuals.forEach((m) => next.add(m.id))
      return next
    })
  }

  const handleDeselectAllFiltered = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      filteredAndSortedManuals.forEach((m) => next.delete(m.id))
      return next
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedIds.size === 0) return

    let manualPagesMap: Record<string, number[]> | undefined = undefined
    let targetIds = Array.from(selectedIds)

    if (scope === 'pending') {
      manualPagesMap = {}
      targetIds.forEach((id) => {
        const pgs = getPendingPagesForManual(id, extractionType)
        if (pgs.length > 0) {
          manualPagesMap![id] = pgs
        }
      })

      const withPending = Object.keys(manualPagesMap)
      if (withPending.length > 0) {
        targetIds = withPending
      } else {
        alert(
          `None of the ${selectedIds.size} selected manual(s) have pending un-extracted pages for ${
            extractionType === 'spares' ? 'Spares' : extractionType === 'jobs' ? 'Jobs' : 'General'
          }.\n\nPlease switch Page Scope to "Complete Selected Pages" to re-extract all reference pages.`
        )
        return
      }
    } else {
      manualPagesMap = {}
      targetIds.forEach((id) => {
        const pgs = getTargetPagesForManual(id, extractionType)
        if (pgs.length > 0) {
          manualPagesMap![id] = pgs
        }
      })
      if (Object.keys(manualPagesMap).length === 0) {
        manualPagesMap = undefined
      }
    }

    onConfirm(targetIds, extractionType, scope, manualPagesMap)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-6xl rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl p-5 sm:p-6 text-slate-100 max-h-[92vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <Layers className="h-5 w-5 text-emerald-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-100">Confirm Extraction Batch</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Choose extraction mode and whether to extract pending pages only or rerun complete selected pages.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content columns */}
        <form onSubmit={handleSubmit} className="flex-1 min-h-0 flex flex-col md:flex-row gap-6 mt-4">
          {/* Left: Manuals List Selector */}
          <div className="flex-1 min-w-0 flex flex-col min-h-0">
            {/* Filter Bar */}
            <div className="flex flex-col gap-2.5 mb-3">
              <div className="flex flex-col sm:flex-row gap-2.5 items-center justify-between">
                {/* Search */}
                <div className="relative w-full sm:flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    placeholder="Search manuals..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-lg border border-slate-800 bg-slate-950/60 pl-9 pr-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none transition-colors"
                  />
                </div>

                {/* Category Filter */}
                <div className="relative w-full sm:w-48 shrink-0">
                  <Filter className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="w-full rounded-lg border border-slate-800 bg-slate-950/60 pl-8 pr-3 py-2 text-xs text-slate-200 focus:border-sky-500 focus:outline-none transition-colors"
                  >
                    <option value="all">All Categories ({manuals.length})</option>
                    {availableCategories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                    <option value="__uncategorized__">Uncategorized</option>
                  </select>
                </div>
              </div>

              {/* Selection Status Pills & Quick Actions */}
              <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
                {/* Status Pills */}
                <div className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-lg border border-slate-850">
                  <button
                    type="button"
                    onClick={() => setSelectionFilter('all')}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      selectionFilter === 'all'
                        ? 'bg-slate-800 text-sky-400 font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    All ({manuals.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectionFilter('selected')}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      selectionFilter === 'selected'
                        ? 'bg-emerald-950/80 border border-emerald-800 text-emerald-400 font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Selected Only ({selectedIds.size})
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectionFilter('unselected')}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      selectionFilter === 'unselected'
                        ? 'bg-slate-800 text-slate-300 font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Unselected ({manuals.length - selectedIds.size})
                  </button>
                </div>

                {/* Batch Selection Buttons */}
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={handleSelectAllFiltered}
                    className="flex items-center gap-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-2.5 py-1 text-slate-300 transition-colors"
                  >
                    <CheckSquare className="h-3 w-3 text-emerald-400" />
                    <span>Select Filtered</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleDeselectAllFiltered}
                    className="flex items-center gap-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-2.5 py-1 text-slate-300 transition-colors"
                  >
                    <Square className="h-3 w-3 text-slate-500" />
                    <span>Deselect Filtered</span>
                  </button>
                </div>
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto rounded-lg border border-slate-800/80 bg-slate-950/40 p-2 divide-y divide-slate-850">
              {filteredAndSortedManuals.length === 0 ? (
                <div className="py-12 text-center text-slate-500">
                  <FileText className="mx-auto h-8 w-8 opacity-30 mb-2" />
                  <p className="text-xs">No manuals match your search and filter criteria.</p>
                </div>
              ) : (
                filteredAndSortedManuals.map((m) => {
                  const isChecked = selectedIds.has(m.id)
                  const compPages = m.pages_with_components_physical || m.pages_with_components
                  const jobPages = m.pages_with_jobs_physical || m.pages_with_jobs
                  const sparePages = m.pages_with_spares_physical || m.pages_with_spares

                  const pendingPages = getPendingPagesForManual(m.id, extractionType)
                  const hasPending = pendingPages.length > 0

                  return (
                    <div
                      key={m.id}
                      onClick={() => handleToggleSelect(m.id)}
                      className={`flex items-start gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${
                        isChecked
                          ? 'bg-sky-950/20 border-l-2 border-sky-500 hover:bg-sky-950/30'
                          : 'hover:bg-slate-800/20 opacity-75 hover:opacity-100'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        className="mt-1 h-3.5 w-3.5 rounded border-slate-800 bg-slate-950 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 truncate">
                            <p className={`text-xs font-semibold break-all ${isChecked ? 'text-slate-100 font-bold' : 'text-slate-400'}`}>
                              {m.original_filename}
                            </p>
                            {isChecked && (
                              <span className="shrink-0 text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-sky-900/50 text-sky-300 border border-sky-700/50">
                                Selected
                              </span>
                            )}
                          </div>
                          {m.category && (
                            <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                              {m.category}
                            </span>
                          )}
                        </div>

                        {/* Page reference ranges / Pending pages badge */}
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-[10px]">
                          {scope === 'pending' ? (
                            hasPending ? (
                              <span className="inline-flex items-center gap-1 text-amber-300 bg-amber-950/60 border border-amber-800/80 px-2 py-0.5 rounded text-[10px] font-bold">
                                <Clock className="h-3 w-3 text-amber-400 shrink-0" />
                                <span>
                                  Pending {extractionType === 'spares' ? 'Spares' : extractionType === 'jobs' ? 'Jobs' : 'Pages'}:{' '}
                                  <span className="font-extrabold text-amber-200">{pendingPages.join(', ')}</span> ({pendingPages.length} pgs)
                                </span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-emerald-400 bg-emerald-950/60 border border-emerald-800/80 px-2 py-0.5 rounded text-[10px] font-semibold">
                                <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                                <span>All {extractionType} pages extracted (0 pending)</span>
                              </span>
                            )
                          ) : (
                            <div className="flex flex-wrap gap-x-3 gap-y-1 text-slate-500 break-words">
                              {compPages && <span className="break-all">Comp Pages: <span className="text-slate-400 font-medium">{compPages}</span></span>}
                              {jobPages && <span className="break-all">Job Pages: <span className="text-slate-400 font-medium">{jobPages}</span></span>}
                              {sparePages && <span className="break-all">Spare Pages: <span className="text-slate-400 font-medium">{sparePages}</span></span>}
                              {!compPages && !jobPages && !sparePages && <span className="italic text-slate-500">No page references defined</span>}
                            </div>
                          )}

                          {extractionType === 'jobs' && !jobPages && !m.pages_with_jobs && (
                            <span className="text-amber-800 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded text-[10px] font-bold">
                              ⚠️ No Job pages defined
                            </span>
                          )}
                          {extractionType === 'spares' && !sparePages && !m.pages_with_spares && (
                            <span className="text-amber-800 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded text-[10px] font-bold">
                              ⚠️ No Spare pages defined
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Right: Sidebar Panel */}
          <div className="w-full md:w-88 bg-slate-950/40 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between shrink-0 overflow-y-auto">
            <div className="space-y-4">
              {/* Scope Selection: Pending Pages vs Complete Selected Pages */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs uppercase font-bold text-slate-300 tracking-wider">Pages to Extract</h3>
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold bg-emerald-950 border border-emerald-700/60 text-emerald-400">
                    Smart Scope
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  {/* Option 1: Pending Pages Only */}
                  <label
                    className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer transition-all ${
                      scope === 'pending'
                        ? 'border-emerald-500 bg-emerald-950/20'
                        : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900/60'
                    }`}
                  >
                    <input
                      type="radio"
                      name="extraction_scope"
                      checked={scope === 'pending'}
                      onChange={() => setScope('pending')}
                      className="mt-0.5 h-3.5 w-3.5 border-slate-700 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-slate-950"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-200">Pending Pages Only</span>
                        <span className="text-[9px] uppercase px-1.5 py-0.2 rounded font-bold bg-emerald-900/60 text-emerald-300 border border-emerald-700/50">
                          Recommended
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        Extracts only pages that do not yet have extracted items for the chosen mode.
                      </p>
                      <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-amber-400 font-semibold bg-amber-950/40 border border-amber-800/40 px-2 py-0.5 rounded">
                        <Clock className="h-3 w-3 shrink-0" />
                        <span>
                          {totalPendingPages} pending pages across {manualsWithPendingCount} manual(s)
                        </span>
                      </div>
                    </div>
                  </label>

                  {/* Option 2: Complete Selected Pages */}
                  <label
                    className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer transition-all ${
                      scope === 'full'
                        ? 'border-sky-500 bg-sky-950/20'
                        : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900/60'
                    }`}
                  >
                    <input
                      type="radio"
                      name="extraction_scope"
                      checked={scope === 'full'}
                      onChange={() => setScope('full')}
                      className="mt-0.5 h-3.5 w-3.5 border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-200">Complete Selected Pages</span>
                        <RotateCcw className="h-3 w-3 text-slate-400" />
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        Re-extracts all reference page ranges configured on selected manuals from scratch.
                      </p>
                      {totalConfiguredPages > 0 && (
                        <div className="mt-1.5 text-[10px] text-slate-400 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
                          {totalConfiguredPages} total reference pages configured
                        </div>
                      )}
                    </div>
                  </label>
                </div>
              </div>

              {/* Extraction Mode */}
              <div>
                <h3 className="text-xs uppercase font-bold text-slate-400 tracking-wider mb-2">Extraction Mode</h3>
                
                <div className="flex flex-col gap-2">
                  {/* General Mode */}
                  <label className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer transition-all ${
                    extractionType === 'general'
                      ? 'border-sky-500 bg-sky-950/15'
                      : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900/60'
                  }`}>
                    <input
                      type="radio"
                      name="extraction_type"
                      checked={extractionType === 'general'}
                      onChange={() => setExtractionType('general')}
                      className="mt-0.5 h-3.5 w-3.5 border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                    />
                    <div>
                      <span className="text-xs font-bold text-slate-200">General Extraction</span>
                      <p className="text-[10px] text-slate-400 mt-0.5">Extracts components, jobs, and spares.</p>
                    </div>
                  </label>

                  {/* Jobs Only Mode */}
                  <label className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer transition-all ${
                    extractionType === 'jobs'
                      ? 'border-sky-500 bg-sky-950/15'
                      : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900/60'
                  }`}>
                    <input
                      type="radio"
                      name="extraction_type"
                      checked={extractionType === 'jobs'}
                      onChange={() => setExtractionType('jobs')}
                      className="mt-0.5 h-3.5 w-3.5 border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                    />
                    <div>
                      <span className="text-xs font-bold text-slate-200">Jobs Only</span>
                      <p className="text-[10px] text-slate-400 mt-0.5">Extracts maintenance jobs and procedures only.</p>
                    </div>
                  </label>

                  {/* Spares Only Mode */}
                  <label className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer transition-all ${
                    extractionType === 'spares'
                      ? 'border-sky-500 bg-sky-950/15'
                      : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900/60'
                  }`}>
                    <input
                      type="radio"
                      name="extraction_type"
                      checked={extractionType === 'spares'}
                      onChange={() => setExtractionType('spares')}
                      className="mt-0.5 h-3.5 w-3.5 border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                    />
                    <div>
                      <span className="text-xs font-bold text-slate-200">Spares Only</span>
                      <p className="text-[10px] text-slate-400 mt-0.5">Extracts replacement spare parts and tables only.</p>
                    </div>
                  </label>
                </div>
              </div>
            </div>

            {/* Summary & Trigger */}
            <div className="mt-4 pt-3 border-t border-slate-850">
              <div className="flex justify-between items-center text-xs mb-3">
                <span className="text-slate-400">Selected Manuals:</span>
                <span className="font-bold text-white bg-slate-800 px-2 py-0.5 rounded-full">
                  {selectedIds.size} / {manuals.length}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <button
                  type="submit"
                  disabled={selectedIds.size === 0 || isPending || (scope === 'pending' && totalPendingPages === 0)}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-xs font-bold text-white px-4 py-2.5 transition-colors shadow-sm cursor-pointer disabled:cursor-not-allowed"
                >
                  <Zap className="h-4 w-4" />
                  <span>
                    {isPending
                      ? 'Starting...'
                      : scope === 'pending' && totalPendingPages === 0
                      ? '0 Pending Pages Found'
                      : scope === 'pending'
                      ? `Extract ${totalPendingPages} Pending Page${totalPendingPages === 1 ? '' : 's'}`
                      : 'Begin Full Extraction'}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="w-full rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 px-4 py-2 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

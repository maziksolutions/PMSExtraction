import React, { useState, useMemo, useEffect } from 'react'
import { X, Search, Zap, Layers, FileText } from 'lucide-react'

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

interface ExtractionConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  manuals: ManualItem[]
  initialSelectedIds: Set<string> | string[]
  initialExtractionType: 'general' | 'jobs' | 'spares'
  onConfirm: (finalSelectedIds: string[], extractionType: 'general' | 'jobs' | 'spares') => void
  isExtractAll?: boolean
  isPending?: boolean
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
}: ExtractionConfirmationModalProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [extractionType, setExtractionType] = useState<'general' | 'jobs' | 'spares'>('general')
  const [searchQuery, setSearchQuery] = useState('')

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
      setSearchQuery('')
    }
  }, [isOpen, initialSelectedIds, initialExtractionType, isExtractAll, manuals])

  const filteredManuals = useMemo(() => {
    if (!searchQuery.trim()) return manuals
    const query = searchQuery.toLowerCase()
    return manuals.filter((m) =>
      m.original_filename.toLowerCase().includes(query) ||
      (m.category || '').toLowerCase().includes(query)
    )
  }, [manuals, searchQuery])

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
      filteredManuals.forEach((m) => next.add(m.id))
      return next
    })
  }

  const handleDeselectAllFiltered = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      filteredManuals.forEach((m) => next.delete(m.id))
      return next
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedIds.size === 0) return
    onConfirm(Array.from(selectedIds), extractionType)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-900 shadow-2xl p-6 text-slate-100 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <Layers className="h-5 w-5 text-emerald-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-100">Confirm Extraction Batch</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Review and refine the selection of manuals and the target extraction mode before beginning.
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
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex flex-col sm:flex-row gap-3 mb-3 items-center justify-between">
              {/* Search */}
              <div className="relative w-full sm:max-w-xs">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Search manuals..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950/60 pl-9 pr-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none transition-colors"
                />
              </div>

              {/* Select Actions */}
              <div className="flex gap-2 w-full sm:w-auto shrink-0 justify-end">
                <button
                  type="button"
                  onClick={handleSelectAllFiltered}
                  className="rounded bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-2 py-1 text-slate-300 transition-colors"
                >
                  Select All
                </button>
                <button
                  type="button"
                  onClick={handleDeselectAllFiltered}
                  className="rounded bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-2 py-1 text-slate-300 transition-colors"
                >
                  Deselect All
                </button>
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto rounded-lg border border-slate-800/80 bg-slate-950/40 p-2 divide-y divide-slate-850">
              {filteredManuals.length === 0 ? (
                <div className="py-12 text-center text-slate-500">
                  <FileText className="mx-auto h-8 w-8 opacity-30 mb-2" />
                  <p className="text-xs">No manuals match your search.</p>
                </div>
              ) : (
                filteredManuals.map((m) => {
                  const isChecked = selectedIds.has(m.id)
                  // Page references preview text
                  const compPages = m.pages_with_components_physical ?? m.pages_with_components
                  const jobPages = m.pages_with_jobs_physical ?? m.pages_with_jobs
                  const sparePages = m.pages_with_spares_physical ?? m.pages_with_spares

                  return (
                    <div
                      key={m.id}
                      onClick={() => handleToggleSelect(m.id)}
                      className={`flex items-start gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${
                        isChecked ? 'bg-slate-800/20 hover:bg-slate-800/30' : 'hover:bg-slate-800/10'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}} // Handle on click div
                        className="mt-1 h-3.5 w-3.5 rounded border-slate-800 bg-slate-950 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className={`text-xs font-semibold break-all ${isChecked ? 'text-slate-200' : 'text-slate-400'}`}>
                            {m.original_filename}
                          </p>
                          {m.category && (
                            <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                              {m.category}
                            </span>
                          )}
                        </div>
                        
                        {/* Page reference ranges overview */}
                        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[10px] text-slate-500">
                          {compPages && <span>Comp Pages: <span className="text-slate-400">{compPages}</span></span>}
                          {jobPages && <span>Job Pages: <span className="text-slate-400">{jobPages}</span></span>}
                          {sparePages && <span>Spare Pages: <span className="text-slate-400">{sparePages}</span></span>}
                          {!compPages && !jobPages && !sparePages && <span className="italic text-slate-600">No page references defined</span>}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Right: Sidebar Panel */}
          <div className="w-full md:w-72 bg-slate-950/30 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between shrink-0">
            <div>
              <h3 className="text-xs uppercase font-bold text-slate-400 tracking-wider mb-3">Extraction Mode</h3>
              
              {/* Option cards */}
              <div className="flex flex-col gap-2.5">
                {/* General Mode */}
                <label className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-all ${
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
                    <p className="text-[10px] text-slate-400 mt-0.5">Extracts all categories (components, jobs, and spares).</p>
                  </div>
                </label>

                {/* Jobs Only Mode */}
                <label className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-all ${
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
                <label className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-all ${
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

            {/* Summary & Trigger */}
            <div className="mt-6 pt-4 border-t border-slate-850">
              <div className="flex justify-between items-center text-xs mb-4">
                <span className="text-slate-400">Selected Manuals:</span>
                <span className="font-bold text-white bg-slate-800 px-2 py-0.5 rounded-full">
                  {selectedIds.size}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <button
                  type="submit"
                  disabled={selectedIds.size === 0 || isPending}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-xs font-semibold text-white px-4 py-2 transition-colors"
                >
                  <Zap className="h-4 w-4" />
                  <span>{isPending ? 'Starting...' : 'Begin Extraction'}</span>
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

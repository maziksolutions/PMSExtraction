import React, { useState, useMemo, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  X,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Package,
  Wrench,
  BookOpen,
  Play,
  RotateCcw,
  Plus,
  RefreshCw,
  ExternalLink,
  Layers,
  Sparkles,
  Search,
  Filter,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'

export interface NoExtractedManual {
  manual_id: string
  original_filename: string
  category?: string | null
  missing_components_pages: number[]
  missing_jobs_pages: number[]
  missing_spares_pages: number[]
  missing_components_count: number
  missing_jobs_count: number
  missing_spares_count: number
  total_missing_pages_count: number
}

export interface ExtractedManual {
  manual_id: string
  original_filename: string
  category?: string | null
  extracted_components_pages: number[]
  extracted_jobs_pages: number[]
  extracted_spares_pages: number[]
  extracted_components_count: number
  extracted_jobs_count: number
  extracted_spares_count: number
  total_extracted_pages_count: number
}

export interface QueuedPageItem {
  id: string // `${manualId}-${entityType}-${page}`
  manualId: string
  filename: string
  entityType: 'component' | 'job' | 'spare'
  page: number
}

interface NoExtractedRecordsModalProps {
  isOpen: boolean
  onClose: () => void
  data: {
    manuals: NoExtractedManual[]
    total_no_extracted_pages: number
    extracted_manuals?: ExtractedManual[]
    total_extracted_pages?: number
    all_manuals_summary?: Record<string, any>
  } | null
  vesselId?: string
  isExtracting?: boolean
  onExtractQueued?: (queuedItems: QueuedPageItem[]) => Promise<void> | void
  queuedPages?: QueuedPageItem[]
  setQueuedPages?: React.Dispatch<React.SetStateAction<QueuedPageItem[]>>
  initialTab?: 'extracted' | 'pending'
}

export function NoExtractedRecordsModal({
  isOpen,
  onClose,
  data,
  vesselId: propVesselId,
  isExtracting = false,
  onExtractQueued,
  queuedPages: propQueuedPages,
  setQueuedPages: propSetQueuedPages,
  initialTab = 'extracted',
}: NoExtractedRecordsModalProps) {
  if (!isOpen) return null

  const navigate = useNavigate()
  const { vesselId: routeVesselId } = useParams<{ vesselId?: string }>()
  const vesselId = propVesselId || routeVesselId

  // Tab state: default to 'extracted' per user requirement
  const [activeTab, setActiveTab] = useState<'extracted' | 'pending'>(initialTab)

  // Reset tab when modal opens if initialTab changes
  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab)
    }
  }, [isOpen, initialTab])

  // Support controlled or local queued state
  const [localQueued, setLocalQueued] = useState<QueuedPageItem[]>([])
  const queuedItems = propQueuedPages !== undefined ? propQueuedPages : localQueued
  const setQueuedItems = propSetQueuedPages !== undefined ? propSetQueuedPages : setLocalQueued

  const [loadingPdfKey, setLoadingPdfKey] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [searchFilter, setSearchFilter] = useState('')

  const pendingManuals = data?.manuals || []
  const extractedManuals = data?.extracted_manuals || []
  const allManualsSummary = data?.all_manuals_summary || {}
  const totalExtractedPages = data?.total_extracted_pages ?? 0
  const totalPendingPages = data?.total_no_extracted_pages ?? 0

  // Filtered lists
  const filteredExtractedManuals = useMemo(() => {
    if (!searchFilter.trim()) return extractedManuals
    const q = searchFilter.toLowerCase()
    return extractedManuals.filter(
      (m) =>
        m.original_filename.toLowerCase().includes(q) ||
        (m.category && m.category.toLowerCase().includes(q))
    )
  }, [extractedManuals, searchFilter])

  const filteredPendingManuals = useMemo(() => {
    if (!searchFilter.trim()) return pendingManuals
    const q = searchFilter.toLowerCase()
    return pendingManuals.filter(
      (m) =>
        m.original_filename.toLowerCase().includes(q) ||
        (m.category && m.category.toLowerCase().includes(q))
    )
  }, [pendingManuals, searchFilter])

  // Check if an item is already queued
  const isQueued = (manualId: string, entityType: 'component' | 'job' | 'spare', page: number) => {
    const id = `${manualId}-${entityType}-${page}`
    return queuedItems.some((item) => item.id === id)
  }

  // Add item to queue
  const addQueueItem = (item: { manualId: string; filename: string; entityType: 'component' | 'job' | 'spare'; page: number }) => {
    if (isExtracting) return
    const id = `${item.manualId}-${item.entityType}-${pageIdSafe(item.page)}`
    setQueuedItems((prev) => {
      if (prev.some((p) => p.id === id)) return prev
      return [...prev, { ...item, id }]
    })
  }

  const pageIdSafe = (p: number) => `${p}`

  // Remove item from queue
  const removeQueueItem = (id: string) => {
    if (isExtracting) return
    setQueuedItems((prev) => prev.filter((p) => p.id !== id))
  }

  // Queue all missing pages across all manuals
  const queueAllMissingPages = () => {
    if (isExtracting) return
    const allItems: QueuedPageItem[] = []
    pendingManuals.forEach((m) => {
      m.missing_components_pages.forEach((p) => {
        allItems.push({
          id: `${m.manual_id}-component-${p}`,
          manualId: m.manual_id,
          filename: m.original_filename,
          entityType: 'component',
          page: p,
        })
      })
      m.missing_jobs_pages.forEach((p) => {
        allItems.push({
          id: `${m.manual_id}-job-${p}`,
          manualId: m.manual_id,
          filename: m.original_filename,
          entityType: 'job',
          page: p,
        })
      })
      m.missing_spares_pages.forEach((p) => {
        allItems.push({
          id: `${m.manual_id}-spare-${p}`,
          manualId: m.manual_id,
          filename: m.original_filename,
          entityType: 'spare',
          page: p,
        })
      })
    })

    setQueuedItems((prev) => {
      const existingIds = new Set(prev.map((i) => i.id))
      const toAdd = allItems.filter((i) => !existingIds.has(i.id))
      return [...prev, ...toAdd]
    })
  }

  // Clear selections
  const clearQueue = () => {
    if (isExtracting) return
    setQueuedItems([])
  }

  // Open manual PDF in a new tab at the specific page
  const openPdfAtPage = async (manualId: string, pageNumber: number) => {
    const key = `${manualId}-${pageNumber}`
    if (loadingPdfKey) return
    setLoadingPdfKey(key)

    const token = useAuthStore.getState().accessToken
    const base = (apiClient.defaults.baseURL ?? '/api/v1').replace(/\/$/, '')
    const url = `${base}/vessels/${vesselId}/manuals/${manualId}/view`

    try {
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(120_000),
      })
      if (!resp.ok) {
        const errData = await resp.json().catch(() => null)
        alert(`Could not open manual PDF:\n${errData?.detail ?? `Server error ${resp.status}`}`)
        return
      }

      const ct = resp.headers.get('content-type') ?? ''
      if (ct.includes('application/json')) {
        const json = (await resp.json()) as { url: string }
        const targetUrl = json.url.includes('#') ? json.url : `${json.url}#page=${pageNumber}`
        const win = window.open(targetUrl, '_blank')
        if (!win) alert('Please allow popups to open the manual PDF.')
      } else {
        const blob = await resp.blob()
        const blobUrl = URL.createObjectURL(blob)
        const win = window.open(`${blobUrl}#page=${pageNumber}`, '_blank')
        setTimeout(() => URL.revokeObjectURL(blobUrl), 120_000)
        if (!win) alert('Please allow popups to open the manual PDF.')
      }
    } catch (err: any) {
      alert(`Could not open file: ${err?.message ?? 'Network error'}`)
    } finally {
      setLoadingPdfKey(null)
    }
  }

  // Drag handlers for queue
  const handleDragStart = (
    e: React.DragEvent,
    item: { manualId: string; filename: string; entityType: 'component' | 'job' | 'spare'; page: number }
  ) => {
    if (isExtracting) return
    e.dataTransfer.setData('application/json', JSON.stringify(item))
    e.dataTransfer.effectAllowed = 'copy'
  }

  const handleDragOver = (e: React.DragEvent) => {
    if (isExtracting) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setIsDragOver(true)
  }

  const handleDragLeave = () => {
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    if (isExtracting) return
    e.preventDefault()
    setIsDragOver(false)
    try {
      const raw = e.dataTransfer.getData('application/json')
      if (raw) {
        const item = JSON.parse(raw)
        if (item && item.manualId && item.entityType && item.page) {
          addQueueItem(item)
        }
      }
    } catch {
      // Ignored non-json drops
    }
  }

  // Group queued items by manual for display
  const queuedByManual = queuedItems.reduce<Record<string, { filename: string; items: QueuedPageItem[] }>>((acc, item) => {
    if (!acc[item.manualId]) {
      acc[item.manualId] = { filename: item.filename, items: [] }
    }
    acc[item.manualId].items.push(item)
    return acc
  }, {})

  const handleTriggerExtract = () => {
    if (!onExtractQueued || queuedItems.length === 0 || isExtracting) return
    onExtractQueued(queuedItems)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3 sm:p-5">
      <div className="relative w-full max-w-6xl rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl p-5 sm:p-6 text-slate-100 max-h-[92vh] flex flex-col overflow-hidden">
        {/* Header Bar */}
        <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-3 shrink-0">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-xl border ${
              activeTab === 'extracted'
                ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                : 'bg-amber-500/15 border-amber-500/30 text-amber-400'
            }`}>
              {activeTab === 'extracted' ? <BookOpen className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-lg font-bold text-slate-100">
                  {activeTab === 'extracted' ? 'Manuals Extracted Pages' : 'Pending Unextracted Pages'}
                </h2>
                {/* Mode Pill Badges */}
                <div className="flex items-center gap-1.5">
                  <span
                    style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                    className="border text-[11px] font-extrabold px-2 py-0.5 rounded-full shadow-xs tracking-wide"
                  >
                    {totalExtractedPages} Extracted Pages
                  </span>
                  {totalPendingPages > 0 && (
                    <span
                      style={{ backgroundColor: '#fef3c7', color: '#78350f', borderColor: '#fde68a' }}
                      className="border text-[11px] font-extrabold px-2 py-0.5 rounded-full shadow-xs tracking-wide"
                    >
                      {totalPendingPages} Pending Pages
                    </span>
                  )}
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {activeTab === 'extracted'
                  ? 'Showing manuals with successfully extracted records. Click any page number to open the PDF directly to that page.'
                  : 'Target pages with zero extracted records. Click page to view PDF, or drag/queue to re-extract.'}
              </p>
            </div>
          </div>

          {/* Top Actions: Tabs & Queue Trigger */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* View Switcher Tabs */}
            <div className="flex items-center p-0.5 rounded-lg border border-slate-700 bg-slate-950/60 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setActiveTab('extracted')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
                  activeTab === 'extracted'
                    ? 'bg-emerald-600 text-white font-bold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Extracted Pages ({extractedManuals.length})</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('pending')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
                  activeTab === 'pending'
                    ? 'bg-amber-600 text-white font-bold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>Pending ({pendingManuals.length})</span>
              </button>
            </div>

            {/* If on pending tab and items queued */}
            {activeTab === 'pending' && queuedItems.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={clearQueue}
                  disabled={isExtracting}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-xs font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
                  title="Clear all queued selections"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-slate-400" />
                  Clear
                </button>

                <button
                  type="button"
                  onClick={handleTriggerExtract}
                  disabled={isExtracting}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow-md transition-all disabled:opacity-60"
                  title="Run extraction on queued pages"
                >
                  {isExtracting ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin text-white" />
                      Extracting...
                    </>
                  ) : (
                    <>
                      <Play className="h-3.5 w-3.5 fill-current" />
                      Extract ({queuedItems.length})
                    </>
                  )}
                </button>
              </>
            )}

            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors ml-1"
              title="Close modal"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Running Banner Notice */}
        {isExtracting && (
          <div className="mt-3 px-4 py-2 rounded-xl bg-sky-950/40 border border-sky-800/50 flex items-center justify-between text-xs text-sky-200 shrink-0">
            <div className="flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-sky-400 shrink-0" />
              <span>
                <strong>Extraction is currently running.</strong> Selections are preserved. You can close this modal to monitor live progress on the Manuals page.
              </span>
            </div>
          </div>
        )}

        {/* Search Bar */}
        <div className="mt-3 mb-2 flex items-center justify-between gap-3 shrink-0">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder={
                activeTab === 'extracted'
                  ? 'Search extracted manuals by filename or category...'
                  : 'Search pending manuals...'
              }
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950/70 pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
          {activeTab === 'pending' && pendingManuals.length > 0 && (
            <button
              type="button"
              onClick={queueAllMissingPages}
              disabled={isExtracting}
              className="text-xs text-sky-400 hover:text-sky-300 font-semibold inline-flex items-center gap-1 hover:underline disabled:opacity-40 shrink-0"
            >
              <Plus className="h-3.5 w-3.5" />
              Queue All Missing Pages ({totalPendingPages})
            </button>
          )}
        </div>

        {/* ─── TAB 1: EXTRACTED PAGES VIEW ──────────────────────────────────── */}
        {activeTab === 'extracted' && (
          <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-950/60 mt-1 min-h-[380px] flex flex-col">
            {filteredExtractedManuals.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-12 text-center text-slate-400 p-6">
                <BookOpen className="h-12 w-12 text-slate-600 mb-3" />
                <p className="text-sm font-semibold text-slate-200">
                  {searchFilter ? 'No extracted manuals match your search filter.' : 'No extracted manuals records found yet.'}
                </p>
                <p className="text-xs text-slate-500 mt-1 max-w-md">
                  Run extraction on your instruction manuals to populate components, jobs, and spares data.
                </p>
                {pendingManuals.length > 0 && (
                  <button
                    onClick={() => setActiveTab('pending')}
                    className="mt-4 px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-xs font-bold text-white transition-colors"
                  >
                    View {pendingManuals.length} Manuals with Pending Pages
                  </button>
                )}
              </div>
            ) : (
              <table className="w-full text-sm text-left border-collapse">
                <thead className="sticky top-0 z-10 bg-slate-900 border-b border-slate-800 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  <tr>
                    <th className="py-2.5 px-3 w-[34%]">Manual File</th>
                    <th className="py-2.5 px-2 w-[20%]">Extracted Components</th>
                    <th className="py-2.5 px-2 w-[20%]">Extracted Jobs</th>
                    <th className="py-2.5 px-2 w-[20%]">Extracted Spares</th>
                    <th className="py-2.5 px-2 text-center w-[6%]">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-xs">
                  {filteredExtractedManuals.map((manual) => (
                    <tr key={manual.manual_id} className="hover:bg-slate-900/40 transition-colors">
                      {/* Filename & Category */}
                      <td className="py-3 px-3 font-semibold text-slate-300 break-words">
                        <div className="flex flex-col gap-1">
                          <span className="font-semibold text-slate-200" title={manual.original_filename}>
                            {manual.original_filename}
                          </span>
                          {manual.category && (
                            <span className="inline-block self-start text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60">
                              {manual.category}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Component Pages */}
                      <td className="py-3 px-2">
                        {manual.extracted_components_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.extracted_components_pages.map((p) => {
                              const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                              return (
                                <button
                                  key={`comp-${p}`}
                                  type="button"
                                  onClick={() => openPdfAtPage(manual.manual_id, p)}
                                  style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border hover:shadow-sm transition-all focus:outline-none"
                                  title={`Click to view page ${p} in PDF (yielded Components)`}
                                >
                                  {isLoading ? (
                                    <RefreshCw className="h-2.5 w-2.5 animate-spin text-emerald-700" />
                                  ) : (
                                    <CheckCircle2 className="h-2.5 w-2.5 text-emerald-600 shrink-0" />
                                  )}
                                  <span>p. {p}</span>
                                </button>
                              )
                            })}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-xs italic">—</span>
                        )}
                      </td>

                      {/* Job Pages */}
                      <td className="py-3 px-2">
                        {manual.extracted_jobs_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.extracted_jobs_pages.map((p) => {
                              const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                              return (
                                <button
                                  key={`job-${p}`}
                                  type="button"
                                  onClick={() => openPdfAtPage(manual.manual_id, p)}
                                  style={{ backgroundColor: '#fef3c7', color: '#78350f', borderColor: '#fde68a' }}
                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border hover:shadow-sm transition-all focus:outline-none"
                                  title={`Click to view page ${p} in PDF (yielded Jobs)`}
                                >
                                  {isLoading ? (
                                    <RefreshCw className="h-2.5 w-2.5 animate-spin text-amber-700" />
                                  ) : (
                                    <CheckCircle2 className="h-2.5 w-2.5 text-amber-600 shrink-0" />
                                  )}
                                  <span>p. {p}</span>
                                </button>
                              )
                            })}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-xs italic">—</span>
                        )}
                      </td>

                      {/* Spare Pages */}
                      <td className="py-3 px-2">
                        {manual.extracted_spares_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.extracted_spares_pages.map((p) => {
                              const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                              return (
                                <button
                                  key={`spare-${p}`}
                                  type="button"
                                  onClick={() => openPdfAtPage(manual.manual_id, p)}
                                  style={{ backgroundColor: '#ffedd5', color: '#9a3412', borderColor: '#fed7aa' }}
                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border hover:shadow-sm transition-all focus:outline-none"
                                  title={`Click to view page ${p} in PDF (yielded Spares)`}
                                >
                                  {isLoading ? (
                                    <RefreshCw className="h-2.5 w-2.5 animate-spin text-orange-700" />
                                  ) : (
                                    <CheckCircle2 className="h-2.5 w-2.5 text-orange-600 shrink-0" />
                                  )}
                                  <span>p. {p}</span>
                                </button>
                              )
                            })}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-xs italic">—</span>
                        )}
                      </td>

                      {/* Total */}
                      <td className="py-3 px-2 text-center">
                        <span
                          style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                          className="border text-[11px] font-extrabold px-2 py-0.5 rounded-full inline-block"
                        >
                          {manual.total_extracted_pages_count}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* ─── TAB 2: PENDING / UNEXTRACTED PAGES VIEW ──────────────────────── */}
        {activeTab === 'pending' && (
          <div className="flex-1 overflow-hidden mt-1 flex flex-col lg:flex-row gap-4 min-h-[380px]">
            {pendingManuals.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-12 text-center text-slate-400">
                <CheckCircle2 className="h-14 w-14 text-emerald-400 mb-3" />
                <p className="text-base font-semibold text-slate-100">All specified pages have at least one extracted record!</p>
                <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                  No targeted pages are pending extraction. You can review all extracted data in their respective sections:
                </p>
                {vesselId && (
                  <div className="flex items-center justify-center gap-3 mt-6">
                    <button
                      onClick={() => {
                        onClose()
                        navigate(`/vessels/${vesselId}/components`)
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-750 text-xs font-medium text-emerald-400 border border-slate-700 transition-colors shadow-sm"
                    >
                      <Wrench className="h-3.5 w-3.5" />
                      Components Review
                    </button>
                    <button
                      onClick={() => {
                        onClose()
                        navigate(`/vessels/${vesselId}/jobs`)
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-750 text-xs font-medium text-sky-400 border border-slate-700 transition-colors shadow-sm"
                    >
                      <BookOpen className="h-3.5 w-3.5" />
                      Jobs Review
                    </button>
                    <button
                      onClick={() => {
                        onClose()
                        navigate(`/vessels/${vesselId}/spares`)
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-750 text-xs font-medium text-amber-400 border border-slate-700 transition-colors shadow-sm"
                    >
                      <Package className="h-3.5 w-3.5" />
                      Spares Review
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
                {/* Left Side: Manuals Table */}
                <div className="flex-1 min-w-0 overflow-auto rounded-xl border border-slate-800 bg-slate-950/60 flex flex-col">
                  <div className="p-2.5 border-b border-slate-800/80 bg-slate-900/60 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Layers className="h-4 w-4 text-slate-400" />
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                        Pending Pages by Manual ({filteredPendingManuals.length})
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      Drag badge or click <Plus className="inline h-3 w-3 text-sky-400" /> to queue for extraction
                    </span>
                  </div>

                  <div className="flex-1 overflow-auto">
                    <table className="w-full text-sm text-left border-collapse">
                      <thead className="sticky top-0 z-10 bg-slate-900 border-b border-slate-800 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        <tr>
                          <th className="py-2.5 px-3 w-[34%]">Manual File</th>
                          <th className="py-2.5 px-2 w-[20%]">Components Pending</th>
                          <th className="py-2.5 px-2 w-[20%]">Jobs Pending</th>
                          <th className="py-2.5 px-2 w-[20%]">Spares Pending</th>
                          <th className="py-2.5 px-2 text-center w-[6%]">Pending</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-xs">
                        {filteredPendingManuals.map((manual) => {
                          const summary = allManualsSummary[manual.manual_id]
                          const extComp = summary?.extracted_components_pages || []
                          const extJob = summary?.extracted_jobs_pages || []
                          const extSpare = summary?.extracted_spares_pages || []

                          return (
                            <tr key={manual.manual_id} className="hover:bg-slate-900/40 transition-colors">
                              {/* Filename & Info */}
                              <td className="py-3 px-3 font-semibold text-slate-300 break-words">
                                <div className="flex flex-col gap-1">
                                  <span className="font-semibold text-slate-200" title={manual.original_filename}>
                                    {manual.original_filename}
                                  </span>
                                  {manual.category && (
                                    <span className="inline-block self-start text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60">
                                      {manual.category}
                                    </span>
                                  )}
                                  {/* If manual has completed pages, show completed summary badge */}
                                  {(extComp.length > 0 || extJob.length > 0 || extSpare.length > 0) && (
                                    <span
                                      style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                                      className="inline-flex items-center gap-1 self-start text-[10px] font-bold px-1.5 py-0.5 rounded border mt-0.5"
                                    >
                                      <CheckCircle2 className="h-2.5 w-2.5 text-emerald-600" />
                                      {extComp.length + extJob.length + extSpare.length} Page(s) Extracted
                                    </span>
                                  )}
                                </div>
                              </td>

                              {/* Components Column: Shows Pending + Completed Highlights */}
                              <td className="py-3 px-2">
                                <div className="flex flex-col gap-1.5">
                                  {/* Pending / Missing pages */}
                                  {manual.missing_components_pages.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {manual.missing_components_pages.map((p) => {
                                        const queued = isQueued(manual.manual_id, 'component', p)
                                        const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                        return (
                                          <div
                                            key={`comp-miss-${p}`}
                                            draggable={!isExtracting}
                                            onDragStart={(e) =>
                                              handleDragStart(e, {
                                                manualId: manual.manual_id,
                                                filename: manual.original_filename,
                                                entityType: 'component',
                                                page: p,
                                              })
                                            }
                                            style={
                                              queued
                                                ? { backgroundColor: '#e0f2fe', color: '#0369a1', borderColor: '#7dd3fc' }
                                                : { backgroundColor: '#ffe4e6', color: '#9f1239', borderColor: '#fecdd3' }
                                            }
                                            className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none shadow-xs ${
                                              isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'
                                            }`}
                                          >
                                            <button
                                              type="button"
                                              onClick={() => openPdfAtPage(manual.manual_id, p)}
                                              className="hover:underline flex items-center gap-1 focus:outline-none"
                                              title={`Click to view page ${p} in PDF | Drag to 'To Extract' queue`}
                                            >
                                              {isLoading ? (
                                                <RefreshCw className="h-2.5 w-2.5 animate-spin" />
                                              ) : (
                                                <span>p. {p}</span>
                                              )}
                                            </button>
                                            {!queued && !isExtracting && (
                                              <button
                                                type="button"
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  addQueueItem({
                                                    manualId: manual.manual_id,
                                                    filename: manual.original_filename,
                                                    entityType: 'component',
                                                    page: p,
                                                  })
                                                }}
                                                className="opacity-70 group-hover:opacity-100 hover:scale-110 transition-transform ml-0.5"
                                                title="Add to queue"
                                              >
                                                <Plus className="h-3 w-3" />
                                              </button>
                                            )}
                                            {queued && (
                                              <span title="Queued" className="inline-flex items-center"><CheckCircle2 className="h-2.5 w-2.5 text-sky-600 shrink-0" /></span>
                                            )}
                                          </div>
                                        )
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-slate-500 text-xs italic">No pending</span>
                                  )}

                                  {/* Completed / Extracted pages highlight */}
                                  {extComp.length > 0 && (
                                    <div className="flex flex-wrap gap-1 pt-1 border-t border-slate-800/40">
                                      {extComp.map((p: number) => (
                                        <button
                                          key={`comp-done-${p}`}
                                          type="button"
                                          onClick={() => openPdfAtPage(manual.manual_id, p)}
                                          style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                                          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-bold border hover:shadow-xs transition-all"
                                          title={`Extraction complete on page ${p} — click to view in PDF`}
                                        >
                                          <CheckCircle2 className="h-2.5 w-2.5 text-emerald-600" />
                                          <span>p. {p}</span>
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </td>

                              {/* Jobs Column: Shows Pending + Completed Highlights */}
                              <td className="py-3 px-2">
                                <div className="flex flex-col gap-1.5">
                                  {/* Pending / Missing pages */}
                                  {manual.missing_jobs_pages.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {manual.missing_jobs_pages.map((p) => {
                                        const queued = isQueued(manual.manual_id, 'job', p)
                                        const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                        return (
                                          <div
                                            key={`job-miss-${p}`}
                                            draggable={!isExtracting}
                                            onDragStart={(e) =>
                                              handleDragStart(e, {
                                                manualId: manual.manual_id,
                                                filename: manual.original_filename,
                                                entityType: 'job',
                                                page: p,
                                              })
                                            }
                                            style={
                                              queued
                                                ? { backgroundColor: '#e0f2fe', color: '#0369a1', borderColor: '#7dd3fc' }
                                                : { backgroundColor: '#fef3c7', color: '#78350f', borderColor: '#fde68a' }
                                            }
                                            className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none shadow-xs ${
                                              isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'
                                            }`}
                                          >
                                            <button
                                              type="button"
                                              onClick={() => openPdfAtPage(manual.manual_id, p)}
                                              className="hover:underline flex items-center gap-1 focus:outline-none"
                                              title={`Click to view page ${p} in PDF | Drag to 'To Extract' queue`}
                                            >
                                              {isLoading ? (
                                                <RefreshCw className="h-2.5 w-2.5 animate-spin" />
                                              ) : (
                                                <span>p. {p}</span>
                                              )}
                                            </button>
                                            {!queued && !isExtracting && (
                                              <button
                                                type="button"
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  addQueueItem({
                                                    manualId: manual.manual_id,
                                                    filename: manual.original_filename,
                                                    entityType: 'job',
                                                    page: p,
                                                  })
                                                }}
                                                className="opacity-70 group-hover:opacity-100 hover:scale-110 transition-transform ml-0.5"
                                                title="Add to queue"
                                              >
                                                <Plus className="h-3 w-3" />
                                              </button>
                                            )}
                                            {queued && (
                                              <span title="Queued" className="inline-flex items-center"><CheckCircle2 className="h-2.5 w-2.5 text-sky-600 shrink-0" /></span>
                                            )}
                                          </div>
                                        )
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-slate-500 text-xs italic">No pending</span>
                                  )}

                                  {/* Completed / Extracted pages highlight */}
                                  {extJob.length > 0 && (
                                    <div className="flex flex-wrap gap-1 pt-1 border-t border-slate-800/40">
                                      {extJob.map((p: number) => (
                                        <button
                                          key={`job-done-${p}`}
                                          type="button"
                                          onClick={() => openPdfAtPage(manual.manual_id, p)}
                                          style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                                          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-bold border hover:shadow-xs transition-all"
                                          title={`Extraction complete on page ${p} — click to view in PDF`}
                                        >
                                          <CheckCircle2 className="h-2.5 w-2.5 text-emerald-600" />
                                          <span>p. {p}</span>
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </td>

                              {/* Spares Column: Shows Pending + Completed Highlights */}
                              <td className="py-3 px-2">
                                <div className="flex flex-col gap-1.5">
                                  {/* Pending / Missing pages */}
                                  {manual.missing_spares_pages.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {manual.missing_spares_pages.map((p) => {
                                        const queued = isQueued(manual.manual_id, 'spare', p)
                                        const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                        return (
                                          <div
                                            key={`spare-miss-${p}`}
                                            draggable={!isExtracting}
                                            onDragStart={(e) =>
                                              handleDragStart(e, {
                                                manualId: manual.manual_id,
                                                filename: manual.original_filename,
                                                entityType: 'spare',
                                                page: p,
                                              })
                                            }
                                            style={
                                              queued
                                                ? { backgroundColor: '#e0f2fe', color: '#0369a1', borderColor: '#7dd3fc' }
                                                : { backgroundColor: '#ffedd5', color: '#9a3412', borderColor: '#fed7aa' }
                                            }
                                            className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none shadow-xs ${
                                              isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'
                                            }`}
                                          >
                                            <button
                                              type="button"
                                              onClick={() => openPdfAtPage(manual.manual_id, p)}
                                              className="hover:underline flex items-center gap-1 focus:outline-none"
                                              title={`Click to view page ${p} in PDF | Drag to 'To Extract' queue`}
                                            >
                                              {isLoading ? (
                                                <RefreshCw className="h-2.5 w-2.5 animate-spin" />
                                              ) : (
                                                <span>p. {p}</span>
                                              )}
                                            </button>
                                            {!queued && !isExtracting && (
                                              <button
                                                type="button"
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  addQueueItem({
                                                    manualId: manual.manual_id,
                                                    filename: manual.original_filename,
                                                    entityType: 'spare',
                                                    page: p,
                                                  })
                                                }}
                                                className="opacity-70 group-hover:opacity-100 hover:scale-110 transition-transform ml-0.5"
                                                title="Add to queue"
                                              >
                                                <Plus className="h-3 w-3" />
                                              </button>
                                            )}
                                            {queued && (
                                              <span title="Queued" className="inline-flex items-center"><CheckCircle2 className="h-2.5 w-2.5 text-sky-600 shrink-0" /></span>
                                            )}
                                          </div>
                                        )
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-slate-500 text-xs italic">No pending</span>
                                  )}

                                  {/* Completed / Extracted pages highlight */}
                                  {extSpare.length > 0 && (
                                    <div className="flex flex-wrap gap-1 pt-1 border-t border-slate-800/40">
                                      {extSpare.map((p: number) => (
                                        <button
                                          key={`spare-done-${p}`}
                                          type="button"
                                          onClick={() => openPdfAtPage(manual.manual_id, p)}
                                          style={{ backgroundColor: '#d1fae5', color: '#065f46', borderColor: '#a7f3d0' }}
                                          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-bold border hover:shadow-xs transition-all"
                                          title={`Extraction complete on page ${p} — click to view in PDF`}
                                        >
                                          <CheckCircle2 className="h-2.5 w-2.5 text-emerald-600" />
                                          <span>p. {p}</span>
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </td>

                              {/* Total Pending */}
                              <td className="py-3 px-2 text-center">
                                <span
                                  style={{ backgroundColor: '#fef3c7', color: '#78350f', borderColor: '#fde68a' }}
                                  className="border text-[11px] font-extrabold px-2 py-0.5 rounded-full inline-block"
                                >
                                  {manual.total_missing_pages_count}
                                </span>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Right Side: "To Extract" Dropzone Queue */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`w-full lg:w-[360px] shrink-0 rounded-xl border flex flex-col transition-all overflow-hidden ${
                    isDragOver
                      ? 'border-sky-400 bg-sky-950/50 shadow-lg shadow-sky-950/50 ring-2 ring-sky-500/40'
                      : 'border-slate-800 bg-slate-950/80'
                  }`}
                >
                  {/* Queue Header */}
                  <div className="p-3 border-b border-slate-800 bg-slate-900/80 flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-sky-400" />
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
                        To Extract Queue
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">
                        {queuedItems.length}
                      </span>
                    </div>

                    {queuedItems.length > 0 && !isExtracting && (
                      <button
                        type="button"
                        onClick={clearQueue}
                        className="text-[11px] text-slate-400 hover:text-rose-400 transition-colors"
                        title="Clear queue"
                      >
                        Clear
                      </button>
                    )}
                  </div>

                  {/* Queue Body */}
                  <div className="flex-1 overflow-auto p-3">
                    {queuedItems.length === 0 ? (
                      <div
                        className={`h-full min-h-[220px] rounded-xl border-2 border-dashed flex flex-col items-center justify-center p-6 text-center transition-colors ${
                          isDragOver
                            ? 'border-sky-400 bg-sky-900/20 text-sky-300'
                            : 'border-slate-800 bg-slate-900/30 text-slate-500'
                        }`}
                      >
                        <Layers className={`h-8 w-8 mb-2 ${isDragOver ? 'text-sky-400 animate-bounce' : 'text-slate-600'}`} />
                        <p className="text-xs font-semibold text-slate-300">Drag & Drop Page Tiles Here</p>
                        <p className="text-[11px] text-slate-500 mt-1 max-w-[200px]">
                          Or click the <Plus className="inline h-3 w-3 text-sky-400" /> on any page badge to queue it for re-extraction.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {Object.entries(queuedByManual).map(([mid, group]) => (
                          <div key={mid} className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                            <p className="text-xs font-semibold text-slate-200 truncate mb-1.5" title={group.filename}>
                              {group.filename}
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {group.items.map((item) => (
                                <span
                                  key={item.id}
                                  style={
                                    item.entityType === 'component'
                                      ? { backgroundColor: '#ffe4e6', color: '#9f1239', borderColor: '#fecdd3' }
                                      : item.entityType === 'job'
                                      ? { backgroundColor: '#fef3c7', color: '#78350f', borderColor: '#fde68a' }
                                      : { backgroundColor: '#ffedd5', color: '#9a3412', borderColor: '#fed7aa' }
                                  }
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border shadow-xs"
                                >
                                  <span className="uppercase text-[10px] opacity-75">{item.entityType[0]}:</span>
                                  <span>p. {item.page}</span>
                                  {!isExtracting && (
                                    <button
                                      type="button"
                                      onClick={() => removeQueueItem(item.id)}
                                      className="hover:opacity-70 ml-0.5"
                                      title="Remove from queue"
                                    >
                                      <X className="h-3 w-3" />
                                    </button>
                                  )}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Queue Footer Action */}
                  <div className="p-3 border-t border-slate-800 bg-slate-900/90 flex flex-col gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={handleTriggerExtract}
                      disabled={queuedItems.length === 0 || isExtracting}
                      className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {isExtracting ? (
                        <>
                          <RefreshCw className="h-3.5 w-3.5 animate-spin text-white" />
                          Extraction Running...
                        </>
                      ) : (
                        <>
                          <Play className="h-3.5 w-3.5 fill-current" />
                          Extract {queuedItems.length} Selected Page{queuedItems.length === 1 ? '' : 's'}
                        </>
                      )}
                    </button>

                    <p className="text-[10px] text-slate-500 text-center">
                      Selections are locked during extraction runs.
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* Modal Footer */}
        <div className="flex justify-between items-center border-t border-slate-800 pt-3.5 mt-3 shrink-0">
          <span className="text-xs text-slate-500">
            {activeTab === 'extracted'
              ? `${extractedManuals.length} manual(s) with extracted records. Click any page number to open PDF.`
              : `${queuedItems.length} page(s) staged for re-extraction.`}
          </span>
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

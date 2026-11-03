import React, { useState } from 'react'
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
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'

export interface NoExtractedManual {
  manual_id: string
  original_filename: string
  missing_components_pages: number[]
  missing_jobs_pages: number[]
  missing_spares_pages: number[]
  missing_components_count: number
  missing_jobs_count: number
  missing_spares_count: number
  total_missing_pages_count: number
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
    all_manuals_summary?: Record<string, any>
  } | null
  vesselId?: string
  isExtracting?: boolean
  onExtractQueued?: (queuedItems: QueuedPageItem[]) => Promise<void> | void
  queuedPages?: QueuedPageItem[]
  setQueuedPages?: React.Dispatch<React.SetStateAction<QueuedPageItem[]>>
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
}: NoExtractedRecordsModalProps) {
  if (!isOpen) return null

  const navigate = useNavigate()
  const { vesselId: routeVesselId } = useParams<{ vesselId?: string }>()
  const vesselId = propVesselId || routeVesselId

  // Support controlled or local queued state
  const [localQueued, setLocalQueued] = useState<QueuedPageItem[]>([])
  const queuedItems = propQueuedPages !== undefined ? propQueuedPages : localQueued
  const setQueuedItems = propSetQueuedPages !== undefined ? propSetQueuedPages : setLocalQueued

  const [loadingPdfKey, setLoadingPdfKey] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const manuals = data?.manuals || []

  // Check if an item is already queued
  const isQueued = (manualId: string, entityType: 'component' | 'job' | 'spare', page: number) => {
    const id = `${manualId}-${entityType}-${page}`
    return queuedItems.some((item) => item.id === id)
  }

  // Add item to queue
  const addQueueItem = (item: { manualId: string; filename: string; entityType: 'component' | 'job' | 'spare'; page: number }) => {
    if (isExtracting) return
    const id = `${item.manualId}-${item.entityType}-${item.page}`
    setQueuedItems((prev) => {
      if (prev.some((p) => p.id === id)) return prev
      return [...prev, { ...item, id }]
    })
  }

  // Remove item from queue
  const removeQueueItem = (id: string) => {
    if (isExtracting) return
    setQueuedItems((prev) => prev.filter((p) => p.id !== id))
  }

  // Queue all missing pages across all manuals
  const queueAllMissingPages = () => {
    if (isExtracting) return
    const allItems: QueuedPageItem[] = []
    manuals.forEach((m) => {
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

  // Drag handlers
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
    } catch (err) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-3 sm:p-5">
      <div className="relative w-full max-w-6xl rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl p-5 sm:p-6 text-slate-100 max-h-[90vh] flex flex-col">
        {/* Header Bar */}
        <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100">Specified Pages with No Extracted Records</h2>
                {manuals.length > 0 && (
                  <span className="bg-amber-950/80 text-amber-300 border border-amber-800/80 text-xs font-semibold px-2 py-0.5 rounded-full">
                    {data?.total_no_extracted_pages || 0} pages pending
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Click any page tile to view in PDF at that exact page. Drag & drop tiles (or click{' '}
                <Plus className="inline h-3 w-3 text-sky-400" />) to the <span className="text-sky-300 font-semibold">"To Extract"</span> queue.
              </p>
            </div>
          </div>

          {/* Top Actions */}
          <div className="flex items-center gap-2">
            {queuedItems.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={clearQueue}
                  disabled={isExtracting}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-750 transition-colors disabled:opacity-50"
                  title="Clear all queued selections"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-slate-400" />
                  Clear Selections
                </button>

                <button
                  type="button"
                  onClick={handleTriggerExtract}
                  disabled={isExtracting}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-xs font-bold text-white shadow-md shadow-emerald-950/50 transition-all disabled:opacity-60"
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
                      Extract Queued Pages ({queuedItems.length})
                    </>
                  )}
                </button>
              </>
            )}

            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
              title="Close modal"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Running Banner Notice */}
        {isExtracting && (
          <div className="mt-3 px-4 py-2.5 rounded-xl bg-sky-950/40 border border-sky-800/50 flex items-center justify-between text-xs text-sky-200">
            <div className="flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-sky-400 shrink-0" />
              <span>
                <strong>Extraction is in progress on queued pages.</strong> Selections are locked. You may close this modal to check progress on the manuals page and return anytime.
              </span>
            </div>
          </div>
        )}

        {/* Content Body: Split Layout */}
        <div className="flex-1 overflow-hidden mt-4 flex flex-col lg:flex-row gap-4 min-h-[380px]">
          {manuals.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center py-12 text-center text-slate-400">
              <CheckCircle2 className="h-14 w-14 text-emerald-400 mb-3" />
              <p className="text-base font-semibold text-slate-100">All specified pages have at least one extracted record!</p>
              <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                No targeted pages were skipped or returned zero records. You can review all extracted data in their respective review sections:
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
              {/* Left Side: Manuals Table (62% width on lg) */}
              <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-950/60 flex flex-col">
                <div className="p-3 border-b border-slate-800/80 bg-slate-900/60 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-slate-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                      Unextracted Pages by Manual
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={queueAllMissingPages}
                    disabled={isExtracting}
                    className="text-xs text-sky-400 hover:text-sky-300 font-semibold inline-flex items-center gap-1 hover:underline disabled:opacity-40"
                  >
                    <Plus className="h-3 w-3" />
                    Queue All Missing Pages
                  </button>
                </div>

                <div className="flex-1 overflow-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="sticky top-0 z-10 bg-slate-900 border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                      <tr>
                        <th className="py-2.5 px-3 w-[36%]">Manual File</th>
                        <th className="py-2.5 px-2 w-[18%]">Components</th>
                        <th className="py-2.5 px-2 w-[18%]">Jobs</th>
                        <th className="py-2.5 px-2 w-[18%]">Spares</th>
                        <th className="py-2.5 px-2 text-center w-[10%]">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-xs">
                      {manuals.map((manual) => (
                        <tr key={manual.manual_id} className="hover:bg-slate-900/40 transition-colors">
                          {/* Filename */}
                          <td className="py-3 px-3 font-semibold text-slate-300 break-words">
                            <span title={manual.original_filename}>{manual.original_filename}</span>
                          </td>

                          {/* Components */}
                          <td className="py-3 px-2">
                            {manual.missing_components_pages.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {manual.missing_components_pages.map((p) => {
                                  const queued = isQueued(manual.manual_id, 'component', p)
                                  const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                  return (
                                    <div
                                      key={`comp-${p}`}
                                      draggable={!isExtracting}
                                      onDragStart={(e) =>
                                        handleDragStart(e, {
                                          manualId: manual.manual_id,
                                          filename: manual.original_filename,
                                          entityType: 'component',
                                          page: p,
                                        })
                                      }
                                      className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none ${
                                        queued
                                          ? 'bg-sky-950/70 text-sky-300 border-sky-600/80 ring-1 ring-sky-500/30'
                                          : 'bg-rose-950/60 text-rose-300 border-rose-900/60 hover:bg-rose-900/40 hover:border-rose-700'
                                      } ${isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'}`}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => openPdfAtPage(manual.manual_id, p)}
                                        className="hover:underline flex items-center gap-1 focus:outline-none"
                                        title={`Click to view page ${p} in PDF | Drag to 'To Extract' column`}
                                      >
                                        {isLoading ? (
                                          <RefreshCw className="h-2.5 w-2.5 animate-spin text-rose-300" />
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
                                          className="opacity-60 group-hover:opacity-100 hover:text-sky-300 ml-0.5"
                                          title="Add to 'To Extract' queue"
                                        >
                                          <Plus className="h-3 w-3" />
                                        </button>
                                      )}
                                      {queued && (
                                        <CheckCircle2 className="h-2.5 w-2.5 text-sky-400 shrink-0" title="Queued" />
                                      )}
                                    </div>
                                  )
                                })}
                              </div>
                            ) : (
                              <span className="text-slate-600 text-xs italic">None</span>
                            )}
                          </td>

                          {/* Jobs */}
                          <td className="py-3 px-2">
                            {manual.missing_jobs_pages.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {manual.missing_jobs_pages.map((p) => {
                                  const queued = isQueued(manual.manual_id, 'job', p)
                                  const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                  return (
                                    <div
                                      key={`job-${p}`}
                                      draggable={!isExtracting}
                                      onDragStart={(e) =>
                                        handleDragStart(e, {
                                          manualId: manual.manual_id,
                                          filename: manual.original_filename,
                                          entityType: 'job',
                                          page: p,
                                        })
                                      }
                                      className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none ${
                                        queued
                                          ? 'bg-sky-950/70 text-sky-300 border-sky-600/80 ring-1 ring-sky-500/30'
                                          : 'bg-amber-950/60 text-amber-300 border-amber-900/60 hover:bg-amber-900/40 hover:border-amber-700'
                                      } ${isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'}`}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => openPdfAtPage(manual.manual_id, p)}
                                        className="hover:underline flex items-center gap-1 focus:outline-none"
                                        title={`Click to view page ${p} in PDF | Drag to 'To Extract' column`}
                                      >
                                        {isLoading ? (
                                          <RefreshCw className="h-2.5 w-2.5 animate-spin text-amber-300" />
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
                                          className="opacity-60 group-hover:opacity-100 hover:text-sky-300 ml-0.5"
                                          title="Add to 'To Extract' queue"
                                        >
                                          <Plus className="h-3 w-3" />
                                        </button>
                                      )}
                                      {queued && (
                                        <CheckCircle2 className="h-2.5 w-2.5 text-sky-400 shrink-0" title="Queued" />
                                      )}
                                    </div>
                                  )
                                })}
                              </div>
                            ) : (
                              <span className="text-slate-600 text-xs italic">None</span>
                            )}
                          </td>

                          {/* Spares */}
                          <td className="py-3 px-2">
                            {manual.missing_spares_pages.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {manual.missing_spares_pages.map((p) => {
                                  const queued = isQueued(manual.manual_id, 'spare', p)
                                  const isLoading = loadingPdfKey === `${manual.manual_id}-${p}`
                                  return (
                                    <div
                                      key={`spare-${p}`}
                                      draggable={!isExtracting}
                                      onDragStart={(e) =>
                                        handleDragStart(e, {
                                          manualId: manual.manual_id,
                                          filename: manual.original_filename,
                                          entityType: 'spare',
                                          page: p,
                                        })
                                      }
                                      className={`group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold border transition-all select-none ${
                                        queued
                                          ? 'bg-sky-950/70 text-sky-300 border-sky-600/80 ring-1 ring-sky-500/30'
                                          : 'bg-orange-950/60 text-orange-300 border-orange-900/60 hover:bg-orange-900/40 hover:border-orange-700'
                                      } ${isExtracting ? 'cursor-not-allowed opacity-75' : 'cursor-grab active:cursor-grabbing'}`}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => openPdfAtPage(manual.manual_id, p)}
                                        className="hover:underline flex items-center gap-1 focus:outline-none"
                                        title={`Click to view page ${p} in PDF | Drag to 'To Extract' column`}
                                      >
                                        {isLoading ? (
                                          <RefreshCw className="h-2.5 w-2.5 animate-spin text-orange-300" />
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
                                          className="opacity-60 group-hover:opacity-100 hover:text-sky-300 ml-0.5"
                                          title="Add to 'To Extract' queue"
                                        >
                                          <Plus className="h-3 w-3" />
                                        </button>
                                      )}
                                      {queued && (
                                        <CheckCircle2 className="h-2.5 w-2.5 text-sky-400 shrink-0" title="Queued" />
                                      )}
                                    </div>
                                  )
                                })}
                              </div>
                            ) : (
                              <span className="text-slate-600 text-xs italic">None</span>
                            )}
                          </td>

                          {/* Total */}
                          <td className="py-3 px-2 text-center font-bold text-amber-400">
                            {manual.total_missing_pages_count}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Right Side: "To Extract" Dropzone Queue (38% width on lg) */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`w-full lg:w-[380px] rounded-xl border flex flex-col transition-all ${
                  isDragOver
                    ? 'border-sky-400 bg-sky-950/50 shadow-lg shadow-sky-950/50 ring-2 ring-sky-500/40'
                    : 'border-slate-800 bg-slate-950/80'
                }`}
              >
                {/* Queue Header */}
                <div className="p-3 border-b border-slate-800 bg-slate-900/80 flex items-center justify-between">
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
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${
                                  item.entityType === 'component'
                                    ? 'bg-rose-950/70 text-rose-300 border-rose-800/80'
                                    : item.entityType === 'job'
                                    ? 'bg-amber-950/70 text-amber-300 border-amber-800/80'
                                    : 'bg-orange-950/70 text-orange-300 border-orange-800/80'
                                }`}
                              >
                                <span className="uppercase text-[10px] opacity-75">{item.entityType[0]}:</span>
                                <span>p. {item.page}</span>
                                {!isExtracting && (
                                  <button
                                    type="button"
                                    onClick={() => removeQueueItem(item.id)}
                                    className="hover:text-white ml-0.5"
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
                <div className="p-3 border-t border-slate-800 bg-slate-900/90 flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={handleTriggerExtract}
                    disabled={queuedItems.length === 0 || isExtracting}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-xs font-bold text-white shadow-lg shadow-emerald-950/60 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
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
                    Selections are preserved if you close the modal to check progress.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex justify-between items-center border-t border-slate-800 pt-4 mt-4">
          <span className="text-xs text-slate-500">
            {queuedItems.length > 0
              ? `${queuedItems.length} page(s) staged for re-extraction.`
              : 'Select pages to re-run extraction on targeted sections.'}
          </span>
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

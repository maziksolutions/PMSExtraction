import React, { useEffect, useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, FileSearch, Maximize2, RefreshCw, RotateCcw, RotateCw, Scissors, X, ZoomIn, ZoomOut, CheckCircle, Loader2 } from 'lucide-react'
import apiClient from '@/api/client'

interface PreviewPage {
  page_number: number
  text_excerpt?: string | null
  image_data_url?: string | null
  error?: string | null
}

interface PreviewResponse {
  manual_id: string
  file_name: string
  file_extension: string | null
  page_count: number | null
  pages: PreviewPage[]
}

interface DragPoint {
  x: number
  y: number
}

interface ManualPagePreviewProps {
  vesselId: string
  manualId: string | null | undefined
  manualName?: string | null
  title: string
  subtitle?: string | null
  defaultPages?: string | number | null
  panelClassName?: string
  headerContent?: React.ReactNode
  showTextSnippet?: boolean
  hideHeader?: boolean
  enableSnipPush?: boolean
}

function getApiError(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const d = e?.response?.data?.detail
  if (typeof d === 'string' && d) return d
  return e?.message ?? 'Request failed'
}

async function imageElementToBlob(
  imgEl: HTMLImageElement,
  cropBox?: { x1: number; y1: number; x2: number; y2: number }
): Promise<Blob> {
  const canvas = document.createElement('canvas')
  let sx = 0, sy = 0, sw = imgEl.naturalWidth, sh = imgEl.naturalHeight
  if (cropBox) {
    const offsetWidth = imgEl.offsetWidth || 1
    const offsetHeight = imgEl.offsetHeight || 1
    const scaleX = imgEl.naturalWidth / offsetWidth
    const scaleY = imgEl.naturalHeight / offsetHeight
    sx = Math.round(cropBox.x1 * scaleX)
    sy = Math.round(cropBox.y1 * scaleY)
    sw = Math.round((cropBox.x2 - cropBox.x1) * scaleX)
    sh = Math.round((cropBox.y2 - cropBox.y1) * scaleY)
  }
  
  // Guard against non-finite or invalid numbers
  if (!isFinite(sx) || isNaN(sx)) sx = 0
  if (!isFinite(sy) || isNaN(sy)) sy = 0
  if (!isFinite(sw) || isNaN(sw) || sw <= 0) sw = imgEl.naturalWidth || 1
  if (!isFinite(sh) || isNaN(sh) || sh <= 0) sh = imgEl.naturalHeight || 1

  canvas.width = Math.max(1, sw)
  canvas.height = Math.max(1, sh)
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(imgEl, sx, sy, sw, sh, 0, 0, sw, sh)
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Canvas toBlob failed'))), 'image/png')
  )
}

const ManualPagePreview: React.FC<ManualPagePreviewProps> = ({
  vesselId,
  manualId,
  manualName,
  title,
  subtitle,
  defaultPages,
  panelClassName,
  headerContent,
  showTextSnippet = true,
  hideHeader = false,
  enableSnipPush = false,
}) => {
  const [pageInput, setPageInput] = useState('')
  const [requestedPages, setRequestedPages] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [rotation, setRotation] = useState(0)
  const [activePageNumber, setActivePageNumber] = useState<number | null>(null)
  const [zoom, setZoom] = useState(1.0)

  // Snip Tool States
  const [isSnipMode, setIsSnipMode] = useState(false)
  const [snippingPageNumber, setSnippingPageNumber] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState<DragPoint | null>(null)
  const [dragEnd, setDragEnd] = useState<DragPoint | null>(null)
  const [hasSelection, setHasSelection] = useState(false)
  const [isExtractingText, setIsExtractingText] = useState(false)
  const [extractedText, setExtractedText] = useState('')
  const [selectedTargetField, setSelectedTargetField] = useState('job_description')
  const [ocrError, setOcrError] = useState<string | null>(null)
  const [pushSuccess, setPushSuccess] = useState(false)

  const imgRef = useRef<HTMLImageElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const isDraggingRef = useRef(false)

  useEffect(() => {
    // If defaultPages is not provided or is empty/null/undefined, default to Page 1
    const nextValue = defaultPages == null || String(defaultPages).trim() === '' ? '1' : String(defaultPages)
    setPageInput(nextValue)
    setRequestedPages(nextValue)
    // Clear snip states when manual/page changes
    setDragStart(null)
    setDragEnd(null)
    setHasSelection(false)
    setExtractedText('')
    setOcrError(null)
  }, [defaultPages, manualId])

  const { data, isFetching, isError, refetch, error } = useQuery<PreviewResponse>({
    queryKey: ['manual-preview', vesselId, manualId, requestedPages],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/manuals/${manualId}/page-preview`, {
          params: { pages: requestedPages },
        })
        .then((response) => response.data),
    enabled: !!manualId && !!requestedPages,
    retry: false,
  })

  useEffect(() => {
    const pages = data?.pages ?? []
    setActivePageNumber(pages.length > 1 ? pages[0].page_number : null)
  }, [data?.pages])

  const visiblePages =
    activePageNumber == null
      ? data?.pages ?? []
      : (data?.pages ?? []).filter((page) => page.page_number === activePageNumber)

  const multiPage = (data?.pages?.length ?? 0) > 1

  const goToPage = (pageNum: number) => {
    if (pageNum < 1) return
    const maxPage = data?.page_count ?? 9999
    if (pageNum > maxPage) return

    const isLoaded = data?.pages?.some((p) => p.page_number === pageNum)
    if (isLoaded) {
      setActivePageNumber(pageNum)
    } else {
      const pageStr = String(pageNum)
      setPageInput(pageStr)
      setRequestedPages(pageStr)
      setActivePageNumber(pageNum)
    }
  }

  // Pointer dragging logic for visual selection box
  const getOverlayPoint = (clientX: number, clientY: number): DragPoint => {
    if (!overlayRef.current) return { x: 0, y: 0 }
    const rect = overlayRef.current.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(clientX - rect.left, rect.width)),
      y: Math.max(0, Math.min(clientY - rect.top, rect.height)),
    }
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>, pageNum: number) => {
    if (!overlayRef.current) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    setSnippingPageNumber(pageNum)
    const pt = getOverlayPoint(e.clientX, e.clientY)
    setDragStart(pt)
    setDragEnd(pt)
    isDraggingRef.current = true
    setIsDragging(true)
    setHasSelection(false)
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return
    setDragEnd(getOverlayPoint(e.clientX, e.clientY))
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return
    isDraggingRef.current = false
    setIsDragging(false)
    const end = getOverlayPoint(e.clientX, e.clientY)
    setDragEnd(end)
    setDragStart((prev) => {
      if (prev) {
        const w = Math.abs(end.x - prev.x)
        const h = Math.abs(end.y - prev.y)
        setHasSelection(w > 15 && h > 15)
      }
      return prev
    })
  }

  const selectionRect =
    dragStart && dragEnd
      ? {
          left: Math.min(dragStart.x, dragEnd.x),
          top: Math.min(dragStart.y, dragEnd.y),
          width: Math.abs(dragEnd.x - dragStart.x),
          height: Math.abs(dragEnd.y - dragStart.y),
        }
      : null

  const getCropBox = (): { x1: number; y1: number; x2: number; y2: number } | undefined => {
    if (!hasSelection || !dragStart || !dragEnd) return undefined
    return {
      x1: Math.min(dragStart.x, dragEnd.x),
      y1: Math.min(dragStart.y, dragEnd.y),
      x2: Math.max(dragStart.x, dragEnd.x),
      y2: Math.max(dragStart.y, dragEnd.y),
    }
  }

  const handleExtractText = async () => {
    if (!imgRef.current) return
    setIsExtractingText(true)
    setOcrError(null)
    setExtractedText('')
    try {
      const cropBox = getCropBox()
      const blob = await imageElementToBlob(imgRef.current, cropBox)
      const formData = new FormData()
      formData.append('image', blob, 'snipped_region.png')
      
      const res = await apiClient.post(`/vessels/${vesselId}/jobs/snip-ocr`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      })
      
      const text = res.data.text ?? ''
      setExtractedText(text)
    } catch (err) {
      setOcrError(getApiError(err))
    } finally {
      setIsExtractingText(false)
    }
  }

  const renderPageCards = (fullscreen = false) => (
    <div className="space-y-4">
      {!requestedPages ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          Enter page numbers to load a manual preview.
        </div>
      ) : null}

      {requestedPages && !isFetching && !data?.pages?.length ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          No preview pages were returned for this selection.
        </div>
      ) : null}

      {isFetching && !data?.pages?.length ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          Loading preview pages...
        </div>
      ) : null}

      {visiblePages.map((page) => (
        <section key={page.page_number} className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
          <div className="border-b border-slate-800 px-2.5 py-1">
            <div className="text-xs font-semibold text-slate-300">Physical Page {page.page_number}</div>
            {page.error ? <div className="mt-1 text-xs text-red-300">{page.error}</div> : null}
          </div>
          <div className="space-y-2 p-1.5">
            {page.image_data_url ? (
              <div className="overflow-auto rounded-lg border border-slate-800 bg-slate-900/70">
                <div 
                  className={`flex ${fullscreen ? 'min-w-max justify-center p-4' : 'min-w-max p-1.5'}`}
                  style={{ zoom: zoom }}
                >
                  <div className="relative inline-block select-none">
                    <img
                      ref={imgRef}
                      src={page.image_data_url}
                      alt={`Manual page ${page.page_number}`}
                      draggable={false}
                      className="rounded-lg bg-white transition-transform"
                      style={{
                        transform: `rotate(${rotation}deg)`,
                        transformOrigin: 'center center',
                        maxHeight: fullscreen ? '80vh' : undefined,
                        width: rotation % 180 === 0 && !fullscreen ? '100%' : 'auto',
                        maxWidth: rotation % 180 === 0 && !fullscreen ? '100%' : 'none',
                        userSelect: 'none',
                        pointerEvents: 'none',
                      }}
                    />
                    {isSnipMode && (
                      <>
                        {/* Interaction overlay */}
                        <div
                          ref={overlayRef}
                          className="absolute inset-0 z-10"
                          style={{ cursor: 'crosshair', touchAction: 'none' }}
                          onPointerDown={(e) => handlePointerDown(e, page.page_number)}
                          onPointerMove={handlePointerMove}
                          onPointerUp={handlePointerUp}
                          onPointerCancel={handlePointerUp}
                        />
                        {/* Selection rectangle */}
                        {snippingPageNumber === page.page_number && selectionRect && selectionRect.width > 4 && selectionRect.height > 4 && (
                          <div
                            className="pointer-events-none absolute z-20"
                            style={{
                              left: selectionRect.left,
                              top: selectionRect.top,
                              width: selectionRect.width,
                              height: selectionRect.height,
                              border: '2px solid #22c55e',
                              background: 'rgba(34,197,94,0.08)',
                            }}
                          />
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-900/80 text-xs text-slate-500">
                <div className="text-center">
                  <FileSearch className="mx-auto mb-2 h-5 w-5 opacity-40" />
                  Preview image not available for this page.
                </div>
              </div>
            )}
            {showTextSnippet ? (
              <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-2">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Extracted Text Snippet
                </div>
                <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">
                  {page.text_excerpt?.trim() || 'No stored text snippet available for this page.'}
                </pre>
              </div>
            ) : null}
          </div>
        </section>
      ))}
    </div>
  )

  if (!manualId) {
    return (
      <aside className={`${panelClassName ?? 'w-[40rem]'} shrink-0 flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-4`}>
        {headerContent ? (
          <div className="mb-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3 shrink-0">
            {headerContent}
          </div>
        ) : null}
        <div className="flex-1 flex items-center justify-center text-center text-sm text-slate-500 min-h-72">
          Select a record with a manual reference to preview its pages.
        </div>
      </aside>
    )
  }

  return (
    <div className="flex h-full w-full gap-3 overflow-hidden">
      <aside className={`flex-1 flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-1.5`}>
        <div className="mb-1.5 space-y-1.5 shrink-0">
          {!hideHeader && (
            <div className="flex items-center justify-between gap-4 border-b border-slate-800 pb-1.5 mb-1.5">
              <div>
                <h3 className="text-xs font-semibold text-slate-100 leading-tight">{title}</h3>
                {subtitle ? <p className="mt-0.5 text-[10px] text-slate-500 leading-none">{subtitle}</p> : null}
              </div>
              <div className="text-right text-xs text-slate-400 font-medium truncate max-w-[50%]">
                {manualName ?? 'Manual preview'}
              </div>
            </div>
          )}
          {headerContent ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-2">
              {headerContent}
            </div>
          ) : null}
          
          {/* Single-line Compact Toolbar */}
          <div className="flex items-center justify-between flex-wrap gap-2 rounded-lg border border-slate-850 bg-slate-950/40 p-1.5">
            {/* Left Part: Page Input and Page list pagination controls */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-bold text-slate-500 uppercase px-0.5">Pages:</span>
              <input
                type="text"
                value={pageInput}
                onChange={(event) => setPageInput(event.target.value)}
                placeholder="Pages..."
                className="w-16 rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-100 focus:border-sky-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setRequestedPages(pageInput.trim())}
                className="rounded bg-sky-600 px-2 py-0.5 text-xs font-semibold text-white hover:bg-sky-500"
              >
                Load
              </button>
              <button
                type="button"
                onClick={() => refetch()}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Refresh preview"
              >
                <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
              </button>

              {manualName && (
                <>
                  <div className="h-4 w-px bg-slate-800 mx-0.5" />
                  <span 
                    className="max-w-[150px] truncate rounded bg-slate-900 border border-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 font-medium"
                    title={manualName}
                  >
                    {manualName}
                  </span>
                </>
              )}

              <div className="h-4 w-px bg-slate-800 mx-0.5" />

              {/* Previous and Next Page navigation buttons */}
              {data?.pages && data.pages.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <button
                    type="button"
                    onClick={() => {
                      const prevPage = activePageNumber !== null 
                        ? activePageNumber - 1 
                        : (data?.pages?.[0]?.page_number ?? 1) - 1
                      goToPage(prevPage)
                    }}
                    disabled={
                      activePageNumber !== null
                        ? activePageNumber <= 1
                        : !data?.pages?.length || data.pages[0].page_number <= 1
                    }
                    className="rounded border border-slate-700 p-0.5 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                    title="Previous page"
                  >
                    <ChevronLeft className="h-3 w-3" />
                  </button>
                  {multiPage && (
                    <button
                      type="button"
                      onClick={() => setActivePageNumber(null)}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${activePageNumber == null ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                    >
                      All
                    </button>
                  )}
                  {(data?.pages ?? []).map((page) => (
                    <button
                      key={page.page_number}
                      type="button"
                      onClick={() => setActivePageNumber(page.page_number)}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        (activePageNumber === page.page_number || (activePageNumber === null && !multiPage))
                          ? 'bg-sky-600 text-white'
                          : 'border border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {page.page_number}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      const nextPage = activePageNumber !== null 
                        ? activePageNumber + 1 
                        : (data?.pages?.[data.pages.length - 1]?.page_number ?? 1) + 1
                      goToPage(nextPage)
                    }}
                    disabled={
                      activePageNumber !== null
                        ? (data?.page_count !== null && activePageNumber >= data.page_count)
                        : !data?.pages?.length || (data?.page_count !== null && data.pages[data.pages.length - 1].page_number >= data.page_count)
                    }
                    className="rounded border border-slate-700 p-0.5 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                    title="Next page"
                  >
                    <ChevronRight className="h-3 w-3" />
                  </button>
                  {data.page_count && (
                    <span className="text-[10px] text-slate-500 font-medium ml-1">
                      of {data.page_count}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Right Part: Rotate, Zoom, Snip and Maximize */}
            <div className="flex items-center gap-1.5 ml-auto">
              {enableSnipPush && (
                <button
                  type="button"
                  onClick={() => {
                    setIsSnipMode(!isSnipMode)
                    setDragStart(null)
                    setDragEnd(null)
                    setHasSelection(false)
                  }}
                  className={`rounded border px-1.5 py-0.5 text-xs transition-colors flex items-center gap-1 ${
                    isSnipMode
                      ? 'border-sky-600 bg-sky-900/30 text-sky-300'
                      : 'border-slate-700 text-slate-300 hover:bg-slate-805'
                  }`}
                  title="Toggle Snip Tool"
                >
                  <Scissors className="h-3 w-3" />
                  <span>Snip</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsFullscreen(true)}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Open large preview"
              >
                <Maximize2 className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => setRotation((value) => (value + 270) % 360)}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Rotate left"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => setRotation((value) => (value + 90) % 360)}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Rotate right"
              >
                <RotateCw className="h-3 w-3" />
              </button>
              
              <div className="h-4 w-px bg-slate-800 mx-0.5" />
              
              <button
                type="button"
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.1))}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Zoom out"
              >
                <ZoomOut className="h-3 w-3" />
              </button>
              <span className="text-[10px] font-medium text-slate-400 min-w-[2rem] text-center">
                {Math.round(zoom * 100)}%
              </span>
              <button
                type="button"
                onClick={() => setZoom((z) => Math.min(3.0, z + 0.1))}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                title="Zoom in"
              >
                <ZoomIn className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => setZoom(1.0)}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-850 hover:text-white"
                title="Reset zoom"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        {isError ? (
          <div className="rounded-lg border border-red-900/60 bg-red-950/40 p-3 text-xs text-red-200 shrink-0 mb-3">
            {(error as Error)?.message ?? 'Preview could not be loaded.'}
          </div>
        ) : null}

        <div className="flex-1 overflow-y-auto min-h-0 pr-1">
          {renderPageCards(false)}
        </div>
      </aside>

      {/* Standalone Snip & Push Side Panel */}
      {enableSnipPush && (
        <div className="w-80 shrink-0 flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-3">
          <div className="flex shrink-0 items-center gap-2 border-b border-slate-800 pb-2 mb-3">
            <Scissors className="h-4 w-4 text-sky-400" />
            <span className="text-sm font-semibold text-white">Snip &amp; Push to Job</span>
          </div>
          
          <div className="space-y-4 flex-1 flex flex-col min-h-0">
            <button
              type="button"
              onClick={() => {
                setIsSnipMode(!isSnipMode)
                setDragStart(null)
                setDragEnd(null)
                setHasSelection(false)
              }}
              className={`w-full flex items-center justify-center gap-2 rounded-lg py-2.5 text-xs font-semibold transition-colors ${
                isSnipMode
                  ? 'bg-sky-600 text-white hover:bg-sky-500'
                  : 'border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Scissors className="h-4 w-4" />
              {isSnipMode ? 'Deactivate Snip Tool' : 'Activate Snip Tool'}
            </button>
            
            <p className="text-[11px] text-slate-500 leading-normal">
              {isSnipMode
                ? 'Snip Tool is active. Click and drag a box over the PDF text to select, then click Extract.'
                : 'Activate the Snip Tool to select text regions.'}
            </p>

            {hasSelection && isSnipMode && (
              <button
                type="button"
                onClick={handleExtractText}
                disabled={isExtractingText}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-green-700 hover:bg-green-600 py-2.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                {isExtractingText ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4 animate-spin" />}
                {isExtractingText ? 'Extracting Text...' : 'Extract Selection'}
              </button>
            )}

            {ocrError && (
              <div className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
                {ocrError}
              </div>
            )}

            {isExtractingText && !ocrError && (
              <div className="flex flex-col items-center justify-center py-6 gap-2 text-slate-500 shrink-0">
                <Loader2 className="h-6 w-6 animate-spin text-sky-500" />
                <span className="text-xs">Running OCR on crop...</span>
              </div>
            )}

            {(extractedText || (!isExtractingText && !ocrError)) && (
              <div className="flex-1 flex flex-col min-h-0 space-y-3">
                <div className="flex-1 flex flex-col min-h-0">
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Extracted Text</label>
                  <textarea
                    value={extractedText}
                    onChange={(e) => setExtractedText(e.target.value)}
                    className="w-full flex-1 rounded-lg border border-slate-750 bg-slate-950 p-2.5 font-mono text-xs text-slate-200 focus:border-sky-500 focus:outline-none resize-none"
                    placeholder="Extracted text will appear here..."
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Push Target Field</label>
                  <select
                    value={selectedTargetField}
                    onChange={(e) => setSelectedTargetField(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-2 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                  >
                    <option value="job_description">Job Procedure</option>
                    <option value="safety_precaution">Safety Precaution</option>
                    <option value="tools_required">Tools Required</option>
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const channel = new BroadcastChannel('job-editor-channel')
                    channel.postMessage({
                      type: 'PUSH_TEXT',
                      field: selectedTargetField,
                      text: extractedText,
                    })
                    channel.close()
                    setPushSuccess(true)
                    setTimeout(() => setPushSuccess(false), 2000)
                  }}
                  disabled={!extractedText}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 py-2.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  Push to Job Editor
                </button>

                {pushSuccess && (
                  <div className="flex items-center justify-center gap-1.5 rounded-lg border border-green-950 bg-green-950/40 px-3 py-1.5 text-xs text-green-300">
                    <CheckCircle className="h-3.5 w-3.5" />
                    Pushed to Job Editor!
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {isFullscreen ? (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm">
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/95 px-5 py-3 flex-wrap gap-4 z-10">
              <div>
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="mt-1 text-xs text-slate-400">{manualName ?? 'Manual preview'}</div>
              </div>

              {/* Middle part: Load Input & Page Navigation Controls */}
              <div className="flex items-center gap-4 flex-wrap">
                {/* Load Input */}
                <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-2 py-1">
                  <span className="text-[10px] font-semibold uppercase text-slate-500 px-1">Pages:</span>
                  <input
                    type="text"
                    value={pageInput}
                    onChange={(event) => setPageInput(event.target.value)}
                    placeholder="e.g. 9-12 or 3"
                    className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 focus:border-sky-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setRequestedPages(pageInput.trim())}
                    className="rounded bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-500"
                  >
                    Load
                  </button>
                  <button
                    type="button"
                    onClick={() => refetch()}
                    className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                    title="Refresh preview"
                  >
                    <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
                  </button>
                </div>

                {/* Page navigation buttons */}
                {data?.pages && data.pages.length > 0 ? (
                  <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 p-1">
                    <button
                      type="button"
                      onClick={() => {
                        const prevPage = activePageNumber !== null 
                          ? activePageNumber - 1 
                          : (data?.pages?.[0]?.page_number ?? 1) - 1
                        goToPage(prevPage)
                      }}
                      disabled={
                        activePageNumber !== null
                          ? activePageNumber <= 1
                          : !data?.pages?.length || data.pages[0].page_number <= 1
                      }
                      className="rounded border border-slate-700 p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                      title="Previous page"
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </button>
                    {multiPage && (
                      <button
                        type="button"
                        onClick={() => setActivePageNumber(null)}
                        className={`rounded px-2 py-0.5 text-xs ${activePageNumber == null ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}
                      >
                        All Pages
                      </button>
                    )}
                    {(data?.pages ?? []).map((page) => (
                      <button
                        key={page.page_number}
                        type="button"
                        onClick={() => setActivePageNumber(page.page_number)}
                        className={`rounded px-2 py-0.5 text-xs ${
                          (activePageNumber === page.page_number || (activePageNumber === null && !multiPage))
                            ? 'bg-sky-600 text-white'
                            : 'text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        {page.page_number}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => {
                        const nextPage = activePageNumber !== null 
                          ? activePageNumber + 1 
                          : (data?.pages?.[data.pages.length - 1]?.page_number ?? 1) + 1
                        goToPage(nextPage)
                      }}
                      disabled={
                        activePageNumber !== null
                          ? (data?.page_count !== null && activePageNumber >= data.page_count)
                          : !data?.pages?.length || (data?.page_count !== null && data.pages[data.pages.length - 1].page_number >= data.page_count)
                      }
                      className="rounded border border-slate-700 p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                      title="Next page"
                    >
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : null}
              </div>

              {/* Right part: Zoom/Rotate/Close */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.max(0.5, z - 0.1))}
                  className="rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800"
                  title="Zoom out"
                >
                  <ZoomOut className="h-3.5 w-3.5" />
                </button>
                <span className="flex items-center px-1 text-xs font-medium text-slate-300 min-w-[2.5rem] justify-center">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.min(3.0, z + 0.1))}
                  className="rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800"
                  title="Zoom in"
                >
                  <ZoomIn className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setZoom(1.0)}
                  className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                  title="Reset zoom"
                >
                  Reset
                </button>
                <div className="h-6 w-px bg-slate-800 mx-1" />
                <button
                  type="button"
                  onClick={() => setRotation((value) => (value + 270) % 360)}
                  className="rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800"
                  title="Rotate left"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setRotation((value) => (value + 90) % 360)}
                  className="rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800"
                  title="Rotate right"
                >
                  <RotateCw className="h-3.5 w-3.5" />
                </button>
                <div className="h-6 w-px bg-slate-800 mx-1" />
                <button
                  type="button"
                  onClick={() => setIsFullscreen(false)}
                  className="rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800"
                  title="Exit fullscreen"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              {renderPageCards(true)}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default ManualPagePreview

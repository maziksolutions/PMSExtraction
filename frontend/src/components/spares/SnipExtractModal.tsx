import React, { useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Scissors, Upload, X, Loader2, CheckCircle, ChevronDown, RotateCcw, RotateCw } from 'lucide-react'
import apiClient from '@/api/client'

interface ExtractedRecord {
  part_name: string
  part_number: string | null
  drawing_number: string | null
  drawing_position: string | null
  specification: string | null
  spare_maker: string | null
  spare_model: string | null
  confidence_score: number | null
  source_page_number: number | null
}

interface ManualItem {
  id: string
  original_filename: string
  file_extension: string
}

interface DragPoint {
  x: number
  y: number
}

interface SnipExtractModalProps {
  vesselId: string
  onClose: () => void
  onSaved: () => void
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
    const scaleX = imgEl.naturalWidth / imgEl.offsetWidth
    const scaleY = imgEl.naturalHeight / imgEl.offsetHeight
    sx = Math.round(cropBox.x1 * scaleX)
    sy = Math.round(cropBox.y1 * scaleY)
    sw = Math.round((cropBox.x2 - cropBox.x1) * scaleX)
    sh = Math.round((cropBox.y2 - cropBox.y1) * scaleY)
  }
  canvas.width = Math.max(1, sw)
  canvas.height = Math.max(1, sh)
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(imgEl, sx, sy, sw, sh, 0, 0, sw, sh)
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Canvas toBlob failed'))), 'image/png')
  )
}

// Physically rotate image pixels by 90° increments using a canvas so the
// rendered <img> element always has correct layout dimensions (no CSS transform).
function rotateDataUrl(src: string, degrees: 90 | -90): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new window.Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      // 90° rotations swap width/height
      canvas.width = img.height
      canvas.height = img.width
      const ctx = canvas.getContext('2d')!
      ctx.translate(canvas.width / 2, canvas.height / 2)
      ctx.rotate((degrees * Math.PI) / 180)
      ctx.drawImage(img, -img.width / 2, -img.height / 2)
      resolve(canvas.toDataURL('image/png'))
    }
    img.onerror = () => reject(new Error('Failed to load image for rotation'))
    img.src = src
  })
}

// Convert a blob:// or data: URL to a data URL so canvas can read it cross-origin-safely.
function toDataUrl(src: string): Promise<string> {
  if (src.startsWith('data:')) return Promise.resolve(src)
  return new Promise((resolve, reject) => {
    const img = new window.Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight
      canvas.getContext('2d')!.drawImage(img, 0, 0)
      resolve(canvas.toDataURL('image/png'))
    }
    img.onerror = () => reject(new Error('Failed to read image'))
    img.src = src
  })
}

const SnipExtractModal: React.FC<SnipExtractModalProps> = ({ vesselId, onClose, onSaved }) => {
  const imgRef = useRef<HTMLImageElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  const [imageMode, setImageMode] = useState<'manual' | 'upload'>('manual')
  const [selectedManualId, setSelectedManualId] = useState('')
  const [pageInput, setPageInput] = useState('')

  // displayImageUrl is the currently-shown image — may be canvas-rotated from the original
  const [displayImageUrl, setDisplayImageUrl] = useState<string | null>(null)
  const [isRotating, setIsRotating] = useState(false)
  const [loadedManualId, setLoadedManualId] = useState<string | null>(null)
  const [loadedPage, setLoadedPage] = useState<number | null>(null)
  const [isLoadingPage, setIsLoadingPage] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState<DragPoint | null>(null)
  const [dragEnd, setDragEnd] = useState<DragPoint | null>(null)
  const [hasSelection, setHasSelection] = useState(false)

  const [isExtracting, setIsExtracting] = useState(false)
  const [extractedRecords, setExtractedRecords] = useState<ExtractedRecord[]>([])
  const [checkedIndices, setCheckedIndices] = useState<Set<number>>(new Set())
  const [extractError, setExtractError] = useState<string | null>(null)

  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const manualsQuery = useQuery({
    queryKey: ['snip-manuals', vesselId],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/manuals`, { params: { page_size: 500, sort_by: 'filename' } })
        .then((r) => (r.data.items ?? []) as ManualItem[]),
    enabled: !!vesselId,
  })
  const manuals: ManualItem[] = manualsQuery.data ?? []

  const clearSelectionAndResults = () => {
    setDragStart(null)
    setDragEnd(null)
    setHasSelection(false)
    setExtractedRecords([])
    setSaveMessage(null)
  }

  const loadPage = async () => {
    const pageNum = parseInt(pageInput, 10)
    if (!selectedManualId || isNaN(pageNum) || pageNum < 1) return
    setIsLoadingPage(true)
    setLoadError(null)
    setDisplayImageUrl(null)
    clearSelectionAndResults()
    try {
      const res = await apiClient.get(`/vessels/${vesselId}/manuals/${selectedManualId}/page-preview`, {
        params: { pages: String(pageNum) },
      })
      const page = (res.data.pages ?? [])[0]
      if (page?.image_data_url) {
        setDisplayImageUrl(page.image_data_url)
        setLoadedManualId(selectedManualId)
        setLoadedPage(pageNum)
      } else {
        setLoadError('No image available for this page.')
      }
    } catch (err) {
      setLoadError(getApiError(err))
    } finally {
      setIsLoadingPage(false)
    }
  }

  const handleFileUpload = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) return
    const blobUrl = URL.createObjectURL(file)
    clearSelectionAndResults()
    setLoadError(null)
    setLoadedManualId(null)
    setLoadedPage(null)
    try {
      // Convert to data URL so canvas rotation works without CORS issues
      const dataUrl = await toDataUrl(blobUrl)
      URL.revokeObjectURL(blobUrl)
      setDisplayImageUrl(dataUrl)
    } catch {
      setDisplayImageUrl(blobUrl)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }, [handleFileUpload])

  const handleRotate = async (degrees: 90 | -90) => {
    if (!displayImageUrl || isRotating) return
    setIsRotating(true)
    clearSelectionAndResults()
    try {
      const rotated = await rotateDataUrl(displayImageUrl, degrees)
      setDisplayImageUrl(rotated)
    } catch {
      // rotation failed silently — keep current image
    } finally {
      setIsRotating(false)
    }
  }

  const getOverlayPoint = (e: React.MouseEvent<HTMLDivElement>): DragPoint => {
    const rect = overlayRef.current!.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(e.clientX - rect.left, rect.width)),
      y: Math.max(0, Math.min(e.clientY - rect.top, rect.height)),
    }
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!overlayRef.current) return
    e.preventDefault()
    const pt = getOverlayPoint(e)
    setDragStart(pt)
    setDragEnd(pt)
    setIsDragging(true)
    setHasSelection(false)
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || !dragStart) return
    setDragEnd(getOverlayPoint(e))
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging) return
    setIsDragging(false)
    const end = getOverlayPoint(e)
    setDragEnd(end)
    if (dragStart) {
      const w = Math.abs(end.x - dragStart.x)
      const h = Math.abs(end.y - dragStart.y)
      setHasSelection(w > 15 && h > 15)
    }
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

  const handleExtract = async (useSelection: boolean) => {
    if (!imgRef.current || !displayImageUrl) return
    setIsExtracting(true)
    setExtractError(null)
    setExtractedRecords([])
    setSaveMessage(null)
    try {
      const cropBox = useSelection ? getCropBox() : undefined
      const blob = await imageElementToBlob(imgRef.current, cropBox)
      const formData = new FormData()
      formData.append('image', blob, 'page.png')
      if (loadedPage) formData.append('page_number', String(loadedPage))
      const res = await apiClient.post(`/vessels/${vesselId}/spares/snip-extract`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      })
      const records: ExtractedRecord[] = res.data.records ?? []
      setExtractedRecords(records)
      setCheckedIndices(new Set(records.map((_, i) => i)))
    } catch (err) {
      setExtractError(getApiError(err))
    } finally {
      setIsExtracting(false)
    }
  }

  const toggleRecord = (idx: number) => {
    setCheckedIndices((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    if (checkedIndices.size === extractedRecords.length) {
      setCheckedIndices(new Set())
    } else {
      setCheckedIndices(new Set(extractedRecords.map((_, i) => i)))
    }
  }

  const handleSave = async () => {
    const selected = extractedRecords.filter((_, i) => checkedIndices.has(i))
    if (!selected.length) return
    setIsSaving(true)
    setSaveError(null)
    setSaveMessage(null)
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/spares/snip-save`, {
        records: selected,
        source_manual_id: loadedManualId ?? null,
        page_number: loadedPage ?? null,
      })
      setSaveMessage(`${res.data.saved} spare(s) added successfully.`)
      setCheckedIndices(new Set())
      onSaved()
    } catch (err) {
      setSaveError(getApiError(err))
    } finally {
      setIsSaving(false)
    }
  }

  const selectedCount = checkedIndices.size

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950/95 backdrop-blur-sm">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-5 py-3">
        <div className="flex items-center gap-2">
          <Scissors className="h-4 w-4 text-sky-400" />
          <span className="text-sm font-semibold text-white">Snip &amp; Extract Spares</span>
          <span className="text-xs text-slate-500">— Draw a selection box over the table, then extract</span>
        </div>
        <button onClick={onClose} className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Image loader + selection tool */}
        <div className="flex w-[58%] shrink-0 flex-col gap-3 overflow-hidden border-r border-slate-800 p-4">
          {/* Source tabs */}
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => setImageMode('manual')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${imageMode === 'manual' ? 'bg-sky-600 text-white' : 'border border-slate-700 text-slate-400 hover:bg-slate-800'}`}
            >
              Load from Manual
            </button>
            <button
              onClick={() => setImageMode('upload')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${imageMode === 'upload' ? 'bg-sky-600 text-white' : 'border border-slate-700 text-slate-400 hover:bg-slate-800'}`}
            >
              Upload / Paste Screenshot
            </button>
          </div>

          {/* Manual picker */}
          {imageMode === 'manual' && (
            <div className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 p-3">
              <div className="relative flex-1">
                <select
                  value={selectedManualId}
                  onChange={(e) => setSelectedManualId(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-slate-700 bg-slate-800 py-2 pl-3 pr-8 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                >
                  <option value="">Select a manual…</option>
                  {manuals.map((m) => (
                    <option key={m.id} value={m.id}>{m.original_filename}</option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              </div>
              <input
                type="number"
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadPage()}
                placeholder="Page #"
                min={1}
                className="w-20 rounded-lg border border-slate-700 bg-slate-800 px-2 py-2 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
              />
              <button
                onClick={loadPage}
                disabled={!selectedManualId || !pageInput || isLoadingPage}
                className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {isLoadingPage ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Load'}
              </button>
            </div>
          )}

          {/* Upload zone */}
          {imageMode === 'upload' && (
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="shrink-0 rounded-xl border-2 border-dashed border-slate-700 bg-slate-900 p-6 text-center hover:border-sky-700"
            >
              <Upload className="mx-auto mb-2 h-6 w-6 text-slate-500" />
              <p className="text-xs text-slate-400">Drag &amp; drop a screenshot here, or</p>
              <label className="mt-2 inline-block cursor-pointer rounded-lg bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600">
                Browse file
                <input
                  type="file"
                  accept="image/*"
                  className="sr-only"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) handleFileUpload(file)
                  }}
                />
              </label>
              <p className="mt-1 text-[11px] text-slate-600">PNG, JPG, WebP — from Windows Snipping Tool or any source</p>
            </div>
          )}

          {loadError && (
            <div className="shrink-0 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">{loadError}</div>
          )}

          {/* Image display + selection overlay */}
          {displayImageUrl ? (
            <>
              {/* Rotate + hint toolbar */}
              <div className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5">
                <span className="flex-1 text-[11px] text-slate-500">
                  {hasSelection ? 'Selection ready — use Extract Selection or Extract Full Page' : 'Drag to select a table region, then extract'}
                </span>
                <button
                  type="button"
                  onClick={() => handleRotate(-90)}
                  disabled={isRotating}
                  className="rounded border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white disabled:opacity-40"
                  title="Rotate left 90°"
                >
                  {isRotating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={() => handleRotate(90)}
                  disabled={isRotating}
                  className="rounded border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white disabled:opacity-40"
                  title="Rotate right 90°"
                >
                  {isRotating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
                </button>
              </div>

              {/*
                Outer container: scrollable in both axes so wide/tall images
                are fully accessible. The inner wrapper is inline-block so it
                shrinks to exactly the image size — this keeps the overlay and
                selection box perfectly aligned with the visible image.
              */}
              <div className="flex-1 overflow-auto rounded-lg border border-slate-700 bg-slate-900">
                <div className="inline-block min-w-full select-none">
                  <div className="relative inline-block">
                    <img
                      ref={imgRef}
                      src={displayImageUrl}
                      alt="Manual page"
                      draggable={false}
                      className="block bg-white"
                      style={{ userSelect: 'none', pointerEvents: 'none', maxHeight: '100%' }}
                    />
                    {/* Interaction overlay — exactly covers the image */}
                    <div
                      ref={overlayRef}
                      className="absolute inset-0"
                      style={{ cursor: 'crosshair' }}
                      onMouseDown={handleMouseDown}
                      onMouseMove={handleMouseMove}
                      onMouseUp={handleMouseUp}
                      onMouseLeave={handleMouseUp}
                    />
                    {/* Selection rectangle */}
                    {selectionRect && selectionRect.width > 4 && selectionRect.height > 4 && (
                      <div
                        className="pointer-events-none absolute"
                        style={{
                          left: selectionRect.left,
                          top: selectionRect.top,
                          width: selectionRect.width,
                          height: selectionRect.height,
                          border: '2px solid #38bdf8',
                          background: 'rgba(56,189,248,0.08)',
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => handleExtract(false)}
                  disabled={isExtracting || isRotating}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-700 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  {isExtracting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Scissors className="h-3.5 w-3.5" />}
                  Extract Full Page
                </button>
                {hasSelection && (
                  <button
                    onClick={() => handleExtract(true)}
                    disabled={isExtracting || isRotating}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-sky-600 py-2 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                  >
                    {isExtracting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Scissors className="h-3.5 w-3.5" />}
                    Extract Selection
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-800 text-sm text-slate-600">
              {isLoadingPage ? 'Loading page…' : 'Load a page or upload a screenshot to begin'}
            </div>
          )}
        </div>

        {/* Right: Extracted records */}
        <div className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
          <div className="flex shrink-0 items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Extracted Records</h3>
            {extractedRecords.length > 0 && (
              <span className="text-xs text-slate-500">{extractedRecords.length} found</span>
            )}
          </div>

          {extractError && (
            <div className="shrink-0 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">{extractError}</div>
          )}
          {saveError && (
            <div className="shrink-0 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">{saveError}</div>
          )}
          {saveMessage && (
            <div className="flex shrink-0 items-center gap-2 rounded-lg border border-green-900/60 bg-green-950/30 px-3 py-2 text-xs text-green-200">
              <CheckCircle className="h-3.5 w-3.5 shrink-0" />
              {saveMessage}
            </div>
          )}

          {isExtracting && (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-slate-800 text-slate-500">
              <Loader2 className="h-7 w-7 animate-spin text-sky-500" />
              <p className="text-sm">Extracting spare parts with AI…</p>
              <p className="text-xs">This may take 15–30 seconds for dense tables</p>
            </div>
          )}

          {!isExtracting && extractedRecords.length === 0 && (
            <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-800 text-sm text-slate-600">
              {extractError ? 'Extraction failed — check error above' : 'Extract from an image to see results here'}
            </div>
          )}

          {!isExtracting && extractedRecords.length > 0 && (
            <>
              <div className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2">
                <input
                  type="checkbox"
                  checked={checkedIndices.size === extractedRecords.length}
                  onChange={toggleAll}
                  className="h-3.5 w-3.5 rounded"
                />
                <span className="flex-1 text-xs text-slate-400">
                  {selectedCount} of {extractedRecords.length} selected
                </span>
                <button
                  onClick={handleSave}
                  disabled={selectedCount === 0 || isSaving}
                  className="flex items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-50"
                >
                  {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
                  Add {selectedCount > 0 ? `${selectedCount} ` : ''}Spare{selectedCount !== 1 ? 's' : ''}
                </button>
              </div>

              <div className="flex-1 overflow-auto rounded-xl border border-slate-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-[11px] uppercase text-slate-500">
                      <th className="w-8 px-3 py-2"></th>
                      <th className="px-3 py-2">Part Name</th>
                      <th className="px-3 py-2">Part #</th>
                      <th className="px-3 py-2">Pos</th>
                      <th className="px-3 py-2">Drawing #</th>
                      <th className="px-3 py-2">Maker</th>
                      <th className="px-3 py-2">Specification</th>
                      <th className="px-3 py-2">Conf</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {extractedRecords.map((record, idx) => (
                      <tr
                        key={idx}
                        onClick={() => toggleRecord(idx)}
                        className={`cursor-pointer hover:bg-slate-800/50 ${checkedIndices.has(idx) ? 'bg-sky-900/10' : ''}`}
                      >
                        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={checkedIndices.has(idx)}
                            onChange={() => toggleRecord(idx)}
                            className="h-3.5 w-3.5 rounded"
                          />
                        </td>
                        <td className="max-w-[180px] px-3 py-2 font-medium text-slate-200">
                          <div className="truncate" title={record.part_name}>{record.part_name}</div>
                        </td>
                        <td className="px-3 py-2 font-mono text-slate-400">
                          <div className="w-24 truncate" title={record.part_number ?? ''}>{record.part_number ?? '-'}</div>
                        </td>
                        <td className="px-3 py-2 text-slate-400">{record.drawing_position ?? '-'}</td>
                        <td className="px-3 py-2 font-mono text-slate-400">
                          <div className="w-20 truncate" title={record.drawing_number ?? ''}>{record.drawing_number ?? '-'}</div>
                        </td>
                        <td className="px-3 py-2 text-slate-400">
                          <div className="w-24 truncate" title={record.spare_maker ?? ''}>{record.spare_maker ?? '-'}</div>
                        </td>
                        <td className="px-3 py-2 text-slate-400">
                          <div className="max-w-[140px] truncate" title={record.specification ?? ''}>{record.specification ?? '-'}</div>
                        </td>
                        <td className="px-3 py-2">
                          {record.confidence_score != null ? (
                            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                              record.confidence_score >= 80 ? 'bg-green-700 text-green-100'
                              : record.confidence_score >= 60 ? 'bg-amber-700 text-amber-100'
                              : 'bg-red-700 text-red-100'
                            }`}>
                              {record.confidence_score}%
                            </span>
                          ) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default SnipExtractModal

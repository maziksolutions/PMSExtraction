import React, { useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Scissors, Upload, X, Loader2, CheckCircle, ChevronDown, RotateCcw, RotateCw, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, ExternalLink } from 'lucide-react'
import apiClient from '@/api/client'

interface ExtractedRecord {
  job_name: string
  job_code: string | null
  job_description: string | null
  safety_precaution: string | null
  frequency: number | null
  frequency_type: string | null
  is_critical: boolean | null
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

interface SnipExtractJobsModalProps {
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
  zoom: number,
  cropBox?: { x1: number; y1: number; x2: number; y2: number }
): Promise<Blob> {
  const canvas = document.createElement('canvas')
  let sx = 0, sy = 0, sw = imgEl.naturalWidth, sh = imgEl.naturalHeight
  if (cropBox) {
    const rect = imgEl.getBoundingClientRect()
    const unzoomedWidth = (rect.width || 1) / zoom
    const unzoomedHeight = (rect.height || 1) / zoom
    const scaleX = imgEl.naturalWidth / unzoomedWidth
    const scaleY = imgEl.naturalHeight / unzoomedHeight
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

function rotateDataUrl(src: string, degrees: 90 | -90): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new window.Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
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
    img.onerror = (e) => reject(e)
    img.src = src
  })
}

const SnipExtractJobsModal: React.FC<SnipExtractJobsModalProps> = ({ vesselId, onClose, onSaved }) => {
  const [imageMode, setImageMode] = useState<'manual' | 'upload'>('manual')

  // Manual list query
  const { data: manuals = [] } = useQuery<ManualItem[]>({
    queryKey: ['snip-manuals', vesselId],
    queryFn: async () => {
      const res = await apiClient.get(`/vessels/${vesselId}/manuals`, { params: { page_size: 1000 } })
      const items = res.data?.items ?? []
      return items.filter((m: any) =>
        ['pdf', 'png', 'jpg', 'jpeg', 'webp'].includes(m.file_extension?.toLowerCase())
      )
    },
  })

  // Selected Manual/Page details
  const [selectedManualId, setSelectedManualId] = useState<string>('')
  const [pageInput, setPageInput] = useState<string>('1')
  const [loadedManualId, setLoadedManualId] = useState<string | null>(null)
  const [loadedPage, setLoadedPage] = useState<number | null>(null)
  const [isLoadingPage, setIsLoadingPage] = useState(false)
  const [pageLoadError, setPageLoadError] = useState<string | null>(null)

  // Current image state
  const [displayImageUrl, setDisplayImageUrl] = useState<string>('')

  // Crop / Selection tools
  const [zoom, setZoom] = useState<number>(1.0)
  const [rotation, setRotation] = useState<number>(0)
  const [useSelection, setUseSelection] = useState(false)
  const [cropRect, setCropRect] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [startPoint, setStartPoint] = useState<DragPoint>({ x: 0, y: 0 })

  // Extraction outcomes
  const [isExtracting, setIsExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extractedRecords, setExtractedRecords] = useState<ExtractedRecord[]>([])
  const [checkedIndices, setCheckedIndices] = useState<Set<number>>(new Set())

  // Save states
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // Handle manual selection & page loading
  const loadPageWithNum = async (pageNum: number) => {
    if (!selectedManualId) return
    setIsLoadingPage(true)
    setPageLoadError(null)
    setLoadedManualId(null)
    setLoadedPage(null)
    setUseSelection(false)
    setCropRect(null)
    try {
      const res = await apiClient.get(`/vessels/${vesselId}/manuals/${selectedManualId}/pages/${pageNum}/image`)
      if (res.data?.image_url) {
        setDisplayImageUrl(res.data.image_url)
        setLoadedManualId(selectedManualId)
        setLoadedPage(pageNum)
      } else {
        setPageLoadError('Page image not available from server.')
      }
    } catch (err) {
      setPageLoadError(getApiError(err))
    } finally {
      setIsLoadingPage(false)
    }
  }

  const loadPage = () => {
    const pageNum = parseInt(pageInput, 10)
    if (isNaN(pageNum) || pageNum <= 0) return
    loadPageWithNum(pageNum)
  }

  // Handle drag screenshot upload/paste
  const handleImageFile = async (file: File) => {
    setIsLoadingPage(true)
    setPageLoadError(null)
    setLoadedManualId(null)
    setLoadedPage(null)
    setUseSelection(false)
    setCropRect(null)
    try {
      const localUrl = URL.createObjectURL(file)
      const dataUrl = await toDataUrl(localUrl)
      setDisplayImageUrl(dataUrl)
      setPageInput('')
    } catch (err) {
      setPageLoadError('Failed to parse image file: ' + String(err))
    } finally {
      setIsLoadingPage(false)
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile()
        if (file) {
          handleImageFile(file)
          break
        }
      }
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleImageFile(file)
    }
  }

  // Rotation functions
  const handleRotate = async (dir: 'left' | 'right') => {
    if (!displayImageUrl) return
    setIsLoadingPage(true)
    try {
      const deg = dir === 'left' ? -90 : 90
      const rotated = await rotateDataUrl(displayImageUrl, deg)
      setDisplayImageUrl(rotated)
      setCropRect(null)
      setUseSelection(false)
    } catch (err) {
      setPageLoadError('Failed to rotate image: ' + String(err))
    } finally {
      setIsLoadingPage(false)
    }
  }

  // Drag-to-select handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!displayImageUrl || !imgRef.current) return
    const rect = imgRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setIsDrawing(true)
    setStartPoint({ x, y })
    setCropRect({ x1: x, y1: y, x2: x, y2: y })
    setUseSelection(true)
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !imgRef.current) return
    const rect = imgRef.current.getBoundingClientRect()
    const currentX = Math.max(0, Math.min(rect.width, e.clientX - rect.left))
    const currentY = Math.max(0, Math.min(rect.height, e.clientY - rect.top))
    setCropRect({
      x1: Math.min(startPoint.x, currentX),
      y1: Math.min(startPoint.y, currentY),
      x2: Math.max(startPoint.x, currentX),
      y2: Math.max(startPoint.y, currentY),
    })
  }

  const handleMouseUp = () => {
    setIsDrawing(false)
    if (cropRect) {
      const w = cropRect.x2 - cropRect.x1
      const h = cropRect.y2 - cropRect.y1
      if (w < 6 || h < 6) {
        setUseSelection(false)
        setCropRect(null)
      }
    }
  }

  const getCropBox = () => {
    if (!cropRect || !imgRef.current) return undefined
    const rect = imgRef.current.getBoundingClientRect()
    const x1 = cropRect.x1 / zoom
    const y1 = cropRect.y1 / zoom
    const x2 = cropRect.x2 / zoom
    const y2 = cropRect.y2 / zoom
    return { x1, y1, x2, y2 }
  }

  const handleExtract = async () => {
    if (!imgRef.current || !displayImageUrl) return
    setIsExtracting(true)
    setExtractError(null)
    setExtractedRecords([])
    setSaveMessage(null)
    try {
      const cropBox = useSelection ? getCropBox() : undefined
      const blob = await imageElementToBlob(imgRef.current, zoom, cropBox)
      const formData = new FormData()
      formData.append('image', blob, 'page.png')
      if (loadedPage) formData.append('page_number', String(loadedPage))
      const res = await apiClient.post(`/vessels/${vesselId}/jobs/snip-extract`, formData, {
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

  const updateRecord = (idx: number, field: keyof ExtractedRecord, value: any) => {
    setExtractedRecords((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r))
    )
  }

  const handleSave = async () => {
    const selected = extractedRecords.filter((_, i) => checkedIndices.has(i))
    if (!selected.length) return
    setIsSaving(true)
    setSaveError(null)
    setSaveMessage(null)
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/jobs/snip-save`, {
        records: selected,
        source_manual_id: loadedManualId ?? null,
        page_number: loadedPage ?? null,
      })
      setSaveMessage(`${res.data.saved} job(s) added successfully.`)
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
          <span className="text-sm font-semibold text-white">Snip &amp; Extract Jobs</span>
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
              {loadedPage !== null && (
                <button
                  type="button"
                  onClick={() => {
                    const newPage = loadedPage - 1
                    setPageInput(String(newPage))
                    loadPageWithNum(newPage)
                  }}
                  disabled={loadedPage <= 1 || isLoadingPage}
                  className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                  title="Previous page"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
              )}
              <input
                type="number"
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadPage()}
                placeholder="Page #"
                min={1}
                className="w-20 rounded-lg border border-slate-700 bg-slate-800 px-2 py-2 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
              />
              {loadedPage !== null && (
                <button
                  type="button"
                  onClick={() => {
                    const newPage = loadedPage + 1
                    setPageInput(String(newPage))
                    loadPageWithNum(newPage)
                  }}
                  disabled={isLoadingPage}
                  className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                  title="Next page"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                onClick={loadPage}
                disabled={!selectedManualId || isLoadingPage}
                className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {isLoadingPage ? 'Loading...' : 'Go'}
              </button>
              {selectedManualId && (
                <button
                  type="button"
                  onClick={() => {
                    const m = manuals.find(x => x.id === selectedManualId)
                    if (m) {
                      const url = `/vessels/${vesselId}/manual-preview/${m.id}?name=${encodeURIComponent(m.original_filename)}&pages=${pageInput}&mode=snip`
                      window.open(url, '_blank')
                    }
                  }}
                  className="rounded-lg border border-slate-700 p-2 text-sky-400 hover:bg-slate-800"
                  title="Open manual in a new tab"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Screenshot upload */}
          {imageMode === 'upload' && (
            <div
              onPaste={handlePaste}
              className="flex shrink-0 items-center justify-between gap-4 rounded-lg border border-dashed border-slate-700 bg-slate-900/50 p-4"
            >
              <div className="text-left">
                <p className="text-xs font-medium text-slate-300">Paste an image directly (Ctrl+V) or click upload</p>
                <p className="mt-1 text-[11px] text-slate-600">PNG, JPG, WebP — from Windows Snipping Tool or any source</p>
              </div>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700">
                <Upload className="h-3.5 w-3.5" />
                Choose File
                <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" />
              </label>
            </div>
          )}

          {/* Viewport for image manipulation */}
          <div className="relative flex-1 rounded-lg border border-slate-800 bg-slate-950 overflow-hidden flex flex-col">
            {pageLoadError && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/80 p-4 text-center">
                <div className="max-w-md rounded-lg border border-red-900 bg-red-950/50 p-4 text-xs text-red-400">
                  {pageLoadError}
                </div>
              </div>
            )}

            {isLoadingPage && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-950/80 gap-2">
                <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
                <span className="text-xs text-slate-400">Rendering page image...</span>
              </div>
            )}

            {displayImageUrl ? (
              <>
                {/* Control bar */}
                <div className="absolute left-3 top-3 z-10 flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900/90 p-1 backdrop-blur-sm">
                  <button
                    onClick={() => setZoom((z) => Math.max(0.4, z - 0.1))}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                    title="Zoom Out"
                  >
                    <ZoomOut className="h-3.5 w-3.5" />
                  </button>
                  <span className="px-1 text-[10px] font-mono text-slate-300">{Math.round(zoom * 100)}%</span>
                  <button
                    onClick={() => setZoom((z) => Math.min(3.0, z + 0.1))}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                    title="Zoom In"
                  >
                    <ZoomIn className="h-3.5 w-3.5" />
                  </button>
                  <div className="mx-1 h-3.5 w-px bg-slate-800" />
                  <button
                    onClick={() => handleRotate('left')}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                    title="Rotate Left"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleRotate('right')}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                    title="Rotate Right"
                  >
                    <RotateCw className="h-3.5 w-3.5" />
                  </button>
                  <div className="mx-1 h-3.5 w-px bg-slate-800" />
                  <button
                    onClick={() => {
                      setUseSelection(!useSelection)
                      setCropRect(null)
                    }}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors ${useSelection ? 'bg-sky-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}
                  >
                    {useSelection ? 'Deactivate Snip' : 'Activate Snip'}
                  </button>
                </div>

                {/* Scroller wrapper */}
                <div className="flex-1 overflow-auto p-4 select-none" ref={containerRef}>
                  <div
                    className="relative inline-block origin-top-left"
                    style={{
                      width: imgRef.current ? imgRef.current.naturalWidth * zoom : 'auto',
                      height: imgRef.current ? imgRef.current.naturalHeight * zoom : 'auto',
                    }}
                    onMouseDown={useSelection ? handleMouseDown : undefined}
                    onMouseMove={useSelection ? handleMouseMove : undefined}
                    onMouseUp={useSelection ? handleMouseUp : undefined}
                  >
                    <img
                      ref={imgRef}
                      src={displayImageUrl}
                      alt="Manual page"
                      draggable={false}
                      className="max-w-none block"
                      style={{
                        width: 'auto',
                        height: 'auto',
                        transform: `scale(${zoom})`,
                        transformOrigin: '0 0',
                      }}
                    />

                    {/* Crop selection rectangle */}
                    {useSelection && cropRect && (
                      <div
                        className="absolute border border-dashed border-sky-400 bg-sky-500/10 pointer-events-none"
                        style={{
                          left: cropRect.x1,
                          top: cropRect.y1,
                          width: cropRect.x2 - cropRect.x1,
                          height: cropRect.y2 - cropRect.y1,
                        }}
                      />
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-500 p-8 text-center gap-2">
                <Scissors className="h-8 w-8 text-slate-700" />
                <span className="text-xs">No manual page loaded. Select a manual or paste a screenshot above.</span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Extraction Results */}
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-900/40 p-4">
          <div className="flex shrink-0 items-center justify-between pb-3">
            <h3 className="text-xs font-semibold text-slate-300">Extracted Jobs List</h3>
            {displayImageUrl && (
              <button
                onClick={handleExtract}
                disabled={isExtracting || isLoadingPage}
                className="flex items-center gap-1.5 rounded-lg bg-green-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-green-600 disabled:opacity-50"
              >
                {isExtracting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Extracting...
                  </>
                ) : (
                  <>
                    <Scissors className="h-3.5 w-3.5" />
                    {useSelection ? 'Extract Snip' : 'Extract Full Page'}
                  </>
                )}
              </button>
            )}
          </div>

          {extractError && (
            <div className="mb-3 shrink-0 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
              {extractError}
            </div>
          )}

          {saveError && (
            <div className="mb-3 shrink-0 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
              {saveError}
            </div>
          )}

          {saveMessage && (
            <div className="mb-3 shrink-0 flex items-center gap-2 rounded-lg border border-green-950 bg-green-950/40 px-3 py-2 text-xs text-green-400">
              <CheckCircle className="h-4 w-4 text-green-400" />
              {saveMessage}
            </div>
          )}

          {isExtracting && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-2">
              <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
              <span className="text-xs font-medium">Running Claude/OpenAI Vision PMS job parser...</span>
              <span className="text-[11px] text-slate-500">Normally takes 10 to 15 seconds. Please wait.</span>
            </div>
          )}

          {!isExtracting && extractedRecords.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-lg text-slate-500 p-8 text-center">
              <span className="text-xs">No records extracted yet. Adjust the viewport and click Extract.</span>
            </div>
          )}

          {!isExtracting && extractedRecords.length > 0 && (
            <>
              {/* Save toolbar */}
              <div className="flex shrink-0 items-center justify-between border-t border-b border-slate-800 bg-slate-900/80 px-3 py-2 text-xs">
                <span className="text-slate-400 font-medium">
                  {selectedCount} of {extractedRecords.length} job(s) selected
                </span>
                <button
                  onClick={handleSave}
                  disabled={selectedCount === 0 || isSaving}
                  className="flex items-center gap-1.5 rounded bg-sky-600 px-3 py-1 font-semibold text-white hover:bg-sky-500 disabled:opacity-40"
                >
                  {isSaving ? 'Saving...' : 'Add Selected to Jobs'}
                </button>
              </div>

              {/* Records table list */}
              <div className="flex-1 overflow-auto min-h-0 border border-slate-800 rounded-b-lg">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead className="sticky top-0 bg-slate-950 text-slate-400 uppercase text-[9px] tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="px-3 py-2 w-8">
                        <input
                          type="checkbox"
                          checked={checkedIndices.size === extractedRecords.length}
                          onChange={toggleAll}
                          className="h-3.5 w-3.5 rounded"
                        />
                      </th>
                      <th className="px-2 py-2 w-1/3">Job Name</th>
                      <th className="px-2 py-2">Code</th>
                      <th className="px-2 py-2 w-12 text-center">Freq</th>
                      <th className="px-2 py-2 w-16">Unit</th>
                      <th className="px-2 py-2">Procedure / Description</th>
                      <th className="px-2 py-2 w-12 text-center">Crit</th>
                      <th className="px-3 py-2 w-12">Conf</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 bg-slate-950/20">
                    {extractedRecords.map((record, idx) => (
                      <tr
                        key={idx}
                        className={`hover:bg-slate-900/50 ${checkedIndices.has(idx) ? 'bg-sky-950/5' : 'opacity-60'}`}
                      >
                        <td className="px-3 py-1.5">
                          <input
                            type="checkbox"
                            checked={checkedIndices.has(idx)}
                            onChange={() => toggleRecord(idx)}
                            className="h-3.5 w-3.5 rounded"
                          />
                        </td>
                        <td className="px-2 py-1 font-medium text-slate-200">
                          <input
                            value={record.job_name}
                            onChange={(e) => updateRecord(idx, 'job_name', e.target.value)}
                            className="w-full min-w-[120px] rounded border border-transparent bg-transparent px-1 py-0.5 text-xs text-slate-200 hover:border-slate-600 focus:border-sky-500 focus:bg-slate-800 focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1">
                          <input
                            value={record.job_code ?? ''}
                            onChange={(e) => updateRecord(idx, 'job_code', e.target.value)}
                            className="w-16 rounded border border-transparent bg-transparent px-1 py-0.5 font-mono text-xs text-slate-400 hover:border-slate-600 focus:border-sky-500 focus:bg-slate-800 focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1 text-center">
                          <input
                            type="number"
                            value={record.frequency ?? ''}
                            onChange={(e) => updateRecord(idx, 'frequency', e.target.value ? parseInt(e.target.value, 10) : null)}
                            className="w-10 rounded border border-transparent bg-transparent px-1 py-0.5 text-center text-xs text-slate-400 hover:border-slate-600 focus:border-sky-500 focus:bg-slate-800 focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1">
                          <select
                            value={record.frequency_type ?? ''}
                            onChange={(e) => updateRecord(idx, 'frequency_type', e.target.value || null)}
                            className="w-16 rounded border border-transparent bg-transparent px-0.5 py-0.5 text-xs text-slate-400 hover:border-slate-600 focus:border-sky-500 focus:bg-slate-800 focus:outline-none"
                          >
                            <option value="">None</option>
                            <option value="daily">daily</option>
                            <option value="weekly">weekly</option>
                            <option value="monthly">monthly</option>
                            <option value="yearly">yearly</option>
                            <option value="hourly">hourly</option>
                          </select>
                        </td>
                        <td className="px-2 py-1">
                          <textarea
                            value={record.job_description ?? ''}
                            onChange={(e) => updateRecord(idx, 'job_description', e.target.value)}
                            className="w-full min-w-[150px] h-6 rounded border border-transparent bg-transparent px-1 py-0.5 text-xs text-slate-400 hover:border-slate-600 focus:border-sky-500 focus:bg-slate-800 focus:outline-none resize-y"
                          />
                        </td>
                        <td className="px-2 py-1 text-center">
                          <input
                            type="checkbox"
                            checked={!!record.is_critical}
                            onChange={(e) => updateRecord(idx, 'is_critical', e.target.checked)}
                            className="h-3.5 w-3.5 rounded"
                          />
                        </td>
                        <td className="px-3 py-1.5">
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

export default SnipExtractJobsModal

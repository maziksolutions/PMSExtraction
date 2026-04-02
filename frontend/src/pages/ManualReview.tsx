import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle,
  CheckCircle2,
  RefreshCw,
  Save,
  ScanSearch,
  Copy,
  FileText,
  Trash2,
  ChevronDown,
  ChevronRight,
  Download,
  XCircle,
  Upload,
  Zap,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Manual {
  id: string
  original_filename: string
  file_size_bytes: number
  status: string
  category: string | null
  classification_confidence: number | null
  useful_for_extraction: string | null
  pages_with_components: string | null
  pages_with_jobs: string | null
  pages_with_spares: string | null
  pages_with_components_printed: string | null
  pages_with_jobs_printed: string | null
  pages_with_spares_printed: string | null
  pages_with_components_physical: string | null
  pages_with_jobs_physical: string | null
  pages_with_spares_physical: string | null
  page_explanations: string | null
  reviewer_comments: string | null
  supply_type: string | null
  is_duplicate: boolean
  duplicate_of_id: string | null
  blob_storage_key?: string | null
}

interface Gap {
  category: string
  status: string
  message: string
}

interface PreCheckItem {
  id: string
  machinery_name: string
  status: 'found' | 'low_confidence' | 'missing'
  matched_manual?: string
  match_score?: number
  user_acknowledgement?: string
  absence_reason?: string
}

interface PreCheckResult {
  items: PreCheckItem[]
  run_at: string
}

interface ScreeningStatus {
  total: number
  done: number
  status: 'idle' | 'running' | 'completed' | 'failed'
}

interface ExtractionStatus {
  total: number
  done: number
  status: 'idle' | 'running' | 'completed' | 'failed'
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CATEGORIES = [
  'Instruction Manual',
  'Machinery Particulars',
  'General Arrangement',
  'Pipeline Diagrams/P&ID',
  'LSA/FFA Plans',
  'Tank Capacity Plan',
  'Yard/Finished Drawings',
  'Electrical Diagrams',
  'Class Certificates/Surveys',
  'Unknown/Unclassifiable',
]

const ACK_OPTIONS = [
  { value: '', label: '— Select action —' },
  { value: 'upload_pending', label: 'Upload Pending' },
  { value: 'genuinely_absent', label: 'Genuinely Absent' },
  { value: 'not_applicable', label: 'Not Applicable' },
  { value: 'confirmed', label: 'Confirmed' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-500">—</span>
  const color =
    value >= 85 ? 'bg-green-700 text-green-100' :
    value >= 60 ? 'bg-amber-700 text-amber-100' :
    'bg-red-700 text-red-100'
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{value}%</span>
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function parseDownloadFilename(contentDisposition: string | undefined, fallback: string): string {
  if (!contentDisposition) return fallback
  const match = contentDisposition.match(/filename="?([^"]+)"?/)
  return match?.[1] ?? fallback
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

type PageReasonKind = 'components' | 'jobs' | 'spares'

interface PageExplanationEntry {
  printed_page?: number | null
  reference?: string[]
  components?: string[]
  jobs?: string[]
  spares?: string[]
}

function expandPageTokens(value: string | null | undefined): number[] {
  if (!value) return []
  const pages = new Set<number>()
  value.split(',').forEach((token) => {
    const cleaned = token.trim()
    if (!cleaned) return
    if (cleaned.includes('-')) {
      const [startRaw, endRaw] = cleaned.split('-', 2)
      const start = Number(startRaw.trim())
      const end = Number(endRaw.trim())
      if (!Number.isFinite(start) || !Number.isFinite(end)) return
      const from = Math.min(start, end)
      const to = Math.max(start, end)
      for (let page = from; page <= to; page += 1) pages.add(page)
      return
    }
    const page = Number(cleaned)
    if (Number.isFinite(page)) pages.add(page)
  })
  return Array.from(pages).sort((a, b) => a - b)
}

function parsePageExplanations(raw: string | null | undefined): Record<string, PageExplanationEntry> {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw) as Record<string, PageExplanationEntry>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function buildExplanationRows(
  raw: string | null | undefined,
  physicalRefs: string | null | undefined,
  kind: PageReasonKind,
) {
  const explanationMap = parsePageExplanations(raw)
  return expandPageTokens(physicalRefs)
    .map((physicalPage) => {
      const entry = explanationMap[String(physicalPage)] ?? {}
      const reasons = [
        ...(entry.reference ?? []),
        ...(entry[kind] ?? []),
      ]
      return {
        physicalPage,
        printedPage: entry.printed_page ?? null,
        reasons,
      }
    })
    .filter((row) => row.reasons.length > 0)
}

interface PageReferenceEditorProps {
  printedValue: string | null | undefined
  physicalValue: string | null | undefined
  onPrintedChange: (value: string) => void
  onPhysicalChange: (value: string) => void
  explanationRows: Array<{ physicalPage: number; printedPage: number | null; reasons: string[] }>
  printedPlaceholder: string
  physicalPlaceholder: string
}

const PageReferenceEditor: React.FC<PageReferenceEditorProps> = ({
  printedValue,
  physicalValue,
  onPrintedChange,
  onPhysicalChange,
  explanationRows,
  printedPlaceholder,
  physicalPlaceholder,
}) => (
  <div className="min-w-[160px] space-y-1">
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Printed</div>
      <input
        type="text"
        value={printedValue ?? ''}
        onChange={(e) => onPrintedChange(e.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
        placeholder={printedPlaceholder}
      />
    </div>
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Physical</div>
      <input
        type="text"
        value={physicalValue ?? ''}
        onChange={(e) => onPhysicalChange(e.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
        placeholder={physicalPlaceholder}
      />
    </div>
    {explanationRows.length > 0 && (
      <details className="rounded border border-slate-800 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-300">
        <summary className="cursor-pointer select-none text-sky-400">Why selected?</summary>
        <div className="mt-2 space-y-2">
          {explanationRows.map((row) => (
            <div key={row.physicalPage} className="rounded bg-slate-900/80 px-2 py-1.5">
              <div className="font-medium text-slate-200">
                Physical {row.physicalPage}
                {row.printedPage !== null ? ` • Printed ${row.printedPage}` : ' • No printed page'}
              </div>
              <div className="mt-1 space-y-1 text-slate-400">
                {row.reasons.map((reason, index) => (
                  <p key={`${row.physicalPage}-${index}`}>{reason}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </details>
    )}
  </div>
)

// ─── Pre-Check Panel ─────────────────────────────────────────────────────────

const PreCheckPanel: React.FC<{ vesselId: string }> = ({ vesselId }) => {
  const [expanded, setExpanded] = useState(false)
  const [ackOverrides, setAckOverrides] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const { data: result, isLoading } = useQuery<PreCheckResult>({
    queryKey: ['precheck', vesselId],
    queryFn: async () => {
      const res = await apiClient.get(`/vessels/${vesselId}/precheck`)
      return res.data
    },
    enabled: !!vesselId,
  })

  const runMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/vessels/${vesselId}/precheck/run`)
      return res.data as PreCheckResult
    },
    onSuccess: () => {
      setAckOverrides({})
      queryClient.invalidateQueries({ queryKey: ['precheck', vesselId] })
      setExpanded(true)
    },
  })

  const patchMutation = useMutation({
    mutationFn: async ({ itemId, user_acknowledgement, absence_reason }: {
      itemId: string; user_acknowledgement: string; absence_reason?: string
    }) => {
      await apiClient.patch(`/vessels/${vesselId}/precheck/${itemId}`, {
        user_acknowledgement,
        ...(absence_reason !== undefined && { absence_reason }),
      })
    },
    onSuccess: (_data, vars) => {
      setAckOverrides((prev) => ({ ...prev, [vars.itemId]: vars.user_acknowledgement }))
      queryClient.invalidateQueries({ queryKey: ['precheck', vesselId] })
    },
  })

  const items = result?.items ?? []
  const missing = items.filter((i) => i.status === 'missing')
  const found = items.filter((i) => i.status === 'found')
  const lowConf = items.filter((i) => i.status === 'low_confidence')

  const hasMissing = missing.length > 0

  return (
    <div className={`rounded-xl border ${hasMissing ? 'border-red-700 bg-red-900/10' : items.length > 0 ? 'border-emerald-700 bg-emerald-900/10' : 'border-slate-700 bg-slate-900'} overflow-hidden`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="flex items-center gap-2 text-sm font-semibold text-slate-200 hover:text-white"
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Instruction Manual Pre-Check
          {items.length > 0 && (
            <span className="flex items-center gap-2 ml-2">
              {found.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-900 text-emerald-300 border border-emerald-700">
                  {found.length} found
                </span>
              )}
              {lowConf.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900 text-amber-300 border border-amber-700">
                  {lowConf.length} low confidence
                </span>
              )}
              {missing.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300 border border-red-700">
                  {missing.length} missing
                </span>
              )}
            </span>
          )}
        </button>
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="flex items-center gap-2 rounded-lg bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {runMutation.isPending ? <RefreshCw className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {runMutation.isPending ? 'Running...' : 'Run Pre-Check'}
        </button>
      </div>

      {/* Results table */}
      {expanded && items.length > 0 && (
        <div className="border-t border-slate-700 overflow-x-auto">
          {result?.run_at && (
            <p className="px-4 py-2 text-xs text-slate-500">
              Last run: {new Date(result.run_at).toLocaleString()}
            </p>
          )}
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-900/50 text-slate-400 uppercase">
                <th className="px-4 py-2 text-left font-medium">Machinery</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
                <th className="px-4 py-2 text-left font-medium">Matched Manual</th>
                <th className="px-4 py-2 text-left font-medium">Score</th>
                <th className="px-4 py-2 text-left font-medium">Acknowledgement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {items.map((item) => (
                <tr key={item.id} className={`${item.status === 'missing' ? 'bg-red-900/10' : item.status === 'low_confidence' ? 'bg-amber-900/10' : ''}`}>
                  <td className="px-4 py-2 text-slate-200 font-medium">{item.machinery_name}</td>
                  <td className="px-4 py-2">
                    {item.status === 'found' ? (
                      <span className="inline-flex items-center gap-1 text-emerald-400"><CheckCircle className="h-3 w-3" />Found</span>
                    ) : item.status === 'low_confidence' ? (
                      <span className="inline-flex items-center gap-1 text-amber-400"><AlertTriangle className="h-3 w-3" />Low Confidence</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-400"><XCircle className="h-3 w-3" />Missing</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-400">{item.matched_manual ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-400">
                    {item.match_score != null ? `${Math.round(item.match_score * 100)}%` : '—'}
                  </td>
                  <td className="px-4 py-2">
                    {item.status === 'found' ? (
                      <span className="text-emerald-400">No action needed</span>
                    ) : (
                      <div className="space-y-1">
                        <select
                          value={ackOverrides[item.id] ?? item.user_acknowledgement ?? ''}
                          onChange={(e) => {
                            const val = e.target.value
                            setAckOverrides((p) => ({ ...p, [item.id]: val }))
                            if (val !== 'genuinely_absent') {
                              patchMutation.mutate({ itemId: item.id, user_acknowledgement: val })
                            }
                          }}
                          disabled={patchMutation.isPending}
                          className="px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-xs focus:outline-none focus:border-sky-500 w-44"
                        >
                          {ACK_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                        {(ackOverrides[item.id] ?? item.user_acknowledgement) === 'genuinely_absent' && (
                          <input
                            type="text"
                            placeholder="Reason..."
                            defaultValue={item.absence_reason ?? ''}
                            onBlur={(e) => patchMutation.mutate({
                              itemId: item.id,
                              user_acknowledgement: 'genuinely_absent',
                              absence_reason: e.target.value,
                            })}
                            className="w-44 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-xs focus:outline-none focus:border-sky-500"
                          />
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {expanded && items.length === 0 && !isLoading && (
        <div className="border-t border-slate-700 px-4 py-6 text-center text-slate-500 text-sm">
          Click "Run Pre-Check" to check which machinery instruction manuals are present.
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const ManualReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()
  const importFileInputRef = useRef<HTMLInputElement>(null)

  const [filterCategory, setFilterCategory] = useState('')
  const [filterConfidence, setFilterConfidence] = useState('')
  const [filterFilename, setFilterFilename] = useState('')
  const [filterUseful, setFilterUseful] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [sortBy, setSortBy] = useState('filename')
  const [sortOrder, setSortOrder] = useState('asc')
  const [edits, setEdits] = useState<Record<string, Partial<Manual>>>({})
  const [screeningPolling, setScreeningPolling] = useState(false)
  const [extractionPolling, setExtractionPolling] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  // ── Data queries ──────────────────────────────────────────────────────────

  // Reset to page 1 when filters or sort changes
  useEffect(() => {
    setPage(1)
  }, [filterCategory, filterConfidence, filterFilename, filterUseful, sortBy, sortOrder, pageSize])

  const { data, isLoading } = useQuery({
    queryKey: ['manuals', vesselId, filterCategory, filterConfidence, filterFilename, filterUseful, page, pageSize, sortBy, sortOrder],
    queryFn: () => {
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (filterCategory) params.category = filterCategory
      if (filterConfidence) params.min_confidence = filterConfidence
      if (filterFilename) params.search = filterFilename
      if (filterUseful) params.useful_for_extraction = filterUseful
      return apiClient
        .get(`/vessels/${vesselId}/manuals`, { params })
        .then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const { data: missingReport } = useQuery({
    queryKey: ['missing-report', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/manuals/missing-report`).then((r) => r.data),
    enabled: !!vesselId,
  })

  // ── Screening ─────────────────────────────────────────────────────────────

  const { data: screeningData } = useQuery<ScreeningStatus>({
    queryKey: ['screening-status', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/manuals/screening-status`).then((r) => r.data),
    // Always fetch once on mount so we can detect if screening is already running
    enabled: !!vesselId,
    refetchInterval: screeningPolling ? 1500 : false,
  })

  useEffect(() => {
    if (!screeningData) return
    if (screeningData.status === 'running') {
      // Auto-start polling if the server is already screening (e.g. after page reload)
      setScreeningPolling(true)
    }
    if (screeningData.status === 'completed' || screeningData.status === 'failed') {
      setScreeningPolling(false)
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
    }
  }, [screeningData?.status, vesselId, queryClient])

  const [screenMessage, setScreenMessage] = useState<string | null>(null)

  const screenAllMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/manuals/screen-all`).then((r) => r.data),
    onSuccess: (data) => {
      if (data.started) {
        setScreenMessage(null)
        setScreeningPolling(true)
      } else {
        setScreenMessage(data.message ?? 'No manuals to screen.')
        queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      }
    },
    onError: () => setScreenMessage('Screen All failed — check server logs.'),
  })

  // ── Extraction ────────────────────────────────────────────────────────────

  const { data: extractionData } = useQuery<ExtractionStatus>({
    queryKey: ['extraction-status', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/extraction-status`).then((r) => r.data),
    enabled: !!vesselId && extractionPolling,
    refetchInterval: extractionPolling ? 2000 : false,
  })

  useEffect(() => {
    if (extractionData?.status === 'completed' || extractionData?.status === 'failed') {
      setExtractionPolling(false)
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
    }
  }, [extractionData?.status, vesselId, queryClient])

  const extractAllMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/extract-all`).then((r) => r.data),
    onSuccess: (data) => {
      if (data.started) setExtractionPolling(true)
    },
  })

  const screenSelectedMutation = useMutation({
    mutationFn: () =>
      apiClient
        .post(`/vessels/${vesselId}/manuals/screen-selected`, { manual_ids: Array.from(selectedIds) })
        .then((r) => r.data),
    onSuccess: (data) => {
      if (data.started) setScreeningPolling(true)
    },
  })

  const extractSelectedMutation = useMutation({
    mutationFn: () =>
      apiClient
        .post(`/vessels/${vesselId}/manuals/extract-selected`, { manual_ids: Array.from(selectedIds) })
        .then((r) => r.data),
    onSuccess: (data) => {
      if (data.started) setExtractionPolling(true)
    },
  })

  // ── Editing / saving ──────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: ({ manualId, data }: { manualId: string; data: Partial<Manual> }) =>
      apiClient.patch(`/vessels/${vesselId}/manuals/${manualId}`, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      setEdits({})
    },
  })

  const exportScreeningMutation = useMutation({
    mutationFn: () =>
      apiClient.get(`/vessels/${vesselId}/manuals/export-screening`, {
        params: {
          ...(filterCategory ? { category: filterCategory } : {}),
          ...(filterConfidence ? { min_confidence: Number(filterConfidence) } : {}),
          ...(filterFilename ? { search: filterFilename } : {}),
          ...(filterUseful ? { useful_for_extraction: filterUseful } : {}),
          sort_by: sortBy,
          sort_order: sortOrder,
        },
        responseType: 'blob',
      }),
    onSuccess: (response) => {
      const filename = parseDownloadFilename(
        response.headers['content-disposition'],
        'manual_review_export.xlsx',
      )
      triggerBlobDownload(response.data, filename)
      setImportError(null)
    },
    onError: () => {
      setImportError('Export failed. Please try again or check server logs.')
    },
  })

  const downloadTemplateMutation = useMutation({
    mutationFn: () =>
      apiClient.get(`/vessels/${vesselId}/manuals/screening-template`, {
        responseType: 'blob',
      }),
    onSuccess: (response) => {
      const filename = parseDownloadFilename(
        response.headers['content-disposition'],
        'manual_review_template.xlsx',
      )
      triggerBlobDownload(response.data, filename)
      setImportError(null)
    },
    onError: () => {
      setImportError('Template download failed. Please try again.')
    },
  })

  const importScreeningMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await apiClient.post(`/vessels/${vesselId}/manuals/import-screening`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data as { message: string; updated: number; skipped: number; errors?: string[] }
    },
    onSuccess: (data) => {
      setImportMessage(data.message)
      setImportError(data.errors?.length ? data.errors.join(' | ') : null)
      setEdits({})
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail
      setImportError(detail ?? 'Import failed. Please check the Excel format and try again.')
      setImportMessage(null)
    },
  })

  const triggerClassificationMutation = useMutation({
    mutationFn: (manualId: string) =>
      apiClient.post(`/vessels/${vesselId}/manuals/${manualId}/trigger-classification`).then((r) => r.data),
  })

  // ── Delete ────────────────────────────────────────────────────────────────

  const deleteMutation = useMutation({
    mutationFn: (manualId: string) =>
      apiClient.delete(`/vessels/${vesselId}/manuals/${manualId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const handleDeleteSelected = useCallback(async () => {
    if (!window.confirm(`Delete ${selectedIds.size} manual(s)? This cannot be undone.`)) return
    for (const id of Array.from(selectedIds)) {
      await deleteMutation.mutateAsync(id)
    }
  }, [selectedIds, deleteMutation])

  // ── Edit helpers ──────────────────────────────────────────────────────────

  const handleEdit = useCallback((manualId: string, field: keyof Manual, value: string) => {
    setEdits((prev) => ({ ...prev, [manualId]: { ...prev[manualId], [field]: value } }))
  }, [])

  const handleSaveAll = useCallback(() => {
    Object.entries(edits).forEach(([manualId, changes]) => {
      saveMutation.mutate({ manualId, data: changes })
    })
  }, [edits, saveMutation])

  const handleImportExcel = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!window.confirm('Import this screening Excel and overwrite the current screening values for matched manuals?')) {
      return
    }
    setImportMessage(null)
    setImportError(null)
    importScreeningMutation.mutate(file)
  }, [importScreeningMutation])

  // ── Selection ─────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    const pageIds = manuals.map((m) => m.id)
    const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id))
    if (allPageSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        pageIds.forEach((id) => next.delete(id))
        return next
      })
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        pageIds.forEach((id) => next.add(id))
        return next
      })
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const isScreening = screeningPolling || screenAllMutation.isPending
  const isExtracting = extractionPolling || extractAllMutation.isPending || extractSelectedMutation.isPending
  const screeningProgress = screeningData && screeningData.total > 0
    ? Math.round((screeningData.done / screeningData.total) * 100) : 0
  const extractionProgress = extractionData && extractionData.total > 0
    ? Math.round((extractionData.done / extractionData.total) * 100) : 0

  const manuals: Manual[] = data?.items ?? []
  const total: number = data?.total ?? 0
  const gaps: Gap[] = missingReport?.gaps ?? []

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Manual Review</h1>
          <p className="mt-1 text-sm text-slate-400">
            Review classifications, run screening, and extract data using Claude AI.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {Object.keys(edits).length > 0 && (
            <button
              onClick={handleSaveAll}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              Save {Object.keys(edits).length}
            </button>
          )}
          <input
            ref={importFileInputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={handleImportExcel}
          />
          <button
            onClick={() => exportScreeningMutation.mutate()}
            disabled={exportScreeningMutation.isPending}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            {exportScreeningMutation.isPending ? 'Exporting...' : 'Export Screening'}
          </button>
          <button
            onClick={() => downloadTemplateMutation.mutate()}
            disabled={downloadTemplateMutation.isPending}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            <FileText className="h-4 w-4" />
            {downloadTemplateMutation.isPending ? 'Preparing...' : 'Template'}
          </button>
          <button
            onClick={() => importFileInputRef.current?.click()}
            disabled={importScreeningMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {importScreeningMutation.isPending ? 'Importing...' : 'Import Screening'}
          </button>
          {selectedIds.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete {selectedIds.size}
            </button>
          )}
          <button
            onClick={() => extractAllMutation.mutate()}
            disabled={isExtracting}
            className="flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-60"
          >
            {isExtracting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            {isExtracting ? `Extracting ${extractionData?.done ?? 0}/${extractionData?.total ?? '...'}` : 'Extract All'}
          </button>
          {selectedIds.size > 0 && (
            <button
              onClick={() => extractSelectedMutation.mutate()}
              disabled={isExtracting || extractSelectedMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              <Zap className="h-4 w-4" />
              Extract Selected ({selectedIds.size})
            </button>
          )}
          <button
            onClick={() => screenAllMutation.mutate()}
            disabled={isScreening}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
          >
            {isScreening ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            {isScreening ? `Screening ${screeningData?.done ?? 0}/${screeningData?.total ?? '...'}` : 'Screen All'}
          </button>
          {selectedIds.size > 0 && (
            <button
              onClick={() => screenSelectedMutation.mutate()}
              disabled={isScreening || screenSelectedMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-60"
            >
              <ScanSearch className="h-4 w-4" />
              Screen Selected ({selectedIds.size})
            </button>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-amber-700 bg-amber-900/20 px-4 py-3 text-sm text-amber-200">
        Export the current review list to Excel, update it offline, then import it back. Import overwrites the current screening values for matched manuals, so the imported refs take priority over auto-screening.
      </div>

      {importMessage && (
        <div className="rounded-xl border border-emerald-700 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-300">
          {importMessage}
        </div>
      )}

      {importError && (
        <div className="rounded-xl border border-red-700 bg-red-900/20 px-4 py-3 text-sm text-red-300">
          {importError}
        </div>
      )}

      {/* Pre-Check panel — inline */}
      <PreCheckPanel vesselId={vesselId!} />

      {/* Screen All message banner */}
      {screenMessage && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-300">
          <span>{screenMessage}</span>
          <button onClick={() => setScreenMessage(null)} className="text-slate-500 hover:text-slate-300 text-xs">✕</button>
        </div>
      )}

      {/* Screening complete banner */}
      {!isScreening && screeningData?.status === 'completed' && (
        <div className="flex items-center gap-2 rounded-xl border border-violet-700 bg-violet-900/20 px-4 py-3 text-sm text-violet-300">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          Screening complete — {screeningData.total} manual{screeningData.total !== 1 ? 's' : ''} classified. Review the categories below, then run Extract Selected on instruction manuals.
        </div>
      )}

      {/* Extraction complete banner */}
      {!isExtracting && extractionData?.status === 'completed' && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-700 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-400">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          Extraction complete — {extractionData.total} manual{extractionData.total !== 1 ? 's' : ''} processed. Check Components, Jobs &amp; Spares pages.
        </div>
      )}

      {/* Screening progress bar */}
      {isScreening && screeningData && screeningData.total > 0 && (
        <div className="rounded-xl border border-violet-700 bg-violet-900/20 p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-violet-300">Screening manuals... {screeningData.done} / {screeningData.total}</span>
            <span className="text-violet-400">{screeningProgress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div className="h-2 rounded-full bg-violet-500 transition-all duration-500" style={{ width: `${screeningProgress}%` }} />
          </div>
        </div>
      )}

      {/* Extraction progress bar */}
      {isExtracting && extractionData && extractionData.total > 0 && (
        <div className="rounded-xl border border-emerald-700 bg-emerald-900/20 p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-emerald-300">
              Extracting with Claude AI... {extractionData.done} / {extractionData.total} manuals
            </span>
            <span className="text-emerald-400">{extractionProgress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div className="h-2 rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${extractionProgress}%` }} />
          </div>
        </div>
      )}

      {/* Missing category gaps */}
      {gaps.length > 0 && (
        <div className="rounded-xl border border-amber-700 bg-amber-900/20 p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <h2 className="text-sm font-semibold text-amber-300">Missing Document Categories ({gaps.length})</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {gaps.map((g) => (
              <span key={g.category} className="rounded-full bg-amber-800/50 px-3 py-1 text-xs text-amber-200">
                {g.category}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter + Sort bar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={filterFilename}
          onChange={(e) => setFilterFilename(e.target.value)}
          placeholder="Search filename..."
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={filterUseful}
          onChange={(e) => setFilterUseful(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">All (Useful)</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
          <option value="partial">Partial</option>
        </select>
        <select
          value={filterConfidence}
          onChange={(e) => setFilterConfidence(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">Any Confidence</option>
          <option value="85">≥85%</option>
          <option value="60">≥60%</option>
          <option value="40">≥40%</option>
        </select>
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
          <span>Sort:</span>
          <select
            value={`${sortBy}:${sortOrder}`}
            onChange={(e) => { const [sb, so] = e.target.value.split(':'); setSortBy(sb); setSortOrder(so) }}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="filename:asc">Filename A-Z</option>
            <option value="filename:desc">Filename Z-A</option>
            <option value="created_at:desc">Date (newest)</option>
            <option value="created_at:asc">Date (oldest)</option>
            <option value="confidence:desc">Confidence (high)</option>
            <option value="confidence:asc">Confidence (low)</option>
          </select>
        </div>
        {(filterCategory || filterConfidence || filterFilename || filterUseful) && (
          <button
            onClick={() => { setFilterCategory(''); setFilterConfidence(''); setFilterFilename(''); setFilterUseful('') }}
            className="rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Manuals table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        {isLoading ? (
          <div className="py-16 text-center text-slate-500">Loading manuals...</div>
        ) : manuals.length === 0 ? (
          <div className="py-16 text-center text-slate-500">No manuals found. Upload files from the Ingestion page.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
                <th className="px-3 py-3">
                  <input
                    type="checkbox"
                    checked={manuals.length > 0 && manuals.every((m) => selectedIds.has(m.id))}
                    onChange={toggleSelectAll}
                    className="rounded border-slate-600"
                  />
                </th>
                <th className="px-3 py-3">File Name</th>
                <th className="px-3 py-3">Size</th>
                <th className="px-3 py-3">Category</th>
                <th className="px-3 py-3">Useful</th>
                <th className="px-3 py-3">Comp. Ref</th>
                <th className="px-3 py-3">Job Ref</th>
                <th className="px-3 py-3">Spare Ref</th>
                <th className="px-3 py-3">Source</th>
                <th className="px-3 py-3">Confidence</th>
                <th className="px-3 py-3">Comments</th>
                <th className="px-3 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {manuals.map((m) => {
                const edit = edits[m.id] ?? {}
                const changed = Object.keys(edit).length > 0
                const isSelected = selectedIds.has(m.id)
                const componentExplanationRows = buildExplanationRows(
                  m.page_explanations,
                  (edit.pages_with_components_physical as string | undefined) ?? m.pages_with_components_physical,
                  'components',
                )
                const jobExplanationRows = buildExplanationRows(
                  m.page_explanations,
                  (edit.pages_with_jobs_physical as string | undefined) ?? m.pages_with_jobs_physical,
                  'jobs',
                )
                const spareExplanationRows = buildExplanationRows(
                  m.page_explanations,
                  (edit.pages_with_spares_physical as string | undefined) ?? m.pages_with_spares_physical,
                  'spares',
                )
                return (
                  <tr
                    key={m.id}
                    className={`transition-colors hover:bg-slate-800/50 ${changed ? 'bg-sky-900/10' : ''} ${isSelected ? 'bg-slate-700/30' : ''}`}
                  >
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(m.id)}
                        className="rounded border-slate-600"
                      />
                    </td>
                    <td className="px-3 py-3 max-w-xs">
                      <button
                        onClick={async () => {
                          const token = useAuthStore.getState().accessToken
                          const base = (apiClient.defaults.baseURL ?? '/api/v1').replace(/\/$/, '')
                          const url = `${base}/vessels/${vesselId}/manuals/${m.id}/view`
                          try {
                            const resp = await fetch(url, {
                              headers: { Authorization: `Bearer ${token}` },
                              signal: AbortSignal.timeout(120_000),
                            })
                            if (!resp.ok) {
                              const errData = await resp.json().catch(() => null)
                              const msg = errData?.detail ?? `Server error ${resp.status}`
                              alert(`Could not open file:\n${msg}`)
                              return
                            }
                            const ct = resp.headers.get('content-type') ?? ''
                            if (ct.includes('application/json')) {
                              // Azure SAS redirect
                              const json = await resp.json() as { url: string }
                              window.open(json.url, '_blank')
                            } else {
                              // Binary stream (MinIO) — create a blob URL
                              const blob = await resp.blob()
                              const blobUrl = URL.createObjectURL(blob)
                              const win = window.open(blobUrl, '_blank')
                              setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
                              if (!win) alert('Please allow popups for this site to view files.')
                            }
                          } catch (err: any) {
                            alert(`Could not open file:\n${err?.message ?? 'Network error'}`)
                          }
                        }}
                        className="flex items-center gap-1.5 text-left hover:text-sky-400 transition-colors group"
                        title="Click to view PDF"
                      >
                        <FileText className="h-4 w-4 text-slate-500 group-hover:text-sky-400 shrink-0" />
                        <span className="font-medium text-slate-200 group-hover:text-sky-400 truncate max-w-[200px]">
                          {m.original_filename}
                        </span>
                      </button>
                      {m.is_duplicate && (
                        <span className="inline-flex items-center gap-1 mt-0.5 rounded-full bg-amber-800/50 px-2 py-0.5 text-xs text-amber-300">
                          <Copy className="h-3 w-3" />
                          Duplicate
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-slate-400 whitespace-nowrap">{formatBytes(m.file_size_bytes)}</td>
                    <td className="px-3 py-3">
                      <select
                        value={edit.category ?? m.category ?? ''}
                        onChange={(e) => handleEdit(m.id, 'category', e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">—</option>
                        {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={edit.useful_for_extraction ?? m.useful_for_extraction ?? ''}
                        onChange={(e) => handleEdit(m.id, 'useful_for_extraction', e.target.value)}
                        className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">—</option>
                        <option value="yes">Yes</option>
                        <option value="partial">Partial</option>
                        <option value="no">No</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <PageReferenceEditor
                        printedValue={(edit.pages_with_components_printed as string | undefined) ?? m.pages_with_components_printed}
                        physicalValue={(edit.pages_with_components_physical as string | undefined) ?? m.pages_with_components_physical}
                        onPrintedChange={(value) => handleEdit(m.id, 'pages_with_components_printed', value)}
                        onPhysicalChange={(value) => handleEdit(m.id, 'pages_with_components_physical', value)}
                        explanationRows={componentExplanationRows}
                        printedPlaceholder=""
                        physicalPlaceholder=""
                      />
                    </td>
                    <td className="px-3 py-3">
                      <PageReferenceEditor
                        printedValue={(edit.pages_with_jobs_printed as string | undefined) ?? m.pages_with_jobs_printed}
                        physicalValue={(edit.pages_with_jobs_physical as string | undefined) ?? m.pages_with_jobs_physical}
                        onPrintedChange={(value) => handleEdit(m.id, 'pages_with_jobs_printed', value)}
                        onPhysicalChange={(value) => handleEdit(m.id, 'pages_with_jobs_physical', value)}
                        explanationRows={jobExplanationRows}
                        printedPlaceholder=""
                        physicalPlaceholder=""
                      />
                    </td>
                    <td className="px-3 py-3">
                      <PageReferenceEditor
                        printedValue={(edit.pages_with_spares_printed as string | undefined) ?? m.pages_with_spares_printed}
                        physicalValue={(edit.pages_with_spares_physical as string | undefined) ?? m.pages_with_spares_physical}
                        onPrintedChange={(value) => handleEdit(m.id, 'pages_with_spares_printed', value)}
                        onPhysicalChange={(value) => handleEdit(m.id, 'pages_with_spares_physical', value)}
                        explanationRows={spareExplanationRows}
                        printedPlaceholder=""
                        physicalPlaceholder=""
                      />
                    </td>
                    <td className="px-3 py-3">
                      {(() => {
                        const supplyVal = edit.supply_type ?? m.supply_type ?? 'OEM'
                        return (
                          <select
                            value={supplyVal}
                            onChange={(e) => handleEdit(m.id, 'supply_type', e.target.value)}
                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs focus:border-sky-500 focus:outline-none"
                            style={{ color: supplyVal === 'yard_supply' ? '#fbbf24' : '#86efac' }}
                          >
                            <option value="OEM">OEM</option>
                            <option value="yard_supply">Yard Supply</option>
                          </select>
                        )
                      })()}
                    </td>
                    <td className="px-3 py-3">
                      <ConfidenceBadge value={m.classification_confidence} />
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        value={edit.reviewer_comments ?? m.reviewer_comments ?? ''}
                        onChange={(e) => handleEdit(m.id, 'reviewer_comments', e.target.value)}
                        className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="Comment..."
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1">
                        {changed && (
                          <button
                            onClick={() => saveMutation.mutate({ manualId: m.id, data: edit })}
                            className="rounded bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-500"
                            title="Save"
                          >
                            <Save className="h-3 w-3" />
                          </button>
                        )}
                        <button
                          onClick={() => triggerClassificationMutation.mutate(m.id)}
                          className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                          title="Re-classify"
                        >
                          <RefreshCw className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Delete "${m.original_filename}"?`)) {
                              deleteMutation.mutate(m.id)
                            }
                          }}
                          className="rounded bg-red-900/50 px-2 py-1 text-xs text-red-400 hover:bg-red-800"
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination controls */}
      {total > 0 && (
        <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-400">
          <span>
            Showing {Math.min((page - 1) * pageSize + 1, total)}–{Math.min(page * pageSize, total)} of {total} manuals
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-xs">Page {page} / {Math.ceil(total / pageSize) || 1}</span>
            <button
              onClick={() => setPage((p) => Math.min(Math.ceil(total / pageSize), p + 1))}
              disabled={page >= Math.ceil(total / pageSize)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40"
            >
              Next
            </button>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value={100}>100 / page</option>
              <option value={200}>200 / page</option>
              <option value={500}>500 / page</option>
              <option value={1000}>1000 / page</option>
            </select>
          </div>
        </div>
      )}
    </div>
  )
}

export default ManualReview

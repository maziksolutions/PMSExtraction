import React, { useState, useCallback, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle,
  CheckCircle2,
  RefreshCw,
  Save,
  Filter,
  ScanSearch,
  Copy,
  FileText,
  Trash2,
  ChevronDown,
  ChevronRight,
  XCircle,
  Zap,
} from 'lucide-react'
import apiClient from '@/api/client'

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
  reviewer_comments: string | null
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

  const [filterCategory, setFilterCategory] = useState('')
  const [filterConfidence, setFilterConfidence] = useState('')
  const [edits, setEdits] = useState<Record<string, Partial<Manual>>>({})
  const [screeningPolling, setScreeningPolling] = useState(false)
  const [extractionPolling, setExtractionPolling] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // ── Data queries ──────────────────────────────────────────────────────────

  const { data, isLoading } = useQuery({
    queryKey: ['manuals', vesselId, filterCategory, filterConfidence],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterCategory) params.category = filterCategory
      if (filterConfidence) params.min_confidence = filterConfidence
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
    enabled: !!vesselId && screeningPolling,
    refetchInterval: screeningPolling ? 1500 : false,
  })

  useEffect(() => {
    if (screeningData?.status === 'completed' || screeningData?.status === 'failed') {
      setScreeningPolling(false)
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
    }
  }, [screeningData?.status, vesselId, queryClient])

  const screenAllMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/manuals/screen-all`).then((r) => r.data),
    onSuccess: (data) => {
      if (data.started) setScreeningPolling(true)
      else queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
    },
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

  // ── Editing / saving ──────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: ({ manualId, data }: { manualId: string; data: Partial<Manual> }) =>
      apiClient.patch(`/vessels/${vesselId}/manuals/${manualId}`, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      setEdits({})
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

  // ── Selection ─────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === manuals.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(manuals.map((m) => m.id)))
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const isScreening = screeningPolling || screenAllMutation.isPending
  const isExtracting = extractionPolling || extractAllMutation.isPending
  const screeningProgress = screeningData && screeningData.total > 0
    ? Math.round((screeningData.done / screeningData.total) * 100) : 0
  const extractionProgress = extractionData && extractionData.total > 0
    ? Math.round((extractionData.done / extractionData.total) * 100) : 0

  const manuals: Manual[] = data?.items ?? []
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
          <button
            onClick={() => screenAllMutation.mutate()}
            disabled={isScreening}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
          >
            {isScreening ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            {isScreening ? `Screening ${screeningData?.done ?? 0}/${screeningData?.total ?? '...'}` : 'Screen All'}
          </button>
        </div>
      </div>

      {/* Pre-Check panel — inline */}
      <PreCheckPanel vesselId={vesselId!} />

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

      {/* Filter bar */}
      <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
        <Filter className="h-4 w-4 text-slate-400" />
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={filterConfidence}
          onChange={(e) => setFilterConfidence(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">All Confidence</option>
          <option value="85">High (≥85%)</option>
          <option value="60">Medium (≥60%)</option>
        </select>
        {(filterCategory || filterConfidence) && (
          <button
            onClick={() => { setFilterCategory(''); setFilterConfidence('') }}
            className="text-xs text-slate-400 underline hover:text-slate-200"
          >
            Clear
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
                    checked={selectedIds.size === manuals.length && manuals.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded border-slate-600"
                  />
                </th>
                <th className="px-3 py-3">File Name</th>
                <th className="px-3 py-3">Size</th>
                <th className="px-3 py-3">Category</th>
                <th className="px-3 py-3">Useful</th>
                <th className="px-3 py-3">Comp. Pages</th>
                <th className="px-3 py-3">Job Pages</th>
                <th className="px-3 py-3">Spare Pages</th>
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
                const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'
                const viewUrl = `${apiBase}/vessels/${vesselId}/manuals/${m.id}/view`

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
                        onClick={() => window.open(viewUrl, '_blank')}
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
                        <option value="Yes">Yes</option>
                        <option value="Reference">Ref</option>
                        <option value="No">No</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_components ?? m.pages_with_components ?? ''}
                        onChange={(e) => handleEdit(m.id, 'pages_with_components', e.target.value)}
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="1-50"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_jobs ?? m.pages_with_jobs ?? ''}
                        onChange={(e) => handleEdit(m.id, 'pages_with_jobs', e.target.value)}
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="51-80"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_spares ?? m.pages_with_spares ?? ''}
                        onChange={(e) => handleEdit(m.id, 'pages_with_spares', e.target.value)}
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="81-120"
                      />
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
    </div>
  )
}

export default ManualReview

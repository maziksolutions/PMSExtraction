import React, { useState, useCallback, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Save,
  Filter,
  ScanSearch,
  CheckCircle2,
} from 'lucide-react'
import apiClient from '@/api/client'

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
}

interface Gap {
  category: string
  status: string
  message: string
}

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

function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-500">—</span>
  const color =
    value >= 85
      ? 'bg-green-700 text-green-100'
      : value >= 60
      ? 'bg-amber-700 text-amber-100'
      : 'bg-red-700 text-red-100'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {value}%
    </span>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface ScreeningStatus {
  total: number
  done: number
  status: 'idle' | 'running' | 'completed' | 'failed'
}

const ManualReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterCategory, setFilterCategory] = useState('')
  const [filterConfidence, setFilterConfidence] = useState('')
  const [edits, setEdits] = useState<Record<string, Partial<Manual>>>({})
  const [screeningPolling, setScreeningPolling] = useState(false)

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
      apiClient
        .post(`/vessels/${vesselId}/manuals/${manualId}/trigger-classification`)
        .then((r) => r.data),
  })

  // Screening status poll
  const { data: screeningData } = useQuery<ScreeningStatus>({
    queryKey: ['screening-status', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/manuals/screening-status`).then((r) => r.data),
    enabled: !!vesselId && screeningPolling,
    refetchInterval: screeningPolling ? 1500 : false,
  })

  // Stop polling when done
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
      if (data.started) {
        setScreeningPolling(true)
      } else {
        queryClient.invalidateQueries({ queryKey: ['manuals', vesselId] })
      }
    },
  })

  const isScreening = screeningPolling || screenAllMutation.isPending
  const screeningProgress =
    screeningData && screeningData.total > 0
      ? Math.round((screeningData.done / screeningData.total) * 100)
      : 0

  const handleEdit = useCallback(
    (manualId: string, field: keyof Manual, value: string) => {
      setEdits((prev) => ({
        ...prev,
        [manualId]: { ...prev[manualId], [field]: value },
      }))
    },
    []
  )

  const handleSaveAll = useCallback(() => {
    Object.entries(edits).forEach(([manualId, changes]) => {
      saveMutation.mutate({ manualId, data: changes })
    })
  }, [edits, saveMutation])

  const manuals: Manual[] = data?.items ?? []
  const gaps: Gap[] = missingReport?.gaps ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Manual Review</h1>
          <p className="mt-1 text-sm text-slate-400">
            Review and correct AI classification of vessel manuals.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {Object.keys(edits).length > 0 && (
            <button
              onClick={handleSaveAll}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              Save {Object.keys(edits).length} correction(s)
            </button>
          )}
          <button
            onClick={() => screenAllMutation.mutate()}
            disabled={isScreening}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
          >
            {isScreening ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <ScanSearch className="h-4 w-4" />
            )}
            {isScreening ? 'Screening...' : 'Start Screening'}
          </button>
        </div>
      </div>

      {/* Screening progress banner */}
      {isScreening && screeningData && screeningData.total > 0 && (
        <div className="rounded-xl border border-violet-700 bg-violet-900/20 p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-violet-300">
              Screening manuals... {screeningData.done} / {screeningData.total} done
            </span>
            <span className="text-violet-400">{screeningProgress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-2 rounded-full bg-violet-500 transition-all duration-500"
              style={{ width: `${screeningProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Screening complete banner */}
      {!isScreening && screeningData?.status === 'completed' && (
        <div className="flex items-center gap-2 rounded-xl border border-green-700 bg-green-900/20 px-4 py-3 text-sm text-green-400">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          Screening complete — {screeningData.total} manual{screeningData.total !== 1 ? 's' : ''} classified.
        </div>
      )}

      {/* Missing Manual Alert */}
      {gaps.length > 0 && (
        <div className="rounded-xl border border-amber-700 bg-amber-900/20 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <h2 className="text-sm font-semibold text-amber-300">
              Missing Manual Gaps ({gaps.length})
            </h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {gaps.map((g) => (
              <span
                key={g.category}
                className="rounded-full bg-amber-800/50 px-3 py-1 text-xs text-amber-200"
              >
                {g.category}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
        <Filter className="h-4 w-4 text-slate-400" />
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
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
            onClick={() => {
              setFilterCategory('')
              setFilterConfidence('')
            }}
            className="text-xs text-slate-400 underline hover:text-slate-200"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        {isLoading ? (
          <div className="py-16 text-center text-slate-500">Loading manuals...</div>
        ) : manuals.length === 0 ? (
          <div className="py-16 text-center text-slate-500">No manuals found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
                <th className="px-4 py-3">File Name</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Useful</th>
                <th className="px-4 py-3">Components</th>
                <th className="px-4 py-3">Jobs</th>
                <th className="px-4 py-3">Spares</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Comments</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {manuals.map((m) => {
                const edit = edits[m.id] ?? {}
                const changed = Object.keys(edit).length > 0
                return (
                  <tr
                    key={m.id}
                    className={`transition-colors hover:bg-slate-800/50 ${
                      changed ? 'bg-sky-900/10' : ''
                    }`}
                  >
                    <td className="px-4 py-3 text-slate-200 font-medium max-w-xs truncate">
                      {m.original_filename}
                    </td>
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {formatBytes(m.file_size_bytes)}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={edit.category ?? m.category ?? ''}
                        onChange={(e) => handleEdit(m.id, 'category', e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">—</option>
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={edit.useful_for_extraction ?? m.useful_for_extraction ?? ''}
                        onChange={(e) =>
                          handleEdit(m.id, 'useful_for_extraction', e.target.value)
                        }
                        className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">—</option>
                        <option value="Yes">Yes</option>
                        <option value="Reference">Reference</option>
                        <option value="No">No</option>
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_components ?? m.pages_with_components ?? ''}
                        onChange={(e) =>
                          handleEdit(m.id, 'pages_with_components', e.target.value)
                        }
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="e.g. 1-50"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_jobs ?? m.pages_with_jobs ?? ''}
                        onChange={(e) => handleEdit(m.id, 'pages_with_jobs', e.target.value)}
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="e.g. 51-80"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        value={edit.pages_with_spares ?? m.pages_with_spares ?? ''}
                        onChange={(e) =>
                          handleEdit(m.id, 'pages_with_spares', e.target.value)
                        }
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="e.g. 81-120"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <ConfidenceBadge value={m.classification_confidence} />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        value={edit.reviewer_comments ?? m.reviewer_comments ?? ''}
                        onChange={(e) =>
                          handleEdit(m.id, 'reviewer_comments', e.target.value)
                        }
                        className="w-36 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        placeholder="Add comment..."
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {changed && (
                          <button
                            onClick={() =>
                              saveMutation.mutate({ manualId: m.id, data: edit })
                            }
                            className="rounded bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-500"
                            title="Save"
                          >
                            <Save className="h-3 w-3" />
                          </button>
                        )}
                        <button
                          onClick={() =>
                            triggerClassificationMutation.mutate(m.id)
                          }
                          className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                          title="Re-classify"
                        >
                          <RefreshCw className="h-3 w-3" />
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

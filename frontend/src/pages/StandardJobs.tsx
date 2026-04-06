import React, { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Play, Upload, XCircle } from 'lucide-react'
import apiClient from '@/api/client'

interface StandardJob {
  id: string
  class_society: string
  job_type?: string
  machinery_type: string
  job_name: string
  job_description: string | null
  frequency: number | null
  frequency_type: string | null
  is_critical: boolean
  library_reference: string | null
}

interface Match {
  id: string
  standard_job_id: string
  matched_job_id: string | null
  match_status: string
  match_score: number | null
  not_applicable_reason: string | null
  matched_job_name?: string | null
  matched_job_code?: string | null
  matched_job_qc_status?: string | null
}

const MATCH_COLORS: Record<string, string> = {
  matched: 'bg-green-700 text-green-100',
  partial: 'bg-amber-700 text-amber-100',
  not_found: 'bg-red-700 text-red-100',
  not_applicable: 'bg-slate-600 text-slate-300',
}

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]

const StandardJobs: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterSociety, setFilterSociety] = useState('')
  const [filterMachinery, setFilterMachinery] = useState('')
  const [filterMatchStatus, setFilterMatchStatus] = useState('')
  const [naReason, setNaReason] = useState('')
  const [naMatchId, setNaMatchId] = useState<string | null>(null)
  const [showNaDialog, setShowNaDialog] = useState(false)
  const [importJobType, setImportJobType] = useState<'standard' | 'class'>('standard')
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([])
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const { data: stdJobsData } = useQuery({
    queryKey: ['standard-jobs', importJobType, filterSociety, filterMachinery],
    queryFn: () => {
      const params: Record<string, string> = {
        page: '1',
        page_size: '5000',
        is_critical: 'false',
        job_type: importJobType,
      }
      if (importJobType === 'class' && filterSociety) params.class_society = filterSociety
      if (filterMachinery) params.machinery_type = filterMachinery
      return apiClient.get('/standard-jobs', { params }).then((r) => r.data)
    },
  })

  const { data: matchesData } = useQuery({
    queryKey: ['std-job-matches', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/standard-jobs/matches`, { params: { page: 1, page_size: 5000 } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const runComparisonMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/run-comparison`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      setActionMessage('Comparison completed against instruction-manual jobs.')
      setActionError(null)
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Comparison failed')
      setActionMessage(null)
    },
  })

  const importJobMutation = useMutation({
    mutationFn: (standardJobId: string) =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/import/${standardJobId}`).then((r) => r.data),
    onSuccess: () => {
      setActionMessage('Library job added to vessel jobs.')
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Failed to add library job to vessel')
      setActionMessage(null)
    },
  })

  const importLibraryMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await apiClient.post(`/standard-jobs/bulk-import?job_type=${importJobType}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data
    },
    onSuccess: () => {
      setActionMessage('Standard jobs library imported successfully.')
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['standard-jobs'] })
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Library import failed')
      setActionMessage(null)
    },
  })

  const markNaMutation = useMutation({
    mutationFn: ({ matchId, reason }: { matchId: string; reason: string }) =>
      apiClient.patch(`/vessels/${vesselId}/standard-jobs/matches/${matchId}`, {
        match_status: 'not_applicable',
        not_applicable_reason: reason,
      }).then((r) => r.data),
    onSuccess: () => {
      setActionMessage('Standard job marked as not applicable.')
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      setShowNaDialog(false)
      setNaReason('')
      setNaMatchId(null)
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Unable to update match')
      setActionMessage(null)
    },
  })

  const importSelectedMutation = useMutation({
    mutationFn: (payload: { standard_job_ids?: string[]; import_all?: boolean }) =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/import-batch`, {
        standard_job_ids: payload.standard_job_ids ?? [],
        job_type: importJobType,
        class_society: filterSociety || null,
        machinery_type: filterMachinery || null,
        include_critical: false,
        import_all: payload.import_all ?? false,
      }).then((r) => r.data),
    onSuccess: (data) => {
      setActionMessage(`Imported ${data.imported} and merged ${data.merged} library jobs into the vessel.`)
      setActionError(null)
      setSelectedJobIds([])
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Failed to apply library jobs to vessel')
      setActionMessage(null)
    },
  })

  const removeSelectedMutation = useMutation({
    mutationFn: (payload: { standard_job_ids?: string[]; remove_all?: boolean }) =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/remove-batch`, {
        standard_job_ids: payload.standard_job_ids ?? [],
        job_type: importJobType,
        class_society: filterSociety || null,
        machinery_type: filterMachinery || null,
        include_critical: false,
        remove_all: payload.remove_all ?? false,
      }).then((r) => r.data),
    onSuccess: (data) => {
      setActionMessage(`Removed ${data.removed} vessel-side imported jobs.`)
      setActionError(null)
      setSelectedJobIds([])
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
    },
    onError: (err: any) => {
      setActionError(err?.response?.data?.detail || 'Failed to remove imported jobs from vessel')
      setActionMessage(null)
    },
  })

  const allJobs: StandardJob[] = stdJobsData?.items ?? []
  const matches: Match[] = matchesData?.items ?? []
  const matchByStdJobId = Object.fromEntries(matches.map((m) => [m.standard_job_id, m]))

  const filteredJobs = allJobs.filter((job) => {
    if (importJobType === 'standard' && (job.class_society !== 'General' || job.is_critical)) return false
    if (importJobType === 'class' && (job.class_society === 'General' || job.is_critical)) return false
    if (filterMatchStatus) {
      const status = matchByStdJobId[job.id]?.match_status ?? 'not_found'
      if (status !== filterMatchStatus) return false
    }
    return true
  })

  const selectedSet = new Set(selectedJobIds)
  const visibleMatches = matches.filter((match) => filteredJobs.some((job) => job.id === match.standard_job_id))
  const matchedCount = visibleMatches.filter((m) => m.match_status === 'matched').length
  const partialCount = visibleMatches.filter((m) => m.match_status === 'partial').length
  const notFoundCount = visibleMatches.filter((m) => m.match_status === 'not_found').length
  const total = filteredJobs.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageJobs = filteredJobs.slice((page - 1) * pageSize, page * pageSize)
  const allSelected = pageJobs.length > 0 && pageJobs.every((job) => selectedSet.has(job.id))

  React.useEffect(() => {
    setPage(1)
    setSelectedJobIds([])
  }, [importJobType, filterSociety, filterMachinery, filterMatchStatus, pageSize])

  React.useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const handleMarkNA = (matchId: string) => {
    setNaMatchId(matchId)
    setShowNaDialog(true)
  }

  const handleLibraryImport = (file?: File | null) => {
    if (!file) return
    setActionError(null)
    setActionMessage(null)
    importLibraryMutation.mutate(file)
  }

  const toggleJobSelection = (jobId: string) => {
    setSelectedJobIds((prev) => (
      prev.includes(jobId) ? prev.filter((id) => id !== jobId) : [...prev, jobId]
    ))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Standard Jobs Comparison</h1>
          <p className="mt-1 text-sm text-slate-400">
            Compare instruction-manual vessel jobs against imported company SMS and CMS/class job libraries.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Critical jobs are managed separately from Jobs Review and are not part of this comparison run.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={importJobType}
            onChange={(e) => setImportJobType(e.target.value as 'standard' | 'class')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200"
          >
            <option value="standard">Company SMS Jobs</option>
            <option value="class">CMS / Class Jobs</option>
          </select>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            <Upload className="h-4 w-4" />
            {importLibraryMutation.isPending ? 'Importing...' : 'Import Library'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => handleLibraryImport(e.target.files?.[0])}
          />
          <button
            onClick={() => runComparisonMutation.mutate()}
            disabled={runComparisonMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {runComparisonMutation.isPending ? 'Running...' : 'Run Comparison'}
          </button>
        </div>
      </div>

      {(actionMessage || actionError) && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${actionError ? 'border-red-800 bg-red-950/30 text-red-300' : 'border-emerald-800 bg-emerald-950/30 text-emerald-300'}`}>
          {actionError || actionMessage}
        </div>
      )}

      {visibleMatches.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl border border-green-800 bg-green-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-green-400">{matchedCount}</p>
            <p className="text-xs text-green-300">Matched</p>
          </div>
          <div className="rounded-xl border border-amber-800 bg-amber-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-amber-400">{partialCount}</p>
            <p className="text-xs text-amber-300">Partial Match</p>
          </div>
          <div className="rounded-xl border border-red-800 bg-red-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-red-400">{notFoundCount}</p>
            <p className="text-xs text-red-300">Not Found</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
        <select
          value={filterSociety}
          onChange={(e) => setFilterSociety(e.target.value)}
          disabled={importJobType !== 'class'}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 disabled:opacity-60"
        >
          <option value="">All Class Societies</option>
          <option value="DNV GL">DNV GL</option>
          <option value="Lloyd's Register">Lloyd's Register</option>
          <option value="Bureau Veritas">Bureau Veritas</option>
          <option value="ABS">ABS</option>
          <option value="ClassNK">ClassNK</option>
        </select>
        <input
          type="text"
          value={filterMachinery}
          onChange={(e) => setFilterMachinery(e.target.value)}
          placeholder="Machinery type..."
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
        />
        <select
          value={filterMatchStatus}
          onChange={(e) => setFilterMatchStatus(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Match Status</option>
          <option value="matched">Matched</option>
          <option value="partial">Partially Matched</option>
          <option value="not_found">Not Matched</option>
          <option value="not_applicable">Not Applicable</option>
        </select>
      </div>

      <div className="rounded-xl border border-sky-900/50 bg-sky-950/20 px-4 py-3 text-xs text-sky-200">
        Supported workbook import: <span className="font-medium">Audit standard jobs</span>, <span className="font-medium">Annex Job Title</span>, and <span className="font-medium">Critical Jobs</span>. Critical jobs go into the library but are excluded from comparison.
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => importSelectedMutation.mutate({ standard_job_ids: selectedJobIds })}
          disabled={selectedJobIds.length === 0 || importSelectedMutation.isPending}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          Add Selected To Vessel
        </button>
        <button
          onClick={() => importSelectedMutation.mutate({ import_all: true })}
          disabled={filteredJobs.length === 0 || importSelectedMutation.isPending}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          Add All Filtered
        </button>
        <button
          onClick={() => removeSelectedMutation.mutate({ standard_job_ids: selectedJobIds })}
          disabled={selectedJobIds.length === 0 || removeSelectedMutation.isPending}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-500 disabled:opacity-50"
        >
          Remove Selected From Vessel
        </button>
        <button
          onClick={() => removeSelectedMutation.mutate({ remove_all: true })}
          disabled={filteredJobs.length === 0 || removeSelectedMutation.isPending}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          Remove All Filtered
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
              <th className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => setSelectedJobIds(e.target.checked ? pageJobs.map((job) => job.id) : [])}
                />
              </th>
              <th className="px-4 py-3">Standard Job</th>
              <th className="px-4 py-3">Class Society</th>
              <th className="px-4 py-3">Machinery Type</th>
              <th className="px-4 py-3">Frequency</th>
              <th className="px-4 py-3">Critical</th>
              <th className="px-4 py-3">Match Status</th>
              <th className="px-4 py-3">Matched Vessel Job</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filteredJobs.length === 0 ? (
              <tr>
                <td colSpan={10} className="py-12 text-center text-slate-500">
                  No jobs found for the selected library and filters.
                </td>
              </tr>
            ) : (
              pageJobs.map((job) => {
                const match = matchByStdJobId[job.id]
                return (
                  <tr key={job.id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(job.id)}
                        onChange={() => toggleJobSelection(job.id)}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-slate-200">{job.job_name}</p>
                      {job.library_reference && (
                        <p className="text-xs text-slate-500 font-mono">{job.library_reference}</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-300 text-xs">{job.class_society}</td>
                    <td className="px-4 py-2.5 text-slate-400">{job.machinery_type}</td>
                    <td className="px-4 py-2.5 text-slate-400 text-xs whitespace-nowrap">
                      {job.frequency != null && job.frequency_type
                        ? `${job.frequency} ${job.frequency_type}`
                        : job.frequency_type ?? '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      {job.is_critical ? (
                        <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">
                          Critical
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-col gap-1">
                        <span className={`w-fit rounded-full px-2 py-0.5 text-xs font-medium ${MATCH_COLORS[match?.match_status ?? ''] ?? 'bg-slate-700 text-slate-300'}`}>
                          {match ? match.match_status.replace('_', ' ') : 'Not compared'}
                        </span>
                        <span className="text-xs text-slate-500">
                          {importJobType === 'class' ? 'CMS / Class' : 'Company SMS'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {match ? (
                        <div className="min-w-[190px]">
                          <p className="text-slate-200">{match.matched_job_name ?? 'No vessel job linked'}</p>
                          <p className="text-xs text-slate-500">
                            {[match.matched_job_code, match.matched_job_qc_status].filter(Boolean).join(' • ') || '—'}
                          </p>
                        </div>
                      ) : (
                        <span className="text-slate-600 text-xs">Not compared</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {match?.match_score != null ? `${match.match_score}%` : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        {match && (match.match_status === 'not_found' || match.match_status === 'partial') && (
                          <button
                            onClick={() => importJobMutation.mutate(job.id)}
                            className="rounded bg-sky-700 px-2 py-1 text-xs text-white hover:bg-sky-600"
                            title="Add this standard job into vessel jobs for review"
                          >
                            <Download className="h-3 w-3" />
                          </button>
                        )}
                        {match && match.match_status !== 'not_applicable' && (
                          <button
                            onClick={() => handleMarkNA(match.id)}
                            className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                            title="Mark not applicable"
                          >
                            <XCircle className="h-3 w-3" />
                          </button>
                        )}
                        {match?.not_applicable_reason && (
                          <span className="max-w-xs truncate text-xs text-slate-500">
                            {match.not_applicable_reason}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
        {filteredJobs.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-800 px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>{total} total</span>
              <span>·</span>
              <span>Show</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
                className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-slate-300 text-xs"
              >
                {PAGE_SIZE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <span>per page</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded text-xs bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-40"
              >
                ← Prev
              </button>
              <span className="px-3 text-xs text-slate-500">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2 py-1 rounded text-xs bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>

      {showNaDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">Mark Not Applicable</h3>
            <p className="mb-4 text-sm text-slate-400">
              Please provide a reason why this standard job is not applicable.
            </p>
            <textarea
              value={naReason}
              onChange={(e) => setNaReason(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. Vessel uses different class society requirements"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowNaDialog(false)
                  setNaReason('')
                }}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => naMatchId && markNaMutation.mutate({ matchId: naMatchId, reason: naReason })}
                disabled={!naReason || markNaMutation.isPending}
                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StandardJobs

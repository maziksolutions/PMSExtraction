import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, CheckCircle, XCircle, Upload, AlertCircle, ExternalLink } from 'lucide-react'
import apiClient from '@/api/client'

interface Job {
  id: string
  job_name: string
  job_code: string | null
  component_id: string | null
  job_description: string | null
  frequency: number | null
  frequency_type: string | null
  performing_rank: string | null
  cms_id: string | null
  is_critical: boolean
  confidence_score: number | null
  qc_status: string
  is_unmapped: boolean
  source_manual_id: string | null
  page_reference: number | null
  source_page_number: number | null
  pdf_reference: string | null
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

const JobsReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterQC, setFilterQC] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [filterUnmapped, setFilterUnmapped] = useState(false)
  const [filterFreqType, setFilterFreqType] = useState('')
  const [filterNoCMS, setFilterNoCMS] = useState(false)
  const [filterJobName, setFilterJobName] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', vesselId, filterQC, filterCritical, filterUnmapped, filterFreqType, filterNoCMS, filterJobName],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterCritical) params.is_critical = filterCritical
      if (filterUnmapped) params.is_unmapped = 'true'
      if (filterFreqType) params.frequency_type = filterFreqType
      if (filterJobName) params.search = filterJobName
      return apiClient.get(`/vessels/${vesselId}/jobs`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/jobs/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/jobs/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const triggerExtractionMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/jobs/trigger-extraction`).then((r) => r.data),
  })

  const handleCMSUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const formData = new FormData()
      formData.append('file', file)
      await apiClient.post(`/vessels/${vesselId}/jobs/upload-cms-mapping`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
    },
    [vesselId, queryClient]
  )

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const jobs: Job[] = (data?.items ?? []).filter((j: Job) => {
    if (filterNoCMS && j.cms_id) return false
    return true
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Jobs Review</h1>
          <p className="mt-1 text-sm text-slate-400">Review and correct extracted maintenance jobs.</p>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={() => bulkAcceptMutation.mutate(Array.from(selectedIds))}
                className="flex items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600"
              >
                <CheckCircle className="h-3.5 w-3.5" />
                Accept ({selectedIds.size})
              </button>
              <button
                onClick={() => bulkRejectMutation.mutate(Array.from(selectedIds))}
                className="flex items-center gap-1.5 rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
              >
                <XCircle className="h-3.5 w-3.5" />
                Reject ({selectedIds.size})
              </button>
            </>
          )}
          <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
            <Upload className="h-3.5 w-3.5" />
            Upload CMS Mapping
            <input type="file" accept=".csv" className="hidden" onChange={handleCMSUpload} />
          </label>
          <button
            onClick={() => triggerExtractionMutation.mutate()}
            disabled={triggerExtractionMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" />
            Trigger Extraction
          </button>
        </div>
      </div>

      {/* Quick toggle filters */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setFilterUnmapped(!filterUnmapped)}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
            filterUnmapped ? 'border-amber-600 bg-amber-900/20 text-amber-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
          }`}
        >
          <AlertCircle className="h-3 w-3" />
          Unmapped
        </button>
        <button
          onClick={() => setFilterNoCMS(!filterNoCMS)}
          className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
            filterNoCMS ? 'border-sky-600 bg-sky-900/20 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
          }`}
        >
          CMS Codes Pending
        </button>
        {(filterQC || filterCritical || filterFreqType || filterJobName) && (
          <button
            onClick={() => { setFilterQC(''); setFilterCritical(''); setFilterFreqType(''); setFilterJobName('') }}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
          >
            Clear column filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        {isLoading ? (
          <div className="py-16 text-center text-slate-500">Loading jobs...</div>
        ) : jobs.length === 0 ? (
          <div className="py-16 text-center text-slate-500">No jobs found. Trigger extraction to begin.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    onChange={(e) =>
                      e.target.checked
                        ? setSelectedIds(new Set(jobs.map((j) => j.id)))
                        : setSelectedIds(new Set())
                    }
                    checked={selectedIds.size === jobs.length && jobs.length > 0}
                    className="h-3.5 w-3.5 rounded"
                  />
                </th>
                <th className="px-4 py-3">Job Name</th>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Frequency</th>
                <th className="px-4 py-3">Rank</th>
                <th className="px-4 py-3">CMS ID</th>
                <th className="px-4 py-3">Critical</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">QC Status</th>
              </tr>
              {/* Column filter row */}
              <tr className="border-b border-slate-800 bg-slate-950">
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5">
                  <input
                    type="text"
                    value={filterJobName}
                    onChange={(e) => setFilterJobName(e.target.value)}
                    placeholder="Search..."
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:border-sky-500 focus:outline-none"
                  />
                </td>
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5">
                  <select
                    value={filterFreqType}
                    onChange={(e) => setFilterFreqType(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="yearly">Yearly</option>
                    <option value="running_hours">Running Hours</option>
                  </select>
                </td>
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5">
                  <select
                    value={filterCritical}
                    onChange={(e) => setFilterCritical(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All</option>
                    <option value="true">Critical</option>
                    <option value="false">Non-Critical</option>
                  </select>
                </td>
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5" />
                <td className="px-4 py-1.5">
                  <select
                    value={filterQC}
                    onChange={(e) => setFilterQC(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All</option>
                    <option value="pending">Pending</option>
                    <option value="accepted">Accepted</option>
                    <option value="rejected">Rejected</option>
                  </select>
                </td>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className={`hover:bg-slate-800/50 transition-colors ${
                    selectedIds.has(job.id) ? 'bg-sky-900/10' : ''
                  } ${job.is_unmapped ? 'border-l-2 border-amber-600' : ''}`}
                >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(job.id)}
                      onChange={() => toggleSelect(job.id)}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </td>
                  <td className="px-4 py-2.5 text-slate-200 font-medium">{job.job_name}</td>
                  <td className="px-4 py-2.5 text-slate-400 font-mono text-xs">{job.job_code ?? '—'}</td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate text-xs">
                    {job.job_description?.slice(0, 80) ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-slate-300 whitespace-nowrap">
                    {job.frequency != null && job.frequency_type
                      ? `${job.frequency} ${job.frequency_type.replace('_', ' ')}`
                      : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 text-xs">{job.performing_rank ?? '—'}</td>
                  <td className="px-4 py-2.5">
                    {job.cms_id ? (
                      <span className="font-mono text-xs text-green-400">{job.cms_id}</span>
                    ) : (
                      <span className="text-xs text-amber-500">Pending</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {job.is_critical ? (
                      <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">Critical</span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {job.confidence_score != null ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          job.confidence_score >= 85
                            ? 'bg-green-700 text-green-100'
                            : job.confidence_score >= 60
                            ? 'bg-amber-700 text-amber-100'
                            : 'bg-red-700 text-red-100'
                        }`}
                      >
                        {job.confidence_score}%
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {(job.source_page_number ?? job.page_reference) != null ? (
                      <span
                        title={`${job.pdf_reference ?? 'Manual'} — page ${job.source_page_number ?? job.page_reference}`}
                        className="inline-flex items-center gap-1 text-xs text-sky-400"
                      >
                        <ExternalLink className="h-3 w-3" />
                        p.{job.source_page_number ?? job.page_reference}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        QC_COLORS[job.qc_status] ?? 'bg-slate-700 text-slate-300'
                      }`}
                    >
                      {job.qc_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default JobsReview

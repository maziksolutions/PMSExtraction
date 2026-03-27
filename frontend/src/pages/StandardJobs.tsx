import React, { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Download, XCircle, CheckCircle, AlertTriangle } from 'lucide-react'
import apiClient from '@/api/client'

interface StandardJob {
  id: string
  class_society: string
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
}

const MATCH_COLORS: Record<string, string> = {
  matched: 'bg-green-700 text-green-100',
  partial: 'bg-amber-700 text-amber-100',
  not_found: 'bg-red-700 text-red-100',
  not_applicable: 'bg-slate-600 text-slate-300',
}

const StandardJobs: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterSociety, setFilterSociety] = useState('')
  const [filterMachinery, setFilterMachinery] = useState('')
  const [naReason, setNaReason] = useState('')
  const [naMatchId, setNaMatchId] = useState<string | null>(null)
  const [showNaDialog, setShowNaDialog] = useState(false)

  const { data: stdJobsData } = useQuery({
    queryKey: ['standard-jobs', filterSociety, filterMachinery],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterSociety) params.class_society = filterSociety
      if (filterMachinery) params.machinery_type = filterMachinery
      return apiClient.get('/standard-jobs', { params }).then((r) => r.data)
    },
  })

  const { data: matchesData, refetch: refetchMatches } = useQuery({
    queryKey: ['std-job-matches', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/standard-jobs/matches`).then((r) => r.data),
    enabled: !!vesselId,
  })

  const runComparisonMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/run-comparison`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
    },
  })

  const importJobMutation = useMutation({
    mutationFn: (standardJobId: string) =>
      apiClient
        .post(`/vessels/${vesselId}/standard-jobs/import/${standardJobId}`)
        .then((r) => r.data),
  })

  const markNaMutation = useMutation({
    mutationFn: ({ matchId, reason }: { matchId: string; reason: string }) =>
      apiClient
        .patch(`/vessels/${vesselId}/standard-jobs/matches/${matchId}`, {
          match_status: 'not_applicable',
          not_applicable_reason: reason,
        })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      setShowNaDialog(false)
      setNaReason('')
      setNaMatchId(null)
    },
  })

  const stdJobs: StandardJob[] = stdJobsData?.items ?? []
  const matches: Match[] = matchesData?.items ?? []
  const matchByStdJobId = Object.fromEntries(matches.map((m) => [m.standard_job_id, m]))

  const handleMarkNA = (matchId: string) => {
    setNaMatchId(matchId)
    setShowNaDialog(true)
  }

  const matchedCount = matches.filter((m) => m.match_status === 'matched').length
  const partialCount = matches.filter((m) => m.match_status === 'partial').length
  const notFoundCount = matches.filter((m) => m.match_status === 'not_found').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Standard Jobs Comparison</h1>
          <p className="mt-1 text-sm text-slate-400">
            Compare extracted jobs against class society standard requirements.
          </p>
        </div>
        <button
          onClick={() => runComparisonMutation.mutate()}
          disabled={runComparisonMutation.isPending}
          className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          <Play className="h-4 w-4" />
          {runComparisonMutation.isPending ? 'Running...' : 'Run Comparison'}
        </button>
      </div>

      {/* Summary stats */}
      {matches.length > 0 && (
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

      {/* Filters */}
      <div className="flex gap-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
        <select
          value={filterSociety}
          onChange={(e) => setFilterSociety(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
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
      </div>

      {/* Comparison Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
              <th className="px-4 py-3">Standard Job</th>
              <th className="px-4 py-3">Class Society</th>
              <th className="px-4 py-3">Machinery Type</th>
              <th className="px-4 py-3">Frequency</th>
              <th className="px-4 py-3">Critical</th>
              <th className="px-4 py-3">Match Status</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {stdJobs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-500">
                  No standard jobs found. Run comparison to match against extracted jobs.
                </td>
              </tr>
            ) : (
              stdJobs.map((job) => {
                const match = matchByStdJobId[job.id]
                return (
                  <tr key={job.id} className="hover:bg-slate-800/50 transition-colors">
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
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {match ? (
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            MATCH_COLORS[match.match_status] ?? 'bg-slate-700 text-slate-300'
                          }`}
                        >
                          {match.match_status.replace('_', ' ')}
                        </span>
                      ) : (
                        <span className="text-slate-600 text-xs">Not compared</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {match?.match_score != null ? `${match.match_score}%` : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        {match && match.match_status === 'not_found' && (
                          <button
                            onClick={() => importJobMutation.mutate(job.id)}
                            className="rounded bg-sky-700 px-2 py-1 text-xs text-white hover:bg-sky-600"
                            title="Import this standard job"
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
                          <span className="text-xs text-slate-500 max-w-xs truncate">
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
      </div>

      {/* Not Applicable Dialog */}
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
                onClick={() =>
                  naMatchId && markNaMutation.mutate({ matchId: naMatchId, reason: naReason })
                }
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

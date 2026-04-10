import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Plus, RefreshCw, Trash2 } from 'lucide-react'
import apiClient from '@/api/client'

interface RankOption {
  id: string
  rank_name: string
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const maybeError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = maybeError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return maybeError?.message ?? fallback
}

const JobRanksLibrary: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [newRank, setNewRank] = useState('')
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const ranksQuery = useQuery({
    queryKey: ['job-ranks'],
    queryFn: () => apiClient.get('/job-ranks', { params: { page: 1, page_size: 1000, sort_by: 'rank_name', sort_order: 'asc' } }).then((r) => r.data),
  })

  const createRankMutation = useMutation({
    mutationFn: (rankName: string) => apiClient.post('/job-ranks', { rank_name: rankName }).then((r) => r.data),
    onSuccess: (data) => {
      setNewRank('')
      setActionError(null)
      setActionMessage(`Added rank "${data.rank_name}".`)
      queryClient.invalidateQueries({ queryKey: ['job-ranks'] })
    },
    onError: (error: unknown) => {
      setActionMessage(null)
      setActionError(getApiErrorMessage(error, 'Unable to add rank.'))
    },
  })

  const deleteRankMutation = useMutation({
    mutationFn: (rankName: string) => apiClient.delete(`/job-ranks/${encodeURIComponent(rankName)}`).then((r) => r.data),
    onSuccess: () => {
      setActionError(null)
      setActionMessage('Removed rank from the library.')
      queryClient.invalidateQueries({ queryKey: ['job-ranks'] })
    },
    onError: (error: unknown) => {
      setActionMessage(null)
      setActionError(getApiErrorMessage(error, 'Unable to remove rank.'))
    },
  })

  const rankOptions: RankOption[] = ranksQuery.data?.items ?? []
  const filteredRanks = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return rankOptions
    return rankOptions.filter((rank) => rank.rank_name.toLowerCase().includes(needle))
  }, [rankOptions, search])

  return (
    <div className="space-y-6">
      {!embedded && (
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
            <BookOpen className="h-7 w-7 text-sky-400" />
            Rank Library
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage the performing and verifying rank options used across Standard Jobs and Jobs Review.
          </p>
        </div>
      )}

      {(actionMessage || actionError) && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${actionError ? 'border-red-800 bg-red-950/30 text-red-300' : 'border-emerald-800 bg-emerald-950/30 text-emerald-300'}`}>
          {actionError || actionMessage}
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="flex-1">
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-500">Add Rank</label>
            <div className="flex gap-2">
              <input
                value={newRank}
                onChange={(e) => setNewRank(e.target.value)}
                placeholder="Chief Engineer"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
              />
              <button
                onClick={() => createRankMutation.mutate(newRank)}
                disabled={!newRank.trim() || createRankMutation.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                <Plus className="h-4 w-4" />
                Add
              </button>
            </div>
          </div>
          <div className="w-full md:w-72">
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-500">Search</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter ranks..."
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <div className="text-sm font-semibold text-slate-200">Available Ranks</div>
          <div className="text-xs text-slate-500">{filteredRanks.length} shown / {rankOptions.length} total</div>
        </div>
        {ranksQuery.isLoading ? (
          <div className="py-16 text-center text-slate-500">
            <RefreshCw className="mx-auto mb-2 h-5 w-5 animate-spin" />
            Loading ranks...
          </div>
        ) : filteredRanks.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            No ranks found.
          </div>
        ) : (
          <div className="grid gap-px bg-slate-800 md:grid-cols-2 xl:grid-cols-3">
            {filteredRanks.map((rank) => (
              <div key={rank.id} className="flex items-center justify-between gap-3 bg-slate-900 px-4 py-3 text-sm text-slate-200">
                <span>{rank.rank_name}</span>
                <button
                  onClick={() => deleteRankMutation.mutate(rank.rank_name)}
                  className="text-slate-500 transition-colors hover:text-red-400"
                  title="Remove rank"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default JobRanksLibrary

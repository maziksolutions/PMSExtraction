import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, CheckCircle, XCircle, Image, ExternalLink } from 'lucide-react'
import apiClient from '@/api/client'

interface Spare {
  id: string
  part_name: string
  part_number: string | null
  drawing_number: string | null
  drawing_position: string | null
  specification: string | null
  spare_maker: string | null
  component_id: string | null
  component_name?: string | null
  component_maker?: string | null
  component_model?: string | null
  source_manual_id: string | null
  source_manual_name?: string | null
  pdf_reference?: string | null
  page_reference: number | null
  extraction_method: string
  is_critical: boolean
  confidence_score: number | null
  qc_status: string
  is_duplicate: boolean
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

const METHOD_COLORS: Record<string, string> = {
  table: 'bg-blue-700 text-blue-100',
  text: 'bg-purple-700 text-purple-100',
  drawing: 'bg-amber-700 text-amber-100',
}

const SparesReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterQC, setFilterQC] = useState('')
  const [filterMethod, setFilterMethod] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedSpare, setSelectedSpare] = useState<Spare | null>(null)
  const [pageImageUrl, setPageImageUrl] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['spares', vesselId, filterQC, filterMethod, filterCritical],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterMethod) params.extraction_method = filterMethod
      if (filterCritical) params.is_critical = filterCritical
      return apiClient.get(`/vessels/${vesselId}/spares`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const triggerExtractionMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/spares/trigger-extraction`).then((r) => r.data),
  })

  const loadPageImage = useCallback(
    async (spare: Spare) => {
      setSelectedSpare(spare)
      setPageImageUrl(null)
      try {
        const res = await apiClient.get(`/vessels/${vesselId}/spares/${spare.id}/page-image`)
        setPageImageUrl(res.data.image_url)
      } catch {
        setPageImageUrl(null)
      }
    },
    [vesselId]
  )

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const spares: Spare[] = data?.items ?? []

  return (
    <div className="flex h-full gap-4">
      {/* Left: Spare Grid */}
      <div className="flex flex-1 flex-col gap-4 overflow-hidden">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Spares Review</h1>
            <p className="mt-1 text-sm text-slate-400">Review extracted spare parts.</p>
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

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filterMethod}
            onChange={(e) => setFilterMethod(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Methods</option>
            <option value="table">Table</option>
            <option value="text">Text</option>
            <option value="drawing">Drawing</option>
          </select>
          <select
            value={filterCritical}
            onChange={(e) => setFilterCritical(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Criticality</option>
            <option value="true">Critical</option>
            <option value="false">Non-Critical</option>
          </select>
          <select
            value={filterQC}
            onChange={(e) => setFilterQC(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All QC</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
          </select>
          {(filterQC || filterMethod || filterCritical) && (
            <button
              onClick={() => { setFilterQC(''); setFilterMethod(''); setFilterCritical('') }}
              className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading...</div>
          ) : spares.length === 0 ? (
            <div className="py-16 text-center text-slate-500">
              No spares found. Trigger extraction to begin.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase">
                  <th className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      onChange={(e) =>
                        e.target.checked
                          ? setSelectedIds(new Set(spares.map((s) => s.id)))
                          : setSelectedIds(new Set())
                      }
                      checked={selectedIds.size === spares.length && spares.length > 0}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </th>
                  <th className="px-4 py-3">Part Name</th>
                  <th className="px-4 py-3">Part #</th>
                  <th className="px-4 py-3">Drawing #</th>
                  <th className="px-4 py-3">Pos</th>
                  <th className="px-4 py-3">Maker</th>
                  <th className="px-4 py-3">Component</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Method</th>
                  <th className="px-4 py-3">Critical</th>
                  <th className="px-4 py-3">Conf</th>
                  <th className="px-4 py-3">QC</th>
                  <th className="px-4 py-3">View</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {spares.map((spare) => (
                  <tr
                    key={spare.id}
                    className={`hover:bg-slate-800/50 transition-colors ${
                      selectedIds.has(spare.id) ? 'bg-sky-900/10' : ''
                    } ${selectedSpare?.id === spare.id ? 'bg-slate-800' : ''}`}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(spare.id)}
                        onChange={() => toggleSelect(spare.id)}
                        className="h-3.5 w-3.5 rounded"
                      />
                    </td>
                    <td className="px-4 py-2.5 text-slate-200 font-medium">{spare.part_name}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-400">
                      {spare.part_number ?? '-'}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-400">
                      {spare.drawing_number ?? '-'}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">{spare.drawing_position ?? '-'}</td>
                    <td className="px-4 py-2.5 text-slate-300">{spare.spare_maker ?? '-'}</td>
                    <td className="px-4 py-2.5">
                      {spare.component_name ? (
                        <div className="min-w-[180px]">
                          <p className="text-slate-200">{spare.component_name}</p>
                          <p className="text-xs text-slate-500">
                            {[spare.component_maker, spare.component_model].filter(Boolean).join(' - ') || 'Linked'}
                          </p>
                        </div>
                      ) : (
                        <span className="rounded-full bg-amber-900/40 px-2 py-0.5 text-xs text-amber-300">Unmapped</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.page_reference != null ? (
                        <div className="min-w-[170px] text-xs">
                          <div className="inline-flex items-center gap-1 text-sky-400" title={`${spare.pdf_reference ?? spare.source_manual_name ?? 'Manual'} - page ${spare.page_reference}`}>
                            <ExternalLink className="h-3 w-3" />
                            p.{spare.page_reference}
                          </div>
                          <p className="mt-1 truncate text-slate-500">{spare.source_manual_name ?? spare.pdf_reference ?? 'Manual'}</p>
                        </div>
                      ) : <span className="text-slate-600">-</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          METHOD_COLORS[spare.extraction_method] ?? 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {spare.extraction_method}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.is_critical ? (
                        <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">
                          Critical
                        </span>
                      ) : (
                        <span className="text-slate-600">-</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.confidence_score != null ? (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            spare.confidence_score >= 85
                              ? 'bg-green-700 text-green-100'
                              : spare.confidence_score >= 60
                              ? 'bg-amber-700 text-amber-100'
                              : 'bg-red-700 text-red-100'
                          }`}
                        >
                          {spare.confidence_score}%
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          QC_COLORS[spare.qc_status] ?? 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {spare.qc_status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => loadPageImage(spare)}
                        className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600"
                        title="View page"
                      >
                        <Image className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Right: Page Image Viewer */}
      {selectedSpare && (
        <aside className="w-80 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">Page Viewer</h3>
            <button
              onClick={() => setSelectedSpare(null)}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              Close
            </button>
          </div>
          <div className="mb-3 rounded-lg bg-slate-800 p-3 text-xs text-slate-300 space-y-1">
            <p>
              <span className="text-slate-500">Part:</span> {selectedSpare.part_name}
            </p>
            <p>
              <span className="text-slate-500">Part #:</span> {selectedSpare.part_number ?? '-'}
            </p>
            <p>
              <span className="text-slate-500">Page:</span> {selectedSpare.page_reference ?? '-'}
            </p>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800 min-h-64 flex items-center justify-center">
            {pageImageUrl ? (
              <img
                src={pageImageUrl}
                alt={`Page ${selectedSpare.page_reference}`}
                className="max-w-full rounded"
              />
            ) : (
              <div className="text-center text-slate-500 py-12">
                <Image className="mx-auto mb-2 h-8 w-8 opacity-30" />
                <p className="text-xs">Page image not available</p>
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  )
}

export default SparesReview

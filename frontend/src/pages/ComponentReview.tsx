import React, { useState, useCallback, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ChevronDown, Play, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import apiClient from '@/api/client'

interface Component {
  id: string
  group1: string
  group2: string
  main_machinery: string
  component_name: string
  maker: string | null
  model: string | null
  specification: string | null
  serial_number: string | null
  source_manual_id: string | null
  page_reference: number | null
  confidence_score: number | null
  is_critical: boolean
  qc_status: string
  is_unmapped: boolean
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

interface TreeNode {
  group1: string
  group2s: Record<string, { mainMachinery: Set<string>; count: number }>
  count: number
}

const ComponentReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [selectedGroup1, setSelectedGroup1] = useState<string | null>(null)
  const [selectedGroup2, setSelectedGroup2] = useState<string | null>(null)
  const [showUnmapped, setShowUnmapped] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [filterQC, setFilterQC] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['components', vesselId, selectedGroup1, selectedGroup2, filterQC, showUnmapped],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (selectedGroup1) params.group1 = selectedGroup1
      if (selectedGroup2) params.group2 = selectedGroup2
      if (filterQC) params.qc_status = filterQC
      if (showUnmapped) params.is_unmapped = 'true'
      return apiClient.get(`/vessels/${vesselId}/components`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const allComponentsQuery = useQuery({
    queryKey: ['components-all', vesselId],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/components`, { params: { page_size: 200 } })
        .then((r) => r.data),
    enabled: !!vesselId,
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const triggerExtractionMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/components/trigger-extraction`).then((r) => r.data),
  })

  // Build tree from all components
  const tree = useMemo<Record<string, TreeNode>>(() => {
    const allComponents: Component[] = allComponentsQuery.data?.items ?? []
    const nodes: Record<string, TreeNode> = {}
    for (const comp of allComponents) {
      if (!nodes[comp.group1]) {
        nodes[comp.group1] = { group1: comp.group1, group2s: {}, count: 0 }
      }
      nodes[comp.group1].count++
      if (!nodes[comp.group1].group2s[comp.group2]) {
        nodes[comp.group1].group2s[comp.group2] = {
          mainMachinery: new Set(),
          count: 0,
        }
      }
      nodes[comp.group1].group2s[comp.group2].count++
      nodes[comp.group1].group2s[comp.group2].mainMachinery.add(comp.main_machinery)
    }
    return nodes
  }, [allComponentsQuery.data])

  const toggleGroup = useCallback((key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const components: Component[] = data?.items ?? []

  return (
    <div className="flex h-full gap-4">
      {/* Left Panel: Tree */}
      <aside className="w-64 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">
          Component Hierarchy
        </p>
        <button
          onClick={() => {
            setSelectedGroup1(null)
            setSelectedGroup2(null)
            setShowUnmapped(false)
          }}
          className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
            !selectedGroup1 && !showUnmapped
              ? 'bg-sky-600/20 text-sky-300'
              : 'text-slate-300 hover:bg-slate-800'
          }`}
        >
          All Components
        </button>
        {Object.values(tree).map((node) => (
          <div key={node.group1}>
            <button
              onClick={() => toggleGroup(node.group1)}
              className={`flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                selectedGroup1 === node.group1
                  ? 'bg-sky-600/20 text-sky-300'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {expandedGroups.has(node.group1) ? (
                <ChevronDown className="h-3 w-3 shrink-0" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0" />
              )}
              <span
                className="flex-1 truncate text-left"
                onClick={() => setSelectedGroup1(node.group1)}
              >
                {node.group1}
              </span>
              <span className="rounded-full bg-slate-700 px-1.5 text-xs text-slate-400">
                {node.count}
              </span>
            </button>
            {expandedGroups.has(node.group1) &&
              Object.entries(node.group2s).map(([g2, g2data]) => (
                <button
                  key={g2}
                  onClick={() => {
                    setSelectedGroup1(node.group1)
                    setSelectedGroup2(g2)
                  }}
                  className={`ml-4 flex w-full items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-colors ${
                    selectedGroup2 === g2
                      ? 'bg-sky-600/20 text-sky-300'
                      : 'text-slate-400 hover:bg-slate-800'
                  }`}
                >
                  <span className="flex-1 truncate text-left">{g2}</span>
                  <span className="rounded-full bg-slate-700 px-1.5 text-xs text-slate-500">
                    {g2data.count}
                  </span>
                </button>
              ))}
          </div>
        ))}
        <button
          onClick={() => {
            setSelectedGroup1(null)
            setSelectedGroup2(null)
            setShowUnmapped(true)
          }}
          className={`mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
            showUnmapped ? 'bg-amber-600/20 text-amber-300' : 'text-amber-400 hover:bg-slate-800'
          }`}
        >
          <AlertCircle className="h-3.5 w-3.5" />
          Unmapped
        </button>
      </aside>

      {/* Right Panel: Grid */}
      <div className="flex flex-1 flex-col gap-4 overflow-hidden">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">Components</h1>
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
            <select
              value={filterQC}
              onChange={(e) => setFilterQC(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value="">All QC Status</option>
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
              <option value="modified">Modified</option>
            </select>
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

        <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading...</div>
          ) : components.length === 0 ? (
            <div className="py-16 text-center text-slate-500">
              No components found. Trigger extraction to begin.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase">
                  <th className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedIds(new Set(components.map((c) => c.id)))
                        } else {
                          setSelectedIds(new Set())
                        }
                      }}
                      checked={selectedIds.size === components.length && components.length > 0}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </th>
                  <th className="px-4 py-3">Component</th>
                  <th className="px-4 py-3">Maker</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Specification</th>
                  <th className="px-4 py-3">Page</th>
                  <th className="px-4 py-3">Confidence</th>
                  <th className="px-4 py-3">Critical</th>
                  <th className="px-4 py-3">QC Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {components.map((comp) => (
                  <tr
                    key={comp.id}
                    className={`hover:bg-slate-800/50 transition-colors ${
                      selectedIds.has(comp.id) ? 'bg-sky-900/10' : ''
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(comp.id)}
                        onChange={() => toggleSelect(comp.id)}
                        className="h-3.5 w-3.5 rounded"
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-slate-200">{comp.component_name}</p>
                      <p className="text-xs text-slate-500">
                        {comp.group1} › {comp.group2} › {comp.main_machinery}
                      </p>
                    </td>
                    <td className="px-4 py-2.5 text-slate-300">{comp.maker ?? '—'}</td>
                    <td className="px-4 py-2.5 text-slate-300">{comp.model ?? '—'}</td>
                    <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate">
                      {comp.specification ?? '—'}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">{comp.page_reference ?? '—'}</td>
                    <td className="px-4 py-2.5">
                      {comp.confidence_score !== null ? (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            comp.confidence_score >= 85
                              ? 'bg-green-700 text-green-100'
                              : comp.confidence_score >= 60
                              ? 'bg-amber-700 text-amber-100'
                              : 'bg-red-700 text-red-100'
                          }`}
                        >
                          {comp.confidence_score}%
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {comp.is_critical ? (
                        <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">
                          Critical
                        </span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          QC_COLORS[comp.qc_status] ?? 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {comp.qc_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

export default ComponentReview

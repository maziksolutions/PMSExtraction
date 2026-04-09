import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  RefreshCw,
  Plus,
  ChevronDown,
  ChevronRight,
  BookOpen,
  CheckCircle,
  XCircle,
  Search,
} from 'lucide-react'
import apiClient from '@/api/client'
import JobRanksLibrary from '@/pages/JobRanksLibrary'

// ─── Interfaces ───────────────────────────────────────────────────────────────

type EntityType = 'component' | 'job' | 'spare'
type GlobalSection = EntityType | 'rank'

interface GlobalLibraryEntry {
  id: string
  canonical_data: Record<string, unknown>
  occurrence_count: number
  source_vessels: string[]
  first_seen_at: string
}

interface PopulateResult {
  added: number
  duplicates: number
}

const ENTITY_OPTIONS: { value: EntityType; label: string }[] = [
  { value: 'component', label: 'Components' },
  { value: 'job', label: 'Jobs' },
  { value: 'spare', label: 'Spares' },
]

const SECTION_OPTIONS: { value: GlobalSection; label: string }[] = [
  { value: 'component', label: 'Components' },
  { value: 'job', label: 'Jobs' },
  { value: 'spare', label: 'Spares' },
  { value: 'rank', label: 'Ranks' },
]

const ENTITY_DESCRIPTION: Record<GlobalSection, string> = {
  component: 'Canonical component definitions aggregated across all vessels',
  job: 'Standardised maintenance job definitions from all vessel data',
  spare: 'Global spare parts catalogue built from vessel-level extractions',
  rank: 'Performing and verifying rank options shared across jobs and standard job libraries',
}
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
const SORT_OPTIONS = [
  { value: 'occurrence_count', label: 'Occurrences' },
  { value: 'first_seen_at', label: 'First Seen' },
  { value: 'created_at', label: 'Newest Added' },
]

// ─── Populate Panel ───────────────────────────────────────────────────────────

interface PopulatePanelProps {
  activeEntity: EntityType
  onEntityChange: (e: EntityType) => void
}

const PopulatePanel: React.FC<PopulatePanelProps> = ({ activeEntity, onEntityChange }) => {
  const [vesselId, setVesselId] = useState('')
  const [selectedEntity, setSelectedEntity] = useState<EntityType>(activeEntity)
  const [result, setResult] = useState<PopulateResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const populateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/api/v1/library/global/${selectedEntity}/populate`, {
        vessel_id: vesselId,
      })
      return res.data as PopulateResult
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      onEntityChange(selectedEntity)
    },
    onError: () => {
      setError('Failed to populate library. Check the vessel ID and try again.')
      setResult(null)
    },
  })

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-slate-300 mb-4">Populate from Vessel</h2>
      <div className="flex flex-wrap items-start gap-3">
        {/* Vessel ID */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Vessel ID</label>
          <input
            type="text"
            value={vesselId}
            onChange={(e) => { setVesselId(e.target.value); setResult(null); setError(null) }}
            placeholder="e.g. VES-001"
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm w-52"
          />
        </div>

        {/* Entity type */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Entity Type</label>
          <select
            value={selectedEntity}
            onChange={(e) => setSelectedEntity(e.target.value as EntityType)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-sky-500 text-sm"
          >
            {ENTITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Button */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-transparent select-none">Action</label>
          <button
            onClick={() => populateMutation.mutate()}
            disabled={!vesselId.trim() || populateMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50 text-sm font-medium h-[38px]"
          >
            {populateMutation.isPending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Populate
          </button>
        </div>

        {/* Result */}
        {result && (
          <div className="flex items-center gap-4 self-end pb-0.5">
            <span className="inline-flex items-center gap-1.5 text-emerald-400 text-sm">
              <CheckCircle className="w-4 h-4" />
              <strong>{result.added}</strong> added
            </span>
            <span className="text-slate-400 text-sm">
              <strong>{result.duplicates}</strong> duplicates skipped
            </span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 self-end pb-0.5 text-red-400 text-sm">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Library Table ────────────────────────────────────────────────────────────

interface LibraryTableProps {
  entityType: EntityType
}

const LibraryTable: React.FC<LibraryTableProps> = ({ entityType }) => {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('occurrence_count')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const { data, isLoading } = useQuery({
    queryKey: ['library', 'global-standalone', entityType, search, sortBy, sortOrder, page, pageSize],
    queryFn: async () => {
      const res = await apiClient.get(`/api/v1/library/global/${entityType}`, {
        params: {
          search: search || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
          page,
          page_size: pageSize,
        },
      })
      return res.data
    },
  })
  const entries: GlobalLibraryEntry[] = data?.items ?? data ?? []
  const total = data?.total ?? entries.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  React.useEffect(() => {
    setPage(1)
  }, [entityType, search, sortBy, sortOrder, pageSize])

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center space-y-3">
          <RefreshCw className="w-7 h-7 animate-spin text-sky-400 mx-auto" />
          <p className="text-slate-400 text-sm">Loading {entityType}s...</p>
        </div>
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
        <BookOpen className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <p className="text-slate-400 font-medium">No {entityType}s in global library</p>
        <p className="text-slate-500 text-sm mt-1">
          Use the "Populate from Vessel" panel above to import data.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${entityType} library...`}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="asc">Sort A-Z / Low-High</option>
          <option value="desc">Sort Z-A / High-Low</option>
        </select>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-300 capitalize">{entityType} Library</span>
        <span className="text-xs text-slate-500">{total} entries</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-900/50">
              <th className="text-left px-4 py-3 text-slate-400 font-medium w-8" />
              <th className="text-left px-4 py-3 text-slate-400 font-medium">Canonical Data</th>
              <th className="text-left px-4 py-3 text-slate-400 font-medium">Occurrences</th>
              <th className="text-left px-4 py-3 text-slate-400 font-medium">Source Vessels</th>
              <th className="text-left px-4 py-3 text-slate-400 font-medium">First Seen</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const isExpanded = expandedRows.has(entry.id)
              const dataKeys = Object.keys(entry.canonical_data)
              const previewKey = dataKeys[0]
              const previewValue = previewKey ? String(entry.canonical_data[previewKey]) : ''

              return (
                <tr
                  key={entry.id}
                  className="border-b border-slate-700/50 hover:bg-slate-700/20 transition-colors align-top"
                >
                  <td className="px-4 py-3 pt-3.5">
                    <button
                      onClick={() => toggleRow(entry.id)}
                      className="text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 max-w-lg">
                    {isExpanded ? (
                      <div className="space-y-1.5 py-1">
                        {dataKeys.map((key) => (
                          <div key={key} className="flex gap-3 text-xs">
                            <span className="text-slate-500 font-semibold w-36 flex-shrink-0 capitalize">
                              {key.replace(/_/g, ' ')}:
                            </span>
                            <span className="text-slate-300 break-all">
                              {String(entry.canonical_data[key])}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm">
                        {previewKey && (
                          <span>
                            <span className="text-slate-500 text-xs capitalize">
                              {previewKey.replace(/_/g, ' ')}:{' '}
                            </span>
                            <span className="text-slate-200">
                              {previewValue.slice(0, 90)}
                              {previewValue.length > 90 ? '…' : ''}
                            </span>
                          </span>
                        )}
                        {dataKeys.length > 1 && (
                          <span className="text-slate-600 text-xs ml-2">
                            +{dataKeys.length - 1} more field{dataKeys.length - 1 > 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2.5 py-1 bg-sky-900/40 text-sky-400 text-xs rounded-full border border-sky-600/40 font-medium">
                      {entry.occurrence_count}&times;
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    <div className="flex flex-col gap-1">
                      <span>
                        {entry.source_vessels.length} vessel
                        {entry.source_vessels.length !== 1 ? 's' : ''}
                      </span>
                      {isExpanded && entry.source_vessels.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {entry.source_vessels.map((v) => (
                            <span
                              key={v}
                              className="px-1.5 py-0.5 bg-slate-700 text-slate-300 text-xs rounded"
                            >
                              {v}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                    {new Date(entry.first_seen_at).toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>{total} total entries</span>
          <span>·</span>
          <span>Show</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded border border-slate-600 bg-slate-700 px-2 py-0.5 text-xs text-white"
          >
            {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
          <span>per page</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            disabled={page === 1}
            className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            disabled={page >= totalPages}
            className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const GlobalLibrary: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialSection = (searchParams.get('section') ?? '').toLowerCase()
  const [activeEntity, setActiveEntity] = useState<GlobalSection>(
    initialSection === 'ranks' || initialSection === 'rank'
      ? 'rank'
      : (ENTITY_OPTIONS.some((option) => option.value === initialSection) ? (initialSection as EntityType) : 'component')
  )

  useEffect(() => {
    const sectionParam = (searchParams.get('section') ?? '').toLowerCase()
    const nextSection: GlobalSection =
      sectionParam === 'ranks' || sectionParam === 'rank'
        ? 'rank'
        : (ENTITY_OPTIONS.some((option) => option.value === sectionParam) ? (sectionParam as EntityType) : 'component')
    if (nextSection !== activeEntity) {
      setActiveEntity(nextSection)
    }
  }, [searchParams])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    if (activeEntity === 'component') {
      next.delete('section')
    } else if (activeEntity === 'rank') {
      next.set('section', 'ranks')
    } else {
      next.set('section', activeEntity)
    }
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true })
    }
  }, [activeEntity, searchParams, setSearchParams])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <BookOpen className="w-7 h-7 text-sky-400" />
          Global Library
        </h1>
        <p className="text-slate-400 mt-1">{ENTITY_DESCRIPTION[activeEntity]}</p>
      </div>

      {/* Populate Panel */}
      {activeEntity !== 'rank' && (
        <PopulatePanel activeEntity={activeEntity} onEntityChange={(value) => setActiveEntity(value)} />
      )}

      {/* Tab Bar */}
      <div className="flex gap-1 border-b border-slate-700">
        {SECTION_OPTIONS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setActiveEntity(value)}
            className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeEntity === value
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-white hover:border-slate-500'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeEntity === 'rank' ? (
        <JobRanksLibrary embedded />
      ) : (
        <LibraryTable entityType={activeEntity} />
      )}
    </div>
  )
}

export default GlobalLibrary

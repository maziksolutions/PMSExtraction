import React, { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Upload,
  Plus,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Layers,
  BookOpen,
  GitMerge,
  RefreshCw,
  FileDown,
  Trash2,
  Search,
  Wrench,
} from 'lucide-react'
import apiClient from '@/api/client'
import JobRanksLibrary from '@/pages/JobRanksLibrary'

// ─── Interfaces ───────────────────────────────────────────────────────────────

interface ComponentStructureNode {
  id: string
  group1_code: string
  group1_name: string
  group2_code: string
  group2_name: string
  machinery_code: string
  machinery_name: string
  component_code?: string
  component_name?: string
  component_type?: string
  is_critical: boolean
  criticality?: string
  status: 'active' | 'pending_approval'
}

interface ApprovalRequest {
  id: string
  node: ComponentStructureNode
  requested_by: string
  requested_at: string
  reason?: string
}

interface GlobalLibraryEntry {
  id: string
  canonical_data: Record<string, unknown>
  occurrence_count: number
  source_vessels: string[]
  first_seen_at: string
}

interface ImportResult {
  imported: number
  version: string
}

interface PopulateResult {
  added: number
  duplicates: number
}

interface AddNodeForm {
  group1_code: string
  group1_name: string
  group2_code: string
  group2_name: string
  machinery_code: string
  machinery_name: string
  component_code: string
  component_name: string
  component_type: string
  is_critical: boolean
}

const EMPTY_NODE_FORM: AddNodeForm = {
  group1_code: '',
  group1_name: '',
  group2_code: '',
  group2_name: '',
  machinery_code: '',
  machinery_name: '',
  component_code: '',
  component_name: '',
  component_type: '',
  is_critical: false,
}

type MainTab = 'structure' | 'global' | 'matches'
type GlobalEntity = 'component' | 'job' | 'spare'

// ─── Component Structure Tab ──────────────────────────────────────────────────

const PAGE_SIZE_OPTIONS = [100, 200, 500, 1000]
const COMPONENT_STRUCTURE_SORT_OPTIONS = [
  { value: 'group1_name', label: 'Category' },
  { value: 'group2_name', label: 'Sub Category' },
  { value: 'machinery_name', label: 'Machinery' },
  { value: 'component_name', label: 'Component Name' },
  { value: 'component_code', label: 'Component Code' },
  { value: 'component_type', label: 'Component Type' },
  { value: 'criticality', label: 'Criticality' },
  { value: 'status', label: 'Status' },
]
const MAKER_MODEL_SORT_OPTIONS = [
  { value: 'maker', label: 'Maker' },
  { value: 'model', label: 'Model' },
  { value: 'component_category', label: 'Category' },
  { value: 'created_at', label: 'Newest Added' },
]
const GLOBAL_LIBRARY_SORT_OPTIONS = [
  { value: 'occurrence_count', label: 'Occurrences' },
  { value: 'first_seen_at', label: 'First Seen' },
  { value: 'created_at', label: 'Newest Added' },
]
const MANUAL_MATCH_SORT_OPTIONS = [
  { value: 'match_score', label: 'Match Score' },
  { value: 'match_confidence', label: 'Confidence' },
  { value: 'source_manual_name', label: 'Source Manual' },
  { value: 'matched_manual_name', label: 'Matched Manual' },
  { value: 'matched_vessel_name', label: 'Matched Vessel' },
]

const ComponentStructureTab: React.FC = () => {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [selectedVesselTypeId, setSelectedVesselTypeId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('group1_name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [showAddTypeModal, setShowAddTypeModal] = useState(false)
  const [newTypeName, setNewTypeName] = useState('')
  const [addTypeError, setAddTypeError] = useState('')

  // Vessel types list
  const { data: vtData, isLoading: vtLoading, error: vtError } = useQuery({
    queryKey: ['library', 'vessel-types'],
    queryFn: async () => {
      const res = await apiClient.get('/library/vessel-types')
      return res.data
    },
    retry: 3,
    retryDelay: 2000,
  })
  const vesselTypes: { id: string; name: string; is_system: boolean; component_count: number }[] = vtData?.items ?? []

  // Auto-select first vessel type
  React.useEffect(() => {
    if (!selectedVesselTypeId && vesselTypes.length > 0) {
      setSelectedVesselTypeId(vesselTypes[0].id)
    }
  }, [vesselTypes])

  // Components for selected vessel type
  const { data: pageData, isLoading } = useQuery({
    queryKey: ['library', 'component-structure', selectedVesselTypeId, search, sortBy, sortOrder, page, pageSize],
    queryFn: async () => {
      if (!selectedVesselTypeId) return { items: [], total: 0 }
      const res = await apiClient.get('/library/component-structure', {
        params: {
          vessel_type_id: selectedVesselTypeId,
          search: search || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
          page,
          page_size: pageSize,
        },
      })
      return res.data
    },
    enabled: !!selectedVesselTypeId,
  })
  const nodes: ComponentStructureNode[] = pageData?.items ?? []
  const total: number = pageData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  React.useEffect(() => {
    setPage(1)
  }, [selectedVesselTypeId, search, sortBy, sortOrder, pageSize])

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post(
        `/library/component-structure/import?vessel_type_id=${selectedVesselTypeId ?? ''}`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return res.data as ImportResult
    },
    onSuccess: (data) => {
      setImportResult(data)
      setImportError(null)
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] }); setPage(1)
      queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Unknown error'
      setImportError(`Import failed: ${detail}`)
    },
  })

  const createVesselTypeMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await apiClient.post('/library/vessel-types', { name })
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })
      setSelectedVesselTypeId(data.id)
      setShowAddTypeModal(false)
      setNewTypeName('')
      setAddTypeError('')
    },
    onError: (err: any) => {
      setAddTypeError(err?.response?.data?.detail ?? 'Failed to create vessel type')
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!selectedVesselTypeId) { setImportError('Please select a vessel type first'); return }
    const file = e.target.files?.[0]
    if (file) { importMutation.mutate(file); e.target.value = '' }
  }

  const selectedType = vesselTypes.find(vt => vt.id === selectedVesselTypeId)

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* Left: Vessel Type list */}
      <div className="w-60 shrink-0 rounded-xl border border-slate-800 bg-slate-900 flex flex-col">
        <div className="flex items-center justify-between px-3 py-3 border-b border-slate-800">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Vessel Types</p>
          <button
            onClick={() => setShowAddTypeModal(true)}
            className="rounded p-1 text-slate-500 hover:text-sky-400 hover:bg-slate-800"
            title="Add vessel type"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {vtLoading ? (
            <div className="py-8 text-center text-slate-600 text-xs">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1" />
              Loading...
            </div>
          ) : vtError ? (
            <div className="py-6 text-center space-y-2 px-2">
              <p className="text-red-400 text-xs">Failed to load vessel types.</p>
              <p className="text-slate-600 text-xs">{(vtError as any)?.response?.data?.detail ?? 'Check server logs'}</p>
              <button
                onClick={() => queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })}
                className="text-xs text-sky-400 hover:text-sky-300 underline"
              >
                Retry
              </button>
            </div>
          ) : vesselTypes.length === 0 ? (
            <div className="py-6 text-center space-y-2">
              <p className="text-slate-500 text-xs">No vessel types found.</p>
              <button
                onClick={() => queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })}
                className="text-xs text-sky-400 hover:text-sky-300 underline"
              >
                Retry
              </button>
            </div>
          ) : vesselTypes.map((vt) => (
            <button
              key={vt.id}
              onClick={() => { setSelectedVesselTypeId(vt.id); setPage(1) }}
              className={`w-full flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
                selectedVesselTypeId === vt.id
                  ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                  : 'border border-transparent text-[#72243e] hover:bg-[#fff3f7] hover:text-[#4b1528]'
              }`}
            >
              <span className="flex-1 truncate">{vt.name}</span>
              <span
                className={`rounded-full px-1.5 py-0.5 text-xs shrink-0 ${
                  selectedVesselTypeId === vt.id
                    ? 'bg-[#fff3f7] text-[#8c2f52]'
                    : 'bg-slate-800 text-slate-500'
                }`}
              >
                {vt.component_count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Right: Components for selected vessel type */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        {/* Header row */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">
              {selectedType ? selectedType.name : 'Select a vessel type'}
            </h2>
            {selectedType && (
              <p className="text-xs text-slate-500">{total} components</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input ref={fileInputRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={handleFileChange} />
            <a
              href={`${apiClient.defaults.baseURL}/library/component-structure/template`}
              download="component_library_template.xlsx"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300 hover:text-white rounded-lg transition-colors text-sm"
            >
              <FileDown className="w-3.5 h-3.5" />
              Template
            </a>
            <button
              onClick={() => {
                if (!selectedVesselTypeId) { setImportError('Select a vessel type first'); return }
                fileInputRef.current?.click()
              }}
              disabled={importMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50 text-sm"
            >
              {importMutation.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
              Import Excel
            </button>
          </div>
        </div>

        {selectedVesselTypeId && (
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-64">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search component hierarchy..."
                className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              {COMPONENT_STRUCTURE_SORT_OPTIONS.map((option) => (
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
        )}

        {/* Banners */}
        {importResult && (
          <div className="flex items-center gap-3 p-3 bg-emerald-900/40 border border-emerald-600/50 rounded-lg text-sm">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-emerald-300">Successfully imported <strong>{importResult.imported}</strong> components (version {importResult.version})</span>
            <button onClick={() => setImportResult(null)} className="ml-auto text-emerald-600 hover:text-emerald-300"><XCircle className="w-4 h-4" /></button>
          </div>
        )}
        {importError && (
          <div className="flex items-center gap-3 p-3 bg-red-900/40 border border-red-600/50 rounded-lg text-sm">
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span className="text-red-300">{importError}</span>
            <button onClick={() => setImportError(null)} className="ml-auto text-red-600 hover:text-red-300"><XCircle className="w-4 h-4" /></button>
          </div>
        )}

        {/* Table */}
        {!selectedVesselTypeId ? (
          <div className="flex-1 flex items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900">
            <p className="text-slate-500 text-sm">Select a vessel type from the left panel</p>
          </div>
        ) : (
          <div className="flex-1 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden flex flex-col">
            <div className="flex-1 overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50 sticky top-0">
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Hierarchy Code</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Category</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Type</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Code</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Name</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Critical</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />Loading...
                    </td></tr>
                  ) : nodes.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                      No components yet. Import an Excel file to populate this vessel type.
                    </td></tr>
                  ) : (
                    nodes.map((node) => (
                      <tr key={node.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{(node as any).machinery_code || (node as any).group1_code || '—'}</td>
                        <td className="px-4 py-2.5 text-slate-200 text-xs">{node.group1_name}</td>
                        <td className="px-4 py-2.5 text-slate-300 text-xs">{node.group2_name}</td>
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{node.component_code || '—'}</td>
                        <td className="px-4 py-2.5 text-slate-200 text-sm">{node.component_name || '—'}</td>
                        <td className="px-4 py-2.5">
                          {(() => {
                            const crit = (node as any).criticality ?? (node.is_critical ? 'critical' : 'non_critical')
                            if (crit === 'critical') return <span className="text-xs font-medium text-red-400">Critical</span>
                            if (crit === 'essential') return <span className="text-xs font-medium text-amber-400">Essential</span>
                            return <span className="text-xs text-slate-500">Non Critical</span>
                          })()}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${
                            node.status === 'active'
                              ? 'bg-emerald-900/40 text-emerald-400 border-emerald-600/40'
                              : 'bg-amber-900/40 text-amber-400 border-amber-600/40'
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${node.status === 'active' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                            {node.status === 'active' ? 'Active' : 'Pending'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2.5 shrink-0">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span>{total} total</span>
                <span>·</span>
                <span>Show</span>
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
                  className="bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-white text-xs"
                >
                  {PAGE_SIZE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <span>per page</span>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">← Prev</button>
                <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                  className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">Next →</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Add Vessel Type Modal */}
      {showAddTypeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 space-y-4">
            <h3 className="text-lg font-semibold text-white">Add Vessel Type</h3>
            <input
              autoFocus
              type="text"
              value={newTypeName}
              onChange={(e) => setNewTypeName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && newTypeName.trim()) createVesselTypeMutation.mutate(newTypeName.trim()) }}
              placeholder="e.g. VLCC, Container Ship, RoRo..."
              className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            {addTypeError && <p className="text-red-400 text-sm">{addTypeError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setShowAddTypeModal(false); setNewTypeName(''); setAddTypeError('') }}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
              <button
                onClick={() => { if (newTypeName.trim()) createVesselTypeMutation.mutate(newTypeName.trim()) }}
                disabled={!newTypeName.trim() || createVesselTypeMutation.isPending}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-sm disabled:opacity-50"
              >
                {createVesselTypeMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Maker / Model Library Sub-tab ───────────────────────────────────────────

const MakerModelTab: React.FC = () => {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [sortBy, setSortBy] = useState('maker')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [importMsg, setImportMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [newMaker, setNewMaker] = useState('')
  const [newModel, setNewModel] = useState('')
  const [showAddRow, setShowAddRow] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['maker-models', search, sortBy, sortOrder, page, pageSize],
    queryFn: () =>
      apiClient.get('/maker-models', {
        params: {
          search: search || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
          page,
          page_size: pageSize,
        },
      }).then(r => r.data),
  })
  const items: { id: string; maker: string; model: string | null; component_category: string | null }[] = data?.items ?? []
  const total: number = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  React.useEffect(() => {
    setPage(1)
  }, [search, sortBy, sortOrder, pageSize])

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return apiClient.post('/maker-models/import', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
    },
    onSuccess: (d) => {
      setImportMsg({ type: 'ok', text: `Imported ${d.imported} entries (${d.skipped} duplicates skipped).` })
      queryClient.invalidateQueries({ queryKey: ['maker-models'] })
    },
    onError: (err: any) => {
      setImportMsg({ type: 'err', text: err?.response?.data?.detail ?? err?.message ?? 'Import failed' })
    },
  })

  const addMutation = useMutation({
    mutationFn: () => apiClient.post('/maker-models', { maker: newMaker.trim(), model: newModel.trim() || null }).then(r => r.data),
    onSuccess: (_data, _vars, _ctx) => {
      const label = `${newMaker.trim()}${newModel.trim() ? ` / ${newModel.trim()}` : ''}`
      queryClient.invalidateQueries({ queryKey: ['maker-models'] })
      setNewMaker(''); setNewModel(''); setShowAddRow(false)
      setImportMsg({ type: 'ok', text: `Added "${label}" to the library.` })
    },
    onError: (err: any) => {
      setImportMsg({ type: 'err', text: err?.response?.data?.detail ?? err?.message ?? 'Failed to add entry. Please try again.' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/maker-models/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['maker-models'] }),
  })

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search maker or model..."
            className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
        >
          {MAKER_MODEL_SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
        >
          <option value="asc">Sort A-Z / Low-High</option>
          <option value="desc">Sort Z-A / High-Low</option>
        </select>
        <button
          onClick={() => setShowAddRow(r => !r)}
          className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700"
        >
          <Plus className="h-4 w-4" /> Add Entry
        </button>
        <input ref={fileInputRef} type="file" accept=".xlsx,.csv" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) { importMutation.mutate(f); e.target.value = '' } }} />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={importMutation.isPending}
          className="flex items-center gap-2 rounded-lg bg-sky-700 px-3 py-2 text-sm text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {importMutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Import Excel / CSV
        </button>
      </div>

      {/* Import hint */}
      <p className="text-xs text-slate-500">
        Excel/CSV columns: <span className="text-slate-400 font-mono">Maker</span> (required), <span className="text-slate-400 font-mono">Model</span> (optional), <span className="text-slate-400 font-mono">Category</span> (optional). Duplicates are skipped automatically.
      </p>

      {/* Result banner */}
      {importMsg && (
        <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${importMsg.type === 'ok' ? 'border-emerald-600/40 bg-emerald-900/30 text-emerald-300' : 'border-red-600/40 bg-red-900/30 text-red-300'}`}>
          {importMsg.type === 'ok' ? <CheckCircle className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
          {importMsg.text}
          <button onClick={() => setImportMsg(null)} className="ml-auto text-slate-500 hover:text-slate-300">✕</button>
        </div>
      )}

      {/* Add row inline */}
      {showAddRow && (
        <div className="flex items-center gap-2 rounded-lg border border-sky-700/40 bg-slate-800 px-4 py-3">
          <input type="text" value={newMaker} onChange={e => setNewMaker(e.target.value)}
            placeholder="Maker name *" className="flex-1 rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none" />
          <input type="text" value={newModel} onChange={e => setNewModel(e.target.value)}
            placeholder="Model (optional)" className="flex-1 rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none" />
          <button
            onClick={() => addMutation.mutate()}
            disabled={!newMaker.trim() || addMutation.isPending}
            className="rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500 disabled:opacity-50"
          >Add</button>
          <button onClick={() => setShowAddRow(false)} className="text-slate-500 hover:text-slate-300 text-xs">Cancel</button>
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-slate-700 bg-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-900/50">
              <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Maker</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Model</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Category</th>
              <th className="px-4 py-3 w-10" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={4} className="py-10 text-center text-slate-500">
                <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2" />Loading...
              </td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={4} className="py-10 text-center text-slate-500">
                No entries yet. Import an Excel/CSV file or add entries manually.
              </td></tr>
            ) : items.map(item => (
              <tr key={item.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="px-4 py-2.5 text-slate-200 font-medium">{item.maker}</td>
                <td className="px-4 py-2.5 text-slate-400">{item.model ?? <span className="text-slate-600">—</span>}</td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">{item.component_category ?? '—'}</td>
                <td className="px-4 py-2.5">
                  <button onClick={() => deleteMutation.mutate(item.id)}
                    className="text-slate-600 hover:text-red-400 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* Pagination */}
        {(total > 0 || totalPages > 1) && (
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
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">← Prev</button>
              <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Global Libraries Tab ─────────────────────────────────────────────────────

const GLOBAL_ENTITY_LABELS: Record<GlobalEntity, string> = {
  component: 'Components',
  job: 'Jobs',
  spare: 'Spares',
}

const GLOBAL_LIBRARY_PREFERRED_KEYS: Record<GlobalEntity, string[]> = {
  component: ['component_name', 'main_machinery', 'group1', 'group2', 'maker', 'model'],
  job: ['job_name', 'job_description', 'job_code', 'frequency', 'frequency_type', 'cms_id'],
  spare: ['part_name', 'part_number', 'spare_maker', 'spare_model', 'spare_assembly', 'assembly_description'],
}

const orderCanonicalKeys = (entity: GlobalEntity, data: Record<string, unknown>) => {
  const keys = Object.keys(data)
  const preferred = GLOBAL_LIBRARY_PREFERRED_KEYS[entity] ?? []
  const preferredKeys = preferred.filter((key) => keys.includes(key))
  const remainingKeys = keys.filter((key) => !preferredKeys.includes(key)).sort()
  return [...preferredKeys, ...remainingKeys]
}

const GlobalLibrariesTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeSub, setActiveSub] = useState<'makers' | 'component' | 'job' | 'spare' | 'rank'>('makers')
  const [activeEntity, setActiveEntity] = useState<GlobalEntity>('component')
  const [populateVesselId, setPopulateVesselId] = useState('')
  const [populateResult, setPopulateResult] = useState<PopulateResult | null>(null)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('occurrence_count')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [libraryActionMessage, setLibraryActionMessage] = useState<string | null>(null)

  const { data: entriesData, isLoading } = useQuery({
    queryKey: ['library', 'global', activeEntity, search, sortBy, sortOrder, page, pageSize],
    queryFn: async () => {
      const res = await apiClient.get(`/library/global/${activeEntity}`, {
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
    enabled: activeSub !== 'makers',
  })
  const entries: GlobalLibraryEntry[] = entriesData?.items ?? entriesData ?? []
  const total = entriesData?.total ?? entries.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const deleteEntryMutation = useMutation({
    mutationFn: (entryId: string) => apiClient.delete(`/library/global/${activeEntity}/${entryId}`).then((r) => r.data),
    onSuccess: () => {
      setLibraryActionMessage('Removed entry from the global library.')
      queryClient.invalidateQueries({ queryKey: ['library', 'global'] })
    },
  })

  React.useEffect(() => {
    setPage(1)
  }, [activeSub, activeEntity, search, sortBy, sortOrder, pageSize])

  const populateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/library/global/${activeEntity}/populate`, { vessel_id: populateVesselId })
      return res.data as PopulateResult
    },
    onSuccess: (data) => setPopulateResult(data),
  })

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const SUB_TABS = [
    { key: 'makers' as const, label: 'Maker / Model Library', icon: <Wrench className="w-4 h-4" /> },
    { key: 'component' as const, label: 'Components', icon: null },
    { key: 'job' as const, label: 'Jobs', icon: null },
    { key: 'spare' as const, label: 'Spares', icon: null },
    { key: 'rank' as const, label: 'Ranks', icon: null },
  ]

  return (
    <div className="space-y-6">
      {/* Sub-tabs */}
      <div className="flex gap-1 bg-slate-900/50 p-1 rounded-lg w-fit">
        {SUB_TABS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => {
              setActiveSub(key)
              if (key !== 'makers' && key !== 'rank') setActiveEntity(key as GlobalEntity)
              setPopulateResult(null)
              setPage(1)
            }}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeSub === key
                ? 'border border-[#d4537e] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.22)]'
                : 'border border-transparent text-[#72243e] hover:border-[#ed93b1] hover:bg-[#fff3f7] hover:text-[#4b1528]'
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Maker/Model sub-tab */}
      {activeSub === 'makers' && <MakerModelTab />}

      {/* Rank library sub-tab */}
      {activeSub === 'rank' && <JobRanksLibrary embedded />}

      {/* Component / Job / Spare cross-project global library */}
      {activeSub !== 'makers' && activeSub !== 'rank' && (
        <>
          {libraryActionMessage && (
            <div className="rounded-lg border border-emerald-600/40 bg-emerald-900/30 px-4 py-3 text-sm text-emerald-300">
              {libraryActionMessage}
            </div>
          )}
          {/* Populate from Vessel */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-1">Populate from Vessel</h3>
            <p className="mb-3 text-xs text-slate-400">
              Accepted QC records now auto-sync into Global Libraries. Use this only to backfill a specific vessel on demand.
            </p>
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={populateVesselId}
                onChange={(e) => setPopulateVesselId(e.target.value)}
                placeholder="Enter Vessel ID..."
                className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm w-60"
              />
              <button
                onClick={() => { setPopulateResult(null); populateMutation.mutate() }}
                disabled={!populateVesselId.trim() || populateMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50 text-sm"
              >
                {populateMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Populate
              </button>
              {populateResult && (
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-emerald-400"><strong>{populateResult.added}</strong> added</span>
                  <span className="text-slate-400"><strong>{populateResult.duplicates}</strong> duplicates skipped</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-64">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search ${GLOBAL_ENTITY_LABELS[activeEntity].toLowerCase()} library...`}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
            >
              {GLOBAL_LIBRARY_SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
            >
              <option value="asc">Sort A-Z / Low-High</option>
              <option value="desc">Sort Z-A / High-Low</option>
            </select>
          </div>

          {/* Table */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50">
                    <th className="text-left px-4 py-3 text-slate-400 font-medium w-8" />
                    <th className="text-left px-4 py-3 text-slate-400 font-medium">Canonical Data</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium">Occurrences</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium">Source Vessels</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium">First Seen</th>
                    <th className="px-4 py-3 w-10" />
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />Loading...
                    </td></tr>
                  ) : entries.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                      No {activeSub}s found in global library.
                    </td></tr>
                  ) : entries.map((entry) => {
                    const isExpanded = expandedRows.has(entry.id)
                    const dataKeys = orderCanonicalKeys(activeEntity, entry.canonical_data)
                    const previewKey = dataKeys[0]
                    const previewValue = previewKey ? String(entry.canonical_data[previewKey]) : ''
                    return (
                      <React.Fragment key={entry.id}>
                        <tr className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-3">
                            <button onClick={() => toggleRow(entry.id)} className="text-slate-500 hover:text-slate-300">
                              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            {isExpanded ? (
                              <div className="space-y-1">
                                {dataKeys.map(key => (
                                  <div key={key} className="flex gap-2 text-xs">
                                    <span className="text-slate-500 font-medium w-32 flex-shrink-0">{key}:</span>
                                    <span className="text-slate-300">{String(entry.canonical_data[key])}</span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <span className="text-slate-300">
                                {previewKey && (<>
                                  <span className="text-slate-500 text-xs">{previewKey}: </span>
                                  <span className="text-slate-200">{previewValue.slice(0, 80)}{previewValue.length > 80 ? '…' : ''}</span>
                                </>)}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <span className="inline-flex items-center px-2 py-0.5 bg-sky-900/40 text-sky-400 text-xs rounded-full border border-sky-600/40">
                              {entry.occurrence_count}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-400 text-xs">{entry.source_vessels.length} vessels</td>
                          <td className="px-4 py-3 text-slate-400 text-xs">{new Date(entry.first_seen_at).toLocaleDateString()}</td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => deleteEntryMutation.mutate(entry.id)}
                              className="text-slate-500 transition-colors hover:text-red-400"
                              title="Remove entry"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {(total > 0 || totalPages > 1) && (
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
                  <button onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page === 1}
                    className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40">← Prev</button>
                  <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
                  <button onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))} disabled={page >= totalPages}
                    className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40">Next →</button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Manual Matches Tab ───────────────────────────────────────────────────────

const CONFIDENCE_COLORS: Record<string, string> = {
  exact: 'bg-emerald-700 text-emerald-100',
  high: 'bg-sky-700 text-sky-100',
  medium: 'bg-amber-700 text-amber-100',
  low: 'bg-slate-600 text-slate-200',
}

function formatManualMatchScore(score: unknown): string {
  const numeric = Number(score)
  if (!Number.isFinite(numeric)) return '—'
  if (numeric > 1) return `${Math.round(numeric)}%`
  return `${Math.round(numeric * 100)}%`
}

const ManualMatchesTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedVesselId, setSelectedVesselId] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('match_score')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [runMsg, setRunMsg] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  const vesselsQuery = useQuery({
    queryKey: ['vessels-list-matches'],
    queryFn: () => apiClient.get('/vessels?page=1&page_size=100').then(r => r.data),
  })
  const vessels: { id: string; name: string; imo_number: string }[] = vesselsQuery.data?.items ?? []

  const savedQuery = useQuery({
    queryKey: ['manual-matches', selectedVesselId, search, sortBy, sortOrder, page, pageSize],
    queryFn: () => apiClient.get(`/library/${selectedVesselId}/manuals/matches`, {
      params: {
        search: search || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: pageSize,
      },
    }).then(r => r.data),
    enabled: !!selectedVesselId,
  })
  const savedItems: any[] = savedQuery.data?.items ?? []
  const total = savedQuery.data?.total ?? savedItems.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const reuseMutation = useMutation({
    mutationFn: (matchId: string) =>
      apiClient.post(`/library/${selectedVesselId}/manuals/matches/${matchId}/copy-all`).then(r => r.data),
    onSuccess: (data: any) => {
      setRunMsg(
        `Reused ${data?.copied_components ?? 0} components, ${data?.copied_jobs ?? 0} jobs, and ${data?.copied_spares ?? 0} spares from the matched manual.`
      )
      queryClient.invalidateQueries({ queryKey: ['manual-matches'] })
    },
    onError: (err: any) => {
      setRunMsg(err?.response?.data?.detail ?? err?.message ?? 'Reuse from matched manual failed.')
    },
  })

  const handleFindMatches = async () => {
    if (!selectedVesselId) return
    setIsRunning(true)
    setRunMsg(null)
    try {
      const res = await apiClient.post(`/library/${selectedVesselId}/manuals/find-matches`)
      const data = res.data
      setRunMsg(`Found ${data.total ?? 0} cross-project matches.`)
      setPage(1)
      savedQuery.refetch()
    } catch (err: any) {
      setRunMsg(err?.response?.data?.detail ?? err?.message ?? 'Match search failed.')
    }
    setIsRunning(false)
  }

  React.useEffect(() => {
    setPage(1)
  }, [selectedVesselId, search, sortBy, sortOrder, pageSize])

  return (
    <div className="space-y-4">
      {/* Vessel selector + action */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedVesselId}
          onChange={e => { setSelectedVesselId(e.target.value) }}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none min-w-64"
        >
          <option value="">— Select a vessel —</option>
          {vessels.map(v => (
            <option key={v.id} value={v.id}>{v.name} ({v.imo_number})</option>
          ))}
        </select>
        <button
          onClick={handleFindMatches}
          disabled={!selectedVesselId || isRunning}
          className="flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {isRunning ? <RefreshCw className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
          {isRunning ? 'Searching...' : 'Find Cross-Project Matches'}
        </button>
        {selectedVesselId && !isRunning && (
          <button
            onClick={() => savedQuery.refetch()}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700"
          >
            <RefreshCw className="h-4 w-4" /> Reload Saved
          </button>
        )}
      </div>

      <p className="text-xs text-slate-500">
        Finds manuals from other vessel projects in your organisation that are identical (SHA-256) or have similar filenames (≥60% match). Useful for reusing already-extracted PMS data.
      </p>

      {selectedVesselId && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-64">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search matched manuals or vessels..."
              className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
            />
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
          >
            {MANUAL_MATCH_SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-sky-500 focus:outline-none"
          >
            <option value="asc">Sort A-Z / Low-High</option>
            <option value="desc">Sort Z-A / High-Low</option>
          </select>
        </div>
      )}

      {/* Result message */}
      {runMsg && (
        <div className="rounded-lg border border-sky-700/40 bg-sky-900/20 px-4 py-2 text-sm text-sky-300">
          {runMsg}
        </div>
      )}

      {/* No vessel selected */}
      {!selectedVesselId && (
        <div className="flex flex-col items-center justify-center py-16 space-y-3 text-center">
          <GitMerge className="w-12 h-12 text-slate-600" />
          <p className="text-slate-500">Select a vessel above to find matching manuals across other projects.</p>
        </div>
      )}

      {/* Results table */}
      {selectedVesselId && savedItems.length === 0 && !isRunning && (
        <div className="py-10 text-center text-slate-500 text-sm">
          No matches found yet. Click "Find Cross-Project Matches" to search.
        </div>
      )}

      {savedItems.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-900/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Source Manual</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Matched Manual</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Matched Vessel</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Score</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Confidence</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {savedItems.map((item: any, i: number) => (
                <tr key={item.id ?? `${item.source_manual_id}-${i}`} className="hover:bg-slate-700/30">
                  <td className="px-4 py-2.5 text-slate-200 max-w-xs truncate" title={item.source_manual_name}>
                    {item.source_manual_name}
                  </td>
                  <td className="px-4 py-2.5 text-slate-300 max-w-xs truncate" title={item.matched_manual_name}>
                    {item.matched_manual_name}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400">{item.matched_vessel_name ?? '—'}</td>
                  <td className="px-4 py-2.5 text-slate-300">
                    {formatManualMatchScore(item.match_score)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONFIDENCE_COLORS[item.match_confidence] ?? 'bg-slate-600 text-slate-200'}`}>
                      {item.match_confidence ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => reuseMutation.mutate(String(item.id))}
                      disabled={reuseMutation.isPending}
                      className="rounded-lg bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
                    >
                      {reuseMutation.isPending ? 'Reusing...' : 'Reuse in Vessel'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>{total} total matches</span>
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
              <button onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page === 1}
                className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40">← Prev</button>
              <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
              <button onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))} disabled={page >= totalPages}
                className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40">Next →</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Library Page ────────────────────────────────────────────────────────

const TAB_CONFIG: { key: MainTab; label: string; icon: React.ReactNode }[] = [
  { key: 'structure', label: 'Component Structure', icon: <Layers className="w-4 h-4" /> },
  { key: 'global', label: 'Global Libraries', icon: <BookOpen className="w-4 h-4" /> },
  { key: 'matches', label: 'Manual Matches', icon: <GitMerge className="w-4 h-4" /> },
]

const Library: React.FC = () => {
  const [activeTab, setActiveTab] = useState<MainTab>('structure')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Library Management</h1>
        <p className="text-slate-400 mt-1">
          Manage component structure hierarchy, global libraries, and manual cross-project matches
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 border-b border-slate-700">
        {TAB_CONFIG.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 rounded-t-lg px-5 py-3 text-sm font-semibold border-b-2 transition-colors -mb-px ${
              activeTab === key
                ? 'border-[#d4537e] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                : 'border-transparent text-[#72243e] hover:border-[#ed93b1] hover:bg-[#fff7fa] hover:text-[#4b1528]'
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'structure' && <ComponentStructureTab />}
        {activeTab === 'global' && <GlobalLibrariesTab />}
        {activeTab === 'matches' && <ManualMatchesTab />}
      </div>
    </div>
  )
}

export default Library

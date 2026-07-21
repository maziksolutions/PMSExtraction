import React, { useState, useCallback, useMemo, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  AlertCircle,
  Upload,
  Plus,
  Save,
  Trash2,
  X,
  FileText,
  FolderPlus,
  Wrench,
  RefreshCw,
  FileDown,
  Search,
  FileSearch,
  ArrowRightLeft,
  ExternalLink,
  Copy,
} from 'lucide-react'
import apiClient from '@/api/client'
import { SearchableSelect } from '@/components/SearchableSelect'
import AddComponentModal from '@/components/components/AddComponentModal'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'
import ResizableSplitView from '@/components/layout/ResizableSplitView'
import ResizableRowSplitView from '@/components/layout/ResizableRowSplitView'

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
  location: string | null
  machinery_particulars: string | null
  source_manual_id: string | null
  page_reference: number | null
  confidence_score: number | null
  is_critical: boolean
  criticality: string
  qc_status: string
  is_unmapped: boolean
  job_pages: string | null
  spare_pages: string | null
  pdf_reference: string | null
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

interface TreeNode {
  group1: string
  group2s: Record<string, { mainMachineries: Record<string, number>; count: number }>
  count: number
}

// ---- Add Main Machinery Modal ----
interface AddMachineryModalProps {
  vesselId: string
  onClose: () => void
  onCreated: () => void
  initialGroup1?: string
  initialGroup2?: string
}

function AddMainMachineryModal({ vesselId, onClose, onCreated, initialGroup1, initialGroup2 }: AddMachineryModalProps) {
  const [form, setForm] = useState({
    group1: initialGroup1 ?? '',
    group2: initialGroup2 ?? '',
    main_machinery: '',
  })

  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/components`, {
        group1: form.group1.trim(),
        group2: form.group2.trim(),
        main_machinery: form.main_machinery.trim(),
        component_name: `${form.main_machinery.trim()} System`,
        qc_status: 'pending',
      }).then(r => r.data),
    onSuccess: () => { onCreated(); onClose() },
  })

  const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }))
  const isSubmitDisabled = !form.group1.trim() || !form.group2.trim() || !form.main_machinery.trim() || mutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Add Main Machinery</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Group (Group 1) *</label>
            <input
              value={form.group1}
              onChange={e => set('group1', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. 500 DECK MACHINERY"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Sub-Group (Group 2) *</label>
            <input
              value={form.group2}
              onChange={e => set('group2', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. 510 Anchor Gear"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Main Machinery Name *</label>
            <input
              value={form.main_machinery}
              onChange={e => set('main_machinery', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. Windlass Motor"
              required
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-700 px-6 py-4">
          <button onClick={onClose} className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800">Cancel</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={isSubmitDisabled}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add Main Machinery
          </button>
        </div>
      </div>
    </div>
  )
}


// ---- Copy Components Modal ----
interface CopyModalProps {
  vesselId: string
  selectedIds: Set<string>
  projectManualOptions: string[]
  onClose: () => void
  onCopied: () => void
}

function CopyComponentsModal({ vesselId, selectedIds, projectManualOptions, onClose, onCopied }: CopyModalProps) {
  const [targetPdf, setTargetPdf] = useState('')
  const [targetG1, setTargetG1] = useState('')
  const [targetG2, setTargetG2] = useState('')
  const [targetMM, setTargetMM] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-copy`, {
        ids: Array.from(selectedIds),
        target_pdf_reference: targetPdf,
        target_group1: targetG1.trim() || null,
        target_group2: targetG2.trim() || null,
        target_main_machinery: targetMM.trim() || null,
      }).then(r => r.data),
    onSuccess: () => { onCopied(); onClose() },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Copy Components to Manual</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <p className="text-xs text-slate-300">
            Copying <strong className="text-sky-400">{selectedIds.size}</strong> selected component(s) to another manual reference.
          </p>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Target Manual (PDF Reference) *</label>
            <SearchableSelect
              options={projectManualOptions}
              value={targetPdf}
              onChange={setTargetPdf}
              placeholder="Select target project manual..."
              required
            />
          </div>

          <div className="border-t border-slate-800 pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Optional Hierarchy Overrides</p>
            <div className="space-y-2">
              <input
                value={targetG1}
                onChange={e => setTargetG1(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:border-sky-500 focus:outline-none"
                placeholder="Override Group 1 (optional)"
              />
              <input
                value={targetG2}
                onChange={e => setTargetG2(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:border-sky-500 focus:outline-none"
                placeholder="Override Group 2 (optional)"
              />
              <input
                value={targetMM}
                onChange={e => setTargetMM(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:border-sky-500 focus:outline-none"
                placeholder="Override Main Machinery (optional)"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-slate-700 px-6 py-4">
          <button onClick={onClose} className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800">Cancel</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!targetPdf.trim() || mutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
            Copy Components ({selectedIds.size})
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- Edit row inline ----
interface InlineEdit {
  job_pages?: string
  spare_pages?: string
  pdf_reference?: string
  maker?: string
  model?: string
  serial_number?: string
  location?: string
  machinery_particulars?: string
  criticality?: string
  qc_status?: string
}

const COMP_PAGE_SIZE_OPTIONS = [100, 200, 500, 1000]

const ComponentReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [selectedGroup1, setSelectedGroup1] = useState<string | null>(null)
  const [selectedGroup2, setSelectedGroup2] = useState<string | null>(null)
  const [selectedMachinery, setSelectedMachinery] = useState<string | null>(null)
  const [showUnmapped, setShowUnmapped] = useState(false)
  const [showMappedExtracted, setShowMappedExtracted] = useState(false)
  const [expandedG1, setExpandedG1] = useState<Set<string>>(new Set())
  const [expandedG2, setExpandedG2] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [filterQC, setFilterQC] = useState('')
  const [filterSourceFile, setFilterSourceFile] = useState('')
  const [searchTable, setSearchTable] = useState('')
  const [searchTree, setSearchTree] = useState('')
  const [sortBy, setSortBy] = useState('component_name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showAddMachineryModal, setShowAddMachineryModal] = useState(false)
  const [showCopyModal, setShowCopyModal] = useState(false)
  const [addContext, setAddContext] = useState<{ group1?: string; group2?: string; machinery?: string }>({})
  const [edits, setEdits] = useState<Record<string, InlineEdit>>({})
  const [importResult, setImportResult] = useState<string | null>(null)
  const [showBatchPanel, setShowBatchPanel] = useState(false)
  const [batchFields, setBatchFields] = useState<Record<string, string>>({})
  const [selectedComponent, setSelectedComponent] = useState<Component | null>(null)
  const [mergeSource, setMergeSource] = useState<Component | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const openManualInNewTab = (
    manualId: string | null | undefined,
    name: string | null | undefined,
    pages: string | number | null | undefined
  ) => {
    if (!manualId) return
    const pagesStr = pages == null ? '' : String(pages)
    const nameStr = name || ''
    const url = `/vessels/${vesselId}/manual-preview/${manualId}?name=${encodeURIComponent(nameStr)}&pages=${encodeURIComponent(pagesStr)}`
    window.open(url, '_blank')
  }

  const { data, isLoading } = useQuery({
    queryKey: ['components', vesselId, selectedGroup1, selectedGroup2, selectedMachinery, filterQC, filterSourceFile, showUnmapped, showMappedExtracted, searchTable, sortBy, sortOrder, page, pageSize],
    queryFn: () => {
      const params: Record<string, string | number> = { page, page_size: pageSize, is_unmapped: showUnmapped ? 'true' : 'false' }
      if (showMappedExtracted) params.mapped_extracted = 'true'
      if (selectedGroup1) params.group1 = selectedGroup1
      if (selectedGroup2) params.group2 = selectedGroup2
      if (selectedMachinery) params.main_machinery = selectedMachinery
      if (filterQC) params.qc_status = filterQC
      if (filterSourceFile) params.pdf_reference = filterSourceFile
      if (searchTable) params.search = searchTable
      params.sort_by = sortBy
      params.sort_order = sortOrder
      return apiClient.get(`/vessels/${vesselId}/components`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const manualsQuery = useQuery({
    queryKey: ['vessel-manuals-list', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/manuals`, { params: { page_size: 1000 } }).then((r) => r.data.items as any[]),
    enabled: !!vesselId,
  })

  const sourceFilesQuery = useQuery({
    queryKey: ['component-source-files', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/components/source-files`).then((r) => r.data.items as string[]),
    enabled: !!vesselId,
  })

  // Fetch all components for tree building (large page_size, no filters)
  const allComponentsQuery = useQuery({
    queryKey: ['components-all', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/components`, { params: { page_size: 5000, is_unmapped: 'false' } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const pendingComponentsQuery = useQuery({
    queryKey: ['components', vesselId, 'pending-count'],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/components`, { params: { qc_status: 'pending', page_size: 1 } })
        .then((r) => (r.data.total ?? 0) as number),
    enabled: !!vesselId,
  })
  const pendingCount = pendingComponentsQuery.data

  const projectManualOptions = useMemo<string[]>(() => {
    const list = new Set<string>()
    for (const m of manualsQuery.data ?? []) {
      if (m.original_filename) list.add(m.original_filename)
    }
    for (const s of sourceFilesQuery.data ?? []) {
      if (s) list.add(s)
    }
    return Array.from(list).sort((a, b) => a.localeCompare(b))
  }, [manualsQuery.data, sourceFilesQuery.data])

  const mainMachineryOptions = useMemo<string[]>(() => {
    const set = new Set<string>()
    for (const comp of allComponentsQuery.data?.items ?? []) {
      if (comp.main_machinery) set.add(comp.main_machinery)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [allComponentsQuery.data])

  const makersQuery = useQuery({
    queryKey: ['maker-models', 'makers'],
    queryFn: () => apiClient.get('/maker-models/makers').then(r => r.data),
    staleTime: 60_000,
  })
  const makers: string[] = makersQuery.data?.items ?? []

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['components', vesselId] }); setSelectedIds(new Set()) },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['components', vesselId] }); setSelectedIds(new Set()) },
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-delete`, { ids }).then((r) => r.data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['components', vesselId] }); setSelectedIds(new Set()) },
  })

  const saveMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: InlineEdit }) =>
      apiClient.patch(`/vessels/${vesselId}/components/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      setEdits({})
    },
  })

  const bulkUpdateMutation = useMutation({
    mutationFn: ({ ids, updates }: { ids: string[]; updates: Record<string, string> }) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-update`, { ids, updates }).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      setImportResult(`Batch updated ${data.updated} component(s).`)
      setSelectedIds(new Set())
      setShowBatchPanel(false)
      setBatchFields({})
    },
  })

  const refreshComponentQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
    queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
  }

  const mergeIntoExistingMutation = useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: string; targetId: string }) =>
      apiClient.post(`/vessels/${vesselId}/components/${sourceId}/merge-into`, { target_component_id: targetId }).then((r) => r.data),
    onSuccess: () => {
      refreshComponentQueries()
      setImportResult('Merged extracted component into the selected vessel component.')
      setMergeSource(null)
      setSelectedComponent(null)
    },
  })

  // Reset to page 1 when any filter changes
  React.useEffect(() => { setPage(1) }, [selectedGroup1, selectedGroup2, selectedMachinery, filterQC, filterSourceFile, showUnmapped, showMappedExtracted, searchTable, sortBy, sortOrder, pageSize])

  const handleExcelImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/components/import-excel`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setImportResult(`Imported ${res.data.imported} components (${res.data.skipped} skipped).`)
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
    } catch (err: any) {
      setImportResult(`Import failed: ${err?.response?.data?.detail ?? err?.message}`)
    }
    e.target.value = ''
  }

  const toggleG1 = useCallback((key: string) => {
    setExpandedG1(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }, [])
  const toggleG2 = useCallback((key: string) => {
    setExpandedG2(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }, [])

  const setEdit = (id: string, field: keyof InlineEdit, value: string) => {
    setEdits(prev => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  }

  // Build 3-level sorted tree: group1 → group2 → main_machinery
  const tree = useMemo<TreeNode[]>(() => {
    const allComponents: Component[] = allComponentsQuery.data?.items ?? []
    const map: Record<string, TreeNode> = {}
    for (const comp of allComponents) {
      if (!map[comp.group1]) map[comp.group1] = { group1: comp.group1, group2s: {}, count: 0 }
      map[comp.group1].count++
      if (!map[comp.group1].group2s[comp.group2])
        map[comp.group1].group2s[comp.group2] = { mainMachineries: {}, count: 0 }
      map[comp.group1].group2s[comp.group2].count++
      const mm = comp.main_machinery
      map[comp.group1].group2s[comp.group2].mainMachineries[mm] =
        (map[comp.group1].group2s[comp.group2].mainMachineries[mm] ?? 0) + 1
    }
    // Sort alphabetically at every level
    return Object.values(map).sort((a, b) => a.group1.localeCompare(b.group1))
  }, [allComponentsQuery.data])

  const total: number = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const components: Component[] = data?.items ?? []
  const mappedComponentOptions: Component[] = allComponentsQuery.data?.items ?? []

  React.useEffect(() => {
    if (!components.length) {
      if (selectedComponent && !showUnmapped && !showMappedExtracted) {
        const fallback = mappedComponentOptions.find((component) => component.id === selectedComponent.id)
        if (fallback) setSelectedComponent(fallback)
      }
      return
    }

    if (selectedComponent) {
      const refreshed = components.find((component) => component.id === selectedComponent.id)
      if (refreshed) setSelectedComponent(refreshed)
    }
  }, [components, mappedComponentOptions, selectedComponent, showUnmapped, showMappedExtracted])

  return (
    <>
      {showAddModal && vesselId && (
        <AddComponentModal
          vesselId={vesselId}
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
            queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
          }}
          initialGroup1={addContext.group1}
          initialGroup2={addContext.group2}
          initialMachinery={addContext.machinery}
          initialPdfReference={filterSourceFile}
          mainMachineryOptions={mainMachineryOptions}
          projectManualOptions={projectManualOptions}
        />
      )}

      {showAddMachineryModal && vesselId && (
        <AddMainMachineryModal
          vesselId={vesselId}
          onClose={() => setShowAddMachineryModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
            queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
          }}
          initialGroup1={addContext.group1}
          initialGroup2={addContext.group2}
        />
      )}

      {showCopyModal && vesselId && selectedIds.size > 0 && (
        <CopyComponentsModal
          vesselId={vesselId}
          selectedIds={selectedIds}
          projectManualOptions={projectManualOptions}
          onClose={() => setShowCopyModal(false)}
          onCopied={() => {
            queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
            setSelectedIds(new Set())
          }}
        />
      )}
      {mergeSource && (
        <MergeComponentModal
          source={mergeSource}
          candidates={mappedComponentOptions}
          isPending={mergeIntoExistingMutation.isPending}
          onClose={() => setMergeSource(null)}
          onCreateNew={() => {
            setAddContext({
              group1: mergeSource.group1,
              group2: mergeSource.group2,
              machinery: mergeSource.main_machinery,
            })
            setMergeSource(null)
            setShowAddModal(true)
          }}
          onConfirm={(targetComponentId) => mergeIntoExistingMutation.mutate({ sourceId: mergeSource.id, targetId: targetComponentId })}
        />
      )}
      <ResizableSplitView
        storageKey={`components-review-layout-v2:${vesselId ?? 'default'}`}
        initialLeftPercent={20}
        left={
          <aside className="h-full w-full overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Component Hierarchy</p>
              <button
                onClick={() => { setAddContext({}); setShowAddModal(true) }}
                title="Add component"
                className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-sky-400"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Tree search */}
            <div className="relative mb-2">
              <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500" />
              <input
                value={searchTree}
                onChange={e => setSearchTree(e.target.value)}
                placeholder="Search hierarchy..."
                className="w-full rounded-lg border border-slate-700 bg-slate-800 pl-6 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              />
              {searchTree && (
                <button onClick={() => setSearchTree('')} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* All Components */}
            <button
              onClick={() => { setSelectedGroup1(null); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(false); setShowMappedExtracted(false) }}
              className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                !selectedGroup1 && !showUnmapped && !showMappedExtracted
                  ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                  : 'border border-transparent text-[#72243e] hover:bg-[#fff3f7] hover:text-[#4b1528]'
              }`}
            >
              All Components
              <span className={`ml-auto rounded-full px-1.5 text-xs ${!selectedGroup1 && !showUnmapped && !showMappedExtracted ? 'bg-[#fff3f7] text-[#8c2f52]' : 'bg-slate-700 text-slate-400'}`}>
                {allComponentsQuery.data?.total ?? allComponentsQuery.data?.items?.length ?? 0}
              </span>
            </button>

            {tree.filter(node =>
              !searchTree || node.group1.toLowerCase().includes(searchTree.toLowerCase()) ||
              Object.keys(node.group2s).some(g2 =>
                g2.toLowerCase().includes(searchTree.toLowerCase()) ||
                Object.keys(node.group2s[g2].mainMachineries).some(mm =>
                  mm.toLowerCase().includes(searchTree.toLowerCase())
                )
              )
            ).map((node) => (
              <div key={node.group1}>
                {/* Group 1 */}
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => toggleG1(node.group1)}
                    className="flex items-center p-1 text-slate-400 hover:text-white"
                  >
                    {expandedG1.has(node.group1) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </button>
                  <button
                    onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(false); setShowMappedExtracted(false) }}
                    className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                      selectedGroup1 === node.group1 && !selectedGroup2
                        ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                        : 'border border-transparent text-[#72243e] hover:bg-[#fff3f7] hover:text-[#4b1528]'
                    }`}
                  >
                    <FolderPlus className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                    <span className="flex-1 truncate text-left">{node.group1}</span>
                    <span className={`rounded-full px-1.5 text-xs ${selectedGroup1 === node.group1 && !selectedGroup2 ? 'bg-[#fff3f7] text-[#8c2f52]' : 'bg-slate-700 text-slate-400'}`}>{node.count}</span>
                  </button>
                  <button
                    onClick={() => { setAddContext({ group1: node.group1 }); setShowAddModal(true) }}
                    title="Add to this group"
                    className="rounded p-1 text-slate-600 hover:text-sky-400"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                </div>

                {/* Group 2 — sorted */}
                {expandedG1.has(node.group1) && Object.entries(node.group2s).sort(([a], [b]) => a.localeCompare(b)).map(([g2, g2data]) => (
                  <div key={g2} className="ml-5">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => toggleG2(`${node.group1}::${g2}`)}
                        className="flex items-center p-1 text-slate-500 hover:text-white"
                      >
                        {expandedG2.has(`${node.group1}::${g2}`) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </button>
                      <button
                        onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(g2); setSelectedMachinery(null); setShowUnmapped(false); setShowMappedExtracted(false) }}
                        className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-colors ${
                          selectedGroup2 === g2 && !selectedMachinery
                            ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                            : 'border border-transparent text-[#8f4a64] hover:bg-[#fff3f7] hover:text-[#4b1528]'
                        }`}
                      >
                        <span className="flex-1 truncate text-left">{g2}</span>
                        <span className={selectedGroup2 === g2 && !selectedMachinery ? 'text-[#fff3f7]' : 'text-slate-500'}>{g2data.count}</span>
                      </button>
                      <button
                        onClick={() => { setAddContext({ group1: node.group1, group2: g2 }); setShowAddModal(true) }}
                        title="Add to this sub-group"
                        className="rounded p-0.5 text-slate-600 hover:text-sky-400"
                      >
                        <Plus className="h-3 w-3" />
                      </button>
                    </div>

                    {/* Main Machinery — sorted */}
                    {expandedG2.has(`${node.group1}::${g2}`) && Object.entries(g2data.mainMachineries).sort(([a], [b]) => a.localeCompare(b)).map(([mm, count]) => (
                      <div key={mm} className="ml-5 flex items-center gap-1">
                        <button
                          onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(g2); setSelectedMachinery(mm); setShowUnmapped(false); setShowMappedExtracted(false) }}
                          className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-colors ${
                            selectedMachinery === mm
                              ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                              : 'border border-transparent text-[#8f4a64] hover:bg-[#fff3f7] hover:text-[#4b1528]'
                          }`}
                        >
                          <Wrench className={`h-3 w-3 shrink-0 ${selectedMachinery === mm ? 'text-[#fff3f7]' : 'text-slate-500'}`} />
                          <span className="flex-1 truncate text-left">{mm}</span>
                          <span className={selectedMachinery === mm ? 'text-[#fff3f7]' : 'text-slate-600'}>{count}</span>
                        </button>
                        <button
                          onClick={() => { setAddContext({ group1: node.group1, group2: g2, machinery: mm }); setShowAddModal(true) }}
                          title="Add component here"
                          className="rounded p-0.5 text-slate-600 hover:text-sky-400"
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ))}

            <button
              onClick={() => { setSelectedGroup1(null); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(true); setShowMappedExtracted(false) }}
              className={`mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                showUnmapped
                  ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                  : 'border border-transparent text-[#8f4a64] hover:bg-[#fff3f7] hover:text-[#4b1528]'
              }`}
            >
              <AlertCircle className={`h-3.5 w-3.5 ${showUnmapped ? 'text-[#fff3f7]' : ''}`} />
              Unmapped
            </button>
            <button
              onClick={() => { setSelectedGroup1(null); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(false); setShowMappedExtracted(true) }}
              className={`mt-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                showMappedExtracted
                  ? 'border border-[#b6426b] bg-[#d4537e] text-[#fffdfd] shadow-[0_8px_18px_rgba(212,83,126,0.18)]'
                  : 'border border-transparent text-[#8f4a64] hover:bg-[#fff3f7] hover:text-[#4b1528]'
              }`}
            >
              <FolderPlus className={`h-3.5 w-3.5 ${showMappedExtracted ? 'text-[#fff3f7]' : 'text-amber-500'}`} />
              Mapped Extracted
              <span className={`ml-auto rounded-full px-1.5 text-xs ${showMappedExtracted ? 'bg-[#fff3f7] text-[#8c2f52]' : 'bg-slate-700 text-slate-400'}`}>
                {allComponentsQuery.data?.items?.filter((component: Component) => !component.is_unmapped && !!(component.source_manual_id || component.pdf_reference || component.page_reference !== null || component.job_pages || component.spare_pages)).length ?? 0}
              </span>
            </button>
          </aside>
        }
        right={
          <div className="h-full min-h-0 overflow-hidden flex flex-col gap-2 bg-slate-950 p-1">
                {/* Toolbar */}
                <div className="flex flex-col gap-1.5 bg-slate-900/50 p-2 rounded-xl border border-slate-800/80 shrink-0">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <h1 className="text-sm font-bold text-white flex items-center gap-2">
                      Components
                      <span className="text-[11px] text-slate-500 font-normal">
                        ({total} total{pendingCount !== undefined ? ' · ' : ''}
                        {pendingCount !== undefined && (
                          <span className="text-amber-400 font-medium">{pendingCount} pending</span>
                        )})
                      </span>
                    </h1>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {/* Import Excel */}
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white"
                      >
                        <Upload className="h-3.5 w-3.5" />
                        Import Excel
                      </button>
                      <input ref={fileInputRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={handleExcelImport} />
                      <a
                        href={`${apiClient.defaults.baseURL}/vessels/components/import-template`}
                        download="components_import_template.xlsx"
                        className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white"
                      >
                        <FileDown className="h-3.5 w-3.5" />
                        Template
                      </a>

                      {/* QC Export Components */}
                      <button
                        onClick={async () => {
                          try {
                            const resp = await apiClient.get(`/vessels/${vesselId}/components/qc-export`, { responseType: 'blob' })
                            const disposition = resp.headers['content-disposition'] ?? ''
                            const match = disposition.match(/filename="?([^"]+)"?/)
                            const filename = match ? match[1] : 'Components_QC.xlsx'
                            const a = document.createElement('a')
                            a.href = URL.createObjectURL(resp.data)
                            a.download = filename
                            a.click()
                            setTimeout(() => URL.revokeObjectURL(a.href), 60_000)
                          } catch (e: any) { alert('Export failed: ' + e?.message) }
                        }}
                        className="flex items-center gap-1 rounded-lg border border-violet-700 px-2 py-1 text-xs font-medium text-violet-300 hover:bg-slate-800"
                        title="Download Components QC Review sheet"
                      >
                        <FileDown className="h-3.5 w-3.5" />
                        QC Export
                      </button>

                      {/* Add Component */}
                      <button
                        onClick={() => { setAddContext({}); setShowAddModal(true) }}
                        className="flex items-center gap-1 rounded-lg bg-sky-600 px-2 py-1 text-xs font-medium text-white hover:bg-sky-500"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Add Component
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center justify-between flex-wrap gap-2 border-t border-slate-800/60 pt-1.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {/* Table search */}
                      <div className="relative">
                        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                        <input
                          value={searchTable}
                          onChange={e => setSearchTable(e.target.value)}
                          placeholder="Search components..."
                          className="w-40 rounded-lg border border-slate-700 bg-slate-800 pl-7 pr-6 py-1 text-xs text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                        />
                        {searchTable && (
                          <button onClick={() => setSearchTable('')} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </div>

                      {/* QC filter */}
                      <select
                        value={filterQC}
                        onChange={(e) => setFilterQC(e.target.value)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-1.5 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">All QC</option>
                        <option value="pending">Pending</option>
                        <option value="accepted">Accepted</option>
                        <option value="rejected">Rejected</option>
                        <option value="modified">Modified</option>
                      </select>

                      {/* Source file filter */}
                      <div className="w-56">
                        <SearchableSelect
                          options={projectManualOptions}
                          value={filterSourceFile}
                          onChange={setFilterSourceFile}
                          placeholder="All Manuals / Sources"
                          allowCustom
                        />
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap">
                      {/* Add Main Machinery */}
                      <button
                        onClick={() => setShowAddMachineryModal(true)}
                        className="flex items-center gap-1 rounded-lg border border-sky-700 bg-slate-900 px-2 py-1 text-xs font-medium text-sky-300 hover:bg-slate-800 hover:text-white"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Add Main Machinery
                      </button>

                      {/* Bulk actions */}
                      {selectedIds.size > 0 && (
                        <>
                          <button
                            onClick={() => setShowCopyModal(true)}
                            className="flex items-center gap-1 rounded-lg bg-sky-700 px-2 py-1 text-xs font-medium text-white hover:bg-sky-600"
                          >
                            <Copy className="h-3.5 w-3.5" />
                            Copy to Manual ({selectedIds.size})
                          </button>
                          <button
                            onClick={() => bulkAcceptMutation.mutate(Array.from(selectedIds))}
                            className="flex items-center gap-1 rounded-lg bg-green-700 px-2 py-1 text-xs font-medium text-white hover:bg-green-600"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                            Accept ({selectedIds.size})
                          </button>
                          <button
                            onClick={() => bulkRejectMutation.mutate(Array.from(selectedIds))}
                            className="flex items-center gap-1 rounded-lg bg-red-700 px-2 py-1 text-xs font-medium text-white hover:bg-red-600"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Reject ({selectedIds.size})
                          </button>
                          <button
                            onClick={() => { setShowBatchPanel(p => !p); setBatchFields({}) }}
                            className="flex items-center gap-1 rounded-lg bg-violet-700 px-2 py-1 text-xs font-medium text-white hover:bg-violet-600"
                          >
                            <Wrench className="h-3.5 w-3.5" />
                            Batch Edit ({selectedIds.size})
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm(`Delete ${selectedIds.size} component(s)? This cannot be undone.`)) {
                                bulkDeleteMutation.mutate(Array.from(selectedIds))
                              }
                            }}
                            disabled={bulkDeleteMutation.isPending}
                            className="flex items-center gap-1 rounded-lg bg-rose-900 px-2 py-1 text-xs font-medium text-rose-200 hover:bg-rose-800 disabled:opacity-50"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete ({selectedIds.size})
                          </button>
                        </>
                      )}

                      {/* Save all inline edits */}
                      {Object.keys(edits).length > 0 && (
                        <button
                          onClick={() => Object.entries(edits).forEach(([id, data]) => saveMutation.mutate({ id, data }))}
                          disabled={saveMutation.isPending}
                          className="flex items-center gap-1 rounded-lg bg-violet-600 px-2 py-1 text-xs font-medium text-white hover:bg-violet-500 disabled:opacity-50"
                        >
                          <Save className="h-3.5 w-3.5" />
                          Save {Object.keys(edits).length} edit(s)
                        </button>
                      )}
                    </div>
                  </div>
                </div>

            {/* Excel format hint when empty */}
            {!isLoading && components.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900 p-6 text-center space-y-3">
                <Upload className="mx-auto h-10 w-10 text-slate-600" />
                <p className="text-slate-300 font-medium">No components yet</p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  The vessel baseline should auto-load from the selected vessel type. Use import or manual add only for vessel-specific additions.<br />
                  <strong className="text-slate-400">Excel columns:</strong> Group | Sub-Group | Main Machinery | Component Name | Maker | Model | Serial Number | Specification | Critical | Job Pages | Spare Pages | PDF Reference
                </p>
                <div className="flex justify-center gap-3 pt-1 flex-wrap">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                  >
                    <Upload className="h-4 w-4" /> Import Excel / CSV
                  </button>
                  <button
                    onClick={() => { setAddContext({}); setShowAddModal(true) }}
                    className="flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                  >
                    <Plus className="h-4 w-4" /> Add Manually
                  </button>
                </div>
              </div>
            )}

            {/* Table */}
            {(isLoading || components.length > 0) && (
              <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-900 flex flex-col min-h-0">
                {isLoading ? (
                  <div className="py-16 text-center text-slate-500">Loading...</div>
                ) : (
                  <div className="flex-1 overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase z-10">
                          <th className="px-2 py-1.5 w-8">
                            <input
                              type="checkbox"
                              onChange={e => e.target.checked ? setSelectedIds(new Set(components.map(c => c.id))) : setSelectedIds(new Set())}
                              checked={selectedIds.size === components.length && components.length > 0}
                              className="h-3.5 w-3.5 rounded"
                            />
                          </th>
                          <th className="px-2 py-1.5">Component</th>
                          <th className="px-2 py-1.5">Maker</th>
                          <th className="px-2 py-1.5">Model</th>
                          <th className="px-2 py-1.5">Serial Number</th>
                          <th className="px-2 py-1.5">Job Pages</th>
                          <th className="px-2 py-1.5">Spare Pages</th>
                          <th className="px-2 py-1.5">PDF Reference</th>
                          <th className="px-2 py-1.5">Location</th>
                          <th className="px-2 py-1.5">Mach. Particulars</th>
                          <th className="px-2 py-1.5">Critical</th>
                          <th className="px-2 py-1.5">QC</th>
                          <th className="px-2 py-1.5">Source</th>
                          <th className="px-2 py-1.5">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {components.map((comp) => {
                          const edit = edits[comp.id] ?? {}
                          const changed = Object.keys(edit).length > 0
                          return (
                            <tr
                              key={comp.id}
                              onClick={() => {
                                toggleSelect(comp.id)
                                setSelectedComponent(comp)
                              }}
                              onDoubleClick={() => openManualInNewTab(comp.source_manual_id, comp.pdf_reference, comp.page_reference)}
                              className={`cursor-pointer transition-colors hover:bg-slate-800/50 ${changed ? 'bg-violet-900/10' : ''} ${selectedIds.has(comp.id) ? 'bg-sky-900/10' : ''} ${selectedComponent?.id === comp.id ? 'bg-slate-800/70' : ''}`}
                            >
                              <td className="px-2 py-1" onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
                                <input type="checkbox" checked={selectedIds.has(comp.id)} onChange={() => toggleSelect(comp.id)} className="h-3.5 w-3.5 rounded" />
                              </td>
                              <td className="px-2 py-1 max-w-xs">
                                <p className="font-medium text-slate-200">{comp.component_name}</p>
                                <p className="text-xs text-slate-500 truncate">{comp.group1} › {comp.group2} › {comp.main_machinery}</p>
                              </td>
                              <td className="px-2 py-1">
                                <>
                                  <input
                                    type="text"
                                    list="makers-list"
                                    value={edit.maker ?? comp.maker ?? ''}
                                    onChange={(e) => setEdit(comp.id, 'maker', e.target.value)}
                                    className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                    placeholder="Maker..."
                                  />
                                  <datalist id="makers-list">
                                    {makers.map(mk => <option key={mk} value={mk} />)}
                                  </datalist>
                                </>
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.model ?? comp.model ?? ''}
                                  onChange={e => setEdit(comp.id, 'model', e.target.value)}
                                  className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="—"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.serial_number ?? comp.serial_number ?? ''}
                                  onChange={e => setEdit(comp.id, 'serial_number', e.target.value)}
                                  className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="—"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.job_pages ?? comp.job_pages ?? ''}
                                  onChange={e => setEdit(comp.id, 'job_pages', e.target.value)}
                                  className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="e.g. 21-50"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.spare_pages ?? comp.spare_pages ?? ''}
                                  onChange={e => setEdit(comp.id, 'spare_pages', e.target.value)}
                                  className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="e.g. 81-120"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.pdf_reference ?? comp.pdf_reference ?? ''}
                                  onChange={e => setEdit(comp.id, 'pdf_reference', e.target.value)}
                                  className="w-32 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="filename"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.location ?? comp.location ?? ''}
                                  onChange={e => setEdit(comp.id, 'location', e.target.value)}
                                  className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="—"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={edit.machinery_particulars ?? comp.machinery_particulars ?? ''}
                                  onChange={e => setEdit(comp.id, 'machinery_particulars', e.target.value)}
                                  className="w-32 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                                  placeholder="—"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <select
                                  value={edit.criticality ?? comp.criticality ?? 'non_critical'}
                                  onChange={e => setEdit(comp.id, 'criticality', e.target.value)}
                                  className={`rounded px-2 py-0.5 text-xs font-medium cursor-pointer border-0 focus:outline-none ${
                                    (edit.criticality ?? comp.criticality) === 'critical'
                                      ? 'bg-red-900/60 text-red-300'
                                      : (edit.criticality ?? comp.criticality) === 'essential'
                                      ? 'bg-amber-900/60 text-amber-300'
                                      : 'bg-slate-700 text-slate-400'
                                  }`}
                                >
                                  <option value="non_critical">Non Critical</option>
                                  <option value="essential">Essential</option>
                                  <option value="critical">Critical</option>
                                </select>
                              </td>
                              <td className="px-2 py-1">
                                <select
                                  value={edit.qc_status ?? comp.qc_status}
                                  onChange={e => setEdit(comp.id, 'qc_status', e.target.value)}
                                  className={`rounded-full px-2 py-0.5 text-xs font-medium cursor-pointer border-0 ${QC_COLORS[edit.qc_status ?? comp.qc_status] ?? 'bg-slate-700 text-slate-300'}`}
                                >
                                  <option value="pending">pending</option>
                                  <option value="accepted">accepted</option>
                                  <option value="rejected">rejected</option>
                                  <option value="modified">modified</option>
                                </select>
                              </td>
                              <td className="px-2 py-1" onClick={(e) => e.stopPropagation()}>
                                {comp.source_manual_id ? (
                                  <button
                                    onClick={() => {
                                      setSelectedComponent(comp)
                                      openManualInNewTab(comp.source_manual_id, comp.pdf_reference, comp.page_reference)
                                    }}
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs text-sky-300 hover:bg-slate-800 hover:underline"
                                  >
                                    <ExternalLink className="h-3 w-3" />
                                    {comp.page_reference ? `p.${comp.page_reference}` : 'Preview'}
                                  </button>
                                ) : (
                                  <span className="text-xs text-slate-600">—</span>
                                )}
                              </td>
                              <td className="px-2 py-1" onClick={(e) => e.stopPropagation()}>
                                <div className="flex flex-wrap items-center gap-1.5">
                                  {comp.is_unmapped ? (
                                    <>
                                      <button
                                        onClick={() => {
                                          setSelectedComponent(comp)
                                          setMergeSource(comp)
                                        }}
                                        className="inline-flex items-center gap-1 rounded-lg border border-sky-700 px-2 py-1 text-xs text-sky-300 hover:bg-slate-800"
                                      >
                                        <ArrowRightLeft className="h-3.5 w-3.5" />
                                        Map
                                      </button>
                                      <button
                                        onClick={() => bulkRejectMutation.mutate([comp.id])}
                                        className="inline-flex items-center gap-1 rounded-lg border border-red-800 px-2 py-1 text-xs text-red-300 hover:bg-slate-800"
                                      >
                                        <XCircle className="h-3.5 w-3.5" />
                                        Reject
                                      </button>
                                    </>
                                  ) : (
                                    <button
                                      onClick={() => {
                                        setSelectedComponent(comp)
                                        openManualInNewTab(comp.source_manual_id, comp.pdf_reference, comp.page_reference)
                                      }}
                                      disabled={!comp.source_manual_id}
                                      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 hover:underline disabled:cursor-not-allowed disabled:opacity-40 disabled:no-underline"
                                    >
                                      <ExternalLink className="h-3 w-3" />
                                      Preview
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Pagination bar */}
                {!isLoading && components.length > 0 && (
                  <div className="flex items-center justify-between border-t border-slate-800 px-4 py-2.5 bg-slate-900 z-10">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span>{total} total</span>
                      <span>·</span>
                      <span>Show</span>
                      <select
                        value={pageSize}
                        onChange={(e) => setPageSize(Number(e.target.value))}
                        className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-slate-300 text-xs"
                      >
                        {COMP_PAGE_SIZE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
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
            )}
          </div>
        }
      />

      {/* Standalone manual preview opens in a new tab */}
    </>
  )
}

interface MergeModalProps {
  source: Component
  candidates: Component[]
  isPending: boolean
  onClose: () => void
  onCreateNew: () => void
  onConfirm: (targetComponentId: string) => void
}

function MergeComponentModal({ source, candidates, isPending, onClose, onCreateNew, onConfirm }: MergeModalProps) {
  const [search, setSearch] = useState(source.component_name)
  const [selectedId, setSelectedId] = useState('')

  const filtered = candidates
    .filter((candidate) => candidate.id !== source.id)
    .filter((candidate) => {
      const haystack = `${candidate.component_name} ${candidate.group1} ${candidate.group2} ${candidate.main_machinery} ${candidate.maker ?? ''} ${candidate.model ?? ''}`.toLowerCase()
      return haystack.includes(search.toLowerCase())
    })
    .slice(0, 30)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-white">Map To Existing Component</h2>
            <p className="mt-1 text-sm text-slate-400">{source.component_name}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div className="rounded-lg border border-amber-700/40 bg-amber-900/10 px-3 py-2 text-xs text-amber-300">
            If the right component is not in the vessel structure yet, add it first and then come back here to map this extracted record into that new component.
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search target component..."
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
          />
          <div className="max-h-[22rem] space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/40 p-2">
            {filtered.map((candidate) => (
              <button
                key={candidate.id}
                type="button"
                onClick={() => setSelectedId(candidate.id)}
                className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${
                  selectedId === candidate.id
                    ? 'border-sky-500 bg-sky-900/20'
                    : 'border-slate-800 bg-slate-900 hover:bg-slate-800'
                }`}
              >
                <div className="font-medium text-slate-100">{candidate.component_name}</div>
                <div className="mt-1 text-xs text-slate-400">{candidate.group1} • {candidate.group2} • {candidate.main_machinery}</div>
                <div className="mt-1 text-xs text-slate-500">{[candidate.maker, candidate.model].filter(Boolean).join(' • ') || 'No maker/model yet'}</div>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-8 text-center text-sm text-slate-500">No matching vessel components found for that search.</div>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-700 px-6 py-4">
          <button
            onClick={onCreateNew}
            className="rounded-lg border border-emerald-700 px-4 py-2 text-sm text-emerald-300 hover:bg-slate-800"
          >
            Add Component First
          </button>
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
          <button
            onClick={() => onConfirm(selectedId)}
            disabled={!selectedId || isPending}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            Merge Into Selected Component
          </button>
        </div>
      </div>
    </div>
  )
}

export default ComponentReview

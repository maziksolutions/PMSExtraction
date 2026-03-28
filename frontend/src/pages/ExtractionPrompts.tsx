import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Pencil,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  XCircle,
  SlidersHorizontal,
  CheckCircle,
} from 'lucide-react'
import apiClient from '@/api/client'

// ─── Interfaces ───────────────────────────────────────────────────────────────

type ExtractionType = 'component' | 'job' | 'spare'

interface ExtractionPrompt {
  id: string
  prompt_key: string
  extraction_type: ExtractionType
  system_prompt: string
  few_shot_example?: string
  model_id: string
  max_tokens: number
  temperature: number
  version: number
  is_active: boolean
}

interface PromptFormData {
  prompt_key: string
  extraction_type: ExtractionType
  system_prompt: string
  few_shot_example: string
  model_id: string
  max_tokens: number
  temperature: number
}

const EMPTY_FORM: PromptFormData = {
  prompt_key: '',
  extraction_type: 'component',
  system_prompt: '',
  few_shot_example: '',
  model_id: 'claude-sonnet-4-6',
  max_tokens: 4096,
  temperature: 0,
}

const EXTRACTION_TYPE_OPTIONS: { value: ExtractionType; label: string }[] = [
  { value: 'component', label: 'Component' },
  { value: 'job', label: 'Job' },
  { value: 'spare', label: 'Spare' },
]

const TYPE_COLORS: Record<ExtractionType, string> = {
  component: 'bg-sky-900/40 text-sky-400 border-sky-600/40',
  job: 'bg-violet-900/40 text-violet-400 border-violet-600/40',
  spare: 'bg-teal-900/40 text-teal-400 border-teal-600/40',
}

// ─── Prompt Modal ─────────────────────────────────────────────────────────────

interface PromptModalProps {
  initialData?: ExtractionPrompt
  onClose: () => void
  onSaved: () => void
}

const PromptModal: React.FC<PromptModalProps> = ({ initialData, onClose, onSaved }) => {
  const [form, setForm] = useState<PromptFormData>(
    initialData
      ? {
          prompt_key: initialData.prompt_key,
          extraction_type: initialData.extraction_type,
          system_prompt: initialData.system_prompt,
          few_shot_example: initialData.few_shot_example ?? '',
          model_id: initialData.model_id,
          max_tokens: initialData.max_tokens,
          temperature: initialData.temperature,
        }
      : EMPTY_FORM
  )
  const [error, setError] = useState<string | null>(null)

  const isEdit = !!initialData

  const saveMutation = useMutation({
    mutationFn: async (payload: PromptFormData) => {
      if (isEdit) {
        await apiClient.patch(`/api/v1/extraction-prompts/${initialData!.id}`, payload)
      } else {
        await apiClient.post('/api/v1/extraction-prompts', payload)
      }
    },
    onSuccess: () => {
      onSaved()
    },
    onError: () => {
      setError('Failed to save prompt. Please check all fields and try again.')
    },
  })

  const handleChange = <K extends keyof PromptFormData>(field: K, value: PromptFormData[K]) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setError(null)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    saveMutation.mutate(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-3xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">
            {isEdit ? 'Edit Extraction Prompt' : 'Add Extraction Prompt'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 p-3 bg-red-900/40 border border-red-600/50 rounded-lg text-red-300 text-sm">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            {/* Prompt Key */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">
                Prompt Key <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={form.prompt_key}
                onChange={(e) => handleChange('prompt_key', e.target.value)}
                required
                placeholder="e.g. component_extraction_v1"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm"
              />
            </div>

            {/* Extraction Type */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">
                Extraction Type <span className="text-red-400">*</span>
              </label>
              <select
                value={form.extraction_type}
                onChange={(e) => handleChange('extraction_type', e.target.value as ExtractionType)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-sky-500 text-sm"
              >
                {EXTRACTION_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Model ID */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">Model ID</label>
              <input
                type="text"
                value={form.model_id}
                onChange={(e) => handleChange('model_id', e.target.value)}
                placeholder="claude-sonnet-4-6"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm"
              />
            </div>

            {/* Max Tokens */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">Max Tokens</label>
              <input
                type="number"
                value={form.max_tokens}
                onChange={(e) => handleChange('max_tokens', Number(e.target.value))}
                min={256}
                max={16384}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-sky-500 text-sm"
              />
            </div>

            {/* Temperature */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">
                Temperature <span className="text-slate-500">(0 – 1)</span>
              </label>
              <input
                type="number"
                value={form.temperature}
                onChange={(e) => handleChange('temperature', Number(e.target.value))}
                min={0}
                max={1}
                step={0.1}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-sky-500 text-sm"
              />
            </div>
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">
              System Prompt <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.system_prompt}
              onChange={(e) => handleChange('system_prompt', e.target.value)}
              required
              rows={10}
              placeholder="You are an expert maritime PMS data extraction assistant..."
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm font-mono resize-y"
            />
          </div>

          {/* Few Shot Example */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">
              Few-Shot Example <span className="text-slate-500">(optional)</span>
            </label>
            <textarea
              value={form.few_shot_example}
              onChange={(e) => handleChange('few_shot_example', e.target.value)}
              rows={6}
              placeholder="User: Extract components from...\nAssistant: [...]"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm font-mono resize-y"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 px-5 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending && <RefreshCw className="w-4 h-4 animate-spin" />}
              {isEdit ? 'Save Changes' : 'Create Prompt'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Prompt Row ───────────────────────────────────────────────────────────────

interface PromptRowProps {
  prompt: ExtractionPrompt
  onEdit: (prompt: ExtractionPrompt) => void
}

const PromptRow: React.FC<PromptRowProps> = ({ prompt, onEdit }) => {
  const [expanded, setExpanded] = useState(false)
  const truncated = prompt.system_prompt.slice(0, 100)
  const isTruncated = prompt.system_prompt.length > 100

  return (
    <tr className="border-b border-slate-700/50 hover:bg-slate-700/20 transition-colors align-top">
      <td className="px-4 py-3 text-white font-mono text-sm">{prompt.prompt_key}</td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border font-medium ${
            TYPE_COLORS[prompt.extraction_type]
          }`}
        >
          {prompt.extraction_type}
        </span>
      </td>
      <td className="px-4 py-3 text-slate-400 text-xs font-mono">{prompt.model_id}</td>
      <td className="px-4 py-3 text-slate-400 text-sm">{prompt.max_tokens.toLocaleString()}</td>
      <td className="px-4 py-3 text-slate-400 text-sm">{prompt.temperature}</td>
      <td className="px-4 py-3">
        <span className="inline-flex items-center px-2 py-0.5 bg-slate-700 text-slate-300 text-xs rounded-full">
          v{prompt.version}
        </span>
      </td>
      <td className="px-4 py-3">
        {prompt.is_active ? (
          <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
            <CheckCircle className="w-3.5 h-3.5" /> Active
          </span>
        ) : (
          <span className="text-slate-500 text-xs">Inactive</span>
        )}
      </td>
      <td className="px-4 py-3 max-w-xs">
        <div className="text-slate-400 text-xs leading-relaxed">
          <span className="font-mono">
            {expanded ? prompt.system_prompt : truncated}
            {!expanded && isTruncated && '…'}
          </span>
          {isTruncated && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-2 text-sky-400 hover:text-sky-300 transition-colors inline-flex items-center gap-0.5"
            >
              {expanded ? (
                <>
                  Show less <ChevronUp className="w-3 h-3" />
                </>
              ) : (
                <>
                  Show full <ChevronDown className="w-3 h-3" />
                </>
              )}
            </button>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <button
          onClick={() => onEdit(prompt)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded-lg transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
          Edit
        </button>
      </td>
    </tr>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const ExtractionPrompts: React.FC = () => {
  const queryClient = useQueryClient()
  const [filterType, setFilterType] = useState<ExtractionType | 'all'>('all')
  const [showModal, setShowModal] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState<ExtractionPrompt | undefined>(undefined)

  const { data: prompts = [], isLoading } = useQuery<ExtractionPrompt[]>({
    queryKey: ['extraction-prompts', filterType],
    queryFn: async () => {
      const params = filterType !== 'all' ? { extraction_type: filterType } : {}
      const res = await apiClient.get('/api/v1/extraction-prompts', { params })
      return res.data
    },
  })

  const handleEdit = (prompt: ExtractionPrompt) => {
    setEditingPrompt(prompt)
    setShowModal(true)
  }

  const handleCloseModal = () => {
    setShowModal(false)
    setEditingPrompt(undefined)
  }

  const handleSaved = () => {
    queryClient.invalidateQueries({ queryKey: ['extraction-prompts'] })
    handleCloseModal()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <SlidersHorizontal className="w-7 h-7 text-sky-400" />
            Extraction Prompts
          </h1>
          <p className="text-slate-400 mt-1">
            Configure Claude AI prompts for component, job, and spare extraction
          </p>
        </div>
        <button
          onClick={() => { setEditingPrompt(undefined); setShowModal(true) }}
          className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Prompt
        </button>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-400">Filter by type:</span>
        <div className="flex gap-1 bg-slate-900/50 p-1 rounded-lg">
          {(
            [
              { value: 'all', label: 'All' },
              ...EXTRACTION_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
            ] as { value: ExtractionType | 'all'; label: string }[]
          ).map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setFilterType(value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                filterType === value
                  ? 'bg-sky-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-900/50">
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Prompt Key</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Type</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Model</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Max Tokens</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Temp</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Version</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Active</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">System Prompt</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium" />
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />
                    Loading prompts...
                  </td>
                </tr>
              ) : prompts.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                    No extraction prompts found. Click "Add Prompt" to create one.
                  </td>
                </tr>
              ) : (
                prompts.map((prompt) => (
                  <PromptRow key={prompt.id} prompt={prompt} onEdit={handleEdit} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <PromptModal
          initialData={editingPrompt}
          onClose={handleCloseModal}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

export default ExtractionPrompts

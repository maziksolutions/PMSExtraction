import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, CheckCircle, AlertCircle, ArrowRight, Loader2 } from 'lucide-react'
import apiClient from '@/api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ColumnMapping {
  column_index: number
  column_header: string
  field_name: string | null
  auto_mapped: boolean
}

interface SheetMappings {
  [sheetName: string]: ColumnMapping[]
}

interface ParsedTemplate {
  sheet_mappings: SheetMappings
  schema_id?: string
}

const SYSTEM_FIELDS = [
  { value: '', label: '— Not mapped —' },
  // Components
  { value: 'group1', label: 'Group 1' },
  { value: 'group2', label: 'Group 2' },
  { value: 'main_machinery', label: 'Main Machinery' },
  { value: 'component_name', label: 'Component Name' },
  { value: 'maker', label: 'Maker' },
  { value: 'model', label: 'Model' },
  { value: 'specification', label: 'Specification' },
  { value: 'serial_number', label: 'Serial Number' },
  { value: 'is_critical', label: 'Critical Component' },
  // Jobs
  { value: 'job_name', label: 'Job Name' },
  { value: 'job_code', label: 'Job Code' },
  { value: 'job_description', label: 'Job Description' },
  { value: 'safety_precaution', label: 'Safety Precautions' },
  { value: 'tools_required', label: 'Tools Required' },
  { value: 'performing_rank', label: 'Performing Rank' },
  { value: 'verifying_rank', label: 'Verifying Rank' },
  { value: 'frequency', label: 'Frequency' },
  { value: 'frequency_type', label: 'Frequency Type' },
  { value: 'cms_id', label: 'CMS ID' },
  { value: 'component_linked', label: 'Component Linked' },
  // Spares
  { value: 'part_name', label: 'Part Name' },
  { value: 'part_number', label: 'Part Number' },
  { value: 'drawing_number', label: 'Drawing Number' },
  { value: 'drawing_position', label: 'Drawing Position' },
  { value: 'spare_maker', label: 'Spare Maker' },
  { value: 'spare_model', label: 'Spare Model' },
  { value: 'extraction_method', label: 'Extraction Method' },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExportSchemaSetup: React.FC = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [step, setStep] = useState<'upload' | 'map' | 'done'>('upload')
  const [parsedTemplate, setParsedTemplate] = useState<ParsedTemplate | null>(null)
  const [localMappings, setLocalMappings] = useState<SheetMappings>({})
  const [schemaName, setSchemaName] = useState('PMS Import Template')

  // Step 1: Upload template → parse
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('name', schemaName)
      const res = await apiClient.post<ParsedTemplate>('/export-schemas', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: (data) => {
      setParsedTemplate(data)
      setLocalMappings(data.sheet_mappings)
      setStep('map')
    },
  })

  // Step 2: Confirm mappings → save
  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!parsedTemplate?.schema_id) return
      await apiClient.put(`/export-schemas/${parsedTemplate.schema_id}/mapping`, {
        sheet_mappings: localMappings,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['export-schemas'] })
      setStep('done')
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
  }

  const updateFieldMapping = (
    sheetName: string,
    colIndex: number,
    fieldName: string
  ) => {
    setLocalMappings((prev) => ({
      ...prev,
      [sheetName]: prev[sheetName].map((col) =>
        col.column_index === colIndex
          ? { ...col, field_name: fieldName || null }
          : col
      ),
    }))
  }

  const unmappedCount = Object.values(localMappings)
    .flat()
    .filter((c) => !c.field_name).length

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Export Schema Setup</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload your PMS import template Excel file once. The column mapping is
          saved for all future vessel exports.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {[
          { key: 'upload', label: 'Upload Template' },
          { key: 'map', label: 'Map Columns' },
          { key: 'done', label: 'Confirmed' },
        ].map(({ key, label }, i) => {
          const stepOrder = ['upload', 'map', 'done']
          const current = stepOrder.indexOf(step)
          const idx = stepOrder.indexOf(key)
          return (
            <React.Fragment key={key}>
              {i > 0 && <div className="h-px flex-1 bg-slate-700" />}
              <div
                className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium ${
                  idx === current
                    ? 'bg-sky-600 text-white'
                    : idx < current
                    ? 'bg-green-700 text-green-100'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/20 text-xs font-bold">
                  {i + 1}
                </span>
                {label}
              </div>
            </React.Fragment>
          )
        })}
      </div>

      {/* Step 1: Upload */}
      {step === 'upload' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-8">
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Schema Name
            </label>
            <input
              type="text"
              value={schemaName}
              onChange={(e) => setSchemaName(e.target.value)}
              className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
            />
          </div>

          <div
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700 bg-slate-800/50 px-8 py-14 text-center transition-colors hover:border-sky-500/50 hover:bg-slate-800"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="mb-3 h-10 w-10 text-slate-500" />
            <p className="text-sm font-medium text-slate-300">
              Click to upload your PMS Import Template
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Supported: .xlsx — Max 10 MB
            </p>
            {uploadMutation.isPending && (
              <div className="mt-4 flex items-center gap-2 text-sky-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Parsing template…</span>
              </div>
            )}
            {uploadMutation.isError && (
              <p className="mt-4 flex items-center gap-1 text-sm text-red-400">
                <AlertCircle className="h-4 w-4" />
                Failed to parse template. Ensure it is a valid Excel file.
              </p>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      )}

      {/* Step 2: Column mapping */}
      {step === 'map' && parsedTemplate && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-400">
              Auto-mapped columns are highlighted in green. Review and correct
              any mismatched or unmapped columns before confirming.
            </p>
            {unmappedCount > 0 && (
              <span className="rounded-full bg-amber-700 px-3 py-0.5 text-xs font-medium text-amber-100">
                {unmappedCount} unmapped
              </span>
            )}
          </div>

          {Object.entries(localMappings).map(([sheetName, columns]) => (
            <div
              key={sheetName}
              className="rounded-xl border border-slate-800 bg-slate-900"
            >
              <div className="border-b border-slate-800 px-5 py-3">
                <h3 className="font-semibold text-slate-200">
                  Sheet: {sheetName}
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-left text-xs uppercase text-slate-500">
                      <th className="px-5 py-2">Col #</th>
                      <th className="px-5 py-2">Template Header</th>
                      <th className="px-5 py-2">Mapped System Field</th>
                      <th className="px-5 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {columns.map((col) => (
                      <tr key={col.column_index}>
                        <td className="px-5 py-2 text-slate-500">
                          {col.column_index}
                        </td>
                        <td className="px-5 py-2 font-medium text-slate-200">
                          {col.column_header}
                        </td>
                        <td className="px-5 py-2">
                          <select
                            value={col.field_name ?? ''}
                            onChange={(e) =>
                              updateFieldMapping(
                                sheetName,
                                col.column_index,
                                e.target.value
                              )
                            }
                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                          >
                            {SYSTEM_FIELDS.map((f) => (
                              <option key={f.value} value={f.value}>
                                {f.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-5 py-2">
                          {col.field_name ? (
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                col.auto_mapped
                                  ? 'bg-green-800 text-green-200'
                                  : 'bg-sky-800 text-sky-200'
                              }`}
                            >
                              {col.auto_mapped ? 'Auto-mapped' : 'Manual'}
                            </span>
                          ) : (
                            <span className="rounded-full bg-amber-800 px-2 py-0.5 text-xs font-medium text-amber-200">
                              Unmapped
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          <div className="flex justify-end gap-3">
            <button
              onClick={() => setStep('upload')}
              className="rounded-lg border border-slate-700 px-5 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Back
            </button>
            <button
              onClick={() => confirmMutation.mutate()}
              disabled={confirmMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-sky-600 px-6 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {confirmMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              Confirm Mapping
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Done */}
      {step === 'done' && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-green-500/30 bg-green-500/10 py-16">
          <CheckCircle className="mb-4 h-14 w-14 text-green-400" />
          <h2 className="text-xl font-bold text-green-300">
            Export Schema Saved
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            All future vessel exports will use this column mapping automatically.
          </p>
          <button
            onClick={() => navigate(-1)}
            className="mt-6 rounded-lg bg-sky-600 px-6 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            Return to Export
          </button>
        </div>
      )}
    </div>
  )
}

export default ExportSchemaSetup

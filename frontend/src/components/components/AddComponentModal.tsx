import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { X, Plus, RefreshCw } from 'lucide-react'
import apiClient from '@/api/client'
import { SearchableSelect } from '@/components/SearchableSelect'

export interface AddModalProps {
  vesselId: string
  onClose: () => void
  onCreated: () => void
  initialGroup1?: string
  initialGroup2?: string
  initialMachinery?: string
  initialPdfReference?: string
  mainMachineryOptions: string[]
  projectManualOptions: string[]
}

export function AddComponentModal({
  vesselId,
  onClose,
  onCreated,
  initialGroup1,
  initialGroup2,
  initialMachinery,
  initialPdfReference,
  mainMachineryOptions,
  projectManualOptions,
}: AddModalProps) {
  const [form, setForm] = useState({
    group1: initialGroup1 ?? '',
    group2: initialGroup2 ?? '',
    main_machinery: initialMachinery ?? '',
    component_name: '',
    maker: '',
    model: '',
    serial_number: '',
    specification: '',
    is_critical: false,
    criticality: 'non_critical',
    job_pages: '',
    spare_pages: '',
    pdf_reference: initialPdfReference ?? '',
  })

  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/components`, {
        ...form,
        maker: form.maker || null,
        model: form.model || null,
        serial_number: form.serial_number || null,
        specification: form.specification || null,
        job_pages: form.job_pages || null,
        spare_pages: form.spare_pages || null,
        pdf_reference: form.pdf_reference || null,
      }).then(r => r.data),
    onSuccess: () => { onCreated(); onClose() },
  })

  const set = (k: string, v: string | boolean) => setForm(p => ({ ...p, [k]: v }))
  const isSubmitDisabled = !form.component_name.trim() || !form.main_machinery.trim() || mutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Add Component</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-4 max-h-[70vh] overflow-y-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Hierarchy</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Group (Group 1)</label>
              <input
                value={form.group1}
                onChange={e => set('group1', e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                placeholder="Group 1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Sub-Group (Group 2)</label>
              <input
                value={form.group2}
                onChange={e => set('group2', e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                placeholder="Group 2"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">Main Machinery *</label>
              <SearchableSelect
                options={mainMachineryOptions}
                value={form.main_machinery}
                onChange={val => set('main_machinery', val)}
                placeholder="Select or type..."
                required
                allowCustom
              />
            </div>
          </div>

          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 pt-2">Component Details</p>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Component Name *</label>
            <input
              value={form.component_name}
              onChange={e => set('component_name', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. Main Seawater Pump"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[['maker','Maker / Manufacturer'], ['model','Model'], ['serial_number','Serial Number'], ['specification','Specification']].map(([k,label]) => (
              <div key={k}>
                <label className="mb-1 block text-xs text-slate-400">{label}</label>
                <input
                  value={(form as any)[k]}
                  onChange={e => set(k, e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                  placeholder={label}
                />
              </div>
            ))}
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Criticality</label>
            <select
              value={form.criticality}
              onChange={e => set('criticality', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
            >
              <option value="non_critical">Non Critical</option>
              <option value="essential">Essential</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 pt-2">Page References & Manual</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Job Pages</label>
              <input
                value={form.job_pages}
                onChange={e => set('job_pages', e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                placeholder="e.g. 21-50"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Spare Pages</label>
              <input
                value={form.spare_pages}
                onChange={e => set('spare_pages', e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                placeholder="e.g. 51-80"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">PDF Reference (Manual)</label>
              <SearchableSelect
                options={projectManualOptions}
                value={form.pdf_reference}
                onChange={val => set('pdf_reference', val)}
                placeholder="Select project manual..."
                allowCustom
              />
            </div>
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
            Add Component
          </button>
        </div>
      </div>
    </div>
  )
}
export default AddComponentModal

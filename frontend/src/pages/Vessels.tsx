import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Ship, ChevronRight, Loader2, Pencil } from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole } from '@/types'

interface VesselProject {
  id: string
  name: string
  imo_number: string
  vessel_type: string
  shipyard?: string
  status: string
  created_at: string
}

interface VesselListResponse {
  items: VesselProject[]
  total: number
  pages: number
}

const statusColors: Record<string, string> = {
  draft: 'bg-slate-700 text-slate-300',
  ingesting: 'bg-blue-700 text-blue-200',
  classifying: 'bg-purple-700 text-purple-200',
  reviewing: 'bg-amber-700 text-amber-200',
  exporting: 'bg-teal-700 text-teal-200',
  complete: 'bg-green-700 text-green-200',
}

const VESSEL_TYPES = [
  'Bulk Carrier', 'Container Ship', 'Tanker', 'General Cargo',
  'Ro-Ro', 'Passenger', 'Offshore Vessel', 'Tugboat', 'Other',
]

const emptyForm = { name: '', imo_number: '', vessel_type: '', shipyard: '' }

const Vessels: React.FC = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const userRole = user?.role as UserRole | undefined
  const canCreate = userRole === UserRole.SuperAdmin || userRole === UserRole.VesselAdmin

  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState('')

  // Edit state
  const [editingVessel, setEditingVessel] = useState<VesselProject | null>(null)
  const [editForm, setEditForm] = useState(emptyForm)
  const [editError, setEditError] = useState('')

  const { data, isLoading } = useQuery<VesselListResponse>({
    queryKey: ['vessels'],
    queryFn: async () => {
      const res = await apiClient.get('/vessels?page=1&page_size=100')
      return res.data
    },
  })

  const createMutation = useMutation({
    mutationFn: async (payload: typeof form) => {
      const res = await apiClient.post('/vessels', payload)
      return res.data
    },
    onSuccess: (vessel: VesselProject) => {
      queryClient.invalidateQueries({ queryKey: ['vessels'] })
      setShowModal(false)
      setForm(emptyForm)
      navigate(`/vessels/${vessel.id}/ingestion`)
    },
    onError: (err: any) => {
      setFormError(err?.message ?? 'Failed to create vessel')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: typeof editForm }) => {
      const res = await apiClient.put(`/vessels/${id}`, payload)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vessels'] })
      setEditingVessel(null)
      setEditError('')
    },
    onError: (err: any) => {
      setEditError(err?.response?.data?.detail ?? err?.message ?? 'Failed to update vessel')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError('')
    if (!form.name.trim() || !form.imo_number.trim() || !form.vessel_type) {
      setFormError('All fields are required')
      return
    }
    createMutation.mutate(form)
  }

  const openEdit = (e: React.MouseEvent, vessel: VesselProject) => {
    e.stopPropagation()
    setEditingVessel(vessel)
    setEditForm({
      name: vessel.name,
      imo_number: vessel.imo_number,
      vessel_type: vessel.vessel_type,
      shipyard: vessel.shipyard ?? '',
    })
    setEditError('')
  }

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setEditError('')
    if (!editForm.name.trim() || !editForm.imo_number.trim() || !editForm.vessel_type) {
      setEditError('Name, IMO number and vessel type are required')
      return
    }
    updateMutation.mutate({ id: editingVessel!.id, payload: editForm })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Vessel Projects</h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage your vessel PMS data extraction projects
          </p>
        </div>
        {canCreate && (
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500"
          >
            <Plus className="h-4 w-4" />
            New Vessel Project
          </button>
        )}
      </div>

      {/* Vessel list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
        </div>
      ) : !data?.items.length ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-700 py-20 text-center">
          <Ship className="mb-4 h-12 w-12 text-slate-600" />
          <p className="text-lg font-medium text-slate-300">No vessel projects yet</p>
          {canCreate && (
            <button
              onClick={() => setShowModal(true)}
              className="mt-4 flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
            >
              <Plus className="h-4 w-4" />
              Create your first vessel project
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((vessel) => (
            <div
              key={vessel.id}
              className="group relative flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-sky-700 hover:bg-slate-800"
            >
              {/* Edit button — top-right corner */}
              {canCreate && (
                <button
                  onClick={(e) => openEdit(e, vessel)}
                  title="Edit project details"
                  className="absolute right-3 top-3 rounded-lg p-1.5 text-slate-500 opacity-0 transition-opacity hover:bg-slate-700 hover:text-slate-200 group-hover:opacity-100"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}

              {/* Clickable body — navigates into project */}
              <button
                onClick={() => navigate(`/vessels/${vessel.id}/ingestion`)}
                className="flex flex-1 flex-col text-left"
              >
                <div className="flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10">
                    <Ship className="h-5 w-5 text-sky-400" />
                  </div>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[vessel.status] ?? 'bg-slate-700 text-slate-300'}`}>
                    {vessel.status}
                  </span>
                </div>
                <div className="mt-4 flex-1">
                  <p className="pr-6 font-semibold text-white hover:text-sky-300">{vessel.name}</p>
                  <p className="mt-1 text-xs text-slate-500">{vessel.imo_number} · {vessel.vessel_type}</p>
                  {vessel.shipyard && (
                    <p className="mt-0.5 text-xs text-slate-600">{vessel.shipyard}</p>
                  )}
                </div>
                <div className="mt-4 flex items-center text-xs text-sky-400 opacity-0 transition-opacity group-hover:opacity-100">
                  Open project <ChevronRight className="ml-1 h-3 w-3" />
                </div>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Create Vessel Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <h2 className="text-lg font-bold text-white">New Vessel Project</h2>
            <p className="mt-1 text-sm text-slate-400">Enter vessel details to start a new extraction project</p>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Vessel Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. MV Atlantic Star"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">IMO Number</label>
                <input
                  type="text"
                  value={form.imo_number}
                  onChange={e => setForm(f => ({ ...f, imo_number: e.target.value }))}
                  placeholder="e.g. IMO9999999"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Vessel Type</label>
                <select
                  value={form.vessel_type}
                  onChange={e => setForm(f => ({ ...f, vessel_type: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                >
                  <option value="">Select vessel type...</option>
                  {VESSEL_TYPES.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Shipyard / Builder <span className="text-slate-500">(optional)</span></label>
                <input
                  type="text"
                  value={form.shipyard}
                  onChange={e => setForm(f => ({ ...f, shipyard: e.target.value }))}
                  placeholder="e.g. Hyundai Heavy Industries"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              {formError && (
                <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-400">{formError}</p>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowModal(false); setFormError('') }}
                  className="flex-1 rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
                >
                  {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Vessel Modal */}
      {editingVessel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <h2 className="text-lg font-bold text-white">Edit Vessel Project</h2>
            <p className="mt-1 text-sm text-slate-400">Update details for <span className="text-white">{editingVessel.name}</span></p>

            <form onSubmit={handleEditSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Vessel Name</label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">IMO Number</label>
                <input
                  type="text"
                  value={editForm.imo_number}
                  onChange={e => setEditForm(f => ({ ...f, imo_number: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Vessel Type</label>
                <select
                  value={editForm.vessel_type}
                  onChange={e => setEditForm(f => ({ ...f, vessel_type: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                >
                  <option value="">Select vessel type...</option>
                  {VESSEL_TYPES.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Shipyard / Builder <span className="text-slate-500">(optional)</span></label>
                <input
                  type="text"
                  value={editForm.shipyard}
                  onChange={e => setEditForm(f => ({ ...f, shipyard: e.target.value }))}
                  placeholder="e.g. Hyundai Heavy Industries"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
              </div>

              {editError && (
                <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-400">{editError}</p>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingVessel(null)}
                  className="flex-1 rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
                >
                  {updateMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default Vessels

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  UserPlus,
  Pencil,
  UserX,
  X,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole } from '@/types'
import type { User, UserCreate, PaginatedList } from '@/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const roleLabels: Record<UserRole, string> = {
  [UserRole.SuperAdmin]: 'Super Admin',
  [UserRole.VesselAdmin]: 'Vessel Admin',
  [UserRole.QCReviewer]: 'QC Reviewer',
  [UserRole.Viewer]: 'Viewer',
  [UserRole.ApiIntegration]: 'API Integration',
}

const roleBadgeClasses: Record<UserRole, string> = {
  [UserRole.SuperAdmin]: 'bg-violet-700 text-violet-200',
  [UserRole.VesselAdmin]: 'bg-sky-700 text-sky-200',
  [UserRole.QCReviewer]: 'bg-amber-700 text-amber-200',
  [UserRole.Viewer]: 'bg-slate-700 text-slate-300',
  [UserRole.ApiIntegration]: 'bg-emerald-800 text-emerald-200',
}

// ---------------------------------------------------------------------------
// Add User form schema
// ---------------------------------------------------------------------------

const addUserSchema = z.object({
  full_name: z.string().min(1, 'Full name is required'),
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Minimum 8 characters')
    .regex(/[A-Z]/, 'Must contain an uppercase letter')
    .regex(/\d/, 'Must contain a digit'),
  role: z.nativeEnum(UserRole),
})

type AddUserFormData = z.infer<typeof addUserSchema>

// ---------------------------------------------------------------------------
// AddUserModal
// ---------------------------------------------------------------------------

interface AddUserModalProps {
  onClose: () => void
  tenantId: string
}

const AddUserModal: React.FC<AddUserModalProps> = ({ onClose, tenantId }) => {
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AddUserFormData>({
    resolver: zodResolver(addUserSchema),
    defaultValues: { role: UserRole.Viewer },
  })

  const createMutation = useMutation({
    mutationFn: async (data: UserCreate) => {
      const response = await apiClient.post<User>('/users', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (err: Error) => {
      setServerError(err.message)
    },
  })

  const onSubmit = (data: AddUserFormData) => {
    setServerError(null)
    createMutation.mutate({ ...data, tenant_id: tenantId })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="font-semibold text-slate-100">Add New User</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 px-6 py-5">
          {serverError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
              <p className="text-sm text-red-300">{serverError}</p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Full name */}
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Full Name</label>
              <input
                {...register('full_name')}
                placeholder="Jane Smith"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              />
              {errors.full_name && (
                <p className="mt-1 text-xs text-red-400">{errors.full_name.message}</p>
              )}
            </div>

            {/* Email */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Email</label>
              <input
                {...register('email')}
                type="email"
                placeholder="jane@example.com"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>
              )}
            </div>

            {/* Role */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Role</label>
              <select
                {...register('role')}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-500"
              >
                {Object.values(UserRole).map((r) => (
                  <option key={r} value={r}>
                    {roleLabels[r]}
                  </option>
                ))}
              </select>
            </div>

            {/* Password */}
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                Temporary Password
              </label>
              <input
                {...register('password')}
                type="password"
                placeholder="Min 8 chars, 1 uppercase, 1 digit"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              />
              {errors.password && (
                <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:bg-sky-800 disabled:text-sky-400"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <UserPlus className="h-4 w-4" />
              )}
              Create User
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Users page
// ---------------------------------------------------------------------------

const Users: React.FC = () => {
  const { user: currentUser } = useAuthStore()
  const queryClient = useQueryClient()
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['users', page],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedList<User>>(
        `/users?page=${page}&page_size=20`
      )
      return response.data
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: async (userId: string) => {
      await apiClient.put(`/users/${userId}`, { is_active: false })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const roleUpdateMutation = useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: UserRole }) => {
      await apiClient.put(`/users/${userId}`, { role })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setEditingUser(null)
    },
  })

  const users = data?.items ?? []
  const totalPages = data?.pages ?? 1

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">User Management</h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage accounts and roles for the organisation.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-sky-400 active:bg-sky-600"
        >
          <UserPlus className="h-4 w-4" />
          Add User
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 shadow">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Loading users…</span>
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center gap-2 py-16 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Failed to load users.</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  {['Name', 'Email', 'Role', 'Status', 'Last Login', 'Actions'].map((h) => (
                    <th
                      key={h}
                      className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-5 py-3 font-medium text-slate-200">{u.full_name}</td>
                    <td className="px-5 py-3 text-slate-400">{u.email}</td>
                    <td className="px-5 py-3">
                      {editingUser?.id === u.id ? (
                        <select
                          defaultValue={u.role}
                          onChange={(e) =>
                            roleUpdateMutation.mutate({
                              userId: u.id,
                              role: e.target.value as UserRole,
                            })
                          }
                          className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
                        >
                          {Object.values(UserRole).map((r) => (
                            <option key={r} value={r}>
                              {roleLabels[r]}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${roleBadgeClasses[u.role as UserRole]}`}
                        >
                          {roleLabels[u.role as UserRole] ?? u.role}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {u.is_active ? (
                        <span className="flex items-center gap-1.5 text-emerald-400">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Active
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-slate-500">
                          <X className="h-3.5 w-3.5" />
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {u.last_login ? (
                        <span className="flex items-center gap-1.5">
                          <Clock className="h-3 w-3" />
                          {new Date(u.last_login).toLocaleDateString('en-GB')}
                        </span>
                      ) : (
                        <span className="text-slate-600">Never</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        {/* Edit role */}
                        <button
                          onClick={() =>
                            setEditingUser(editingUser?.id === u.id ? null : u)
                          }
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-sky-400"
                          title="Edit role"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        {/* Deactivate — cannot deactivate yourself */}
                        {u.id !== currentUser?.id && u.is_active && (
                          <button
                            onClick={() => deactivateMutation.mutate(u.id)}
                            className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-red-400"
                            title="Deactivate user"
                          >
                            <UserX className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-800 px-5 py-3">
            <p className="text-xs text-slate-500">
              Page {page} of {totalPages} ({data?.total ?? 0} users)
            </p>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add User Modal */}
      {showAddModal && currentUser && (
        <AddUserModal
          onClose={() => setShowAddModal(false)}
          tenantId={currentUser.tenant_id}
        />
      )}
    </div>
  )
}

export default Users

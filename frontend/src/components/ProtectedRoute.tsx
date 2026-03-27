import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import type { UserRole } from '@/types'

interface ProtectedRouteProps {
  children: React.ReactNode
  /** If provided, the user must have one of these roles to access the route. */
  roles?: UserRole[]
}

/**
 * Wraps a route so that:
 *  1. Unauthenticated users are redirected to /login (preserving the intended destination).
 *  2. Authenticated users without the required role receive a 403 screen.
 */
const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, roles }) => {
  const { isAuthenticated, user } = useAuthStore()
  const location = useLocation()

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (roles && roles.length > 0 && !roles.includes(user.role as UserRole)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="rounded-lg border border-red-500/30 bg-slate-900 p-10 text-center shadow-xl">
          <h1 className="mb-2 text-2xl font-bold text-red-400">Access Denied</h1>
          <p className="text-slate-400">
            You do not have permission to view this page.
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Required role(s): {roles.join(', ')}
          </p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

export default ProtectedRoute

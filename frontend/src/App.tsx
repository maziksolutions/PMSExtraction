import React, { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import Layout from '@/components/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import { UserRole } from '@/types'

// ---------------------------------------------------------------------------
// Lazy-loaded pages
// ---------------------------------------------------------------------------

const Login = lazy(() => import('@/pages/Login'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Users = lazy(() => import('@/pages/Users'))
const Vessels = lazy(() => import('@/pages/Vessels'))

// Sprint 2
const Ingestion = lazy(() => import('@/pages/Ingestion'))

// Sprint 3
const ManualReview = lazy(() => import('@/pages/ManualReview'))

// Sprint 4
const ComponentReview = lazy(() => import('@/pages/ComponentReview'))

// Sprint 5
const JobsReview = lazy(() => import('@/pages/JobsReview'))

// Sprint 6
const SparesReview = lazy(() => import('@/pages/SparesReview'))

// Sprint 7
const StandardJobs = lazy(() => import('@/pages/StandardJobs'))

// Sprint 9
const Export = lazy(() => import('@/pages/Export'))
const ExportSchemaSetup = lazy(() => import('@/pages/ExportSchemaSetup'))

// Sprint 11
const FeedbackDashboard = lazy(() => import('@/pages/FeedbackDashboard'))

// Sprint 12
const Admin = lazy(() => import('@/pages/Admin'))

// ---------------------------------------------------------------------------
// TanStack Query client
// ---------------------------------------------------------------------------

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// ---------------------------------------------------------------------------
// Page-level loading fallback
// ---------------------------------------------------------------------------

const PageLoader: React.FC = () => (
  <div className="flex min-h-screen items-center justify-center bg-slate-950">
    <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
  </div>
)

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />

            {/* Protected routes — wrapped in the Layout shell */}
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              {/* Dashboard */}
              <Route index element={<Dashboard />} />

              {/* Users (Super Admin only) */}
              <Route
                path="users"
                element={
                  <ProtectedRoute roles={[UserRole.SuperAdmin]}>
                    <Users />
                  </ProtectedRoute>
                }
              />

              {/* Vessels list */}
              <Route path="vessels" element={<ProtectedRoute><Vessels /></ProtectedRoute>} />

              {/* Sprint 2: Ingestion */}
              <Route
                path="vessels/:vesselId/ingestion"
                element={
                  <ProtectedRoute>
                    <Ingestion />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 3: Manual Review */}
              <Route
                path="vessels/:vesselId/manuals"
                element={
                  <ProtectedRoute>
                    <ManualReview />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 4: Component Review */}
              <Route
                path="vessels/:vesselId/components"
                element={
                  <ProtectedRoute>
                    <ComponentReview />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 5: Jobs Review */}
              <Route
                path="vessels/:vesselId/jobs"
                element={
                  <ProtectedRoute>
                    <JobsReview />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 6: Spares Review */}
              <Route
                path="vessels/:vesselId/spares"
                element={
                  <ProtectedRoute>
                    <SparesReview />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 7: Standard Jobs */}
              <Route
                path="vessels/:vesselId/standard-jobs"
                element={
                  <ProtectedRoute>
                    <StandardJobs />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 9: Export */}
              <Route
                path="vessels/:vesselId/export"
                element={
                  <ProtectedRoute>
                    <Export />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 11: Feedback Dashboard (Super Admin) */}
              <Route
                path="feedback"
                element={
                  <ProtectedRoute roles={[UserRole.SuperAdmin]}>
                    <FeedbackDashboard />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 9: Export Schema Setup */}
              <Route
                path="export-schema-setup"
                element={
                  <ProtectedRoute roles={[UserRole.SuperAdmin, UserRole.VesselAdmin]}>
                    <ExportSchemaSetup />
                  </ProtectedRoute>
                }
              />

              {/* Sprint 12: Admin Console (Super Admin) */}
              <Route
                path="admin"
                element={
                  <ProtectedRoute roles={[UserRole.SuperAdmin]}>
                    <Admin />
                  </ProtectedRoute>
                }
              />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

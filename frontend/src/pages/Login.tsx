import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Ship, Eye, EyeOff, AlertCircle, Loader2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

// ---------------------------------------------------------------------------
// Validation schema
// ---------------------------------------------------------------------------

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormData = z.infer<typeof loginSchema>

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const Login: React.FC = () => {
  const { login } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null)
    try {
      await login(data.email, data.password)
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Login failed. Please try again.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      {/* Background texture */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(45deg, #fff 0, #fff 1px, transparent 0, transparent 50%)',
          backgroundSize: '16px 16px',
        }}
      />

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl shadow-black/60">
          {/* Header band */}
          <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-slate-900 px-8 py-8 text-center">
            {/* Logo */}
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-sky-500 shadow-lg shadow-sky-500/40">
              <Ship className="h-8 w-8 text-white" />
            </div>
            <h1 className="text-xl font-bold text-white">Maritime PMS</h1>
            <p className="mt-1 text-sm text-sky-300/80">Data Extraction &amp; Setup Tool</p>
            <div className="mx-auto mt-4 h-px w-20 bg-gradient-to-r from-transparent via-sky-500 to-transparent" />
          </div>

          {/* Union Maritime branding */}
          <div className="border-b border-slate-800 bg-slate-950/50 px-8 py-3 text-center">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
              Powered by Union Maritime
            </p>
          </div>

          {/* Form */}
          <div className="px-8 py-8">
            <h2 className="mb-6 text-lg font-semibold text-slate-100">Sign in to your account</h2>

            {/* Server error */}
            {serverError && (
              <div className="mb-5 flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                <p className="text-sm text-red-300">{serverError}</p>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
              {/* Email */}
              <div>
                <label
                  htmlFor="email"
                  className="mb-1.5 block text-sm font-medium text-slate-300"
                >
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  {...register('email')}
                  className={[
                    'w-full rounded-lg border px-4 py-2.5 text-sm outline-none transition-colors',
                    'bg-slate-800 text-slate-100 placeholder-slate-500',
                    errors.email
                      ? 'border-red-500/70 focus:border-red-400'
                      : 'border-slate-700 focus:border-sky-500',
                  ].join(' ')}
                />
                {errors.email && (
                  <p className="mt-1.5 text-xs text-red-400">{errors.email.message}</p>
                )}
              </div>

              {/* Password */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-1.5 block text-sm font-medium text-slate-300"
                >
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    {...register('password')}
                    className={[
                      'w-full rounded-lg border px-4 py-2.5 pr-10 text-sm outline-none transition-colors',
                      'bg-slate-800 text-slate-100 placeholder-slate-500',
                      errors.password
                        ? 'border-red-500/70 focus:border-red-400'
                        : 'border-slate-700 focus:border-sky-500',
                    ].join(' ')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                    tabIndex={-1}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                {errors.password && (
                  <p className="mt-1.5 text-xs text-red-400">{errors.password.message}</p>
                )}
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={isSubmitting}
                className={[
                  'flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition-all duration-150',
                  isSubmitting
                    ? 'cursor-not-allowed bg-sky-700 text-sky-300'
                    : 'bg-sky-500 text-white hover:bg-sky-400 active:bg-sky-600',
                  'shadow-lg shadow-sky-500/20',
                ].join(' ')}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Signing in…
                  </>
                ) : (
                  'Sign in'
                )}
              </button>
            </form>
          </div>

          {/* Footer */}
          <div className="border-t border-slate-800 px-8 py-4 text-center">
            <p className="text-xs text-slate-600">
              Authorised personnel only. All activity is monitored and logged.
            </p>
          </div>
        </div>

        {/* Version tag */}
        <p className="mt-4 text-center text-xs text-slate-700">Maritime PMS v1.0.0</p>
      </div>
    </div>
  )
}

export default Login

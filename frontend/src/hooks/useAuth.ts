import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import type { AuthTokens, User } from '@/types'

interface LoginPayload {
  email: string
  password: string
}

interface UseAuthReturn {
  currentUser: User | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export function useAuth(): UseAuthReturn {
  const navigate = useNavigate()
  const {
    user: currentUser,
    isAuthenticated,
    login: storeLogin,
    logout: storeLogout,
  } = useAuthStore()

  /**
   * Authenticate with email + password.
   * On success, fetch the current user profile and store everything.
   * Throws an Error with a human-readable message on failure.
   */
  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      // 1. Obtain tokens
      const tokenResponse = await apiClient.post<AuthTokens>('/auth/login', {
        email,
        password,
      } satisfies LoginPayload)

      const tokens = tokenResponse.data

      // 2. Temporarily set the access token so the next request is authorised
      useAuthStore.setState({ accessToken: tokens.access_token })

      // 3. Fetch the authenticated user profile
      const userResponse = await apiClient.get<User>('/users/me')
      const user = userResponse.data

      // 4. Persist everything in the store
      storeLogin(user, tokens)

      // 5. Redirect to dashboard
      navigate('/', { replace: true })
    },
    [navigate, storeLogin]
  )

  /**
   * Logout: tell the server and clear local state.
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // Ignore server errors on logout — clear state regardless
    } finally {
      storeLogout()
      navigate('/login', { replace: true })
    }
  }, [navigate, storeLogout])

  return {
    currentUser,
    isAuthenticated,
    login,
    logout,
  }
}

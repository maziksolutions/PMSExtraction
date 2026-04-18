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
    refreshToken,
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
      const tokenResponse = await apiClient.post<AuthTokens>('/auth/login', {
        email,
        password,
      } satisfies LoginPayload)

      const tokens = tokenResponse.data

      useAuthStore.setState({ accessToken: tokens.access_token })

      const userResponse = await apiClient.get<User>('/users/me')
      const user = userResponse.data

      storeLogin(user, tokens)
      navigate('/', { replace: true })
    },
    [navigate, storeLogin]
  )

  /**
   * Logout: ask the server to revoke tokens and clear local state.
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      await apiClient.post('/auth/logout', { refresh_token: refreshToken })
    } catch {
      // Clear the local session even if the revoke request fails.
    } finally {
      storeLogout()
      navigate('/login', { replace: true })
    }
  }, [navigate, refreshToken, storeLogout])

  return {
    currentUser,
    isAuthenticated,
    login,
    logout,
  }
}

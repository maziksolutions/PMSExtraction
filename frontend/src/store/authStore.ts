import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { User, AuthTokens } from '@/types'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
}

interface AuthActions {
  setTokens: (tokens: AuthTokens) => void
  setUser: (user: User) => void
  login: (user: User, tokens: AuthTokens) => void
  logout: () => void
  updateAccessToken: (accessToken: string, refreshToken: string) => void
}

type AuthStore = AuthState & AuthActions

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      // --- initial state ---
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      // --- actions ---
      setTokens: (tokens: AuthTokens) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          isAuthenticated: true,
        }),

      setUser: (user: User) => set({ user }),

      login: (user: User, tokens: AuthTokens) =>
        set({
          user,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          isAuthenticated: true,
        }),

      logout: () =>
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        }),

      updateAccessToken: (accessToken: string, refreshToken: string) =>
        set({ accessToken, refreshToken }),
    }),
    {
      name: 'maritime-pms-auth',
      storage: createJSONStorage(() => localStorage),
      // Only persist the token strings and user — not action functions
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

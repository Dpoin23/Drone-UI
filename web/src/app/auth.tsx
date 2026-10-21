import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from '../lib/api'
import type { User } from '../lib/types'
import { AuthContext, type AuthState } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokenStore.get() !== null)

  const clearSession = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(clearSession)
    if (tokenStore.get()) {
      api
        .me()
        .then(setUser)
        .catch(clearSession)
        .finally(() => setLoading(false))
    }
    return () => setUnauthorizedHandler(null)
  }, [clearSession])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async (username, password) => {
        const res = await api.login(username, password)
        tokenStore.set(res.token)
        setUser(res.user)
      },
      register: async (username, password) => {
        const res = await api.register(username, password)
        tokenStore.set(res.token)
        setUser(res.user)
      },
      signOut: async () => {
        await api.logout().catch(() => undefined)
        clearSession()
      },
    }),
    [user, loading, clearSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

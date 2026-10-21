import { createContext, useContext } from 'react'
import type { User } from '../lib/types'

export type AuthState = {
  user: User | null
  loading: boolean
  signIn: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

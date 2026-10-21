import { Loader2 } from 'lucide-react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './app/AppShell'
import { useAuth } from './app/auth-context'
import { SignInPage } from './features/auth/SignInPage'
import { IssuesPage } from './features/issues/IssuesPage'
import { LivestreamPage } from './features/livestream/LivestreamPage'

export default function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="grid h-full place-items-center text-zinc-500">
        <Loader2 className="size-6 animate-spin" />
      </div>
    )
  }

  if (!user) return <SignInPage />

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/live" replace />} />
        <Route path="/live" element={<LivestreamPage />} />
        <Route path="/security" element={<IssuesPage key="security" category="security" />} />
        <Route path="/maintenance" element={<IssuesPage key="maintenance" category="maintenance" />} />
        <Route path="*" element={<Navigate to="/live" replace />} />
      </Route>
    </Routes>
  )
}

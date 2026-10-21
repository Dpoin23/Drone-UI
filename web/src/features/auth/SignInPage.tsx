import { AlertCircle, Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../../app/auth-context'
import { Logo } from '../../components/Logo'

type Mode = 'signin' | 'register'

export function SignInPage() {
  const { signIn, register } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await (mode === 'signin' ? signIn : register)(username.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  return (
    <div className="relative grid min-h-full place-items-center overflow-hidden px-4 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgb(255_255_255/0.04)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.04)_1px,transparent_1px)] [background-size:48px_48px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]"
      />

      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="mb-4 size-12" />
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Perimeter Ground Station</h1>
          <p className="mt-1 text-sm text-zinc-400">
            {mode === 'signin' ? 'Sign in to monitor your perimeter.' : 'Create an operator account.'}
          </p>
        </div>

        <div className="panel p-6">
          <div className="mb-6 grid grid-cols-2 rounded-lg border border-line bg-black/30 p-1 text-sm">
            {(['signin', 'register'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => switchMode(m)}
                className={`rounded-md py-1.5 font-medium transition ${
                  mode === m ? 'bg-white/[0.08] text-zinc-50' : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {m === 'signin' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="label" htmlFor="username">Username</label>
              <input
                id="username"
                className="input"
                autoComplete="username"
                autoFocus
                required
                minLength={3}
                maxLength={32}
                pattern="[A-Za-z0-9_.\-]+"
                title="Letters, numbers, dot, dash and underscore"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                className="input"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {mode === 'register' && <p className="mt-1.5 text-xs text-zinc-500">At least 8 characters.</p>}
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

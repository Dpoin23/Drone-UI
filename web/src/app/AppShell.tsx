import { LogOut, ShieldAlert, Video, Wrench } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { useAuth } from './auth-context'

const tabs = [
  { to: '/live', label: 'Livestream', icon: Video },
  { to: '/security', label: 'Security risks', icon: ShieldAlert },
  { to: '/maintenance', label: 'Maintenance', icon: Wrench },
]

export function AppShell() {
  const { user, signOut } = useAuth()

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-base/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-6 px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <Logo className="size-8" />
            <div className="hidden leading-tight sm:block">
              <div className="text-sm font-semibold text-zinc-100">Perimeter</div>
              <div className="text-[11px] tracking-widest text-zinc-500 uppercase">Ground station</div>
            </div>
          </div>

          <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
            {tabs.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `relative flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition ${
                    isActive
                      ? 'bg-white/[0.06] text-zinc-50'
                      : 'text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={`size-4 ${isActive ? 'text-cyan-400' : ''}`} />
                    <span className="hidden md:inline">{label}</span>
                    {isActive && (
                      <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-cyan-400" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-line bg-white/[0.03] py-1 pr-3 pl-1 sm:flex">
              <span className="grid size-6 place-items-center rounded-full bg-gradient-to-br from-cyan-400 to-violet-500 text-[11px] font-bold text-zinc-950 uppercase">
                {user?.username.slice(0, 1)}
              </span>
              <span className="text-sm text-zinc-300">{user?.username}</span>
            </div>
            <button className="btn-ghost px-2.5" onClick={signOut} title="Sign out">
              <LogOut className="size-4" />
              <span className="hidden lg:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}

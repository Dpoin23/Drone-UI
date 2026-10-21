export function Logo({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="url(#logo-bg)" />
      <g stroke="#22d3ee" strokeWidth="1.8" strokeLinecap="round">
        <circle cx="9.5" cy="9.5" r="3.2" />
        <circle cx="22.5" cy="9.5" r="3.2" />
        <circle cx="9.5" cy="22.5" r="3.2" />
        <circle cx="22.5" cy="22.5" r="3.2" />
        <path d="M11.8 11.8l8.4 8.4M20.2 11.8l-8.4 8.4" />
      </g>
      <rect x="13.4" y="13.4" width="5.2" height="5.2" rx="1.6" fill="#22d3ee" />
      <defs>
        <linearGradient id="logo-bg" x1="0" y1="0" x2="32" y2="32">
          <stop stopColor="#132028" />
          <stop offset="1" stopColor="#0b0f14" />
        </linearGradient>
      </defs>
    </svg>
  )
}

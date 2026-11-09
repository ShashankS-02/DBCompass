/** Compass mark used in the header, loaders and the home page hero. */
export function CompassMark({ className = "h-8 w-8", spinning = false }: { className?: string; spinning?: boolean }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="compass-ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#F96246" />
          <stop offset="100%" stopColor="#D4AC47" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="21" fill="none" stroke="url(#compass-ring)" strokeWidth="3" />
      <g stroke="#E9D3C3" strokeWidth="1.6" strokeLinecap="round">
        <line x1="24" y1="6.5" x2="24" y2="10" />
        <line x1="24" y1="38" x2="24" y2="41.5" />
        <line x1="6.5" y1="24" x2="10" y2="24" />
        <line x1="38" y1="24" x2="41.5" y2="24" />
      </g>
      <g className={spinning ? "origin-center animate-needle-seek" : ""} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
        <path d="M24 11 L28.5 24 L24 24 Z" fill="#F96246" />
        <path d="M24 11 L19.5 24 L24 24 Z" fill="#FA8068" />
        <path d="M24 37 L19.5 24 L24 24 Z" fill="#E9D3C3" />
        <path d="M24 37 L28.5 24 L24 24 Z" fill="#DEBEA8" />
      </g>
      <circle cx="24" cy="24" r="2.4" fill="#FBFCFC" stroke="#486061" strokeWidth="1.2" />
    </svg>
  );
}

export function Wordmark({ light = false }: { light?: boolean }) {
  return (
    <span className={`font-display text-lg font-bold tracking-tight ${light ? "text-snow" : "text-slate-900"}`}>
      DB<span className="text-coral-500">Compass</span>
    </span>
  );
}

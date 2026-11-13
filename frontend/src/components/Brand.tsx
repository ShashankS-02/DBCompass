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
      <g stroke="#FCA48F" strokeWidth="1.6" strokeLinecap="round">
        <line x1="24" y1="6.5" x2="24" y2="10" />
        <line x1="24" y1="38" x2="24" y2="41.5" />
        <line x1="6.5" y1="24" x2="10" y2="24" />
        <line x1="38" y1="24" x2="41.5" y2="24" />
      </g>
      <g className={spinning ? "origin-center animate-needle-seek" : ""} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
        <path d="M24 11 L28.5 24 L24 24 Z" fill="#F96246" />
        <path d="M24 11 L19.5 24 L24 24 Z" fill="#FA8068" />
        <path d="M24 37 L19.5 24 L24 24 Z" fill="#CDA285" />
        <path d="M24 37 L28.5 24 L24 24 Z" fill="#B58665" />
      </g>
      <circle cx="24" cy="24" r="2.4" fill="#FBFCFC" stroke="#251F1C" strokeWidth="1.2" />
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

/** Oversized compass dial drawn in tints of the background: rings, degree ticks and a slow sweep. */
export function DialBackdrop({ className = "" }: { className?: string }) {
  const ticks = [];
  for (let degree = 0; degree < 360; degree += 3) {
    const major = degree % 30 === 0;
    const radians = (degree * Math.PI) / 180;
    const outer = 290;
    const inner = major ? 262 : 278;
    ticks.push(
      <line
        key={degree}
        x1={300 + outer * Math.sin(radians)}
        y1={300 - outer * Math.cos(radians)}
        x2={300 + inner * Math.sin(radians)}
        y2={300 - inner * Math.cos(radians)}
        strokeWidth={major ? 2.4 : 1.2}
      />,
    );
  }
  return (
    <svg
      viewBox="0 0 600 600"
      aria-hidden="true"
      className={`pointer-events-none absolute -right-[18rem] top-1/2 h-[56rem] w-[56rem] -translate-y-1/2 text-white/25 ${className}`}
    >
      <g className="origin-center animate-spin-slow [animation-duration:120s]" style={{ transformBox: "fill-box", transformOrigin: "center" }} stroke="currentColor">
        {ticks}
      </g>
      <circle cx="300" cy="300" r="240" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="300" cy="300" r="170" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 8" />
      <circle cx="300" cy="300" r="96" fill="none" stroke="currentColor" strokeWidth="1" />
      <g className="origin-center animate-spin-slow [animation-duration:24s]" style={{ transformBox: "view-box", transformOrigin: "300px 300px" }}>
        <path d="M300 300 L300 62 A238 238 0 0 1 418 93 Z" fill="currentColor" opacity="0.35" />
      </g>
    </svg>
  );
}

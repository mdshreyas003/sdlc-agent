export function Logo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden>
      <path d="M5 14 10 5l5 9M5 14h10" stroke="var(--fg)" strokeWidth="1.3" fill="none" strokeLinejoin="round" opacity=".55" />
      <circle cx="10" cy="5" r="2.2" fill="#8b5cf6" /><circle cx="5" cy="14" r="2.2" fill="#f97316" /><circle cx="15" cy="14" r="2.2" fill="#3b82f6" />
    </svg>
  );
}

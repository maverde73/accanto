/** Icons from design/accanto-mobile.dc.html.
 *
 * They inherit `currentColor` so a tile's tone drives both its tint and its
 * glyph. Colour is never the only cue: each row also carries a label.
 */

type IconProps = { size?: number };

export function LockIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 10V8a6 6 0 0 1 10.32-4.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function MotionIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13 4l-4 8h4l-1 8 6-10h-4l2-6h-3z" fill="currentColor" />
    </svg>
  );
}

export function HeartIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 21s-7.5-4.6-10-9.2C.5 8.4 2.4 5 6 5c2 0 3.4 1.1 4 2.4.6-1.3 2-2.4 4-2.4 3.6 0 5.5 3.4 4 6.8-2.5 4.6-10 9.2-10 9.2z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
    </svg>
  );
}

export function BatteryIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2" y="7" width="17" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <rect x="21" y="10" width="2" height="4" rx="1" fill="currentColor" />
      <rect x="4" y="9" width="11" height="6" rx="1" fill="currentColor" />
    </svg>
  );
}

export function ChevronIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function PinIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 22s-7-5.5-7-11a7 7 0 1 1 14 0c0 5.5-7 11-7 11z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <circle cx="12" cy="11" r="2.6" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

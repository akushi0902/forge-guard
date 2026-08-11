/**
 * ScoreRing — SVG-based radial progress gauge for health scores.
 *
 * Renders a circular arc proportional to the given score (0–100).
 * Values outside [0, 100] are clamped and a warning is logged.
 *
 * Accessibility: aria-label includes the numeric score so screen readers
 * can announce the value without interpreting the SVG geometry.
 */

import { type CSSProperties } from 'react';

export interface ScoreRingProps {
  /** Score value in the range [0, 100]. Clamped if out of range. */
  score: number;
  /** Diameter of the ring in pixels (default 80). */
  size?: number;
  /** Width of the progress stroke in pixels (default 8). */
  strokeWidth?: number;
  /** CSS color for the progress arc. Defaults to a semantic colour based on score. */
  color?: string;
  /** Additional class name. */
  className?: string;
  /** Inline style overrides. */
  style?: CSSProperties;
  /** ARIA label prefix, e.g. "Security score". */
  label?: string;
}

/** Return a semantic colour based on score range. */
function defaultColor(score: number): string {
  if (score >= 80) return 'var(--mantine-color-success-6, #16a34a)';
  if (score >= 50) return 'var(--mantine-color-warning-6, #d97706)';
  return 'var(--mantine-color-danger-6, #dc2626)';
}

/**
 * Radial progress gauge rendered as an SVG arc.
 *
 * @example
 * <ScoreRing score={87} size={100} label="Health score" />
 * <ScoreRing score={45} color="#d97706" />
 */
export function ScoreRing({
  score,
  size = 80,
  strokeWidth = 8,
  color,
  className,
  style,
  label = 'Score',
}: ScoreRingProps) {
  // Clamp and warn in development.
  let safeScore = score;
  if (isNaN(score)) {
    if (process.env.NODE_ENV !== 'production') {
      console.error('[ScoreRing] Received NaN score; rendering 0.');
    }
    safeScore = 0;
  } else if (score < 0 || score > 100) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn(`[ScoreRing] Score ${score} out of [0, 100] range; clamping.`);
    }
    safeScore = Math.max(0, Math.min(100, score));
  }

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - safeScore / 100);
  const center = size / 2;
  const arcColor = color ?? defaultColor(safeScore);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      style={style}
      role="img"
      aria-label={`${label}: ${Math.round(safeScore)} out of 100`}
    >
      {/* Background track */}
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="var(--mantine-color-neutral-2, #e2e8f0)"
        strokeWidth={strokeWidth}
      />
      {/* Progress arc — starts at 12-o'clock, rotate -90° */}
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke={arcColor}
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={dashOffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
        style={{ transition: 'stroke-dashoffset 0.4s ease' }}
      />
      {/* Numeric score label */}
      <text
        x={center}
        y={center}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={size * 0.22}
        fontWeight="600"
        fill="currentColor"
        aria-hidden="true"
      >
        {Math.round(safeScore)}
      </text>
    </svg>
  );
}

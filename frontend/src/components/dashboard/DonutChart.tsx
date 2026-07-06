export interface DonutSegment {
  label: string
  value: number
  color: string
}

interface DonutChartProps {
  segments: DonutSegment[]
  size?: number
  thickness?: number
}

export function DonutChart({ segments, size = 124, thickness = 16 }: DonutChartProps) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const center = size / 2
  let offset = 0

  return (
    <div className="donut-chart">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Distribution chart">
        <g transform={`rotate(-90 ${center} ${center})`}>
          {total === 0 ? (
            <circle
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke="var(--bs-secondary-bg)"
              strokeWidth={thickness}
            />
          ) : (
            segments.map((segment) => {
              const length = (segment.value / total) * circumference
              const element = (
                <circle
                  key={segment.label}
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="none"
                  stroke={segment.color}
                  strokeWidth={thickness}
                  strokeDasharray={`${length} ${circumference - length}`}
                  strokeDashoffset={-offset}
                />
              )
              offset += length
              return element
            })
          )}
        </g>
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" className="donut-chart__total">
          {total}
        </text>
      </svg>
      <ul className="donut-chart__legend list-unstyled mb-0">
        {segments.map((segment) => (
          <li key={segment.label} className="donut-chart__legend-item">
            <span className="donut-chart__swatch" style={{ backgroundColor: segment.color }} />
            <span>{segment.label}</span>
            <span className="text-secondary ms-auto">{segment.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

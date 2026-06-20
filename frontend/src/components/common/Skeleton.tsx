interface SkeletonProps {
  width?: string
  height?: string
  rounded?: boolean
  className?: string
}

export function Skeleton({ width, height, rounded, className }: SkeletonProps) {
  return (
    <span
      className={`skeleton${rounded ? ' skeleton--rounded' : ''}${className ? ` ${className}` : ''}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}

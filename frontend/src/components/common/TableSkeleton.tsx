import { Skeleton } from './Skeleton'

interface TableSkeletonProps {
  rows?: number
  columns?: number
}

export function TableSkeleton({ rows = 5, columns = 4 }: TableSkeletonProps) {
  return (
    <div className="vstack gap-2" aria-hidden="true">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div className="d-flex gap-3" key={rowIndex}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            <Skeleton key={colIndex} height="1.5rem" className="flex-fill" />
          ))}
        </div>
      ))}
    </div>
  )
}

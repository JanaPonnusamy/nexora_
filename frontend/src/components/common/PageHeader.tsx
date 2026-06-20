interface PageHeaderProps {
  title: string
  breadcrumb: string[]
}

export function PageHeader({ title, breadcrumb }: PageHeaderProps) {
  return (
    <div className="page-header mb-4">
      <nav aria-label="breadcrumb">
        <ol className="breadcrumb mb-2 small">
          {breadcrumb.map((crumb, index) => {
            const isLast = index === breadcrumb.length - 1
            return (
              <li
                key={`${crumb}-${index}`}
                className={`breadcrumb-item${isLast ? ' active' : ''}`}
                aria-current={isLast ? 'page' : undefined}
              >
                {crumb}
              </li>
            )
          })}
        </ol>
      </nav>
      <h1 className="h3 mb-0">{title}</h1>
    </div>
  )
}

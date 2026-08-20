interface PageHeaderProps {
  title: string
  breadcrumb: string[]
  description?: string
}

export function PageHeader({ title, breadcrumb, description }: PageHeaderProps) {
  return (
    <div className="page-header">
      <nav aria-label="breadcrumb">
        <ol className="breadcrumb">
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
      <h1 className="page-header__title">{title}</h1>
      {description && <p className="page-header__description">{description}</p>}
    </div>
  )
}

interface TenantEmptyStateProps {
  onAdd: () => void
}

const FEATURES = [
  {
    icon: 'bi-building',
    title: 'Organizations',
    text: 'Each tenant is an isolated organization on the platform.',
    accent: 'tenant-feature__icon--0',
  },
  {
    icon: 'bi-database',
    title: 'Dedicated database',
    text: 'Tenants map to their own database for clean separation.',
    accent: 'tenant-feature__icon--2',
  },
  {
    icon: 'bi-shop',
    title: 'Stores & users',
    text: 'Add stores and users inside each tenant workspace.',
    accent: 'tenant-feature__icon--1',
  },
  {
    icon: 'bi-shield-lock',
    title: 'Roles & access',
    text: 'Control access with platform roles and permissions.',
    accent: 'tenant-feature__icon--3',
  },
]

export function TenantEmptyState({ onAdd }: TenantEmptyStateProps) {
  return (
    <div className="tenant-empty">
      <div className="tenant-empty__hero">
        <span className="tenant-empty__icon">
          <i className="bi bi-buildings" aria-hidden="true" />
        </span>
        <h2 className="h4 mb-1">No tenants yet</h2>
        <p className="text-secondary mb-3">
          Create your first organization to start managing stores, users and access.
        </p>
        <button type="button" className="btn btn-primary btn-lg" onClick={onAdd}>
          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
          Add Tenant
        </button>
      </div>

      <div className="row row-cols-1 row-cols-sm-2 row-cols-xl-4 g-3">
        {FEATURES.map((feature) => (
          <div className="col" key={feature.title}>
            <div className="card h-100 tenant-feature">
              <div className="card-body">
                <span className={`tenant-feature__icon ${feature.accent}`}>
                  <i className={`bi ${feature.icon}`} aria-hidden="true" />
                </span>
                <div className="fw-semibold mt-2">{feature.title}</div>
                <div className="text-secondary small">{feature.text}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

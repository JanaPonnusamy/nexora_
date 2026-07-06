import type { Store } from '../../types/store'
import { StatCard } from '../dashboard/StatCard'

export function StoreSummary({ stores }: { stores: Store[] }) {
  const total = stores.length
  const active = stores.filter((store) => store.is_active).length
  const inactive = total - active
  const servers = new Set(stores.map((store) => store.server_name).filter(Boolean)).size
  const databases = new Set(stores.map((store) => store.database_name).filter(Boolean)).size

  return (
    <div className="overview-section">
      <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-3">
        <div className="col">
          <StatCard label="Total Stores" value={total} icon="bi-shop" tone="primary" />
        </div>
        <div className="col">
          <StatCard label="Active" value={active} icon="bi-check-circle" tone="success" />
        </div>
        <div className="col">
          <StatCard label="Inactive" value={inactive} icon="bi-pause-circle" tone="secondary" />
        </div>
        <div className="col">
          <StatCard label="Servers" value={servers} icon="bi-hdd-network" tone="info" />
        </div>
        <div className="col">
          <StatCard label="Databases" value={databases} icon="bi-database" tone="warning" />
        </div>
      </div>
    </div>
  )
}

import { MappingList } from './MappingList'
import { RequireStorePair, type MappingCtx } from './shared'

export function ApprovedMappingsTab({ ctx }: { ctx: MappingCtx }) {
  return (
    <RequireStorePair ctx={ctx}>
      <MappingList
        ctx={ctx}
        status="APPROVED"
        title="Approved Mappings"
        icon="bi-check2-circle"
        emptyHint="Human-approved mappings are saved here and reused by future runs and every other module."
      />
    </RequireStorePair>
  )
}

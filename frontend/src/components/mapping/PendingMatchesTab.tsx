import { MappingList } from './MappingList'
import { RequireStorePair, type MappingCtx } from './shared'

export function PendingMatchesTab({ ctx }: { ctx: MappingCtx }) {
  return (
    <RequireStorePair ctx={ctx}>
      <MappingList
        ctx={ctx}
        status="PENDING"
        title="Pending Matches"
        icon="bi-hourglass-split"
        emptyHint="Products the engine could not confidently auto-match appear here for review."
      />
    </RequireStorePair>
  )
}

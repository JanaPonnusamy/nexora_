import { MappingList } from './MappingList'
import { RequireStorePair, type MappingCtx } from './shared'

export function AutoMatchesTab({ ctx }: { ctx: MappingCtx }) {
  return (
    <RequireStorePair ctx={ctx}>
      <MappingList
        ctx={ctx}
        status="AUTO"
        title="Auto Matches"
        icon="bi-lightning-charge"
        emptyHint="High-confidence deterministic matches (supplier / exact / normalized / structured) land here automatically."
      />
    </RequireStorePair>
  )
}

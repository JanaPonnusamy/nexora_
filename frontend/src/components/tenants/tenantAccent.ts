/** Deterministic 0–5 accent index from a tenant seed (code), for colorful avatars. */
export function tenantAccent(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash + seed.charCodeAt(i)) % 6
  }
  return hash
}

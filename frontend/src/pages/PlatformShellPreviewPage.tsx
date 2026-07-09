import '../platform/modules/registerModules'
import { PlatformShell } from '../platform/shell/PlatformShell'

/**
 * Full-page mount for the Desktop Platform shell, separate from the existing
 * AppShell route tree. Lets the platform be built and compared side-by-side
 * with the live app without touching anything it depends on.
 */
export default function PlatformShellPreviewPage() {
  return <PlatformShell />
}

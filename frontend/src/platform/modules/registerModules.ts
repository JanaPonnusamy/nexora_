import { moduleRegistry } from './ModuleRegistry'
import { reportsModule } from './reports.module'
import { purchaseManagerModule } from './purchase-manager.module'

// Static registration list — imported once (as a side effect) before
// PlatformShell first renders. The `has()` guard makes this idempotent under
// Vite HMR, which can re-execute a module's top-level code without a full
// page reload.
const modules = [reportsModule, purchaseManagerModule]

for (const module of modules) {
  if (!moduleRegistry.has(module.id)) {
    moduleRegistry.register(module)
  }
}

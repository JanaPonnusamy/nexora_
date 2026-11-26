// NEXORA MEDIQ Phase 6B: breadcrumb strip (Section / Screen) shown above
// every screen's own content. Pure presentation -- reads the same section
// mapping ErpSidebar uses, never re-derives permissions.
import { erpSectionForScreen } from './erpNav.js';

export function ErpBreadcrumb({ activeItem }) {
  if (!activeItem) return null;
  const section = erpSectionForScreen(activeItem.id);
  return (
    <div className="erp-breadcrumb" aria-label="Breadcrumb">
      {section && (
        <>
          <span className="erp-breadcrumb-section">{section.label}</span>
          <span className="erp-breadcrumb-sep" aria-hidden="true">/</span>
        </>
      )}
      <span className="erp-breadcrumb-current">{activeItem.label}</span>
    </div>
  );
}

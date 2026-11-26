import React from 'react';
import { Breadcrumbs } from './Breadcrumbs.jsx';
import { GlobalSearch } from './GlobalSearch.jsx';
import { NotificationArea } from './NotificationArea.jsx';
import { TenantContext } from './TenantContext.jsx';
import { ThemeSelector } from './ThemeSelector.jsx';
import { UserMenu } from './UserMenu.jsx';
import { GuideButton } from '../help/GuideButton.jsx';

export function TopBar() {
  return (
    <header className="ntm-topbar">
      <Breadcrumbs />
      <GlobalSearch />
      <div className="ntm-topbar__actions">
        <TenantContext />
        <span className="ntm-topbar__divider" aria-hidden="true" />
        <GuideButton />
        <ThemeSelector />
        <NotificationArea />
        <span className="ntm-topbar__divider" aria-hidden="true" />
        <UserMenu />
      </div>
    </header>
  );
}

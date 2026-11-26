import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { breadcrumbsForPath } from '../navigation/navConfig.js';

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = breadcrumbsForPath(pathname.replace(/^#/, ''));

  return (
    <nav className="ntm-breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <li key={`${crumb.label}-${index}`}>
              {last || !crumb.path ? (
                <span aria-current={last ? 'page' : undefined}>{crumb.label}</span>
              ) : (
                <Link to={crumb.path}>{crumb.label}</Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

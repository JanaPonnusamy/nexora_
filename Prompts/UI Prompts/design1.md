# NEXORA PLATFORM

# FRONTEND PRODUCT DESIGN

# VERSION 1.0

## PROJECT

NEXORA PLATFORM

Frontend Root:

E:\Nexora\frontend

Technology Stack:

* React 18
* TypeScript
* Vite
* Bootstrap 5
* Bootstrap Icons
* React Router
* Context API
* Local Storage
* JWT Ready Authentication

---

# DESIGN PHILOSOPHY

NEXORA is a modern SaaS platform.

Design inspiration:

* Linear
* Stripe Dashboard
* GitHub Enterprise
* Notion

NEXORA is NOT:

* Traditional ERP
* Desktop-style CRUD application
* Form-heavy administration portal

Goals:

* Fast navigation
* Clean information density
* Minimal visual noise
* Enterprise-grade usability
* Mobile-first responsiveness
* Consistent component system

---

# RESPONSIVE DESIGN FREEZE

Desktop

> = 1400px

Large Laptop

1200px - 1399px

Laptop

992px - 1199px

Tablet

768px - 991px

Mobile

< 768px

---

# APPLICATION SHELL

Layout Structure

Header

Sidebar

Content Area

Status Bar

Sidebar Behavior

Desktop

Expanded

Tablet

Collapsed

Mobile

Bootstrap Offcanvas

Theme Support

Dark Theme

Light Theme

Theme Persistence

localStorage

Default Theme

Dark

---

# NAVIGATION STRUCTURE

Platform Overview

Platform

* Tenants
* Stores
* Users
* Roles

Administration

* Modules
* Permissions

Reports

Settings

---

# SCREEN 01

## PLATFORM OVERVIEW

Purpose

Landing page after login.

Acts as navigation hub.

Sections

KPI Cards

* Tenants
* Stores
* Users
* Roles
* Modules

Quick Actions

* Create Tenant
* Create Store
* Create User
* Create Role
* Manage Permissions

Behavior

Quick Actions navigate to dedicated screens.

No modal forms.

No Recent Activity in Phase 1.

No Global Search in Phase 1.

---

# SCREEN 02

## TENANT MANAGEMENT

Purpose

Manage organizations.

Layout

Toolbar

* Search Tenant
* Status Filter
* Add Tenant

Grid Columns

* Tenant Code
* Tenant Abbreviation
* Tenant Name
* Database Name
* Status

Actions

* View
* Edit
* Open Stores
* Open Users

Rules

No Delete.

Deactivate Only.

Tenant opens dedicated workspace screen.

No side forms.

No split-screen CRUD.

---

# SCREEN 03

## STORE MANAGEMENT

Purpose

Manage stores under tenants.

Toolbar

* Tenant Filter
* Search Store
* Status Filter
* Add Store

Grid Columns

* Store Code
* Store Name
* Tenant
* Server Name
* Database Name
* Status

Actions

* View
* Edit
* Users
* Roles

Rules

No Delete.

Deactivate Only.

Store opens dedicated workspace screen.

---

# SCREEN 04

## USER MANAGEMENT

Purpose

Manage users and assignments.

Security Model

User -> Multiple Stores

User -> Multiple Roles

Toolbar

* Tenant Filter
* Store Filter
* Role Filter
* Search User
* Status Filter
* Add User

Grid Columns

* Username
* Full Name
* Store Count
* Role Count
* Last Login
* Status

Actions

* View
* Edit
* Store Assignments
* Role Assignments

Workspace Sections

* Profile
* Store Assignments
* Role Assignments
* Access Summary
* Login Activity

Rules

No Delete.

Deactivate Only.

---

# SCREEN 05

## ROLE MANAGEMENT

Role Model

Global Roles Only

Phase 1 Roles

* SUPER_ADMIN
* TENANT_ADMIN
* STORE_ADMIN
* STORE_MANAGER
* STORE_USER
* SYNC_OPERATOR

Toolbar

* Search
* Status Filter
* Add Role

Grid Columns

* Role Name
* Description
* Assigned Users
* Module Count
* Status

Actions

* View
* Edit
* Permissions

Workspace Sections

* Role Information
* Assigned Users
* Permission Summary
* Module Access Summary

Rules

No Custom Role Builder.

No Delete.

Deactivate Only.

---

# SCREEN 06

## PERMISSION MATRIX

Purpose

Central security administration screen.

Layout

Left Panel

Roles

Center Panel

Permission Matrix

Bottom Panel

Permission Summary

Columns

* Module
* View
* Create
* Edit
* Delete
* Export

Behavior

Inline Editing

Immediate Save

No popup editing

Toolbar

* Allow All
* Deny All
* Copy Role
* Refresh

Additional Features

* Search Module
* Filter Enabled
* Filter Disabled

Rules

Permission matrix is the primary security management interface.

---

# SCREEN 07

## MODULE MANAGEMENT

Purpose

Manage module registry.

Toolbar

* Search
* Status Filter
* Add Module

Grid Columns

* Module Code
* Module Name
* Description
* Assigned Roles
* Status

Actions

* View
* Edit
* Permissions

Workspace Sections

* Module Information
* Role Assignments
* Permission Usage
* Configuration

Rules

No Delete.

Deactivate Only.

---

# UX STANDARDS

Use:

* Cards
* Tables
* Badges
* Breadcrumbs
* Skeleton Loaders

Avoid:

* Excessive modals
* Split-screen CRUD layouts
* Complex nested navigation
* Dashboard clutter

---

# MOBILE RULES

Sidebar

Offcanvas

Tables

Convert to cards when necessary

Actions

Large touch targets

Forms

Single-column layout

---

# LOADING STATES

Use Skeleton Loaders

Do Not Use

* Blocking spinners
* Full-page loaders

---

# EMPTY STATES

Every screen must include:

* Empty State
* No Data State
* Error State

---

# IMPLEMENTATION ORDER

Phase UI-01B

Platform Shell

Phase UI-02

Tenant Management

Phase UI-03

Store Management

Phase UI-04

User Management

Phase UI-05

Role Management

Phase UI-06

Permission Matrix

Phase UI-07

Module Management

END OF DESIGN FREEZE

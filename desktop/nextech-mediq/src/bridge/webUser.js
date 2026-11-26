export function toWebUser(user, workspace) {
  if (!user) return null;
  const roles = Array.isArray(user.roles) ? user.roles : [];
  const primary = roles[0] || {};
  const roleNames = roles
    .map((role) => (typeof role === 'string' ? role : role?.role_name))
    .filter(Boolean);
  return {
    id: user.user_id || user.id || '',
    username: user.username || '',
    fullName: user.first_name || user.full_name || user.username || '',
    tenant: workspace?.tenantId || user.tenant_id || '',
    isPlatformUser: Boolean(user.is_platform_user),
    roleNames,
    storeId: primary.store_id || workspace?.storeId || '',
    storeCode: primary.store_code || '',
  };
}

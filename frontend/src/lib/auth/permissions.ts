/** Permission codes (mirror of backend `Perm`, D-52). The backend always re-checks; the panel
 * only hides what the user cannot do. */
export const Perm = {
  USER_READ: "identity.user.read",
  USER_CREATE: "identity.user.create",
  USER_UPDATE: "identity.user.update",
  USER_DISABLE: "identity.user.disable",
  USER_ASSIGN_ROLES: "identity.user.assign_roles",
  USER_RESET_MFA: "identity.user.reset_mfa",
  USER_REVOKE_SESSIONS: "identity.user.revoke_sessions",
  USER_ASSIGN_SCOPES: "identity.user.assign_scopes",
  ROLE_READ: "identity.role.read",
  ROLE_CREATE: "identity.role.create",
  ROLE_UPDATE: "identity.role.update",
  ROLE_DELETE: "identity.role.delete",
  PERMISSION_READ: "identity.permission.read",
  AUDIT_READ: "audit.log.read",
  GEOGRAPHY_READ: "geography.node.read",
  GEOGRAPHY_IMPORT_READ: "geography.import.read",
  PERSON_READ: "people.person.read",
  PERSON_WRITE: "people.person.write",
  PERSON_READ_SENSITIVE: "people.person.read_sensitive",
  PERSON_DELETE: "people.person.delete",
  NOTICE_MANAGE: "people.notice.manage",
  CANDIDACIES_READ: "candidacies.read",
  CATALOG_MANAGE: "candidacies.catalog.manage",
  PROCESS_MANAGE: "candidacies.process.manage",
  NOMINATION_WRITE: "candidacies.nomination.write",
  NOMINATION_APPROVE: "candidacies.nomination.approve",
  RULE_OVERRIDE: "candidacies.rule.override",
  PEACE_MEMBER_READ: "peace_movement.member.read",
  PEACE_MEMBER_WRITE: "peace_movement.member.write",
  PEACE_MEMBER_VALIDATE: "peace_movement.member.validate",
  PEACE_MEMBER_REASSIGN: "peace_movement.member.reassign",
  PEACE_MEMBER_IMPORT: "peace_movement.member.import",
  PEACE_HOUSE_READ: "peace_movement.house.read",
  PEACE_HOUSE_WRITE: "peace_movement.house.write",
  PEACE_HOUSE_REASSIGN_CREDIT: "peace_movement.house.reassign_credit",
  PEACE_STATS_READ: "peace_movement.stats.read",
  PEACE_GOAL_MANAGE: "peace_movement.goal.manage",
} as const;

export type PermCode = (typeof Perm)[keyof typeof Perm];

export interface Grants {
  grants_all: boolean;
  permissions: string[];
}

export function hasPermission(grants: Grants | undefined, code: PermCode): boolean {
  return !!grants && (grants.grants_all || grants.permissions.includes(code));
}

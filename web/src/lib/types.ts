export type Role = "admin" | "member"

export type MembershipRef = {
  org_id: string
  org_name: string
  role: Role
  data_manager: boolean
}

export type Me = {
  id: string
  email: string
  full_name: string
  email_verified: boolean
  memberships: MembershipRef[]
}

export type Org = {
  id: string
  name: string
  slug: string
  key_version: number
  my_role: Role
  my_data_manager: boolean
}

export type Member = {
  id: string
  user_id: string
  full_name: string
  email: string
  role: Role
  data_manager: boolean
  email_verified: boolean
  joined_at: string
}

export type Invitation = {
  id: string
  email: string
  role: Role
  data_manager: boolean
  expires_at: string
  expired: boolean
}

export type AuditEvent = {
  id: string
  action: string
  actor_user_id: string | null
  target_type: string | null
  target_id: string | null
  meta: Record<string, unknown>
  at: string
}

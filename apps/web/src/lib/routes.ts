import type { AuthUser } from "../api/types";
import { homePathFor } from "./labels";

export const CHANGE_PASSWORD_PATH = "/change-password";

/** Where a signed-in user belongs: the forced password screen wins over any home page. */
export function landingPathFor(user: AuthUser): string {
  return user.must_change_password ? CHANGE_PASSWORD_PATH : homePathFor(user.role);
}

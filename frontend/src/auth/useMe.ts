import { useEffect, useState } from "react";
import { apiGet, type CurrentUser } from "../api/client";
import { useAuth } from "./AuthProvider";

/** The signed-in user from /api/me (roles decide what the request pages offer), or null while loading. */
export function useMe(): CurrentUser | null {
  const { getAccessToken } = useAuth();
  const [me, setMe] = useState<CurrentUser | null>(null);
  useEffect(() => {
    apiGet<CurrentUser>("/me", getAccessToken)
      .then(setMe)
      .catch(() => setMe(null));
  }, [getAccessToken]);
  return me;
}

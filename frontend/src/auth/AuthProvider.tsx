import { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  InteractionRequiredAuthError,
  PublicClientApplication,
} from "@azure/msal-browser";
import { MsalProvider, useIsAuthenticated, useMsal } from "@azure/msal-react";

export const DEV_AUTH_BYPASS = import.meta.env.VITE_DEV_AUTH_BYPASS === "true";

const API_SCOPE = import.meta.env.VITE_ENTRA_API_SCOPE ?? "";

export interface AuthState {
  isAuthenticated: boolean;
  mode: "dev_bypass" | "entra";
  getAccessToken: () => Promise<string | null>;
  signIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const authState = useContext(AuthContext);
  if (authState === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return authState;
}

const devAuthState: AuthState = {
  isAuthenticated: true,
  mode: "dev_bypass",
  getAccessToken: async () => null,
  signIn: () => {},
  signOut: () => {},
};

function createMsalInstance(): PublicClientApplication {
  return new PublicClientApplication({
    auth: {
      clientId: import.meta.env.VITE_ENTRA_SPA_CLIENT_ID ?? "",
      authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID ?? ""}`,
      redirectUri: window.location.origin,
    },
    cache: { cacheLocation: "sessionStorage" },
  });
}

function MsalAuthBridge({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  const authState = useMemo<AuthState>(
    () => ({
      isAuthenticated,
      mode: "entra",
      getAccessToken: async () => {
        const account = accounts[0];
        if (!account) {
          return null;
        }
        try {
          const result = await instance.acquireTokenSilent({ scopes: [API_SCOPE], account });
          return result.accessToken;
        } catch (error) {
          if (error instanceof InteractionRequiredAuthError) {
            await instance.acquireTokenRedirect({ scopes: [API_SCOPE], account });
          }
          throw error;
        }
      },
      signIn: () => {
        instance.loginRedirect({ scopes: [API_SCOPE] });
      },
      signOut: () => {
        instance.logoutRedirect();
      },
    }),
    [instance, accounts, isAuthenticated],
  );

  return <AuthContext.Provider value={authState}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const msalInstance = useMemo(() => (DEV_AUTH_BYPASS ? null : createMsalInstance()), []);

  if (msalInstance === null) {
    return <AuthContext.Provider value={devAuthState}>{children}</AuthContext.Provider>;
  }

  return (
    <MsalProvider instance={msalInstance}>
      <MsalAuthBridge>{children}</MsalAuthBridge>
    </MsalProvider>
  );
}

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';

const userPool = new CognitoUserPool({
  UserPoolId: import.meta.env.REACT_APP_USER_POOL_ID || '',
  ClientId: import.meta.env.REACT_APP_CLIENT_ID || '',
});

/** In-memory JWT storage — never persisted to localStorage. */
let cachedSession: CognitoUserSession | null = null;

export function signIn(email: string, password: string): Promise<CognitoUserSession> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });

    user.authenticateUser(authDetails, {
      onSuccess(session) {
        cachedSession = session;
        resolve(session);
      },
      onFailure(err) {
        reject(err);
      },
    });
  });
}

export function signOut(): void {
  const user = userPool.getCurrentUser();
  if (user) user.signOut();
  cachedSession = null;
}

export function getSession(): Promise<CognitoUserSession | null> {
  if (cachedSession?.isValid()) return Promise.resolve(cachedSession);

  return new Promise((resolve) => {
    const user = userPool.getCurrentUser();
    if (!user) return resolve(null);

    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session?.isValid()) return resolve(null);
      cachedSession = session;
      resolve(session);
    });
  });
}

export async function getIdToken(): Promise<string | null> {
  const session = await getSession();
  return session?.getIdToken().getJwtToken() ?? null;
}

export async function getRole(): Promise<string> {
  const session = await getSession();
  if (!session) return 'viewer';
  const payload = session.getIdToken().decodePayload();
  return (payload['custom:role'] as string) || 'viewer';
}

export async function isAuthenticated(): Promise<boolean> {
  const session = await getSession();
  return session?.isValid() ?? false;
}

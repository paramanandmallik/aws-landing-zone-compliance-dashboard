/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly REACT_APP_USER_POOL_ID: string;
  readonly REACT_APP_CLIENT_ID: string;
  readonly REACT_APP_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

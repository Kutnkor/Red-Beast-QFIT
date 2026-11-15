// Types the bundler provides in the real app (Vite here). Only needed to type-check this folder alone.
declare module "*.png" {
  const url: string;
  export default url;
}
declare module "*.css";

interface ImportMetaEnv {
  /** Backend base URL in production, e.g. https://qfit-api.example.org (empty = same origin). */
  readonly VITE_QFIT_API?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

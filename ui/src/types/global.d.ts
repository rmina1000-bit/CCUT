interface CcutSanityState {
  consoleErrorCount: number;
  pageErrorCount: number;
  consoleErrors: string[];
  pageErrors: string[];
}

interface CcutComponentSmokeCaseResult {
  status: 'pending' | 'pass' | 'fail';
  message?: string;
}

interface CcutComponentSmokeState {
  consoleErrorCount: number;
  pageErrorCount: number;
  consoleErrors: string[];
  pageErrors: string[];
  components: Record<string, CcutComponentSmokeCaseResult>;
}

declare global {
  interface Window {
    __CCUT_SANITY__?: CcutSanityState;
    __CCUT_COMPONENT_SMOKE__?: CcutComponentSmokeState;
  }
}

export {};

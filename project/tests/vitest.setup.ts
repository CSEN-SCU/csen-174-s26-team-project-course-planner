import "@testing-library/jest-dom/vitest";

// Some Vitest suites run in non-jsdom environments (or with partially stubbed
// globals). Ensure a basic localStorage exists so onboarding/disclosure tests
// can persist "seen" flags without crashing.
const _memoryStorage = () => {
  let store: Record<string, string> = {};
  return {
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
    removeItem(key: string) {
      delete store[key];
    },
    clear() {
      store = {};
    },
    key(i: number) {
      return Object.keys(store)[i] ?? null;
    },
    get length() {
      return Object.keys(store).length;
    },
  };
};

const ls: any = (globalThis as any).localStorage;
if (
  !ls ||
  typeof ls.getItem !== "function" ||
  typeof ls.setItem !== "function" ||
  typeof ls.removeItem !== "function" ||
  typeof ls.clear !== "function"
) {
  // @ts-expect-error - define minimal Storage for tests
  (globalThis as any).localStorage = _memoryStorage();
}

// jsdom does not implement window.scrollTo; resetPageScroll() calls it on
// every full-screen view mount, so any test that renders <Root> logs a noisy
// "Not implemented: window.scrollTo" React layout-effect stack. Stub it to a
// no-op so the test output stays clean (production uses the real browser API).
if (typeof (globalThis as any).window !== "undefined") {
  (globalThis as any).window.scrollTo = () => {};
}

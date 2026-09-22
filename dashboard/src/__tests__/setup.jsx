import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';

// ── matchMedia mock ──
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// ── ResizeObserver mock ──
class ResizeObserverMock {
  constructor(cb) {
    this._cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverMock;

// ── IntersectionObserver mock ──
class IntersectionObserverMock {
  constructor(cb) {
    this._cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.IntersectionObserver = IntersectionObserverMock;

// ── clipboard mock ──
Object.defineProperty(navigator, 'clipboard', {
  value: {
    writeText: vi.fn().mockResolvedValue(undefined),
    readText: vi.fn().mockResolvedValue(''),
  },
  writable: true,
  configurable: true,
});

// ── framer-motion mock ──
vi.mock('framer-motion', () => {
  const actual = { __esModule: true };

  // Create a wrapper that forwards all props as-is to a plain div/span
  function createMotionProxy() {
    return new Proxy(
      {},
      {
        get(_target, prop) {
          return function MotionComponent({ children, initial, animate, exit, variants, whileHover, whileTap, transition, layout, ...rest }) {
            const Tag = typeof prop === 'string' ? prop : 'div';
            return <Tag data-testid={rest['data-testid']} {...rest}>{children}</Tag>;
          };
        },
      }
    );
  }

  actual.motion = createMotionProxy();
  actual.AnimatePresence = ({ children }) => <>{children}</>;
  actual.useAnimation = () => ({ start: vi.fn(), stop: vi.fn() });
  actual.useMotionValue = (init) => ({ get: () => init, set: vi.fn() });
  actual.useTransform = (val) => val;

  return actual;
});

// ── recharts ResponsiveContainer mock ──
// ResponsiveContainer needs a width/height that jsdom cannot provide
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => (
      <div data-testid="responsive-container" style={{ width: 500, height: 300 }}>
        {children}
      </div>
    ),
  };
});

// ── @monaco-editor/react mock ──
vi.mock('@monaco-editor/react', () => ({
  default: (props) => (
    <textarea
      data-testid="monaco-editor"
      value={props.value || ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    />
  ),
}));

// ── Test QueryClient factory ──
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

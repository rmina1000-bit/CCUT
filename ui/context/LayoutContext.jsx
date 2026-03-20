import React, {
  createContext, useContext, useState, useCallback, useRef, useMemo,
} from 'react';

const MIN_PCT = 3.2; // ≈ 40 px at 1280 wide

const LayoutContext = createContext(null);

export function LayoutProvider({ children }) {
  // Use discrete preferred widths that only change on manual resize
  const [widths, setWidths] = useState({ left: 16, center: 84, right: 0 });
  const [collapsed, setCollapsed] = useState({ left: false, center: false, right: true });

  const preferredWidths = useRef({ left: 16, right: 34 }); // User's desired sizes
  const domRefs = useRef({ container: null, left: null, center: null, right: null });

  const setRef = useCallback((id, el) => { domRefs.current[id] = el; }, []);

  const updateWidths = useCallback((next) => {
    // When the user drags a handle, we update the preferred widths
    if (next.left !== undefined && !collapsed.left) preferredWidths.current.left = next.left;
    if (next.right !== undefined && !collapsed.right) preferredWidths.current.right = next.right;

    setWidths({
      left: Math.max(MIN_PCT, next.left),
      center: Math.max(MIN_PCT, next.center),
      right: Math.max(MIN_PCT, next.right),
    });
  }, [collapsed]);

  const toggleCollapse = useCallback((id) => {
    setCollapsed((prev) => {
      const willCollapse = !prev[id];
      const nextCollapsed = { ...prev, [id]: willCollapse };

      // Calculate new widths deterministically based on preferredWidths and nextCollapsed
      const L = nextCollapsed.left ? 0 : preferredWidths.current.left;
      const R = nextCollapsed.right ? 0 : preferredWidths.current.right;
      const C = Math.max(MIN_PCT, 100 - L - R);

      // Re-adjust L and R if Center is squeezed too hard
      const finalL = L;
      const finalR = R;

      setWidths({ left: finalL, center: C, right: finalR });
      return nextCollapsed;
    });
  }, []); // No longer depends on widths! Very stable for rapid clicks.

  const value = useMemo(
    () => ({ widths, collapsed, domRefs: domRefs.current, setRef, updateWidths, toggleCollapse }),
    [widths, collapsed, setRef, updateWidths, toggleCollapse],
  );

  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
}

export const useLayout = () => useContext(LayoutContext);

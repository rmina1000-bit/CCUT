import React, {
  createContext, useContext, useState, useCallback, useRef, useMemo,
} from 'react';

const MIN_PCT = 3.2; // ≈ 40 px at 1280 wide

const LayoutContext = createContext(null);

export function LayoutProvider({ children }) {
  const [widths, setWidths] = useState({ left: 18, center: 32, right: 50 });
  const [collapsed, setCollapsed] = useState({ left: false, center: false, right: false });

  const savedWidths = useRef({ left: 18, center: 32, right: 50 });
  const domRefs = useRef({ container: null, left: null, center: null, right: null });

  const setRef = useCallback((id, el) => { domRefs.current[id] = el; }, []);

  const updateWidths = useCallback((next) => {
    setWidths({
      left:   Math.max(MIN_PCT, next.left),
      center: Math.max(MIN_PCT, next.center),
      right:  Math.max(MIN_PCT, next.right),
    });
  }, []);

  const toggleCollapse = useCallback((id) => {
    setCollapsed((prev) => {
      const willCollapse = !prev[id];
      if (willCollapse) {
        savedWidths.current[id] = widths[id];
      } else {
        const restore = savedWidths.current[id];
        setWidths((w) => {
          const others = ['left', 'center', 'right'].filter(
            (k) => k !== id && !prev[k],
          );
          const totalOther = others.reduce((s, k) => s + w[k], 0);
          const newW = { ...w, [id]: restore };
          others.forEach((k) => {
            newW[k] = Math.max(
              MIN_PCT,
              w[k] - restore * (w[k] / totalOther),
            );
          });
          return newW;
        });
      }
      return { ...prev, [id]: willCollapse };
    });
  }, [widths]);

  const value = useMemo(
    () => ({ widths, collapsed, domRefs: domRefs.current, setRef, updateWidths, toggleCollapse }),
    [widths, collapsed, setRef, updateWidths, toggleCollapse],
  );

  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
}

export const useLayout = () => useContext(LayoutContext);

import { useState, useEffect, useRef } from "react";

export type ProjectItem = {
  id: string;
  name: string;
  date: string;
  count: number;
};

const MIN_CENTER = 420;
const MIN_RIGHT = 400;
const LEFT_NAV_WIDTH = 220;

export const useWorkspaceLayout = () => {
  const [activeNavItem, setActiveNavItem] = useState("projects");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [projects, setProjects] = useState<ProjectItem[]>([]);

  const [centerWidth, setCenterWidth] = useState<number>(() => {
    const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
    return Math.max(MIN_CENTER, Math.floor(vw * 0.55));
  });

  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const totalWidth = containerRect.width;
      const relativeX = e.clientX - containerRect.left - LEFT_NAV_WIDTH;
      const maxCenter = totalWidth - LEFT_NAV_WIDTH - MIN_RIGHT;
      const clamped = Math.max(MIN_CENTER, Math.min(maxCenter, relativeX));

      setCenterWidth(clamped);
    };

    const handleMouseUp = () => setIsDragging(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  return {
    containerRef,
    activeNavItem,
    setActiveNavItem,
    navCollapsed,
    setNavCollapsed,
    projects,
    setProjects,
    centerWidth,
    isDragging,
    setIsDragging,
  };
};

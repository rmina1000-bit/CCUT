import { useState, useEffect, useRef } from "react";

export type ProjectItem = {
  id: string;
  name: string;
  date: string;
  count: number;
};

const MIN_CENTER = 420;
const MIN_RIGHT = 400;

export const useWorkspaceLayout = () => {
  const [activeNavItem, setActiveNavItem] = useState(() => {
    // [홈] 재시작은 항상 첫 화면(projects). 마지막 프로젝트 자동복원 제거.
    return "projects";
  });
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [projects, setProjects] = useState<ProjectItem[]>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("ccut_projects");
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });

  const [centerWidth, setCenterWidth] = useState<number>(() => {
    const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
    return Math.max(MIN_CENTER, Math.floor(vw * 0.55));
  });

  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem("ccut_active_project_id", activeNavItem);
  }, [activeNavItem]);

  useEffect(() => {
    localStorage.setItem("ccut_projects", JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const currentLeftNavWidth = navCollapsed ? 48 : 320;
      const containerRect = containerRef.current.getBoundingClientRect();
      const totalWidth = containerRect.width;
      const relativeX = e.clientX - containerRect.left - currentLeftNavWidth;
      const maxCenter = totalWidth - currentLeftNavWidth - MIN_RIGHT;
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

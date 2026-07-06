import { useState, useEffect, useRef } from "react";

export type ProjectItem = {
  id: string;
  name: string;
  date: string;
  count: number;
};

// [LAYOUT] 기본 크기 30% 축소 + 사용자 드래그 리사이즈 + localStorage 저장
const MIN_CENTER = 320;
const MIN_RIGHT = 400;
const MIN_NAV = 168;
const MAX_NAV = 460;
const DEFAULT_NAV = 224;      // 기존 320 → 30% 축소
const CENTER_RATIO = 0.385;   // 기존 0.55 → 30% 축소

const loadNum = (key: string): number | null => {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(key);
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

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

  // [LAYOUT] 좌측 사이드바 폭 — 저장값 우선, 없으면 30% 축소 기본값
  const [navWidth, setNavWidth] = useState<number>(() =>
    clamp(loadNum("ccut_nav_width") ?? DEFAULT_NAV, MIN_NAV, MAX_NAV)
  );

  // [LAYOUT] 중앙 채팅 폭 — 저장값 우선, 없으면 vw*0.385(기존 0.55에서 30%↓)
  const [centerWidth, setCenterWidth] = useState<number>(() => {
    const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
    const saved = loadNum("ccut_center_width");
    if (saved != null) return Math.max(MIN_CENTER, saved);
    return Math.max(MIN_CENTER, Math.floor(vw * CENTER_RATIO));
  });

  const [isDragging, setIsDragging] = useState(false);        // 중앙/우측 경계
  const [isNavDragging, setIsNavDragging] = useState(false);  // 좌측 사이드바 경계
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem("ccut_active_project_id", activeNavItem);
  }, [activeNavItem]);

  useEffect(() => {
    localStorage.setItem("ccut_projects", JSON.stringify(projects));
  }, [projects]);

  // [LAYOUT] 리사이즈 결과 저장 → 새로고침 후에도 유지
  useEffect(() => {
    localStorage.setItem("ccut_nav_width", String(navWidth));
  }, [navWidth]);

  useEffect(() => {
    localStorage.setItem("ccut_center_width", String(centerWidth));
  }, [centerWidth]);

  // 중앙/우측 경계 드래그
  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const currentLeftNavWidth = navCollapsed ? 48 : navWidth;
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
  }, [isDragging, navCollapsed, navWidth]);

  // 좌측 사이드바 경계 드래그
  useEffect(() => {
    if (!isNavDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      setNavWidth(clamp(x, MIN_NAV, MAX_NAV));
    };

    const handleMouseUp = () => setIsNavDragging(false);

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
  }, [isNavDragging]);

  return {
    containerRef,
    activeNavItem,
    setActiveNavItem,
    navCollapsed,
    setNavCollapsed,
    projects,
    setProjects,
    navWidth,
    setNavWidth,
    isNavDragging,
    setIsNavDragging,
    centerWidth,
    isDragging,
    setIsDragging,
  };
};

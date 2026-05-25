import React, { useState, useEffect } from "react";
import { fetcher } from "@/services/api";
import { Search, Film, Calendar, Clock, RotateCcw, Box, ArrowRight } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface Source {
  source_id: string;
  file_path: string;
  title: string;
  duration: number;
  fps: number;
  created_at: string | null;
}

interface Program {
  program_id: string;
  name: string;
  status: string;
  created_at: string | null;
}

interface Proposal {
  proposal_id: string;
  source_id: string;
  mode: string;
  duration: number;
  created_at: string | null;
}

interface ArchiveData {
  sources: Source[];
  programs: Program[];
  proposals: Proposal[];
}

export const ArchivePanel: React.FC = () => {
  const [data, setData] = useState<ArchiveData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSubTab, setActiveSubTab] = useState<"sources" | "programs" | "proposals">("sources");

  const fetchArchive = async () => {
    setLoading(true);
    try {
      const res = await fetcher("/archive/list") as ArchiveData;
      setData(res);
    } catch (e) {
      console.error("[ArchivePanel] Error loading archive list:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArchive();
  }, []);

  const filteredSources = data?.sources.filter(s => 
    s.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.source_id.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const filteredPrograms = data?.programs.filter(p => 
    p.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.program_id.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const filteredProposals = data?.proposals.filter(pr => 
    pr.proposal_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    pr.source_id.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const formatSecs = (seconds?: number) => {
    if (!seconds) return "0초";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`;
  };

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">
            CCUT 미디어 아카이브
          </h1>
          <p className="text-[12px] text-muted-foreground/60 mt-1">
            분석이 완료된 비디오 소스 및 이전 제안 이력을 관리합니다.
          </p>
        </div>
        <button
          onClick={fetchArchive}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground/80 transition-colors border border-border/20"
        >
          <RotateCcw size={12} />
          새로고침
        </button>
      </div>

      {/* Stats Board */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">분석된 원본 영상</CardTitle>
            <Film size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.sources.length ?? 0}개</div>
          </CardContent>
        </Card>
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">생성된 프로그램 프로젝트</CardTitle>
            <Box size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.programs.length ?? 0}개</div>
          </CardContent>
        </Card>
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">AI 편집 제안서 이력</CardTitle>
            <ArrowRight size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.proposals.length ?? 0}개</div>
          </CardContent>
        </Card>
      </div>

      {/* Search & Tabs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card/15 p-3 rounded-xl border border-border/10">
        <div className="flex items-center gap-1.5 bg-secondary/30 rounded-lg p-0.5">
          <button
            onClick={() => setActiveSubTab("sources")}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeSubTab === "sources" ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"
            }`}
          >
            원본 리스트
          </button>
          <button
            onClick={() => setActiveSubTab("programs")}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeSubTab === "programs" ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"
            }`}
          >
            프로젝트 관리
          </button>
          <button
            onClick={() => setActiveSubTab("proposals")}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeSubTab === "proposals" ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"
            }`}
          >
            AI 편집제안 이력
          </button>
        </div>

        <div className="relative w-full md:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/40" />
          <Input
            placeholder="아카이브 내 검색..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-8 bg-secondary/30 border-border/10 text-xs focus-visible:ring-primary/40 rounded-lg"
          />
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-h-[300px]">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted-foreground/40 text-xs gap-2">
            <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            아카이브 데이터 로드 중...
          </div>
        ) : (
          <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden">
            {activeSubTab === "sources" && (
              <div className="divide-y divide-border/10">
                {filteredSources.length > 0 ? filteredSources.map(s => (
                  <div key={s.source_id} className="p-4 hover:bg-secondary/20 transition-colors flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Film size={16} className="text-primary" />
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-foreground/90">{s.title || s.source_id}</h4>
                        <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground/60 mt-1">
                          <span className="flex items-center gap-1"><Clock size={10} /> {formatSecs(s.duration)}</span>
                          <span>·</span>
                          <span>{s.fps} FPS</span>
                          <span>·</span>
                          <span className="font-mono text-muted-foreground/45">{s.source_id}</span>
                        </div>
                      </div>
                    </div>
                    {s.created_at && (
                      <div className="text-[11px] text-muted-foreground/40 flex items-center gap-1">
                        <Calendar size={10} />
                        {new Date(s.created_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                )) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 원본 영상이 없습니다.</div>
                )}
              </div>
            )}

            {activeSubTab === "programs" && (
              <div className="divide-y divide-border/10">
                {filteredPrograms.length > 0 ? filteredPrograms.map(p => (
                  <div key={p.program_id} className="p-4 hover:bg-secondary/20 transition-colors flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Box size={16} className="text-primary" />
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-foreground/90">{p.name || p.program_id}</h4>
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60 mt-1">
                          <span className={`px-1.5 py-0.5 rounded-[3px] text-[9px] font-bold ${
                            p.status === "DRAFT" ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"
                          }`}>{p.status}</span>
                          <span>·</span>
                          <span className="font-mono text-muted-foreground/45">{p.program_id}</span>
                        </div>
                      </div>
                    </div>
                    {p.created_at && (
                      <div className="text-[11px] text-muted-foreground/40 flex items-center gap-1">
                        <Calendar size={10} />
                        {new Date(p.created_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                )) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 프로젝트가 없습니다.</div>
                )}
              </div>
            )}

            {activeSubTab === "proposals" && (
              <div className="divide-y divide-border/10">
                {filteredProposals.length > 0 ? filteredProposals.map(pr => (
                  <div key={pr.proposal_id} className="p-4 hover:bg-secondary/20 transition-colors flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <ArrowRight size={16} className="text-primary" />
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-foreground/90">제안서: {pr.proposal_id}</h4>
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60 mt-1">
                          <span className="bg-primary/10 text-primary px-1 py-0.5 rounded text-[9px] font-bold">{pr.mode} Mode</span>
                          <span>·</span>
                          <span>길이: {formatSecs(pr.duration)}</span>
                          <span>·</span>
                          <span className="font-mono text-muted-foreground/45">연동 원본: {pr.source_id}</span>
                        </div>
                      </div>
                    </div>
                    {pr.created_at && (
                      <div className="text-[11px] text-muted-foreground/40 flex items-center gap-1">
                        <Calendar size={10} />
                        {new Date(pr.created_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                )) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 제안 이력이 없습니다.</div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

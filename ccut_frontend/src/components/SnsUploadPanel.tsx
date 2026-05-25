import React, { useState, useEffect } from "react";
import { fetcher, API_BASE_URL } from "@/services/api";
import { Share2, Video, Globe, Play, Youtube, AlertCircle, CheckCircle, RotateCcw } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface PublishedAsset {
  publish_id: string;
  program_id: string;
  platform: string;
  final_video_path: string;
  title: string;
  published_at: string | null;
}

export const SnsUploadPanel: React.FC = () => {
  const [assets, setAssets] = useState<PublishedAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAsset, setSelectedAsset] = useState<PublishedAsset | null>(null);
  
  // Form fields
  const [videoTitle, setVideoTitle] = useState("");
  const [description, setDescription] = useState("");
  const [platform, setPlatform] = useState("YouTube Shorts");
  const [tags, setTags] = useState("#CCUT #AI #Shorts");

  // Progress/Status
  const [publishing, setPublishing] = useState(false);
  const [pubProgress, setPubProgress] = useState(0);
  const [resultMsg, setResultMsg] = useState<{ status: "success" | "error"; text: string; url?: string } | null>(null);

  const fetchAssets = async () => {
    setLoading(true);
    try {
      const data = await fetcher("/publish/list") as PublishedAsset[];
      setAssets(data || []);
      if (data && data.length > 0 && !selectedAsset) {
        handleSelectAsset(data[0]);
      }
    } catch (e) {
      console.error("[SnsUploadPanel] Error loading published assets:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssets();
  }, []);

  const handleSelectAsset = (asset: PublishedAsset) => {
    setSelectedAsset(asset);
    setVideoTitle(asset.title || `송출본 (${asset.program_id})`);
    setDescription("CCUT 1.0.6 AI PD가 자동 편집 및 발행한 영상입니다.");
    setResultMsg(null);
  };

  const handlePublish = async () => {
    if (!selectedAsset) return;
    setPublishing(true);
    setPubProgress(10);
    setResultMsg(null);

    // Progress bar simulation
    const interval = setInterval(() => {
      setPubProgress((p) => {
        if (p >= 90) {
          clearInterval(interval);
          return 90;
        }
        return p + 15;
      });
    }, 400);

    try {
      // Trigger backend publish
      const res = await fetcher(`/publish/${selectedAsset.publish_id}`, {
        method: "POST"
      }) as { status: string; url?: string; message?: string };
      
      clearInterval(interval);
      setPubProgress(100);

      if (res.status === "SUCCESS") {
        setResultMsg({
          status: "success",
          text: res.message || "SNS 채널에 전 세계 송출이 완료되었습니다!",
          url: res.url
        });
        // refresh asset list
        fetchAssets();
      } else {
        setResultMsg({
          status: "error",
          text: res.message || "송출 중 에러가 발생했습니다."
        });
      }
    } catch (err: any) {
      clearInterval(interval);
      setResultMsg({
        status: "error",
        text: err.message || "서버 통신 실패"
      });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">
            SNS 채널 원클릭 퍼블리싱
          </h1>
          <p className="text-[12px] text-muted-foreground/60 mt-1">
            렌더링이 완료된 실제 영상을 YouTube Shorts, TikTok 등 소셜 채널로 즉시 송출합니다.
          </p>
        </div>
        <button
          onClick={fetchAssets}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground/80 transition-colors border border-border/20"
        >
          <RotateCcw size={12} />
          새로고침
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
        {/* Left list of final render exports */}
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-xs font-semibold text-muted-foreground/60 uppercase tracking-widest px-1">
            송출 가능 렌더링 파일 목록
          </h3>
          
          {loading ? (
            <div className="flex items-center justify-center h-48 text-muted-foreground/40 text-xs">
              목록 로딩 중...
            </div>
          ) : assets.length > 0 ? (
            <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
              {assets.map((asset) => (
                <div
                  key={asset.publish_id}
                  onClick={() => handleSelectAsset(asset)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                    selectedAsset?.publish_id === asset.publish_id
                      ? "bg-primary/10 border-primary"
                      : "bg-card/25 border-border/10 hover:border-border/30"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-secondary/80 flex items-center justify-center flex-shrink-0">
                      <Video size={14} className="text-foreground/80" />
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-foreground/90 truncate">{asset.title}</h4>
                      <p className="text-[10px] text-muted-foreground/50 font-mono mt-0.5 truncate">{asset.publish_id}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="bg-secondary px-1.5 py-0.5 rounded text-[8px] font-bold text-muted-foreground/80">
                          {asset.platform || "LOCAL"}
                        </span>
                        {asset.published_at && (
                          <span className="text-[9px] text-muted-foreground/40">
                            {new Date(asset.published_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-card/10 border border-border/10 rounded-xl p-8 text-center text-xs text-muted-foreground/40">
              렌더링 완료 파일이 없습니다. 메인 페이지에서 "출력 제어" 또는 "최종 렌더링"을 먼저 실행하십시오.
            </div>
          )}
        </div>

        {/* Right upload form and controls */}
        <div className="lg:col-span-3">
          {selectedAsset ? (
            <Card className="bg-card/30 border-border/15">
              <CardHeader className="p-4 border-b border-border/10 flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold text-foreground/90">채널 업로드 설정</CardTitle>
                  <p className="text-[10px] text-muted-foreground/45 mt-0.5 font-mono">ID: {selectedAsset.publish_id}</p>
                </div>
                <Globe size={16} className="text-primary/70" />
              </CardHeader>
              <CardContent className="p-6 space-y-4">
                {/* Platform select */}
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground/75 font-semibold">대상 채널</label>
                  <div className="flex items-center gap-2">
                    {["YouTube Shorts", "TikTok", "Instagram Reels"].map((p) => (
                      <button
                        key={p}
                        onClick={() => setPlatform(p)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                          platform === p
                            ? "bg-primary/20 border-primary text-primary"
                            : "bg-secondary/40 border-border/10 text-muted-foreground/70 hover:text-foreground/80"
                        }`}
                      >
                        {p === "YouTube Shorts" && <Youtube size={12} className="text-red-500" />}
                        {p}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Title */}
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground/75 font-semibold">동영상 제목</label>
                  <Input
                    value={videoTitle}
                    onChange={(e) => setVideoTitle(e.target.value)}
                    className="bg-secondary/20 border-border/10 text-xs rounded-lg focus-visible:ring-primary/40"
                  />
                </div>

                {/* Description */}
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground/75 font-semibold">설명글</label>
                  <Textarea
                    value={description}
                    rows={4}
                    onChange={(e) => setDescription(e.target.value)}
                    className="bg-secondary/20 border-border/10 text-xs rounded-lg focus-visible:ring-primary/40 resize-none"
                  />
                </div>

                {/* Tags */}
                <div className="space-y-1.5">
                  <label className="text-[11px] text-muted-foreground/75 font-semibold">태그 (쉼표 또는 띄어쓰기 구분)</label>
                  <Input
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    className="bg-secondary/20 border-border/10 text-xs rounded-lg focus-visible:ring-primary/40"
                  />
                </div>

                {/* Result Message / Progress */}
                {publishing && (
                  <div className="p-4 bg-secondary/20 rounded-xl space-y-2 border border-border/10">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground/60 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-primary animate-ping" />
                        SNS API 채널 전송 중...
                      </span>
                      <span className="font-mono text-primary font-bold">{pubProgress}%</span>
                    </div>
                    <div className="w-full bg-secondary/80 h-1.5 rounded-full overflow-hidden">
                      <div className="bg-primary h-full transition-all duration-300" style={{ width: `${pubProgress}%` }} />
                    </div>
                  </div>
                )}

                {resultMsg && (
                  <div className={`p-4 rounded-xl border flex items-start gap-3 ${
                    resultMsg.status === "success" 
                      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
                      : "bg-red-500/10 border-red-500/20 text-red-400"
                  }`}>
                    {resultMsg.status === "success" ? <CheckCircle size={16} className="mt-0.5" /> : <AlertCircle size={16} className="mt-0.5" />}
                    <div className="text-xs">
                      <p className="font-semibold text-foreground/90">{resultMsg.text}</p>
                      {resultMsg.url && (
                        <a 
                          href={resultMsg.url} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="mt-2 inline-flex items-center gap-1 text-primary hover:underline font-bold"
                        >
                          <Play size={10} className="fill-primary" />
                          게시물 직접 보러가기
                        </a>
                      )}
                    </div>
                  </div>
                )}

                {/* Action Submit */}
                <div className="pt-2">
                  <Button
                    onClick={handlePublish}
                    disabled={publishing}
                    className="w-full flex items-center justify-center gap-2 h-10 text-xs bg-primary hover:bg-primary-hover text-white rounded-lg font-bold"
                  >
                    <Share2 size={13} />
                    {publishing ? "송출 처리 중..." : `${platform} 채널 즉시 업로드`}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="bg-card/10 border border-border/10 rounded-xl p-12 text-center text-xs text-muted-foreground/40 h-full flex flex-col items-center justify-center gap-2">
              <Share2 size={24} className="text-muted-foreground/30" />
              업로드할 비디오를 왼쪽 목록에서 선택해 주세요.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

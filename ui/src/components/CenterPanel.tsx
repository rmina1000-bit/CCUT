import React, { useState, useRef, useEffect } from "react";
import { Upload, Send, Play, Loader2, Check, User, Bot, Plus } from "lucide-react";
import type { Fragment, Proposal, AppState } from "../types/boundaryTypes";
import { ScrollArea } from "./ui/scroll-area";
import { uploadVideo } from "../services/videoService";
import { generateProposals } from "../services/proposalService";

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  proposals?: [Proposal, Proposal];
}

interface CenterPanelProps {
  selectedFragment: Fragment | null;
  selectedSource: string;
  editSequence: Fragment[];
  onProposalSelect: (proposal: Proposal, label: 'A' | 'B') => void;
  onStateChange: (state: AppState) => void;
  onFileUpload: (file: File) => void;
}

const CenterPanel: React.FC<CenterPanelProps> = ({
  selectedFragment,
  selectedSource,
  editSequence,
  onProposalSelect,
  onStateChange,
  onFileUpload,
}) => {
  const [appState, setAppState] = useState<AppState>("empty");
  const [chatInput, setChatInput] = useState("");
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [proposals, setProposals] = useState<[Proposal, Proposal] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Simulated progress during upload (real progress requires XHR)
  useEffect(() => {
    if (appState !== "analyzing") return;
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 90) { clearInterval(interval); return 90; }
        return prev + Math.random() * 8 + 2;
      });
    }, 200);
    return () => clearInterval(interval);
  }, [appState]);

  const changeState = (state: AppState) => {
    console.log('[D3] changeState:', state);
    setAppState(state);
    onStateChange(state);
  };

  const processFile = async (file: File) => {
    console.log('[D2] processFile 진입:', file.name, file.size, 'bytes');
    setError(null);
    changeState('analyzing');
    onFileUpload(file);

    try {
      console.log('[D4] uploadVideo 호출 시작');
      const fragments = await uploadVideo(file, (pct) => setUploadProgress(pct));
      console.log('[D4] fragments 수신:', fragments.length, '개');
      const generatedProposals = await generateProposals(fragments);
      console.log('[D5] proposals 수신:', generatedProposals.length, '개');
      setProposals(generatedProposals);
      setUploadProgress(100);
      setTimeout(() => changeState('proposal'), 400);
    } catch (err) {
      console.error('[D4] 에러 발생:', err);
      setError(err instanceof Error ? err.message : String(err));
      changeState('empty');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    console.log('[D1] handleFileChange 진입');
    const file = e.target.files?.[0];
    console.log('[D1] file:', file?.name, file?.size, file?.type);
    if (!file) { console.log('[D1] file 없음 — return'); return; }
    processFile(file);
  };

  const handleUploadClick = () => {
    console.log('[D1] 업로드 버튼 클릭됨, fileInputRef:', fileInputRef.current);
    fileInputRef.current?.click();
  };

  const handleSelectProposal = (proposal: Proposal) => {
    setSelectedProposalId(proposal.id);
  };

  const handleStartChat = () => {
    if (!proposals || !selectedProposalId) return;
    const proposal = proposals.find(p => p.id === selectedProposalId);
    if (!proposal) return;

    console.log('[D6] onProposalSelect 호출:', proposal.label);
    onProposalSelect(proposal, proposal.label);

    setMessages([{
      id: "1",
      role: "ai",
      content: `"${proposal.title}" 편집안을 선택하셨습니다. ${proposal.description}. 수정이 필요하시면 말씀해 주세요.`,
    }]);
    changeState('chat');
  };

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: "user", content: chatInput };
    setMessages(prev => [...prev, userMsg]);
    setChatInput("");

    // TODO: connect to backend chat/AI endpoint
    setTimeout(() => {
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "ai",
        content: "네, 이해했습니다. 새로운 편집안을 준비하고 있어요.",
        proposals: proposals ?? undefined,
      };
      setMessages(prev => [...prev, aiMsg]);
    }, 1200);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  console.log('[D7] CenterPanel 렌더, appState:', appState, 'proposals:', proposals?.length ?? 0);

  // ── Empty ──
  if (appState === "empty") {
    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 flex items-center justify-center p-6">
          <div
            className="w-full max-w-[260px] border border-dashed border-border/30 rounded-xl p-6 flex flex-col items-center gap-3 hover:border-foreground/15 transition-colors cursor-pointer"
            onClick={(e) => { e.stopPropagation(); handleUploadClick(); }}
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const file = e.dataTransfer.files[0];
              if (file) processFile(file);
            }}
          >
            <div className="w-10 h-10 rounded-xl bg-secondary/60 flex items-center justify-center">
              <Upload size={17} className="text-muted-foreground/70" />
            </div>
            <div className="text-center space-y-0.5">
              <p className="text-[12px] font-medium text-foreground/80">영상을 업로드하세요</p>
              <p className="text-[10px] text-muted-foreground/50">드래그하거나 클릭</p>
            </div>
            {error && (
              <p className="text-[10px] text-red-400 text-center">{error}</p>
            )}
            <button
              className="px-4 py-1.5 rounded-lg border border-foreground/12 bg-transparent text-foreground/70 text-[11px] font-medium hover:bg-foreground/5 hover:border-foreground/20 transition-all"
              onClick={(e) => { e.stopPropagation(); handleUploadClick(); }}
            >
              파일 선택
            </button>
          </div>
          {/* File input outside the clickable div to avoid event conflicts */}
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden', opacity: 0 }}
            onChange={handleFileChange}
          />
        </div>
        <ChatBar
          value={chatInput}
          onChange={setChatInput}
          onSend={handleSendMessage}
          onKeyDown={handleKeyDown}
          onFileSelect={processFile}
          disabled
        />
      </div>
    );
  }

  // ── Analyzing ──
  if (appState === "analyzing") {
    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="flex flex-col items-center gap-4 w-full max-w-[220px]">
            <div className="w-10 h-10 rounded-xl bg-secondary/60 flex items-center justify-center">
              <Loader2 size={17} className="text-primary/70 animate-spin" />
            </div>
            <div className="text-center space-y-0.5">
              <p className="text-[12px] font-medium text-foreground/80">AI가 영상을 분석하고 있어요</p>
              <p className="text-[10px] text-muted-foreground/50">장면 분할, 감정 분석, 구조 파악 중</p>
            </div>
            <div className="w-full h-1 bg-secondary/60 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary/60 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${Math.min(uploadProgress, 100)}%` }}
              />
            </div>
            <p className="text-[9px] text-muted-foreground/40">{Math.min(Math.round(uploadProgress), 100)}%</p>
            {error && <p className="text-[10px] text-red-400 text-center">{error}</p>}
          </div>
        </div>
        <ChatBar value="" onChange={() => {}} onSend={() => {}} onKeyDown={() => {}} disabled />
      </div>
    );
  }

  // ── Proposal ──
  if (appState === "proposal" && proposals) {
    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 py-3 space-y-2">
            <h3 className="text-[11px] font-medium text-foreground/70">편집안 선택</h3>
            <div className="grid grid-cols-2 gap-2">
              {proposals.map((p) => (
                <ProposalCard
                  key={p.id}
                  proposal={p}
                  isSelected={selectedProposalId === p.id}
                  onSelect={() => handleSelectProposal(p)}
                />
              ))}
            </div>
          </div>

          <div className="mx-4 h-px bg-border/20" />

          <div className="px-4 py-3 space-y-2">
            <h4 className="text-[9px] font-medium text-muted-foreground/50 uppercase tracking-wider">Preview</h4>
            {selectedProposalId ? (
              <div className="space-y-2">
                <div className="w-full h-24 rounded-lg border border-border/20 bg-secondary/20 flex items-center justify-center">
                  <Play size={16} className="text-muted-foreground/30" />
                </div>
                <button
                  onClick={handleStartChat}
                  className="w-full py-2 rounded-lg border border-foreground/12 bg-transparent text-foreground/80 text-[11px] font-medium hover:bg-foreground/5 hover:border-foreground/20 transition-all"
                >
                  이 편집안으로 시작하기
                </button>
              </div>
            ) : (
              <div className="w-full h-16 rounded-lg border border-dashed border-border/20 flex items-center justify-center bg-secondary/10">
                <span className="text-[9px] text-muted-foreground/35">편집안을 선택하세요</span>
              </div>
            )}
          </div>
        </div>
        <ChatBar value={chatInput} onChange={setChatInput} onSend={handleSendMessage} onKeyDown={handleKeyDown} />
      </div>
    );
  }

  // ── Chat ──
  return (
    <div className="flex flex-col bg-card/40 h-full w-full">
      <ScrollArea className="flex-1">
        <div className="px-3 py-3 space-y-3">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "ai" && (
                <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot size={10} className="text-primary/70" />
                </div>
              )}
              <div className={`max-w-[85%] space-y-1.5 ${msg.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`px-2.5 py-1.5 rounded-xl text-[12px] leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary/80 text-primary-foreground rounded-br-sm"
                      : "bg-secondary/60 text-foreground/85 rounded-bl-sm"
                  }`}
                >
                  {msg.content}
                </div>
                {msg.proposals && (
                  <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                    {msg.proposals.map((p) => (
                      <ProposalCard
                        key={p.id}
                        proposal={p}
                        isSelected={selectedProposalId === p.id}
                        onSelect={() => {
                          setSelectedProposalId(p.id);
                          onProposalSelect(p, p.label);
                        }}
                        compact
                      />
                    ))}
                  </div>
                )}
              </div>
              {msg.role === "user" && (
                <div className="w-5 h-5 rounded-full bg-secondary/60 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={10} className="text-muted-foreground/60" />
                </div>
              )}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      </ScrollArea>
      <ChatBar value={chatInput} onChange={setChatInput} onSend={handleSendMessage} onKeyDown={handleKeyDown} onFileSelect={processFile} />
    </div>
  );
};

// ── Sub-components ──

interface ChatBarProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onFileSelect?: (file: File) => void;
  disabled?: boolean;
}

const ChatBar: React.FC<ChatBarProps> = ({ value, onChange, onSend, onKeyDown, onFileSelect, disabled }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="px-3 py-2 border-t border-border/15">
      <div className="flex items-center gap-1.5 bg-secondary/50 rounded-xl px-2.5 py-1.5">
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden', opacity: 0 }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file && onFileSelect) {
              console.log('[D1] ChatBar file selected:', file.name);
              onFileSelect(file);
            }
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="w-6 h-6 rounded-full flex items-center justify-center text-muted-foreground/40 hover:text-foreground/60 hover:bg-secondary/60 transition-all flex-shrink-0"
        >
          <Plus size={14} strokeWidth={1.5} />
        </button>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="수정을 요청하거나 질문하세요..."
          className="flex-1 bg-transparent text-[12px] text-foreground/80 placeholder:text-muted-foreground/35 outline-none disabled:opacity-30"
          disabled={disabled}
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="w-6 h-6 rounded-lg flex items-center justify-center text-muted-foreground/40 hover:text-foreground/60 transition-all flex-shrink-0 disabled:opacity-20 disabled:pointer-events-none"
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  );
};

interface ProposalCardProps {
  proposal: Proposal;
  isSelected: boolean;
  onSelect: () => void;
  compact?: boolean;
}

const ProposalCard: React.FC<ProposalCardProps> = ({ proposal, isSelected, onSelect, compact }) => (
  <button
    onClick={onSelect}
    className={`text-left rounded-lg border overflow-hidden transition-all ${
      isSelected
        ? "border-primary/30 bg-primary/5 ring-1 ring-primary/10"
        : "border-border/20 bg-secondary/20 hover:border-border/30 hover:bg-secondary/30"
    }`}
  >
    <div
      className={`w-full ${compact ? "h-12" : "h-16"} relative`}
      style={{
        background: `linear-gradient(135deg, hsl(${proposal.thumbnailHue} 20% 15%), hsl(${proposal.thumbnailHue} 25% 10%))`,
      }}
    >
      {isSelected && (
        <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-primary/80 flex items-center justify-center">
          <Check size={8} className="text-primary-foreground" />
        </div>
      )}
      <div className="absolute bottom-1 left-1.5">
        <span className="text-[9px] font-semibold text-foreground/60">{proposal.id}안</span>
      </div>
    </div>
    <div className={`${compact ? "px-1.5 py-1" : "px-2 py-1.5"} space-y-0`}>
      <p className={`font-medium text-foreground/80 ${compact ? "text-[9px]" : "text-[10px]"}`}>{proposal.title}</p>
      <p className={`text-muted-foreground/50 leading-snug ${compact ? "text-[8px]" : "text-[9px]"}`}>{proposal.description}</p>
    </div>
  </button>
);

export default CenterPanel;
export { CenterPanel };

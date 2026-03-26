import React, { useState, useRef, useEffect } from "react";
import { Upload, Send, Play, Loader2, Check, User, Bot, Plus } from "lucide-react";
import type { Fragment } from "../types/boundaryTypes";
import type { Proposal } from "../services/proposalService";
import { ScrollArea } from "./ui/scroll-area";

export type AppState = "empty" | "analyzing" | "proposal" | "chat" | "error";

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
}

interface CenterPanelProps {
  selectedFragment: Fragment | null;
  selectedSource: string;
  editSequence?: Fragment[];
  /* ── Pipeline callbacks ── */
  appState: AppState;
  proposals: Proposal[];
  analyzeProgress: number;
  pipelineError: string | null;
  onFileUpload: (file: File) => void;
  onProposalSelect: (proposal: Proposal) => void;
  onStateChange: (state: AppState) => void;
}

const CenterPanel: React.FC<CenterPanelProps> = ({
  appState,
  proposals,
  analyzeProgress,
  pipelineError,
  onFileUpload,
  onProposalSelect,
  onStateChange,
}) => {
  const [chatInput, setChatInput] = useState("");
  const [selectedProposalLabel, setSelectedProposalLabel] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ── File selection ── */
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      console.log('[UPLOAD] File selected:', file.name, file.size);
      onFileUpload(file);
    }
    e.target.value = "";
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("video/")) {
      console.log('[UPLOAD] File dropped:', file.name);
      onFileUpload(file);
    }
  };

  /* ── Proposal selection ── */
  const handleSelectProposal = (proposal: Proposal) => {
    console.log('[SEL] Proposal selected:', proposal.label, 'fragments:', proposal.editSequence.length);
    setSelectedProposalLabel(proposal.label);
  };

  const handleStartChat = () => {
    const proposal = proposals.find(p => p.label === selectedProposalLabel);
    if (!proposal) return;

    console.log('[SEL] Starting chat with proposal:', proposal.label, proposal.editSequence.length, 'fragments');
    onProposalSelect(proposal);

    setMessages([{
      id: "1",
      role: "ai",
      content: `"${proposal.description}" 편집안을 선택하셨습니다. 조각 ${proposal.editSequence.length}개로 구성됩니다. 수정이 필요하시면 말씀해 주세요.`,
    }]);
    onStateChange("chat");
  };

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: "user", content: chatInput };
    setMessages(prev => [...prev, userMsg]);
    setChatInput("");
    setTimeout(() => {
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "ai",
        content: "네, 이해했습니다. 새로운 편집안을 준비하고 있어요.",
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

  // ── Empty ──
  if (appState === "empty") {
    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 flex items-center justify-center p-6">
          <div
            className="w-full max-w-[260px] border border-dashed border-border/30 rounded-xl p-6 flex flex-col items-center gap-3 hover:border-foreground/15 transition-colors cursor-pointer"
            onClick={handleUploadClick}
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onDrop={handleDrop}
          >
            <div className="w-10 h-10 rounded-xl bg-secondary/60 flex items-center justify-center">
              <Upload size={17} className="text-muted-foreground/70" />
            </div>
            <div className="text-center space-y-0.5">
              <p className="text-[12px] font-medium text-foreground/80">영상을 업로드하세요</p>
              <p className="text-[10px] text-muted-foreground/50">드래그하거나 클릭</p>
            </div>
            <button
              className="px-4 py-1.5 rounded-lg border border-foreground/12 bg-transparent text-foreground/70 text-[11px] font-medium hover:bg-foreground/5 hover:border-foreground/20 transition-all"
              onClick={(e) => { e.stopPropagation(); handleUploadClick(); }}
            >
              파일 선택
            </button>
            <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={handleFileChange} />
          </div>
        </div>
        <ChatBar value={chatInput} onChange={setChatInput} onSend={handleSendMessage} onKeyDown={handleKeyDown} onFileSelect={onFileUpload} disabled />
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
                style={{ width: `${Math.min(analyzeProgress, 100)}%` }}
              />
            </div>
            <p className="text-[9px] text-muted-foreground/40">{Math.min(Math.round(analyzeProgress), 100)}%</p>
          </div>
        </div>
        <ChatBar value="" onChange={() => {}} onSend={() => {}} onKeyDown={() => {}} onFileSelect={() => {}} disabled />
      </div>
    );
  }

  // ── Error ──
  if (appState === "error") {
    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="flex flex-col items-center gap-4 w-full max-w-[260px]">
            <div className="w-10 h-10 rounded-xl bg-destructive/10 flex items-center justify-center">
              <span className="text-destructive text-lg">!</span>
            </div>
            <div className="text-center space-y-1">
              <p className="text-[12px] font-medium text-foreground/80">분석에 실패했습니다</p>
              <p className="text-[10px] text-muted-foreground/60 leading-relaxed px-2">
                {pipelineError || '알 수 없는 오류가 발생했습니다.'}
              </p>
            </div>
            <button
              onClick={() => onStateChange("empty")}
              className="px-4 py-1.5 rounded-lg border border-foreground/12 bg-transparent text-foreground/70 text-[11px] font-medium hover:bg-foreground/5 hover:border-foreground/20 transition-all"
            >
              다시 시도
            </button>
          </div>
        </div>
        <ChatBar value="" onChange={() => {}} onSend={() => {}} onKeyDown={() => {}} onFileSelect={onFileUpload} disabled />
      </div>
    );
  }

  // ── Proposal ──
  if (appState === "proposal") {
    const proposalA = proposals.find(p => p.label === 'A');
    const proposalB = proposals.find(p => p.label === 'B');

    return (
      <div className="flex flex-col bg-card/40 h-full w-full">
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 py-3 space-y-2">
            <h3 className="text-[11px] font-medium text-foreground/70">편집안 선택</h3>
            <p className="text-[9px] text-muted-foreground/50">
              {proposalA ? `A안: ${proposalA.editSequence.length}개 조각` : ''} / {proposalB ? `B안: ${proposalB.editSequence.length}개 조각` : ''}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {proposals.map((p) => (
                <ProposalCard
                  key={p.label}
                  label={p.label}
                  description={p.description}
                  fragmentCount={p.editSequence.length}
                  fragmentIds={p.editSequence.map(f => f.fragment_id)}
                  isSelected={selectedProposalLabel === p.label}
                  onSelect={() => handleSelectProposal(p)}
                />
              ))}
            </div>
          </div>

          <div className="mx-4 h-px bg-border/20" />

          <div className="px-4 py-3 space-y-2">
            <h4 className="text-[9px] font-medium text-muted-foreground/50 uppercase tracking-wider">Preview</h4>
            {selectedProposalLabel ? (
              <div className="space-y-2">
                <div className="w-full rounded-lg border border-border/20 bg-secondary/20 p-2">
                  <p className="text-[9px] text-muted-foreground/60 mb-1">조각 순서:</p>
                  <div className="flex flex-wrap gap-1">
                    {proposals.find(p => p.label === selectedProposalLabel)?.editSequence.map((f, i) => (
                      <span key={f.fragment_id} className="text-[8px] px-1.5 py-0.5 rounded bg-primary/10 text-primary/80">
                        {i + 1}. {f.fragment_id}
                      </span>
                    ))}
                  </div>
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
        <ChatBar value={chatInput} onChange={setChatInput} onSend={handleSendMessage} onKeyDown={handleKeyDown} onFileSelect={onFileUpload} />
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
      <ChatBar value={chatInput} onChange={setChatInput} onSend={handleSendMessage} onKeyDown={handleKeyDown} onFileSelect={onFileUpload} />
    </div>
  );
};

// ── Sub-components ──

interface ChatBarProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onFileSelect: (file: File) => void;
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
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onFileSelect(file);
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
  label: string;
  description: string;
  fragmentCount: number;
  fragmentIds: string[];
  isSelected: boolean;
  onSelect: () => void;
}

const ProposalCard: React.FC<ProposalCardProps> = ({ label, description, fragmentCount, fragmentIds, isSelected, onSelect }) => {
  const hue = label === 'A' ? 211 : 30;
  return (
    <button
      onClick={onSelect}
      className={`text-left rounded-lg border overflow-hidden transition-all ${
        isSelected
          ? "border-primary/30 bg-primary/5 ring-1 ring-primary/10"
          : "border-border/20 bg-secondary/20 hover:border-border/30 hover:bg-secondary/30"
      }`}
    >
      <div
        className="w-full h-16 relative"
        style={{
          background: `linear-gradient(135deg, hsl(${hue} 20% 15%), hsl(${hue} 25% 10%))`,
        }}
      >
        {isSelected && (
          <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-primary/80 flex items-center justify-center">
            <Check size={8} className="text-primary-foreground" />
          </div>
        )}
        <div className="absolute bottom-1 left-1.5">
          <span className="text-[9px] font-semibold text-foreground/60">{label}안</span>
        </div>
        <div className="absolute bottom-1 right-1.5">
          <span className="text-[8px] text-foreground/40">{fragmentCount}개 조각</span>
        </div>
      </div>
      <div className="px-2 py-1.5 space-y-0.5">
        <p className="font-medium text-foreground/80 text-[10px]">{description}</p>
        <p className="text-muted-foreground/40 text-[8px] leading-snug truncate">
          {fragmentIds.slice(0, 5).join(' → ')}{fragmentIds.length > 5 ? ' …' : ''}
        </p>
      </div>
    </button>
  );
};

export default CenterPanel;
export { CenterPanel };

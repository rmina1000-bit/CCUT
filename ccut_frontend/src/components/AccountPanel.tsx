import React, { useState } from "react";
import { User, LogIn, LogOut, CheckCircle, CreditCard, Chrome, ShieldAlert, Sparkles, Check } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface UserProfile {
  name: string;
  email: string;
  avatar: string;
  plan: "Free" | "AI Pro" | "AI Ultra";
  creditsUsed: number;
  creditsMax: number;
}

export const AccountPanel: React.FC = () => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [payingPlan, setPayingPlan] = useState<string | null>(null);
  const [payProgress, setPayProgress] = useState(0);

  const handleGoogleLogin = () => {
    setLoggingIn(true);
    // Simulate Google Sign-in OAuth popup
    setTimeout(() => {
      setUser({
        name: "국장님",
        email: "director@ccut.ai",
        avatar: "https://lh3.googleusercontent.com/a/default-user=s96-c",
        plan: "Free",
        creditsUsed: 14,
        creditsMax: 100
      });
      setLoggingIn(false);
    }, 1200);
  };

  const handleGooglePay = (planName: "AI Pro" | "AI Ultra") => {
    if (!user) {
      alert("먼저 구글 계정으로 로그인해 주세요!");
      return;
    }
    setPayingPlan(planName);
    setPayProgress(15);

    // Google Pay Billing simulation
    const interval = setInterval(() => {
      setPayProgress((p) => {
        if (p >= 90) {
          clearInterval(interval);
          return 90;
        }
        return p + 25;
      });
    }, 300);

    setTimeout(() => {
      clearInterval(interval);
      setPayProgress(100);
      setUser((prev) => prev ? {
        ...prev,
        plan: planName,
        creditsMax: planName === "AI Pro" ? 500 : 9999
      } : null);
      
      setTimeout(() => {
        setPayingPlan(null);
      }, 800);
    }, 1500);
  };

  const handleLogout = () => {
    setUser(null);
  };

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">
          내 계정 및 구독 관리
        </h1>
        <p className="text-[12px] text-muted-foreground/60 mt-1">
          CCUT 계정을 관리하고 요금제(구독)를 변경하여 AI 자원을 확보합니다.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Card */}
        <div className="lg:col-span-1">
          {user ? (
            <Card className="bg-card/30 border-border/15">
              <CardContent className="p-6 flex flex-col items-center text-center space-y-4">
                <img
                  src={user.avatar}
                  alt={user.name}
                  className="w-16 h-16 rounded-full border border-primary/20 bg-secondary"
                />
                <div>
                  <h3 className="text-sm font-bold text-foreground/90">{user.name}</h3>
                  <p className="text-[10px] text-muted-foreground/50 mt-0.5">{user.email}</p>
                </div>

                <div className="flex items-center gap-1 bg-primary/10 border border-primary/20 px-2.5 py-0.5 rounded-full">
                  <Sparkles size={11} className="text-primary" />
                  <span className="text-[10px] font-bold text-primary">{user.plan} 요금제 이용 중</span>
                </div>

                {/* Credit usage limit */}
                <div className="w-full space-y-2 pt-2 border-t border-border/10">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground/60">이번 달 사용 토큰/용량</span>
                    <span className="font-mono text-foreground/80 font-bold">{user.creditsUsed} / {user.creditsMax === 9999 ? "무제한" : `${user.creditsMax} credits`}</span>
                  </div>
                  <div className="w-full bg-secondary/80 h-1.5 rounded-full overflow-hidden">
                    <div 
                      className="bg-primary h-full transition-all duration-500" 
                      style={{ width: `${Math.min(100, (user.creditsUsed / user.creditsMax) * 100)}%` }} 
                    />
                  </div>
                </div>

                <Button
                  onClick={handleLogout}
                  className="w-full flex items-center justify-center gap-1.5 h-9 text-xs bg-secondary/80 hover:bg-secondary text-foreground/80 rounded-lg"
                >
                  <LogOut size={12} />
                  로그아웃
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="bg-card/30 border-border/15">
              <CardContent className="p-8 flex flex-col items-center text-center space-y-6">
                <div className="w-12 h-12 rounded-full bg-secondary/80 flex items-center justify-center">
                  <User size={20} className="text-muted-foreground/50" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground/90">로그인이 필요합니다</h3>
                  <p className="text-[11px] text-muted-foreground/60 mt-1 max-w-[200px] mx-auto leading-relaxed">
                    구글 연동을 통해 1초 만에 가입 및 로그인이 가능합니다.
                  </p>
                </div>

                {loggingIn ? (
                  <div className="w-full bg-secondary/50 rounded-lg h-10 flex items-center justify-center text-xs text-muted-foreground/50 gap-2">
                    <div className="w-3.5 h-3.5 border-2 border-muted-foreground/30 border-t-muted-foreground rounded-full animate-spin" />
                    구글 간편 로그인 로딩 중...
                  </div>
                ) : (
                  <Button
                    onClick={handleGoogleLogin}
                    className="w-full flex items-center justify-center gap-2 h-10 text-xs bg-white text-black hover:bg-white/90 rounded-lg font-bold"
                  >
                    <Chrome size={14} className="text-blue-500" />
                    Google 계정으로 로그인
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {payingPlan && (
            <div className="fixed inset-0 z-[500] bg-black/75 flex items-center justify-center p-4">
              <div className="bg-[hsl(228,12%,12%)] border border-border/20 max-w-sm w-full rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-2.5">
                  <CreditCard className="text-primary" size={18} />
                  <h4 className="text-sm font-bold text-foreground/90">Google Pay 결제 처리 중</h4>
                </div>
                <p className="text-xs text-muted-foreground/75 leading-relaxed">
                  {payingPlan} 플랜 결제가 구글 인앱/구독 API를 통해 샌드박스에서 연동 승인 처리되고 있습니다.
                </p>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-muted-foreground/50">Google Billing Gateway</span>
                    <span className="text-primary font-bold">{payProgress}%</span>
                  </div>
                  <div className="w-full bg-secondary/80 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-primary h-full transition-all duration-300" style={{ width: `${payProgress}%` }} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Pricing Table */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="text-xs font-semibold text-muted-foreground/60 uppercase tracking-widest px-1">
            CCUT 구독 요금제
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Pro Plan */}
            <Card className={`bg-card/25 border-border/10 flex flex-col justify-between h-full relative ${
              user?.plan === "AI Pro" ? "ring-2 ring-primary/40 border-primary" : ""
            }`}>
              <CardContent className="p-6 space-y-5">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-widest text-primary bg-primary/10 px-2 py-0.5 rounded">가성비 추천</span>
                    <h4 className="text-base font-bold text-foreground/90 mt-2">AI Pro 요금제</h4>
                    <p className="text-[11px] text-muted-foreground/50 mt-0.5">합리적인 4배속 오버나이트 분석</p>
                  </div>
                </div>

                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-black text-foreground/90">₩19,000</span>
                  <span className="text-xs text-muted-foreground/50">/ 월</span>
                </div>

                <ul className="space-y-2 text-xs text-muted-foreground/75">
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 대용량 분석 한도 500 크레딧</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> Local LLM 오버나이트 백그라운드 구동</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 외부 Runway/Kling 어댑터 가드 지원</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> Full HD 렌더링 내보내기 제한 해제</li>
                </ul>
              </CardContent>

              <div className="p-6 pt-0 border-t border-border/5 mt-4">
                <Button
                  onClick={() => handleGooglePay("AI Pro")}
                  disabled={user?.plan === "AI Pro"}
                  className={`w-full flex items-center justify-center gap-2 h-10 text-xs rounded-lg font-bold mt-4 ${
                    user?.plan === "AI Pro"
                      ? "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/10"
                      : "bg-primary hover:bg-primary-hover text-white"
                  }`}
                >
                  <CreditCard size={13} />
                  {user?.plan === "AI Pro" ? "구독 이용 중" : "Google Pay로 구독"}
                </Button>
              </div>
            </Card>

            {/* Ultra Plan */}
            <Card className={`bg-card/25 border-border/10 flex flex-col justify-between h-full relative ${
              user?.plan === "AI Ultra" ? "ring-2 ring-primary/40 border-primary" : ""
            }`}>
              <CardContent className="p-6 space-y-5">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-widest text-primary bg-primary/10 px-2 py-0.5 rounded">최고 사양</span>
                    <h4 className="text-base font-bold text-foreground/90 mt-2">AI Ultra 요금제</h4>
                    <p className="text-[11px] text-muted-foreground/50 mt-0.5">서버 병렬 연산 및 20배속 파이프라인</p>
                  </div>
                </div>

                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-black text-foreground/90">₩39,000</span>
                  <span className="text-xs text-muted-foreground/50">/ 월</span>
                </div>

                <ul className="space-y-2 text-xs text-muted-foreground/75">
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 용량/개수 완전 무제한</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 최상위 AI 모델(Qwen 7B) 다중 병렬 처리</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 외부 비디오 생성 API 결합 한도 상향</li>
                  <li className="flex items-center gap-1.5"><Check size={12} className="text-primary flex-shrink-0" /> 4K Ultra HD 고품질 내보내기 지원</li>
                </ul>
              </CardContent>

              <div className="p-6 pt-0 border-t border-border/5 mt-4">
                <Button
                  onClick={() => handleGooglePay("AI Ultra")}
                  disabled={user?.plan === "AI Ultra"}
                  className={`w-full flex items-center justify-center gap-2 h-10 text-xs rounded-lg font-bold mt-4 ${
                    user?.plan === "AI Ultra"
                      ? "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/10"
                      : "bg-primary hover:bg-primary-hover text-white"
                  }`}
                >
                  <CreditCard size={13} />
                  {user?.plan === "AI Ultra" ? "구독 이용 중" : "Google Pay로 구독"}
                </Button>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

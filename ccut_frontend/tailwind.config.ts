import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      // [CCUT-TOKEN 2026-08-02 국장 확정] 글자 크기는 이 다섯 개가 전부다.
      //   왜: 실측 결과 화면에 글자 크기가 14종 흩어져 있었다
      //   (8·9·10·10.5·11·11.5·12·13·14·14.5·15·16·17·18px).
      //   10.5px 와 11px 을 눈으로 구분할 사람은 없는데, 국장이 "여기 좀 작네" 하면
      //   14곳을 찾아다녀야 했다 — 하루종일 조금씩 손보게 되던 진짜 원인이다.
      //   국장 지시: "극단적으로 작고, 적고, 소수인 것. 그러면서 다름은 확실히."
      //   ★새 크기를 임의로 추가하지 마라. 모자라면 국장에게 보고하고 늘린다.
      //   수치는 참조 제품(Claude·ChatGPT) 계열에 맞췄다 — 본문 15px/행간 1.7,
      //   메타 13px, 제목 18px. 폰트는 이미 Inter 로 같다.
      fontSize: {
        micro: ["11px", { lineHeight: "1.45" }],   // 배지·타일 라벨 (구 8·9·10px)
        meta: ["13px", { lineHeight: "1.55" }],    // 시각·개수·캡션 (구 11·12px)
        body: ["15px", { lineHeight: "1.7" }],     // 대화·전사 본문 (구 13·14·15px)
        title: ["18px", { lineHeight: "1.4" }],    // 제목 (구 16·17·18px)
        display: ["22px", { lineHeight: "1.3" }],  // 예약 — 현재 쓰는 곳 없음
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
        ccut: {
          deep: "hsl(var(--ccut-bg-deep))",
          panel: "hsl(var(--ccut-bg-panel))",
          elevated: "hsl(var(--ccut-bg-elevated))",
          gold: "hsl(var(--ccut-gold))",
          "gold-dim": "hsl(var(--ccut-gold-dim))",
          stroke: "hsl(var(--ccut-stroke))",
          indigo: "hsl(var(--ccut-indigo))",
          amber: "hsl(var(--ccut-amber))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;

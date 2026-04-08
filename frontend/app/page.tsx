"use client";

import Link from "next/link";

const FEATURES = [
  {
    icon: "🤖",
    title: "AI 포트폴리오 진단",
    desc: "Claude AI가 현재 자산 배분의 강점과 약점을 CFP 수준으로 분석합니다.",
  },
  {
    icon: "📈",
    title: "5년 시뮬레이션",
    desc: "비관·기본·낙관 3개 시나리오로 5년 후 예상 자산을 시각화합니다.",
  },
  {
    icon: "📄",
    title: "전문가 수준 PDF",
    desc: "5페이지 전문 리포트를 즉시 다운로드. 차트·표·AI 분석이 모두 포함됩니다.",
  },
];

const USE_CASES = [
  { emoji: "💼", text: "ISA/연금저축 굴리고 있는데 리밸런싱 감이 없던 직장인 A씨", result: "맞춤 리밸런싱 가이드 획득" },
  { emoji: "📊", text: "ETF 조금씩 사고 있는데 제대로 하는 건지 모르던 투자 입문자 B씨", result: "포트폴리오 위험 진단 완료" },
  { emoji: "🏠", text: "5년 후 주택 구입을 목표로 자산 증식을 계획하는 C씨", result: "목표 달성 시나리오 수립" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* 히어로 섹션 */}
      <section className="bg-navy text-white py-20 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <div className="inline-block bg-gold-500 text-white text-xs font-bold px-3 py-1 rounded-full mb-4">
            AI 기반 재무 설계
          </div>
          <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-4">
            5분 만에 받는
            <br />
            <span className="text-gold-400">AI 재무 설계 리포트</span>
          </h1>
          <p className="text-lg text-blue-100 mb-8 max-w-xl mx-auto">
            내 포트폴리오를 입력하면, AI가 현재 시장 상황을 반영하여
            <br />
            <strong>5년 뒤 예상 자산</strong>과 <strong>맞춤 리밸런싱 전략</strong>을 분석합니다.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/input/step1"
              className="px-8 py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors shadow-lg"
            >
              지금 무료로 시작하기 →
            </Link>
          </div>

          <p className="mt-4 text-sm text-blue-200">
            미리보기는 무료 · 전체 리포트 <strong className="text-gold-400">4,900원</strong>
          </p>
        </div>
      </section>

      {/* 기능 소개 */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-center text-3xl font-bold text-navy mb-12">
            단순 계산기가 아닌 <span className="text-gold-500">AI 분석 리포트</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {FEATURES.map((f, i) => (
              <div key={i} className="card text-center hover:shadow-md transition-shadow">
                <div className="text-4xl mb-3">{f.icon}</div>
                <h3 className="text-lg font-bold text-navy mb-2">{f.title}</h3>
                <p className="text-gray-600 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 사용 사례 */}
      <section className="py-16 px-4 bg-gray-50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-center text-3xl font-bold text-navy mb-10">이런 분들이 사용했습니다</h2>
          <div className="space-y-4">
            {USE_CASES.map((u, i) => (
              <div key={i} className="card flex items-center gap-4">
                <div className="text-3xl">{u.emoji}</div>
                <div className="flex-1">
                  <p className="text-gray-700 text-sm">{u.text}</p>
                </div>
                <div className="text-xs font-bold text-green-600 bg-green-50 px-3 py-1 rounded-full whitespace-nowrap">
                  {u.result}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 가격 */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-sm mx-auto">
          <h2 className="text-center text-3xl font-bold text-navy mb-8">가격</h2>
          <div className="card border-2 border-gold-400 text-center">
            <div className="text-sm text-gray-500 mb-1">기본 리포트</div>
            <div className="text-5xl font-bold text-navy mb-1">
              4,900<span className="text-2xl">원</span>
            </div>
            <div className="text-sm text-gold-500 mb-6">커피 한 잔 값에 AI 재무 설계</div>
            <ul className="text-left space-y-2 mb-6">
              {[
                "5페이지 전문 PDF 리포트",
                "AI 포트폴리오 종합 진단",
                "비관/기본/낙관 3개 시나리오",
                "맞춤 리밸런싱 추천",
                "현재 시장 환경 분석",
                "즉시 다운로드 + 이메일 발송",
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-2 text-sm text-gray-700">
                  <span className="text-gold-500">✓</span> {item}
                </li>
              ))}
            </ul>
            <Link
              href="/input/step1"
              className="block w-full py-3 bg-gold-500 text-white font-bold rounded-xl hover:bg-gold-600 transition-colors"
            >
              지금 시작하기
            </Link>
          </div>
        </div>
      </section>

      {/* 하단 CTA */}
      <section className="py-16 px-4 bg-navy text-white text-center">
        <h2 className="text-3xl font-bold mb-4">
          내 포트폴리오, <span className="text-gold-400">지금 당장 점검해보세요</span>
        </h2>
        <p className="text-blue-200 mb-8">5분 입력 · AI 분석 · 전문 PDF 리포트</p>
        <Link
          href="/input/step1"
          className="inline-block px-10 py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors shadow-lg"
        >
          무료로 미리보기 시작 →
        </Link>
      </section>

      {/* 면책 고지 */}
      <footer className="bg-gray-900 text-gray-400 text-center py-6 px-4 text-xs">
        <p>
          본 서비스는 정보 제공 목적이며, 투자 권유 또는 투자 자문에 해당하지 않습니다.
          <br />
          모든 투자에는 원금 손실의 위험이 있습니다. © 2024 포트폴리오 AI 리포트
        </p>
      </footer>
    </div>
  );
}

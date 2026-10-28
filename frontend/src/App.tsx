import { useEffect, useState } from "react";

type ApiStatus = "checking" | "connected" | "unavailable";

export default function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();

    fetch("/api/health/live", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return response.json() as Promise<{ status: string }>;
      })
      .then(({ status }) => {
        setApiStatus(status === "alive" ? "connected" : "unavailable");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setApiStatus("unavailable");
      });

    return () => controller.abort();
  }, []);

  const statusText: Record<ApiStatus, string> = {
    checking: "API 연결 확인 중",
    connected: "API 연결됨",
    unavailable: "API에 연결할 수 없습니다",
  };

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="과수화상병 AI 대응지원 홈">
          <span className="brand-mark" aria-hidden="true">과</span>
          <span>과수화상병 AI 대응지원</span>
        </a>
        <span className="phase-label">개발 환경 · Phase 1</span>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <p className="eyebrow">ORCHARD HEALTH, SUPPORTED BY AI</p>
        <h1 id="hero-title">의심 증상을 살피고,<br />다음 대응을 준비하세요.</h1>
        <p className="intro">
          사진 기반 의심 증상 탐지와 검토된 대응 정보를 지원하는 서비스입니다.
          AI 분석은 확진이나 공식 방제 지침을 대체하지 않습니다.
        </p>
        <div className="notice">
          <span aria-hidden="true">i</span>
          <p>현재는 개발 기반을 준비 중입니다. 실제 분석 기능은 검증된 모델이 연결된 뒤 제공됩니다.</p>
        </div>
        <div className={`connection connection-${apiStatus}`} role="status" aria-live="polite">
          <span className="status-dot" aria-hidden="true" />
          {statusText[apiStatus]}
        </div>
      </section>

      <footer>
        <span>과수화상병 의심 증상 탐지 및 대응 지원</span>
        <span>사진만으로 과수화상병을 확진할 수 없습니다.</span>
      </footer>
    </main>
  );
}

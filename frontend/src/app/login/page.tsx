
"use client";

import { useState, type FormEvent } from "react";
import { waitForBackend } from "../../lib/waitForBackend";

export default function OrganizerLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warmingUp, setWarmingUp] = useState(false);


  async function handleLogin(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (loading) return;

    setLoading(true);
    setError("");

    try {
      // Wake FastAPI before attempting login.
      setWarmingUp(true);
      await waitForBackend();
      setWarmingUp(false);

      // Existing login request remains unchanged.
      const response = await fetch(
        "/api/auth/organizer/login",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({ email, password }),
        }
      );

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Invalid email or password.");
        }

        throw new Error(
          "Unable to sign in. Check the backend server."
        );
      }

      window.location.assign("/");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Login failed."
      );
    } finally {
      setWarmingUp(false);
      setLoading(false);
    }
  }


  return (
    <main className="em-login">
      <div className="em-login-shell">

        {/* LEFT — BRAND EXPERIENCE */}
        <section className="em-login-hero">
          <div className="em-login-hero-glow" />

          <div className="em-login-brand">
            <div className="em-login-brand-mark">
              E<span>✳</span>
            </div>

            <div className="em-login-brand-text">
              <strong>
                EventMesh<span>.</span>
              </strong>
              <small>AI OPERATIONS PLATFORM</small>
            </div>
          </div>

          <div className="em-login-hero-content">
            <div className="em-login-eyebrow">
              <span className="em-login-eyebrow-dot" />
              THE INTELLIGENT EVENT PLATFORM
            </div>

            <h1>
              Run events
              <br />
              smarter<span>.</span>
            </h1>

            <p className="em-login-hero-description">
              One connected workspace to manage event
              operations, anticipate disruptions, and
              make confident decisions.
            </p>

            <div className="em-login-visual">
              <div className="em-login-visual-header">
                <div className="em-login-visual-icon">✳</div>

                <div>
                  <strong>Event intelligence</strong>
                  <small>Operations overview</small>
                </div>

                <div className="em-login-visual-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>

              <div className="em-login-flow">
                <div className="em-login-flow-step">
                  <span className="em-login-step-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M12 3L2 20h20L12 3Z" />
                      <path d="M12 9v5M12 17h.01" />
                    </svg>
                  </span>

                  <span>
                    <b>Detect</b>
                    <small>Identify disruptions</small>
                  </span>
                </div>

                <span className="em-login-flow-arrow">→</span>

                <div className="em-login-flow-step">
                  <span className="em-login-step-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
                    </svg>
                  </span>

                  <span>
                    <b>Plan</b>
                    <small>Compare options</small>
                  </span>
                </div>

                <span className="em-login-flow-arrow">→</span>

                <div className="em-login-flow-step">
                  <span className="em-login-step-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <circle cx="12" cy="12" r="9" />
                      <path d="m8 12 3 3 5-6" />
                    </svg>
                  </span>

                  <span>
                    <b>Approve</b>
                    <small>Stay in control</small>
                  </span>
                </div>
              </div>

              <div className="em-login-visual-footer">
                <span className="em-login-pulse" />
                Human-controlled recovery workflow
              </div>
            </div>

            <div className="em-login-features">
              <div>
                <span className="em-login-feature-check">✓</span>
                AI-assisted recovery
              </div>

              <div>
                <span className="em-login-feature-check">✓</span>
                Smart scheduling
              </div>

              <div>
                <span className="em-login-feature-check">✓</span>
                PayPal Sandbox integration
              </div>
            </div>
          </div>

          <div className="em-login-hero-footer">
            <span>EVENTMESH AI</span>
            <span>EVENT OPERATIONS, REIMAGINED</span>
          </div>
        </section>

        {/* RIGHT — LOGIN */}
        <section className="em-login-form-section">
          <div className="em-login-form-container">

            <div className="em-login-form-top">
              <span className="em-login-access-tag">
                <span />
                ORGANIZER ACCESS
              </span>
            </div>

            <div className="em-login-heading">
              <div className="em-login-welcome-icon">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect
                    x="3"
                    y="3"
                    width="18"
                    height="18"
                    rx="5"
                  />
                  <path d="M8 12l3 3 5-6" />
                </svg>
              </div>

              <h2>Welcome back</h2>

              <p>
                Sign in to access your EventMesh
                organizer workspace.
              </p>
            </div>

            <form
              onSubmit={handleLogin}
              className="em-login-form"
            >
              <label
                className="em-login-label"
                htmlFor="organizer-email"
              >
                Email address
              </label>

              <div className="em-login-input-wrap">
                <span className="em-login-input-icon">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect
                      x="3"
                      y="5"
                      width="18"
                      height="14"
                      rx="2"
                    />
                    <path d="m3 7 9 6 9-6" />
                  </svg>
                </span>

                <input
                  id="organizer-email"
                  type="email"
                  placeholder="Enter your email address"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />
              </div>

              <label
                className="em-login-label"
                htmlFor="organizer-password"
              >
                Password
              </label>

              <div className="em-login-input-wrap">
                <span className="em-login-input-icon">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect
                      x="5"
                      y="10"
                      width="14"
                      height="11"
                      rx="2"
                    />
                    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                  </svg>
                </span>

                <input
                  id="organizer-password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                />

                <button
                  type="button"
                  className="em-login-show-password"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={
                    showPassword
                      ? "Hide password"
                      : "Show password"
                  }
                  aria-pressed={showPassword}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>

              {error && (
                <div
                  role="alert"
                  className="em-login-error"
                >
                  <span>!</span>
                  {error}
                </div>
              )}

              <button
                className="em-login-submit"
                type="submit"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="em-login-spinner" />
                    {warmingUp ? "Starting server..." : "Signing in..."}
                  </>
                ) : (
                  <>
                    Sign in to workspace
                    <span aria-hidden="true">→</span>
                  </>
                )}
              </button>
            </form>


            {process.env.NODE_ENV !== "production" && (
              <p
                style={{
                  margin: "20px 0 4px",
                  textAlign: "center",
                  color: "#7289a4",
                  fontSize: 13,
                }}
              >
                New to EventMesh AI?{" "}
                <a
                  href="/register"
                  style={{
                    color: "#0070e0",
                    fontWeight: 800,
                    textDecoration: "none",
                  }}
                >
                  Create an organizer account →
                </a>
              </p>
            )}


            <div className="em-login-divider">
              <span />
              <p>YOUR EVENT COMMAND CENTER</p>
              <span />
            </div>

            <div className="em-login-info">
              <div className="em-login-info-icon">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </div>

              <div>
                <strong>Organizer sign-in</strong>
                <p>
                  Use your registered organizer credentials.
                  This is a local development workspace.
                </p>
              </div>
            </div>

            <div className="em-login-bottom">
              <span>© EventMesh AI</span>
              <span>LOCAL DEMO ENVIRONMENT</span>
            </div>
          </div>
        </section>
      </div>

      <style>{`
        .em-login {
          min-height: 100vh;
          background: #f4f8ff;
          color: #12294b;
          font-family: Inter, ui-sans-serif, system-ui,
            -apple-system, "Segoe UI", Arial, sans-serif;
        }

        .em-login * {
          box-sizing: border-box;
        }

        .em-login-shell {
          display: grid;
          grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
          min-height: 100vh;
        }

        /* Left hero */

        .em-login-hero {
          position: relative;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          padding: 38px clamp(28px, 5vw, 78px);
          color: white;
          background:
            radial-gradient(
              ellipse at 90% 55%,
              rgba(0, 112, 224, 0.6),
              transparent 55%
            ),
            linear-gradient(
              145deg,
              #051b42 0%,
              #003087 60%,
              #063b89 100%
            );
        }

        .em-login-hero-glow {
          position: absolute;
          width: 550px;
          height: 550px;
          right: -280px;
          top: 10%;
          border-radius: 50%;
          border: 1px solid rgba(199, 225, 255, 0.18);
          box-shadow:
            0 0 0 85px rgba(139, 200, 255, 0.035),
            0 0 0 180px rgba(139, 200, 255, 0.025);
          pointer-events: none;
        }

        .em-login-brand {
          position: relative;
          z-index: 2;
          display: flex;
          align-items: center;
          gap: 13px;
        }

        .em-login-brand-mark {
          position: relative;
          width: 49px;
          height: 49px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #e5f3ff;
          color: #003087;
          border-radius: 14px;
          font-size: 34px;
          font-weight: 900;
          letter-spacing: -3px;
        }

        .em-login-brand-mark span {
          position: absolute;
          top: 1px;
          right: 3px;
          font-size: 17px;
        }

        .em-login-brand-text strong {
          display: block;
          font-size: 25px;
          font-weight: 850;
          letter-spacing: -1.1px;
        }

        .em-login-brand-text strong span {
          color: #75c6ff;
        }

        .em-login-brand-text small {
          display: block;
          margin-top: 3px;
          color: #a8d2fc;
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 2.2px;
        }

        .em-login-hero-content {
          position: relative;
          z-index: 2;
          width: 100%;
          max-width: 580px;
          margin: auto 0;
          padding: 65px 0;
        }

        .em-login-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          color: #b7dbff;
          font-size: 11px;
          font-weight: 850;
          letter-spacing: 1.8px;
        }

        .em-login-eyebrow-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #70c8ff;
          box-shadow: 0 0 15px rgba(112, 200, 255, 0.7);
        }

        .em-login-hero-content h1 {
          margin: 24px 0 20px;
          font-size: clamp(45px, 5vw, 75px);
          line-height: 1.08;
          letter-spacing: -3.5px;
          font-weight: 850;
        }

        .em-login-hero-content h1 span {
          color: #7bc9ff;
        }

        .em-login-hero-description {
          max-width: 490px;
          color: #c3d9f6;
          font-size: 15px;
          line-height: 1.85;
        }

        /* Visual workflow card */

        .em-login-visual {
          width: 100%;
          max-width: 530px;
          margin-top: 39px;
          padding: 22px;
          background: rgba(255, 255, 255, 0.09);
          border: 1px solid rgba(200, 224, 255, 0.24);
          border-radius: 17px;
          backdrop-filter: blur(12px);
          box-shadow: 0 20px 50px rgba(2, 21, 67, 0.2);
        }

        .em-login-visual-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding-bottom: 19px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.13);
        }

        .em-login-visual-icon {
          display: grid;
          place-items: center;
          width: 41px;
          height: 41px;
          border-radius: 11px;
          background: #197ce0;
          color: white;
          font-size: 27px;
        }

        .em-login-visual-header strong {
          display: block;
          font-size: 13px;
        }

        .em-login-visual-header small {
          display: block;
          color: #bad5f6;
          font-size: 11px;
          margin-top: 4px;
        }

        .em-login-visual-dots {
          display: flex;
          gap: 4px;
          margin-left: auto;
        }

        .em-login-visual-dots span {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #9dc6ef;
        }

        .em-login-flow {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 24px 0;
        }

        .em-login-flow-step {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 10px;
          flex: 1;
          text-align: center;
        }

        .em-login-step-icon {
          display: grid;
          place-items: center;
          width: 47px;
          height: 47px;
          border: 1px solid rgba(157, 212, 255, 0.37);
          border-radius: 13px;
          background: rgba(35, 138, 245, 0.25);
        }

        .em-login-step-icon svg {
          width: 23px;
          height: 23px;
          color: #b9e4ff;
        }

        .em-login-flow-step b {
          display: block;
          font-size: 12px;
        }

        .em-login-flow-step small {
          display: block;
          color: #bad3ed;
          font-size: 10px;
          margin-top: 4px;
        }

        .em-login-flow-arrow {
          color: #86b9f0;
          font-size: 20px;
          margin-top: -27px;
        }

        .em-login-visual-footer {
          display: flex;
          align-items: center;
          gap: 9px;
          padding-top: 17px;
          border-top: 1px solid rgba(255, 255, 255, 0.13);
          color: #d0e3fb;
          font-size: 11px;
        }

        .em-login-pulse {
          width: 7px;
          height: 7px;
          background: #7dd2ff;
          border-radius: 50%;
        }

        .em-login-features {
          display: flex;
          flex-wrap: wrap;
          gap: 15px 22px;
          margin-top: 30px;
          color: #c8ddfa;
          font-size: 11px;
        }

        .em-login-features div {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .em-login-feature-check {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: rgba(93, 185, 255, 0.2);
          color: #9bddff;
          font-weight: 800;
        }

        .em-login-hero-footer {
          position: relative;
          z-index: 2;
          display: flex;
          justify-content: space-between;
          gap: 15px;
          color: #88b8ef;
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 1.4px;
        }

        /* Form section */

        .em-login-form-section {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 50px clamp(25px, 5vw, 85px);
          background: #f8fbff;
        }

        .em-login-form-container {
          width: 100%;
          max-width: 440px;
        }

        .em-login-form-top {
          margin-bottom: 44px;
        }

        .em-login-access-tag {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          padding: 9px 13px;
          background: #e9f3ff;
          border: 1px solid #d4e7fb;
          border-radius: 8px;
          color: #005cb4;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1px;
        }

        .em-login-access-tag span {
          width: 7px;
          height: 7px;
          background: #1685e7;
          border-radius: 50%;
        }

        .em-login-welcome-icon {
          display: grid;
          place-items: center;
          width: 53px;
          height: 53px;
          margin-bottom: 25px;
          border-radius: 15px;
          background: #e5f1ff;
          color: #006bd1;
        }

        .em-login-welcome-icon svg {
          width: 27px;
          height: 27px;
        }

        .em-login-heading h2 {
          margin: 0;
          color: #102a50;
          font-size: clamp(30px, 3vw, 39px);
          font-weight: 850;
          letter-spacing: -1.5px;
        }

        .em-login-heading p {
          margin: 12px 0 36px;
          color: #778aa4;
          font-size: 14px;
          line-height: 1.7;
        }

        .em-login-form {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .em-login-label {
          color: #29466e;
          font-size: 12px;
          font-weight: 800;
          margin-bottom: 1px;
        }

        .em-login-input-wrap {
          position: relative;
          display: flex;
          align-items: center;
          margin-bottom: 12px;
        }

        .em-login-input-wrap input {
          width: 100%;
          height: 54px;
          padding: 0 75px 0 47px;
          border: 1px solid #d5e3f3;
          border-radius: 11px;
          outline: none;
          background: #ffffff;
          color: #13335e;
          font-size: 13px;
          transition: border .2s, box-shadow .2s;
        }

        .em-login-input-wrap input::placeholder {
          color: #98a9c1;
        }

        .em-login-input-wrap input:focus {
          border-color: #1685e7;
          box-shadow: 0 0 0 4px rgba(0, 112, 224, 0.09);
        }

        .em-login-input-wrap input:disabled {
          opacity: 0.7;
        }

        .em-login-input-icon {
          position: absolute;
          left: 15px;
          display: grid;
          place-items: center;
          color: #7898b8;
          pointer-events: none;
        }

        .em-login-input-icon svg {
          width: 19px;
          height: 19px;
        }

        .em-login-show-password {
          position: absolute;
          right: 13px;
          padding: 6px 8px;
          border: 0;
          background: transparent;
          color: #0066c9;
          font-size: 12px;
          font-weight: 800;
          cursor: pointer;
        }

        .em-login-show-password:hover {
          color: #003087;
        }

        .em-login-error {
          display: flex;
          gap: 10px;
          align-items: center;
          padding: 13px 14px;
          margin: 0 0 8px;
          background: #fff0f0;
          border: 1px solid #f5cccc;
          border-radius: 9px;
          color: #ad3434;
          font-size: 12px;
          line-height: 1.5;
        }

        .em-login-error span {
          display: grid;
          place-items: center;
          flex: 0 0 19px;
          width: 19px;
          height: 19px;
          border-radius: 50%;
          background: #d85252;
          color: white;
          font-weight: 800;
        }

        .em-login-submit {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 15px;
          height: 54px;
          margin-top: 8px;
          padding: 0 20px;
          border: 0;
          border-radius: 11px;
          background: #0070e0;
          color: white;
          font-size: 14px;
          font-weight: 850;
          box-shadow: 0 8px 20px rgba(0, 112, 224, 0.18);
          cursor: pointer;
          transition: background .2s, transform .2s;
        }

        .em-login-submit:hover:not(:disabled) {
          background: #005cba;
          transform: translateY(-1px);
        }

        .em-login-submit:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .em-login-submit span:last-child {
          font-size: 20px;
        }

        .em-login-spinner {
          width: 17px;
          height: 17px;
          border: 2px solid rgba(255, 255, 255, 0.4);
          border-top-color: #fff;
          border-radius: 50%;
          animation: em-login-spin .8s linear infinite;
        }

        @keyframes em-login-spin {
          to { transform: rotate(360deg); }
        }

        .em-login-divider {
          display: flex;
          align-items: center;
          gap: 13px;
          margin: 34px 0;
        }

        .em-login-divider span {
          flex: 1;
          height: 1px;
          background: #e1eaf5;
        }

        .em-login-divider p {
          margin: 0;
          color: #9babc0;
          font-size: 9px;
          font-weight: 800;
          white-space: nowrap;
          letter-spacing: .8px;
        }

        .em-login-info {
          display: flex;
          gap: 13px;
          padding: 16px;
          background: #edf5ff;
          border: 1px solid #dceafa;
          border-radius: 12px;
        }

        .em-login-info-icon {
          display: grid;
          place-items: center;
          flex: 0 0 36px;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          color: #006bd1;
          background: #dcecff;
        }

        .em-login-info-icon svg {
          width: 20px;
          height: 20px;
        }

        .em-login-info strong {
          display: block;
          color: #27517d;
          font-size: 12px;
        }

        .em-login-info p {
          margin: 5px 0 0;
          color: #7890a9;
          font-size: 11px;
          line-height: 1.65;
        }

        .em-login-bottom {
          display: flex;
          justify-content: space-between;
          gap: 15px;
          margin-top: 45px;
          color: #96a9bf;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: .4px;
        }

        @media (max-width: 1050px) {
          .em-login-hero {
            padding: 30px 32px;
          }

          .em-login-hero-content h1 {
            font-size: 51px;
          }

          .em-login-form-section {
            padding: 45px 32px;
          }

          .em-login-flow {
            gap: 3px;
          }
        }

        @media (max-width: 800px) {
          .em-login-shell {
            grid-template-columns: 1fr;
          }

          .em-login-hero {
            padding: 22px 26px;
          }

          .em-login-hero-content {
            padding: 38px 0 20px;
          }

          .em-login-hero-content h1 {
            font-size: 45px;
            margin: 16px 0 13px;
          }

          .em-login-hero-description {
            font-size: 13px;
            max-width: 550px;
          }

          .em-login-visual,
          .em-login-features,
          .em-login-hero-footer {
            display: none;
          }

          .em-login-form-section {
            padding: 42px 25px 70px;
          }

          .em-login-form-container {
            max-width: 470px;
          }

          .em-login-form-top {
            margin-bottom: 27px;
          }

          .em-login-heading p {
            margin-bottom: 30px;
          }
        }

        @media (max-width: 420px) {
          .em-login-hero-content h1 {
            font-size: 38px;
            letter-spacing: -2px;
          }

          .em-login-heading h2 {
            font-size: 31px;
          }

          .em-login-bottom {
            flex-direction: column;
            gap: 7px;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .em-login *,
          .em-login *::before,
          .em-login *::after {
            animation: none !important;
            transition: none !important;
          }
        }
      `}</style>
    </main>
  );
}

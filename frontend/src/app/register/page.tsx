"use client";

import { useState, type FormEvent } from "react";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function register(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading) return;

    setError("");

    if (password.length < 12 || password.length > 128) {
      setError("Password must be between 12 and 128 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch("/api/auth/organizer/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          password,
          confirm_password: confirmPassword,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Unable to create account."
        );
      }

      setSuccess(true);
      setPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Registration failed."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="register-page">
      <section className="register-hero">
        <a href="/login" className="register-brand">
          <span className="register-logo">E✳</span>
          <span>EventMesh<span className="blue-dot">.</span></span>
        </a>

        <div className="register-hero-content">
          <p className="register-eyebrow">EVENTMESH AI OPERATIONS</p>
          <h1>
            Your events.<br />
            Your workspace<span className="blue-dot">.</span>
          </h1>
          <p>
            Create your organizer account to manage schedules,
            handle disruptions, and explore intelligent event operations.
          </p>

          <div className="register-feature">✓ AI-assisted recovery</div>
          <div className="register-feature">✓ Smart event scheduling</div>
          <div className="register-feature">✓ PayPal Sandbox integration</div>
        </div>

        <small>EVENT OPERATIONS, REIMAGINED</small>
      </section>

      <section className="register-right">
        <div className="register-card">
          <span className="register-tag">ORGANIZER REGISTRATION</span>

          {success ? (
            <div role="status" className="register-success">
              <div className="register-check">✓</div>
              <h2>Account created!</h2>
              <p>
                Your organizer account is ready.
                Sign in using <strong>{email}</strong>.
              </p>
              <a href="/login" className="register-submit">
                Go to Sign In →
              </a>
            </div>
          ) : (
            <>
              <h2>Create your account<span className="blue-dot">.</span></h2>
              <p className="register-description">
                Get started with your EventMesh AI workspace.
              </p>

              <form onSubmit={register} className="register-form">
                <label htmlFor="reg-name">Full name</label>
                <input
                  id="reg-name"
                  type="text"
                  placeholder="Your full name"
                  autoComplete="name"
                  required
                  minLength={2}
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />

                <label htmlFor="reg-email">Email address</label>
                <input
                  id="reg-email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />

                <label htmlFor="reg-password">Password</label>
                <div className="register-password">
                  <input
                    id="reg-password"
                    type={showPassword ? "text" : "password"}
                    placeholder="At least 12 characters"
                    autoComplete="new-password"
                    required
                    minLength={12}
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>

                <label htmlFor="reg-confirm">Confirm password</label>
                <input
                  id="reg-confirm"
                  type={showPassword ? "text" : "password"}
                  placeholder="Confirm your password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />

                {error && (
                  <div className="register-error" role="alert">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  className="register-submit"
                  disabled={loading}
                >
                  {loading ? "Creating account..." : "Create organizer account →"}
                </button>
              </form>

              <p className="register-switch">
                Already have an account?{" "}
                <a href="/login">Sign in →</a>
              </p>
            </>
          )}

          <p className="register-footer">
            Local development · PayPal Sandbox only
          </p>
        </div>
      </section>

      <style>{`
        .register-page {
          display: grid;
          grid-template-columns: 1fr 1fr;
          min-height: 100vh;
          background: #f5f9ff;
          color: #102a50;
          font-family: Inter, system-ui, Arial, sans-serif;
        }
        .register-page * { box-sizing: border-box; }
        .register-hero {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 35px;
          padding: clamp(28px, 5vw, 65px);
          background: linear-gradient(140deg, #071e49, #003087 65%, #0869c8);
          color: white;
        }
        .register-brand {
          display: flex;
          align-items: center;
          gap: 13px;
          width: fit-content;
          color: white;
          text-decoration: none;
          font-size: 24px;
          font-weight: 850;
        }
        .register-logo {
          display: grid;
          place-items: center;
          width: 47px;
          height: 47px;
          border-radius: 12px;
          background: #e5f2ff;
          color: #003087;
          font-size: 25px;
        }
        .blue-dot { color: #77c7ff; }
        .register-eyebrow {
          color: #a4d7ff;
          font-size: 11px;
          font-weight: 850;
          letter-spacing: 2px;
        }
        .register-hero h1 {
          margin: 19px 0;
          font-size: clamp(38px, 4.4vw, 66px);
          line-height: 1.12;
          letter-spacing: -2px;
        }
        .register-hero-content > p:not(.register-eyebrow) {
          max-width: 480px;
          color: #c7dffb;
          font-size: 15px;
          line-height: 1.8;
          margin-bottom: 30px;
        }
        .register-feature {
          padding: 11px 0;
          color: #dcecff;
          font-size: 13px;
        }
        .register-hero > small {
          color: #99bdec;
          letter-spacing: 1.4px;
          font-size: 10px;
          font-weight: 800;
        }
        .register-right {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 45px 25px;
        }
        .register-card {
          width: 100%;
          max-width: 435px;
        }
        .register-tag {
          display: inline-block;
          padding: 9px 12px;
          background: #e6f2ff;
          border: 1px solid #cde4fb;
          border-radius: 8px;
          color: #005cb9;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1px;
        }
        .register-card h2 {
          margin: 24px 0 9px;
          font-size: 37px;
          letter-spacing: -1.5px;
          font-weight: 850;
        }
        .register-description {
          color: #7c8fa9;
          font-size: 13px;
          line-height: 1.7;
          margin-bottom: 24px;
        }
        .register-form {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .register-form label {
          margin-top: 8px;
          color: #25466f;
          font-size: 12px;
          font-weight: 800;
        }
        .register-form input {
          width: 100%;
          height: 49px;
          border: 1px solid #d3e3f5;
          border-radius: 9px;
          background: white;
          color: #16365f;
          padding: 0 14px;
          outline: none;
          font-size: 13px;
        }
        .register-form input:focus {
          border-color: #0070e0;
          box-shadow: 0 0 0 3px rgba(0,112,224,.12);
        }
        .register-password { position: relative; }
        .register-password input { padding-right: 70px; }
        .register-password button {
          position: absolute;
          right: 9px;
          top: 9px;
          padding: 7px;
          border: 0;
          background: transparent;
          color: #0064c8;
          font-size: 12px;
          font-weight: 800;
        }
        .register-submit {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          min-height: 51px;
          margin-top: 18px;
          padding: 13px;
          border: 0;
          border-radius: 9px;
          background: #0070e0;
          color: white;
          font-size: 13px;
          font-weight: 850;
          text-decoration: none;
          cursor: pointer;
        }
        .register-submit:hover:not(:disabled) { background: #0059b9; }
        .register-submit:disabled { opacity: .6; }
        .register-switch {
          margin-top: 24px;
          text-align: center;
          color: #8194ac;
          font-size: 12px;
        }
        .register-switch a {
          color: #0069ce;
          font-weight: 800;
          text-decoration: none;
        }
        .register-error {
          margin-top: 10px;
          padding: 12px;
          border: 1px solid #efc5c5;
          border-radius: 8px;
          background: #fff0f0;
          color: #a63333;
          font-size: 12px;
        }
        .register-success p {
          color: #7489a5;
          line-height: 1.7;
        }
        .register-check {
          display: grid;
          place-items: center;
          width: 60px;
          height: 60px;
          margin-top: 25px;
          border-radius: 16px;
          background: #e4f5eb;
          color: #20854b;
          font-size: 30px;
        }
        .register-footer {
          margin-top: 42px;
          padding-top: 18px;
          border-top: 1px solid #e0e9f5;
          color: #96a9c0;
          font-size: 11px;
          text-align: center;
        }
        @media (max-width: 800px) {
          .register-page { grid-template-columns: 1fr; }
          .register-hero { padding: 25px; gap: 18px; }
          .register-hero h1 { font-size: 39px; }
          .register-feature, .register-hero > small { display: none; }
          .register-right { padding: 35px 20px; }
        }
      `}</style>
    </main>
  );
}

// Only ever rendered when APP_PASSWORD is set on the server.
import { useState } from "react";
import { api } from "../api";
import { SERIF, T } from "../theme";
import { Button, ErrorNote, TextInput } from "../components/ui";

export default function Login({ onAuthenticated }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onAuthenticated();
    } catch (e) {
      setError(e.message || "Couldn't sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", padding: "1.5rem",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          width: "100%", maxWidth: "22rem", background: T.panel,
          border: `1px solid ${T.border}`, borderRadius: "4px", padding: "1.5rem",
          display: "flex", flexDirection: "column", gap: "0.9rem",
        }}
      >
        <div>
          <div style={{ color: T.brass, fontSize: "0.95rem" }}>◆</div>
          <h1
            style={{
              fontFamily: SERIF, color: T.parchment,
              fontSize: "1.4rem", margin: "0.35rem 0 0",
            }}
          >
            The Briefing Table
          </h1>
          <p
            style={{
              color: T.parchmentDim, fontSize: "0.85rem",
              lineHeight: 1.6, margin: "0.5rem 0 0",
            }}
          >
            This instance is password-protected.
          </p>
        </div>

        <label htmlFor="password" style={{ color: T.parchmentDim, fontSize: "0.8rem" }}>
          Password
        </label>
        <input
          id="password"
          type="password"
          value={password}
          autoFocus
          onChange={(e) => setPassword(e.target.value)}
          style={{
            background: T.panelAlt, color: T.parchment,
            border: `1px solid ${T.border}`, borderRadius: "3px",
            padding: "0.5rem 0.6rem", fontSize: "0.9rem",
          }}
        />

        <ErrorNote message={error} />

        <Button type="submit" disabled={busy || !password}>
          {busy ? "Checking..." : "Enter"}
        </Button>
      </form>
    </div>
  );
}

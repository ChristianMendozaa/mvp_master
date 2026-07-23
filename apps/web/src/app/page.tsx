import Link from "next/link";

import { browserSession } from "@/lib/auth";

export default async function Home(): Promise<React.ReactElement> {
  const session = await browserSession();
  return (
    <main
      className="shell"
      style={{ minHeight: "100vh", display: "grid", alignItems: "center" }}
    >
      <section
        style={{
          display: "grid",
          gap: "2rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          alignItems: "center",
        }}
      >
        <div>
          <p className="eyebrow">Controlled software delivery</p>
          <h1
            style={{
              fontSize: "clamp(2.7rem, 8vw, 6.4rem)",
              lineHeight: 0.93,
              margin: "1rem 0",
            }}
          >
            From client intent to verified change.
          </h1>
          <p
            className="muted"
            style={{ fontSize: "1.15rem", maxWidth: "42rem", lineHeight: 1.65 }}
          >
            Structure requirements, approve scope, dispatch isolated coding
            agents, and review independent evidence before a pull request is
            delivered.
          </p>
          <Link className="button" href={session ? "/app" : "/api/auth/login"}>
            {session ? "Open control plane" : "Sign in with local OIDC"}
          </Link>
        </div>
        <aside className="card" aria-label="Delivery workflow">
          {[
            "Client intake preserved",
            "Versioned specification approved",
            "Execution policy authorized",
            "Agent isolated and budgeted",
            "Tests run independently",
            "Evidence attached to delivery",
          ].map((item, index) => (
            <div
              key={item}
              style={{
                display: "grid",
                gridTemplateColumns: "2rem 1fr",
                gap: "0.75rem",
                padding: "0.9rem 0",
                borderBottom: index === 5 ? 0 : "1px solid var(--line)",
              }}
            >
              <strong style={{ color: "var(--brand)" }}>
                {String(index + 1).padStart(2, "0")}
              </strong>
              <span>{item}</span>
            </div>
          ))}
        </aside>
      </section>
    </main>
  );
}

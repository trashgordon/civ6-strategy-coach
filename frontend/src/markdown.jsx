// The plan comes back as markdown. This is the prototype's renderer, kept deliberately
// small: headers, bullets, numbered lists, bold, and rules are all the coach emits.
import { T, SERIF, SANS } from "./theme";

function renderInline(text, keyBase) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={`${keyBase}-${i}`} style={{ color: T.brass }}>
        {part}
      </strong>
    ) : (
      <span key={`${keyBase}-${i}`}>{part}</span>
    )
  );
}

export function Markdown({ text }) {
  if (!text) return null;

  const blocks = [];
  let listBuffer = [];
  let listType = null;
  // Soft-wrapped prose arrives as several source lines that are really one paragraph.
  // Buffer and join them, or each wrapped line renders as its own spaced-out <p>.
  let paraBuffer = [];

  function flushPara() {
    if (!paraBuffer.length) return;
    const joined = paraBuffer.join(" ");
    const key = `para-${blocks.length}`;
    blocks.push(
      <p
        key={key}
        style={{
          fontFamily: SANS,
          color: T.parchmentDim,
          lineHeight: 1.7,
          margin: "0 0 0.75rem",
        }}
      >
        {renderInline(joined, key)}
      </p>
    );
    paraBuffer = [];
  }

  function flushList() {
    if (!listBuffer.length) return;
    const Tag = listType === "ol" ? "ol" : "ul";
    const key = `list-${blocks.length}`;
    blocks.push(
      <Tag
        key={key}
        style={{
          margin: "0.5rem 0 1rem 0",
          paddingLeft: "1.25rem",
          listStyleType: listType === "ol" ? "decimal" : "disc",
          color: T.parchment,
        }}
      >
        {listBuffer.map((item, i) => (
          <li key={i} style={{ marginBottom: "0.35rem", lineHeight: 1.6 }}>
            {renderInline(item, `${key}-${i}`)}
          </li>
        ))}
      </Tag>
    );
    listBuffer = [];
    listType = null;
  }

  // Close whatever is open. Order matters: prose came before any list that follows it.
  function flush() {
    flushPara();
    flushList();
  }

  text.split("\n").forEach((raw, idx) => {
    const trimmed = raw.trim();

    if (!trimmed) {
      flush();
      return;
    }
    if (/^-{3,}$/.test(trimmed)) {
      flush();
      blocks.push(
        <div
          key={`hr-${idx}`}
          style={{ borderTop: `1px solid ${T.border}`, margin: "1.25rem 0" }}
        />
      );
      return;
    }

    const h3 = trimmed.match(/^###\s+(.*)/);
    const h2 = trimmed.match(/^##\s+(.*)/);
    const h1 = trimmed.match(/^#\s+(.*)/);
    const ol = trimmed.match(/^\d+\.\s+(.*)/);
    const ul = trimmed.match(/^[-*]\s+(.*)/);

    if (h3) {
      flush();
      blocks.push(
        <h3
          key={idx}
          style={{
            fontFamily: SANS, color: T.parchment, fontSize: "1.05rem", fontWeight: 600,
            margin: "1rem 0 0.35rem",
          }}
        >
          {renderInline(h3[1], `h3-${idx}`)}
        </h3>
      );
    } else if (h2) {
      flush();
      blocks.push(
        <h2
          key={idx}
          style={{
            fontFamily: SERIF, color: T.brass, fontSize: "1.2rem",
            margin: "1.5rem 0 0.6rem",
            borderBottom: `1px solid ${T.border}`, paddingBottom: "0.35rem",
          }}
        >
          {renderInline(h2[1], `h2-${idx}`)}
        </h2>
      );
    } else if (h1) {
      flush();
      blocks.push(
        <h1
          key={idx}
          style={{
            fontFamily: SERIF, color: T.parchment, fontSize: "1.5rem",
            margin: "1.5rem 0 0.5rem",
          }}
        >
          {renderInline(h1[1], `h1-${idx}`)}
        </h1>
      );
    } else if (ol) {
      flushPara();
      if (listType !== "ol") flushList();
      listType = "ol";
      listBuffer.push(ol[1]);
    } else if (ul) {
      flushPara();
      if (listType !== "ul") flushList();
      listType = "ul";
      listBuffer.push(ul[1]);
    } else {
      // Plain prose. A list can't continue across it, so close the list first.
      flushList();
      paraBuffer.push(trimmed);
    }
  });

  flush();
  return <>{blocks}</>;
}

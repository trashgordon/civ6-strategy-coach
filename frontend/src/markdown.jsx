// The plan comes back as markdown. This is a deliberately small renderer covering what
// the coach's prompt actually allows: headers, bullets, numbered lists, bold, italics,
// rules, and simple tables (a city-by-city layout or era-by-era cards reads far better
// as a table than as prose).
import { T, SERIF, SANS } from "./theme";

function renderInline(text, keyBase) {
  // Bold first, then italics inside each non-bold run, so **bold** never gets eaten by
  // the single-asterisk pattern.
  const boldParts = text.split(/\*\*(.+?)\*\*/g);
  return boldParts.flatMap((part, i) => {
    if (i % 2 === 1) {
      return [
        <strong key={`${keyBase}-b${i}`} style={{ color: T.brass }}>
          {part}
        </strong>,
      ];
    }
    return part.split(/(?<!\*)\*([^*\n]+)\*(?!\*)/g).map((piece, j) =>
      j % 2 === 1 ? (
        <em key={`${keyBase}-i${i}-${j}`}>{piece}</em>
      ) : (
        <span key={`${keyBase}-t${i}-${j}`}>{piece}</span>
      )
    );
  });
}

const isTableLine = (line) => line.startsWith("|") && line.length > 1;

function parseCells(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

// The |---|:--:|---| line under a header row. Never confused with a --- rule, because
// that has no pipes and is handled before we get here.
const isSeparatorRow = (cells) =>
  cells.length > 0 && cells.every((c) => /^:?-{1,}:?$/.test(c));

export function Markdown({ text }) {
  if (!text) return null;

  const blocks = [];
  let listBuffer = [];
  let listType = null;
  let paraBuffer = [];
  let tableBuffer = [];

  function flushPara() {
    if (!paraBuffer.length) return;
    const joined = paraBuffer.join(" ");
    const key = `para-${blocks.length}`;
    blocks.push(
      <p
        key={key}
        style={{
          fontFamily: SANS, color: T.parchmentDim, lineHeight: 1.7,
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
          margin: "0.5rem 0 1rem 0", paddingLeft: "1.25rem",
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

  function flushTable() {
    if (!tableBuffer.length) return;
    const key = `table-${blocks.length}`;
    const rows = tableBuffer.map(parseCells);
    tableBuffer = [];

    let header = null;
    let body = rows;
    if (rows.length > 1 && isSeparatorRow(rows[1])) {
      header = rows[0];
      body = rows.slice(2);
    }
    // Drop any stray separator rows the model emitted mid-table.
    body = body.filter((cells) => !isSeparatorRow(cells));
    if (!header && !body.length) return;

    const cell = {
      padding: "0.45rem 0.7rem",
      borderBottom: `1px solid ${T.border}`,
      fontSize: "0.85rem",
      lineHeight: 1.55,
      textAlign: "left",
      verticalAlign: "top",
      color: T.parchment,
    };

    blocks.push(
      // Wide layout tables must scroll inside the dossier, not stretch the page.
      <div key={key} style={{ overflowX: "auto", margin: "0.75rem 0 1.25rem" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "22rem" }}>
          {header && (
            <thead>
              <tr>
                {header.map((text, i) => (
                  <th
                    key={i}
                    scope="col"
                    style={{
                      ...cell,
                      color: T.parchmentDim,
                      fontSize: "0.72rem",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      borderBottom: `1px solid ${T.brassDim}`,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {renderInline(text, `${key}-h${i}`)}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {body.map((cells, r) => (
              <tr key={r}>
                {cells.map((text, ci) => (
                  <td
                    key={ci}
                    style={{
                      ...cell,
                      // The first column is the row's label — give it the brass accent.
                      color: ci === 0 && header ? T.brass : T.parchment,
                    }}
                  >
                    {renderInline(text, `${key}-${r}-${ci}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // Close whatever is open, in the order things can nest.
  function flush() {
    flushPara();
    flushList();
    flushTable();
  }

  text.split("\n").forEach((raw, idx) => {
    const trimmed = raw.trim();

    if (!trimmed) {
      flush();
      return;
    }

    // Table rows accumulate until something that isn't one.
    if (isTableLine(trimmed)) {
      flushPara();
      flushList();
      tableBuffer.push(trimmed);
      return;
    }
    flushTable();

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
            fontFamily: SANS, color: T.parchment, fontSize: "1.05rem",
            fontWeight: 600, margin: "1rem 0 0.35rem",
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
      flushList();
      paraBuffer.push(trimmed);
    }
  });

  flush();
  return <>{blocks}</>;
}

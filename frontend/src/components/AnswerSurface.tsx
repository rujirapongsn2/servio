"use client";

import { TextMessage } from "./messages/TextMessage";
import type { AnswerSurface as Answer } from "@/lib/a2ui-answers";
import styles from "./AnswerSurface.module.css";

export function AnswerSurface({ surface, locale = "th" }: { surface: Answer; locale?: "th" | "en" }) {
  const th = locale === "th";
  return <section className={styles.answer} data-a2ui-catalog="answers" aria-label={th ? "คำตอบ" : "Answer"}>
    <TextMessage text={surface.text} isUser={false} />
    {surface.results.map((result, index) => <details key={index} className={styles.details}>
      <summary>{th ? "ข้อมูลประกอบ" : "Result details"}{surface.results.length > 1 ? ` ${index + 1}` : ""}</summary>
      <div className={styles.scroll} role="region" tabIndex={0} aria-label={th ? "ข้อมูลจากเครื่องมือ" : "Tool data"}>
        {result.rows.length === 0 ? <p role="status">{th ? "ไม่พบข้อมูล" : "No results"}</p>
          : result.rows.length === 1 ? <dl className={styles.fields}>{result.columns.map((column, i) => <div key={i}><dt>{column}</dt><dd>{result.rows[0][i]}</dd></div>)}</dl>
          : <table><caption className="sr-only">{th ? "ผลการค้นข้อมูล" : "Query results"}</caption><thead><tr>{result.columns.map((column, i) => <th scope="col" key={i}>{column}</th>)}</tr></thead>
            <tbody>{result.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table>}
      </div>
      {result.truncated && <p className={styles.notice} role="status">{th ? "แสดงข้อมูลบางส่วน" : "Showing partial results"}</p>}
    </details>)}
    {surface.sources.length > 0 && <details className={styles.details}>
      <summary>{th ? "แหล่งข้อมูลที่ค้นคืน" : "Retrieved sources"} ({surface.sources.length})</summary>
      <ol className={styles.sources}>{surface.sources.map((source, index) => <li key={index}>
        <strong>{source.title}</strong>{source.excerpt && <p>{source.excerpt}</p>}
      </li>)}</ol>
    </details>}
  </section>;
}

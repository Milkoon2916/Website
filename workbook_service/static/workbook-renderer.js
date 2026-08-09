/**
 * workbook-renderer.js
 * generateWorkbook()이 반환한 데이터(master/chunks/odd)를 학생용 워크북 HTML로 변환.
 * 업로드된 "NE능률(민병천) 공통영어1 10단계 워크북" 샘플과 동일한 10단계 구성.
 * 체크된 steps 배열에 있는 단계만 렌더링한다.
 *
 * 사용 예:
 *   import { renderWorkbookHTML } from "./workbook-renderer.js";
 *   const html = renderWorkbookHTML(workbook, { title: "지문 제목", steps: [1,4,8] });
 */

function escapeHtml(str = "") {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------
// 텍스트 안의 특정 부분 문자열들을 순서대로 찾아 감싸는 유틸
// (빈칸 처리 / 밑줄 처리에 공용으로 사용. 이미 사용된 위치는 건너뛰어 중복 매칭을 피한다)
// ---------------------------------------------------------
function wrapPhrases(text, phrases, wrapFn) {
  const marks = []; // { start, end, item }
  let searchFrom = 0;
  for (const item of phrases) {
    const phrase = item.phrase ?? item;
    if (!phrase) continue;
    const idx = text.indexOf(phrase, searchFrom);
    if (idx === -1) continue; // 못 찾으면 스킵 (LLM 출력 불일치 방어)
    marks.push({ start: idx, end: idx + phrase.length, item });
    searchFrom = idx + phrase.length;
  }
  marks.sort((a, b) => a.start - b.start);

  let html = "";
  let cursor = 0;
  for (const m of marks) {
    html += escapeHtml(text.slice(cursor, m.start));
    html += wrapFn(escapeHtml(text.slice(m.start, m.end)), m.item);
    cursor = m.end;
  }
  html += escapeHtml(text.slice(cursor));
  return html;
}

// ---------------------------------------------------------
// CSS — 뉴트럴 톤 + 나눔고딕 (사이트 전체 톤과 통일)
// ---------------------------------------------------------
const CSS = `
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  :root{
    --ink:#1F2123; --ink-soft:#6B6E73; --rule:#E3E2DE;
    --accent:#4B4D52; --accent-dark:#26272A; --accent-pale:#EDECE9;
  }
  body {
    font-family: "NanumGothic", "Nanum Gothic", "Noto Sans CJK KR", sans-serif;
    color: var(--ink);
    line-height: 1.6;
    font-size: 10.5pt;
  }
  h1.wb-title { font-size: 18pt; margin: 0 0 4mm; font-weight: 800; }
  .wb-meta { display:flex; gap: 12mm; font-size: 10pt; color:var(--ink-soft); margin-bottom: 8mm; border-bottom: 1.5px solid var(--accent-dark); padding-bottom: 4mm; }
  .wb-meta span b { color:var(--ink); }

  section.step { page-break-before: always; }
  section.step:first-of-type { page-break-before: auto; }

  .step-header { display:flex; align-items:baseline; gap: 8px; margin-bottom: 3mm; }
  .step-badge {
    display:inline-block; background:var(--accent); color:#fff; font-weight:700;
    font-size: 9.5pt; padding: 3px 10px; border-radius: 4px; white-space:nowrap;
  }
  .step-title { font-size: 14pt; font-weight:800; }
  .step-desc { font-size: 9.3pt; color:var(--ink-soft); margin-bottom: 6mm; }

  .num { color:var(--accent-dark); font-weight:700; margin-right: 4px; }
  .answer-line { border-bottom: 1px solid var(--ink-soft); height: 7mm; margin: 2mm 0; }

  /* STEP 1: 본문 해석지 (2단 표) */
  table.bilingual { width:100%; border-collapse:collapse; }
  table.bilingual td { vertical-align:top; padding: 2.5mm 3mm; font-size: 10.3pt; border-bottom: 1px dotted var(--rule); }
  table.bilingual td.en-col { width:52%; border-right: 1px solid var(--rule); }
  table.bilingual td.ko-col { width:48%; color:#333; }
  table.bilingual tr.heading-row td { font-weight:800; font-size:11.5pt; padding-top:5mm; border-bottom:none; }

  /* STEP 2 / 3: 빈칸 연습 */
  .fillblock { margin-bottom: 6mm; padding-bottom: 4mm; border-bottom: 1px dotted var(--rule); }
  .fillblock .src { font-size: 10.8pt; }
  .fillblock .target { font-size: 10.3pt; color:#333; margin-top: 2mm; }
  .blank-fill {
    display:inline-block; min-width: 22mm; border-bottom: 1.4px solid var(--ink-soft);
    margin: 0 2px; height: 1em; vertical-align: -2px;
  }

  /* STEP 5: 동사형 */
  .verbform-hint { color: var(--accent-dark); font-weight:700; }

  /* STEP 6: 어법 선택형 */
  .choice-bracket { color: var(--accent-dark); font-weight:700; }

  /* STEP 7: 어색한 곳 찾기 */
  .odd-box { border:1px solid var(--rule); border-radius:6px; padding:5mm 6mm; margin-bottom:5mm; background:var(--accent-pale); }
  .odd-box .odd-label { font-size:9.5pt; font-weight:700; color:var(--accent-dark); margin-bottom:2mm; }
  .odd-box .odd-text { font-size: 10.3pt; line-height:1.8; }
  .odd-cand { text-decoration: underline; font-weight:700; }
  .odd-answers { margin-top: 4mm; font-size: 10pt; }
  .odd-answers .oa-row { display:flex; gap:4mm; align-items:center; margin-bottom:2mm; }
  .odd-answers .oa-blank { flex:1; border-bottom:1px solid var(--ink-soft); height:6mm; }
  .odd-answers .oa-arrow { color:var(--ink-soft); }

  /* STEP 8: 순서배열 */
  .order-item { margin-bottom: 6mm; padding-bottom:4mm; border-bottom:1px dotted var(--rule); }
  .order-item .ko { font-size:10.3pt; margin-bottom:2mm; }
  .order-item .pool { font-size:10.5pt; color:#333; }

  /* STEP 9: 영작 */
  .compose-item { margin-bottom: 7mm; padding-bottom:4mm; border-bottom:1px dotted var(--rule); }
  .compose-item .ko { font-size:10.5pt; margin-bottom:2mm; }
  .word-box {
    background:var(--accent-pale); border:1px solid var(--rule); border-radius:6px;
    padding:2mm 4mm; font-size:10pt; color:var(--accent-dark); margin-bottom:3mm; display:inline-block;
  }

  /* STEP 10: Check */
  .check-item { margin-bottom: 6mm; padding-bottom:4mm; border-bottom:1px dotted var(--rule); }
  .check-item .type-badge {
    font-size:8.5pt; font-weight:700; color:var(--accent-dark); background:var(--accent-pale);
    border-radius:4px; padding:2px 7px; margin-right:6px;
  }

  /* 정답지 */
  .answer-key { page-break-before: always; }
  .answer-key h2 { border-bottom: 2px solid var(--accent-dark); padding-bottom:2mm; }
  .answer-key .ak-section { margin-bottom: 8mm; }
  .answer-key .ak-section h3 { font-size:12pt; color:var(--ink); }
  .answer-key ul { padding-left: 18px; list-style: none; }
  .answer-key li { margin-bottom: 2mm; font-size: 10pt; }
`;

// ---------------------------------------------------------
// 공통 헬퍼
// ---------------------------------------------------------
function sentencesOnly(master) {
  return master.sentences.filter((s) => !s.is_heading);
}

function koById(master) {
  const map = {};
  master.sentences.forEach((s) => (map[s.id] = s.ko));
  return map;
}

function stepWrap(badge, title, desc, innerHtml) {
  return `
    <section class="step">
      <div class="step-header"><span class="step-badge">${badge}</span><span class="step-title">${title}</span></div>
      <div class="step-desc">${desc}</div>
      ${innerHtml}
    </section>`;
}

// ---------------------------------------------------------
// STEP 1: 본문 해석지
// ---------------------------------------------------------
function renderStep1(master) {
  const rows = master.sentences
    .map((s) => {
      if (s.is_heading) {
        return `<tr class="heading-row"><td colspan="2">${escapeHtml(s.en)} <span style="color:var(--ink-soft); font-weight:400;">— ${escapeHtml(s.ko)}</span></td></tr>`;
      }
      return `<tr>
        <td class="en-col"><span class="num">${s.id}.</span>${escapeHtml(s.en)}</td>
        <td class="ko-col">${escapeHtml(s.ko)}</td>
      </tr>`;
    })
    .join("");

  return stepWrap(
    "STEP 1",
    "본문 해석지",
    "영문과 해석을 읽으며 문장의 의미를 파악해 보세요.",
    `<table class="bilingual">${rows}</table>`
  );
}

// ---------------------------------------------------------
// STEP 2: 빈칸 연습 (우리말) — 영문 보고 한글 빈칸 채우기
// ---------------------------------------------------------
function renderStep2(master) {
  const items = sentencesOnly(master)
    .map((s) => {
      const koHtml = wrapPhrases(
        s.ko,
        (s.highlights || []).map((h) => ({ phrase: h.ko })),
        () => `<span class="blank-fill"></span>`
      );
      return `
      <div class="fillblock">
        <div class="src"><span class="num">${s.id}.</span>${escapeHtml(s.en)}</div>
        <div class="target">${koHtml}</div>
      </div>`;
    })
    .join("");

  return stepWrap("STEP 2", "빈칸 연습 (우리말)", "영문을 보고 우리말 해석을 완성하시오.", items);
}

// ---------------------------------------------------------
// STEP 3: 빈칸 연습 (영문) — 한글 보고 영문 빈칸 채우기
// ---------------------------------------------------------
function renderStep3(master) {
  const items = sentencesOnly(master)
    .map((s) => {
      const enHtml = wrapPhrases(
        s.en,
        (s.highlights || []).map((h) => ({ phrase: h.en })),
        () => `<span class="blank-fill"></span>`
      );
      return `
      <div class="fillblock">
        <div class="src">${escapeHtml(s.ko)}</div>
        <div class="target"><span class="num">${s.id}.</span>${enHtml}</div>
      </div>`;
    })
    .join("");

  return stepWrap("STEP 3", "빈칸 연습 (영문)", "우리말 해석을 보고 영문을 완성하시오.", items);
}

// ---------------------------------------------------------
// STEP 4: 해석 연습
// ---------------------------------------------------------
function renderStep4(master) {
  const items = sentencesOnly(master)
    .map(
      (s) => `
      <div class="fillblock">
        <div class="src"><span class="num">${s.id}.</span>${escapeHtml(s.en)}</div>
        <div class="answer-line"></div>
      </div>`
    )
    .join("");

  return stepWrap("STEP 4", "해석 연습", "영어 문장을 읽고 우리말 해석을 쓰시오.", items);
}

// ---------------------------------------------------------
// STEP 5: 동사형 연습
// ---------------------------------------------------------
function renderStep5(master) {
  const items = sentencesOnly(master)
    .filter((s) => s.verb_targets && s.verb_targets.length > 0)
    .map((s) => {
      const enHtml = wrapPhrases(
        s.en,
        s.verb_targets.map((v) => ({ phrase: v.correct_form, base: v.base_form })),
        (safe, item) => `<span class="verbform-hint">(${escapeHtml(item.base)})</span>`
      );
      return `
      <div class="fillblock">
        <div class="src">${escapeHtml(s.ko)}</div>
        <div class="target"><span class="num">${s.id}.</span>${enHtml}</div>
      </div>`;
    })
    .join("");

  return stepWrap("STEP 5", "동사형 연습", "괄호 안에 주어진 단어를 알맞게 고쳐 쓰세요.", items);
}

// ---------------------------------------------------------
// STEP 6: 어법 선택형 연습
// ---------------------------------------------------------
function renderStep6(master) {
  const items = sentencesOnly(master)
    .filter((s) => s.choice_points && s.choice_points.length > 0)
    .map((s) => {
      const enHtml = wrapPhrases(
        s.en,
        s.choice_points.map((c) => ({ phrase: c.correct, incorrect: c.incorrect })),
        (safe, item) => `<span class="choice-bracket">[${safe} / ${escapeHtml(item.incorrect)}]</span>`
      );
      return `
      <div class="fillblock">
        <div class="src">${escapeHtml(s.ko)}</div>
        <div class="target"><span class="num">${s.id}.</span>${enHtml}</div>
      </div>`;
    })
    .join("");

  return stepWrap("STEP 6", "어법 선택형 연습", "괄호 안에서 어법상 알맞은 것을 골라 보세요.", items);
}

// ---------------------------------------------------------
// STEP 7: 어색한 곳 찾기 연습
// ---------------------------------------------------------
function renderOddVariant(label, variant) {
  if (!variant || !variant.text) return "";
  const html = wrapPhrases(variant.text, variant.candidates || [], (safe) => `<span class="odd-cand">${safe}</span>`);
  const answerRows = [1, 2, 3]
    .map(
      () => `
      <div class="oa-row">
        <div class="oa-blank"></div>
        <div class="oa-arrow">→</div>
        <div class="oa-blank"></div>
      </div>`
    )
    .join("");

  return `
    <div class="odd-box">
      <div class="odd-label">${label}</div>
      <div class="odd-text">${html}</div>
      <div class="odd-answers">${answerRows}</div>
    </div>`;
}

function renderStep7(odd) {
  const items = (odd.paragraphs || [])
    .map(
      (p) => `
      <div style="margin-bottom:8mm;">
        <div style="font-weight:700; margin-bottom:2mm;">${p.paragraph_id} 다음 글의 밑줄 친 부분 중 세 개를 찾아 바르게 고쳐 쓰시오.</div>
        ${renderOddVariant("문맥상 어색한 것 찾기", p.context_variant)}
        ${renderOddVariant("어법상 어색한 것 찾기", p.grammar_variant)}
      </div>`
    )
    .join("");

  return stepWrap(
    "STEP 7",
    "어색한 곳 찾기 연습",
    "다음 글의 밑줄 친 부분 중 어색한 것을 세 개 찾아 쓰고, 알맞은 표현으로 고쳐 쓰시오.",
    items
  );
}

// ---------------------------------------------------------
// STEP 8: 순서배열 연습
// ---------------------------------------------------------
function renderStep8(master, chunks) {
  const ko = koById(master);
  const items = (chunks.unscramble || [])
    .map(
      (u) => `
      <div class="order-item">
        <div class="ko"><span class="num">${u.sentence_id}.</span>${escapeHtml(ko[u.sentence_id] || "")}</div>
        <div class="pool">(${u.shuffled_chunks.map((c) => escapeHtml(c)).join(" / ")})</div>
        <div class="answer-line"></div>
      </div>`
    )
    .join("");

  return stepWrap(
    "STEP 8",
    "순서배열 연습",
    "다음 우리말과 같은 뜻이 되도록 주어진 단어 및 어구를 알맞게 배열해 보세요.",
    items
  );
}

// ---------------------------------------------------------
// STEP 9: 영작 연습
// ---------------------------------------------------------
function renderStep9(master) {
  const items = sentencesOnly(master)
    .filter((s) => s.hint_words && s.hint_words.length > 0)
    .map(
      (s) => `
      <div class="compose-item">
        <div class="ko"><span class="num">${s.id}.</span>${escapeHtml(s.ko)}</div>
        <div class="word-box">${s.hint_words.map((w) => escapeHtml(w)).join(", ")}</div>
        <div class="answer-line"></div>
        <div class="answer-line"></div>
      </div>`
    )
    .join("");

  return stepWrap("STEP 9", "영작 연습", "다음 우리말과 같은 뜻이 되도록 주어진 단어를 활용하여 영작해 보세요.", items);
}

// ---------------------------------------------------------
// STEP 10: Check (종합 — 문장마다 유형을 돌려가며 섞어서 출제)
// ---------------------------------------------------------
function renderStep10(master, chunks) {
  const chunkBySentence = {};
  (chunks?.unscramble || []).forEach((u) => (chunkBySentence[u.sentence_id] = u));

  const items = [];
  for (const s of sentencesOnly(master)) {
    const rotation = s.id % 4;
    let html = "";

    if (rotation === 0 && s.choice_points && s.choice_points.length > 0) {
      const enHtml = wrapPhrases(
        s.en,
        s.choice_points.map((c) => ({ phrase: c.correct, incorrect: c.incorrect })),
        (safe, item) => `<span class="choice-bracket">[${safe} / ${escapeHtml(item.incorrect)}]</span>`
      );
      html = `<span class="type-badge">어법선택</span>${escapeHtml(s.ko)}<br><span class="num">${s.id}.</span>${enHtml}`;
    } else if (rotation === 1 && s.highlights && s.highlights.length > 0) {
      const koHtml = wrapPhrases(s.ko, s.highlights.map((h) => ({ phrase: h.ko })), () => `<span class="blank-fill"></span>`);
      html = `<span class="type-badge">빈칸(우리말)</span>${escapeHtml(s.en)}<br><span class="num">${s.id}.</span>${koHtml}`;
    } else if (rotation === 2 && chunkBySentence[s.id]) {
      const u = chunkBySentence[s.id];
      html = `<span class="type-badge">순서배열</span>${escapeHtml(s.ko)}<br><span class="num">${s.id}.</span>(${u.shuffled_chunks.map((c) => escapeHtml(c)).join(" / ")})<div class="answer-line"></div>`;
    } else if (s.verb_targets && s.verb_targets.length > 0) {
      const enHtml = wrapPhrases(
        s.en,
        s.verb_targets.map((v) => ({ phrase: v.correct_form, base: v.base_form })),
        (safe, item) => `<span class="verbform-hint">(${escapeHtml(item.base)})</span>`
      );
      html = `<span class="type-badge">동사형</span>${escapeHtml(s.ko)}<br><span class="num">${s.id}.</span>${enHtml}`;
    } else {
      html = `<span class="type-badge">해석</span><span class="num">${s.id}.</span>${escapeHtml(s.en)}<div class="answer-line"></div>`;
    }

    items.push(`<div class="check-item">${html}</div>`);
  }

  return stepWrap(
    "STEP 10",
    "Check (종합)",
    "여러 유형이 섞여 있습니다. 앞에서 배운 내용을 종합적으로 점검해 보세요.",
    items.join("")
  );
}

// ---------------------------------------------------------
// 정답지
// ---------------------------------------------------------
function renderAnswerKey(workbook, steps) {
  const need = new Set(steps);
  const sections = [];
  const master = workbook.master;

  if (master && (need.has(1) || need.has(4))) {
    const list = master.sentences
      .filter((s) => !s.is_heading)
      .map((s) => `<li>${s.id}. ${escapeHtml(s.ko)}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 1 / 4 — 해석</h3><ul>${list}</ul></div>`);
  }

  if (master && need.has(2)) {
    const list = sentencesOnly(master)
      .filter((s) => s.highlights && s.highlights.length)
      .map((s) => `<li>${s.id}. ${s.highlights.map((h) => escapeHtml(h.ko)).join(", ")}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 2 — 빈칸(우리말)</h3><ul>${list}</ul></div>`);
  }

  if (master && need.has(3)) {
    const list = sentencesOnly(master)
      .filter((s) => s.highlights && s.highlights.length)
      .map((s) => `<li>${s.id}. ${s.highlights.map((h) => escapeHtml(h.en)).join(", ")}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 3 — 빈칸(영문)</h3><ul>${list}</ul></div>`);
  }

  if (master && need.has(5)) {
    const list = sentencesOnly(master)
      .filter((s) => s.verb_targets && s.verb_targets.length)
      .map((s) => `<li>${s.id}. ${s.verb_targets.map((v) => escapeHtml(v.correct_form)).join(", ")}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 5 — 동사형</h3><ul>${list}</ul></div>`);
  }

  if (master && need.has(6)) {
    const list = sentencesOnly(master)
      .filter((s) => s.choice_points && s.choice_points.length)
      .map((s) => `<li>${s.id}. ${s.choice_points.map((c) => escapeHtml(c.correct)).join(", ")}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 6 — 어법 선택형</h3><ul>${list}</ul></div>`);
  }

  if (workbook.odd && need.has(7)) {
    const list = (workbook.odd.paragraphs || [])
      .map((p) => {
        const ctx = (p.context_variant?.candidates || [])
          .filter((c) => c.is_wrong)
          .map((c) => `${escapeHtml(c.phrase)} → ${escapeHtml(c.correct_form)}`)
          .join(" / ");
        const gr = (p.grammar_variant?.candidates || [])
          .filter((c) => c.is_wrong)
          .map((c) => `${escapeHtml(c.phrase)} → ${escapeHtml(c.correct_form)}`)
          .join(" / ");
        return `<li>문단 ${p.paragraph_id} — 문맥: ${ctx}<br>어법: ${gr}</li>`;
      })
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 7 — 어색한 곳 찾기</h3><ul>${list}</ul></div>`);
  }

  if (workbook.chunks && need.has(8)) {
    const list = (workbook.chunks.unscramble || [])
      .map((u) => `<li>${u.sentence_id}. ${escapeHtml(u.correct_chunks.join(" "))}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 8 — 순서배열</h3><ul>${list}</ul></div>`);
  }

  if (master && need.has(9)) {
    const list = sentencesOnly(master)
      .filter((s) => s.hint_words && s.hint_words.length)
      .map((s) => `<li>${s.id}. ${escapeHtml(s.en)}</li>`)
      .join("");
    sections.push(`<div class="ak-section"><h3>STEP 9 — 영작 (예시 답)</h3><ul>${list}</ul></div>`);
  }

  if (!sections.length) return "";

  return `
    <section class="answer-key">
      <h2>정답 (교사용)</h2>
      ${sections.join("\n")}
    </section>`;
}

// ---------------------------------------------------------
// 전체 문서 렌더링
// ---------------------------------------------------------
export function renderWorkbookHTML(workbook, { title = "영어 지문 워크북", steps = null, includeAnswerKey = true } = {}) {
  const need = new Set(steps && steps.length ? steps : workbook.steps || [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  const master = workbook.master;
  const chunks = workbook.chunks;
  const odd = workbook.odd;

  const parts = [];
  if (need.has(1) && master) parts.push(renderStep1(master));
  if (need.has(2) && master) parts.push(renderStep2(master));
  if (need.has(3) && master) parts.push(renderStep3(master));
  if (need.has(4) && master) parts.push(renderStep4(master));
  if (need.has(5) && master) parts.push(renderStep5(master));
  if (need.has(6) && master) parts.push(renderStep6(master));
  if (need.has(7) && odd) parts.push(renderStep7(odd));
  if (need.has(8) && master && chunks) parts.push(renderStep8(master, chunks));
  if (need.has(9) && master) parts.push(renderStep9(master));
  if (need.has(10) && master) parts.push(renderStep10(master, chunks));
  if (includeAnswerKey) parts.push(renderAnswerKey(workbook, [...need]));

  return `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(title)}</title>
  <style>${CSS}</style>
</head>
<body>
  <h1 class="wb-title">${escapeHtml(title)}</h1>
  <div class="wb-meta">
    <span>이름: <b>______________</b></span>
    <span>날짜: <b>______________</b></span>
  </div>
  ${parts.join("\n")}
</body>
</html>`;
}

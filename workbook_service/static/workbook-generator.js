/**
 * workbook-generator.js
 * 지문(passage)을 넣으면 10단계 워크북 데이터를 생성하는 모듈 (NE능률 계열 시판 워크북 구성과 동일한 10단계).
 * 브라우저에서 사용자 자신의 Gemini API 키로 직접 호출하는 구조.
 *
 * 10단계:
 *  1. 본문 해석지        2. 빈칸 연습(우리말)   3. 빈칸 연습(영문)
 *  4. 해석 연습          5. 동사형 연습         6. 어법 선택형 연습
 *  7. 어색한 곳 찾기 연습 8. 순서배열 연습        9. 영작 연습
 * 10. Check(종합)
 *
 * 사용 예:
 *   import { generateWorkbook, MODEL_OPTIONS } from "./workbook-generator.js";
 *   const workbook = await generateWorkbook({
 *     passage: "...",
 *     apiKey: "AIza...",
 *     model: "gemini-3.6-flash",
 *     steps: [1,2,3,4,5,6,7,8,9,10],   // 체크된 스텝만
 *   });
 */

// ---------------------------------------------------------
// 1. 모델 옵션 (드롭다운 UI에 그대로 사용 가능)
// ---------------------------------------------------------
export const MODEL_OPTIONS = [
  {
    value: "gemini-3.5-flash-lite",
    label: "빠르고 저렴 (3.5 Flash-Lite)",
    description: "대량 생성/속도 우선일 때",
  },
  {
    value: "gemini-3.6-flash",
    label: "균형 (3.6 Flash) - 추천",
    description: "구조화 추출 정확도와 비용의 균형",
  },
  {
    value: "gemini-3.1-pro",
    label: "고품질 (3.1 Pro)",
    description: "어법 포인트 선정처럼 정교한 판단이 필요할 때",
  },
];

const DEFAULT_MODEL = "gemini-3.6-flash";
const API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

const SYSTEM_INSTRUCTION =
  "당신은 한국 고등학교/중학교 영어 내신 교재를 만드는 전문 교사입니다. " +
  "시중 유명 내신 대비 워크북(NE능률 계열)과 동일한 수준과 형식으로 문제를 만듭니다. " +
  "아래 지문을 분석해서 지시된 형식의 JSON으로만 출력하세요. " +
  "설명, 마크다운, 코드블록 없이 순수 JSON만 반환합니다.";

// 사람이 읽는 단계 이름 (진행상황 표시/체크박스 라벨에 공용으로 사용)
export const STEP_LABELS = {
  1: "본문 해석지",
  2: "빈칸 연습 (우리말)",
  3: "빈칸 연습 (영문)",
  4: "해석 연습",
  5: "동사형 연습",
  6: "어법 선택형 연습",
  7: "어색한 곳 찾기 연습",
  8: "순서배열 연습",
  9: "영작 연습",
  10: "Check (종합)",
};
export const ALL_STEPS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// ---------------------------------------------------------
// 2. 공통 Gemini 호출 함수
// ---------------------------------------------------------
function parseRetryDelayMs(errJson) {
  const details = errJson?.error?.details || [];
  const retryInfo = details.find((d) => String(d["@type"] || "").includes("RetryInfo"));
  const raw = retryInfo?.retryDelay;
  if (raw) {
    const secs = parseFloat(String(raw).replace("s", ""));
    if (!Number.isNaN(secs)) return Math.ceil(secs * 1000) + 1000;
  }
  return null;
}

async function callGemini({ apiKey, model, prompt, schema, onStatus, maxRetries = 4 }) {
  const url = `${API_BASE}/${model}:generateContent?key=${apiKey}`;

  const body = {
    system_instruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: {
      responseMimeType: "application/json",
      responseSchema: schema,
      temperature: 0.3,
    },
  };

  let res;
  for (let attempt = 0; ; attempt++) {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (res.ok || (res.status !== 429 && res.status !== 503) || attempt >= maxRetries) break;

    let waitMs = res.status === 429 ? 20000 : 5000;
    try {
      const errJson = await res.clone().json();
      const parsed = parseRetryDelayMs(errJson);
      if (parsed) waitMs = parsed;
    } catch (e) { /* 파싱 실패 시 기본 대기시간 사용 */ }

    if (onStatus) {
      onStatus(
        res.status === 429
          ? `Gemini 요청 한도(429)에 걸렸어요. ${Math.ceil(waitMs / 1000)}초 후 자동 재시도합니다... (${attempt + 1}/${maxRetries})`
          : `Gemini 서버가 잠시 과부하 상태예요(503). ${Math.ceil(waitMs / 1000)}초 후 자동 재시도합니다... (${attempt + 1}/${maxRetries})`
      );
    }
    await new Promise((r) => setTimeout(r, waitMs));
  }

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gemini API 오류 (${res.status}): ${errText}`);
  }

  const data = await res.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("Gemini 응답에서 텍스트를 찾을 수 없습니다.");

  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`JSON 파싱 실패: ${e.message}\n원본: ${text.slice(0, 500)}`);
  }
}

// ---------------------------------------------------------
// 3. 문단 분리 유틸 (Step 1 본문 박스 구분 / Step 7 문맥 단위에 재사용)
// ---------------------------------------------------------
function countSentencesRough(text) {
  const n = (text.match(/[.!?][")]?(\s|$)/g) || []).length;
  return Math.max(1, n);
}

function splitParagraphs(passage) {
  const raw = passage.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const paragraphs = raw.length > 0 ? raw : [passage.trim()];

  const merged = [];
  for (const p of paragraphs) {
    if (
      merged.length > 0 &&
      countSentencesRough(p) < 4 &&
      countSentencesRough(merged[merged.length - 1]) < 8
    ) {
      merged[merged.length - 1] = merged[merged.length - 1] + " " + p;
    } else {
      merged.push(p);
    }
  }
  if (merged.length > 1 && countSentencesRough(merged[0]) < 4) {
    merged[1] = merged[0] + " " + merged[1];
    merged.shift();
  }
  return merged;
}

// ---------------------------------------------------------
// 4. 마스터 문장 데이터 생성
//    (Step 1/2/3/4/5/6/9/10 이 전부 이 데이터 하나를 재사용함 — LLM 호출 절약 + 문항 간 표현 일관성 확보)
// ---------------------------------------------------------
const MASTER_SCHEMA = {
  type: "OBJECT",
  properties: {
    sentences: {
      type: "ARRAY",
      items: {
        type: "OBJECT",
        properties: {
          id: { type: "INTEGER" },
          is_heading: { type: "BOOLEAN" },
          en: { type: "STRING" },
          ko: { type: "STRING" },
          highlights: {
            type: "ARRAY",
            items: {
              type: "OBJECT",
              properties: {
                en: { type: "STRING" },
                ko: { type: "STRING" },
                type: { type: "STRING", enum: ["grammar", "vocab"] },
              },
              propertyOrdering: ["en", "ko", "type"],
            },
          },
          verb_targets: {
            type: "ARRAY",
            items: {
              type: "OBJECT",
              properties: {
                base_form: { type: "STRING" },
                correct_form: { type: "STRING" },
              },
              propertyOrdering: ["base_form", "correct_form"],
            },
          },
          choice_points: {
            type: "ARRAY",
            items: {
              type: "OBJECT",
              properties: {
                correct: { type: "STRING" },
                incorrect: { type: "STRING" },
              },
              propertyOrdering: ["correct", "incorrect"],
            },
          },
          hint_words: { type: "ARRAY", items: { type: "STRING" } },
        },
        propertyOrdering: ["id", "is_heading", "en", "ko", "highlights", "verb_targets", "choice_points", "hint_words"],
      },
    },
  },
  propertyOrdering: ["sentences"],
};

export async function generateMasterSentences({ passage, apiKey, model = DEFAULT_MODEL, onStatus }) {
  const prompt = `
다음 영어 지문을 분석해서 문장 단위(그리고 소제목이 있다면 소제목도 별도 항목으로) 데이터를 만드세요.

각 항목(sentence)에 대해:
- is_heading: 소제목(예: "Getting to Know Your Anger" 같은 문단 제목)이면 true, 일반 문장이면 false.
- en: 원문 그대로 (철자/대소문자/구두점 변경 금지)
- ko: 자연스러운 한글 해석 (소제목이면 소제목의 한글 번역)
- highlights: 내신 시험에 나올 만한 핵심 어법 포인트/어휘를 3~6개 골라 각각 { en: 문장 속 정확한 원문 표현, ko: 그 표현에 대응하는 한글 해석 속 정확한 표현, type: "grammar" 또는 "vocab" } 로 나열 (문장이 짧으면 개수를 줄여도 됨, is_heading이면 빈 배열)
- verb_targets: 그 문장에서 동사형 연습에 쓸 만한 동사 0~3개를 { base_form: 원형/괄호에 제시할 기본형, correct_form: en 안에 실제 등장하는 정확한 활용형 } 로 나열 (is_heading이면 빈 배열)
- choice_points: 어법 선택형 문제에 쓸 어법 포인트 0~3개를 { correct: en 안에 실제 등장하는 정확한 표현, incorrect: 그럴듯하지만 틀린 대안 표현 } 으로 나열 (is_heading이면 빈 배열)
- hint_words: 영작 연습에 쓸, en에 실제 등장하는 핵심 단어를 원문 등장 순서 그대로 3~8개 나열 (is_heading이면 빈 배열)

id는 1부터 지문에 등장하는 순서대로 (소제목 포함) 매기세요.
highlights.en / verb_targets.correct_form / choice_points.correct 는 반드시 해당 문장의 en 안에 정확히 그대로 포함된 부분 문자열이어야 합니다.

[지문]
${passage}
`.trim();

  return callGemini({ apiKey, model, prompt, schema: MASTER_SCHEMA, onStatus });
}

// ---------------------------------------------------------
// 5. 순서배열/언스크램블용 청크 데이터 (Step 8에서 사용)
// ---------------------------------------------------------
const CHUNK_SCHEMA = {
  type: "OBJECT",
  properties: {
    unscramble: {
      type: "ARRAY",
      items: {
        type: "OBJECT",
        properties: {
          sentence_id: { type: "INTEGER" },
          correct_chunks: { type: "ARRAY", items: { type: "STRING" } },
          shuffled_chunks: { type: "ARRAY", items: { type: "STRING" } },
        },
        propertyOrdering: ["sentence_id", "correct_chunks", "shuffled_chunks"],
      },
    },
  },
  propertyOrdering: ["unscramble"],
};

export async function generateChunks({ passage, apiKey, model = DEFAULT_MODEL, onStatus }) {
  const prompt = `
다음 영어 지문의 모든 문장(소제목 제외)에 대해 순서배열(어순 배열) 문제를 만드세요.

청크 분리 규칙:
- 관사(a/an/the)는 뒤에 오는 형용사·명사(구)와 반드시 하나의 청크로 묶습니다.
- 전치사+명사구도 가능하면 하나의 청크로 묶으세요.
- 조동사+본동사 등 동사구는 분리하지 않습니다.
- 문장당 청크는 최소 3개, 최대 8개.
- shuffled_chunks는 correct_chunks를 무작위로 섞은 배열이며, 섞인 순서가 원래 순서와 완전히 같으면 안 됩니다.
- sentence_id는 지문에서 그 문장이 몇 번째 문장인지(소제목 포함해서 순서대로 센 id)와 일치해야 합니다.

[지문]
${passage}
`.trim();

  return callGemini({ apiKey, model, prompt, schema: CHUNK_SCHEMA, onStatus });
}

// ---------------------------------------------------------
// 6. 어색한 곳 찾기 연습용 데이터 (Step 7)
// ---------------------------------------------------------
const ODD_VARIANT_SCHEMA = {
  type: "OBJECT",
  properties: {
    text: { type: "STRING" },
    candidates: {
      type: "ARRAY",
      items: {
        type: "OBJECT",
        properties: {
          phrase: { type: "STRING" },
          is_wrong: { type: "BOOLEAN" },
          correct_form: { type: "STRING" },
        },
        propertyOrdering: ["phrase", "is_wrong", "correct_form"],
      },
    },
  },
  propertyOrdering: ["text", "candidates"],
};

export async function generateOddParagraphs({ passage, apiKey, model = DEFAULT_MODEL, onStatus }) {
  const paragraphs = splitParagraphs(passage);

  const results = await Promise.all(
    paragraphs.map((paragraphText, idx) => {
      const prompt = `
다음은 지문의 한 문단입니다. 이 문단을 바탕으로 "어색한 곳 찾기" 문제 두 종류를 만드세요.

1) context_variant (문맥상 어색한 것 찾기): 문단 속 밑줄 후보 단어를 5~8개 고르되, 그 중 정확히 3개는 문맥상 반대/부적절한 의미의 다른 단어로 바꿔치기하고, 나머지는 원문 그대로 둡니다.
   text: 바꿔치기가 반영된(즉 3개는 이미 틀린 단어로 교체된) 문단 전체 텍스트.
   candidates: text 안에 실제로 등장하는 밑줄 후보들을 등장 순서대로 나열. is_wrong=true인 3개는 correct_form에 원래(정답) 단어를 적고, 나머지(is_wrong=false)는 correct_form을 빈 문자열로 둡니다.

2) grammar_variant (어법상 어색한 것 찾기): 같은 방식이지만 의미가 아니라 어법(문법 형태: 수일치, 시제, 태, to부정사/동명사, 관계사 등)이 틀리도록 정확히 3곳을 바꿉니다.

두 variant 모두 candidates의 phrase는 해당 variant의 text 안에 정확히 그대로 등장하는 부분 문자열이어야 합니다.

[문단]
${paragraphText}
`.trim();

      return callGemini({
        apiKey,
        model,
        prompt,
        onStatus,
        schema: {
          type: "OBJECT",
          properties: {
            context_variant: ODD_VARIANT_SCHEMA,
            grammar_variant: ODD_VARIANT_SCHEMA,
          },
          propertyOrdering: ["context_variant", "grammar_variant"],
        },
      }).then((r) => ({ paragraph_id: idx + 1, ...r }));
    })
  );

  return { paragraphs: results };
}

// ---------------------------------------------------------
// 7. 전체 워크북 생성 — steps 배열에 있는 단계만 필요한 호출을 수행
// ---------------------------------------------------------
export async function generateWorkbook({ passage, apiKey, model = DEFAULT_MODEL, steps = ALL_STEPS, onProgress }) {
  const need = new Set(steps);
  const report = (step, status, message) => onProgress && onProgress({ step, status, message });
  const statusFor = (step) => (message) => report(step, "retry", message);

  const workbook = { passage, model, steps: [...need].sort((a, b) => a - b) };

  // 마스터 문장 데이터: 1,2,3,4,5,6,9,10번 중 하나라도 선택되면 필요
  const needsMaster = [1, 2, 3, 4, 5, 6, 9, 10].some((s) => need.has(s));
  if (needsMaster) {
    report(1, "start");
    workbook.master = await generateMasterSentences({ passage, apiKey, model, onStatus: statusFor(1) });
    report(1, "done");
  }

  // 청크 데이터: 8번 또는 10번(Check에서 순서배열 항목에 재사용)이 선택되면 필요
  if (need.has(8) || need.has(10)) {
    report(8, "start");
    workbook.chunks = await generateChunks({ passage, apiKey, model, onStatus: statusFor(8) });
    report(8, "done");
  }

  // 어색한 곳 찾기: 7번이 선택되면 필요
  if (need.has(7)) {
    report(7, "start");
    workbook.odd = await generateOddParagraphs({ passage, apiKey, model, onStatus: statusFor(7) });
    report(7, "done");
  }

  return workbook;
}

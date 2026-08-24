"use client";

import { useState } from "react";
import { PencilLine, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Questionnaire,
  QuestionnaireChoice,
  QuestionnaireChoices,
  QuestionnaireInput,
  QuestionnaireItem,
  QuestionnaireNext,
  QuestionnairePrevious,
  QuestionnaireProgress,
  QuestionnaireSkip,
  QuestionnaireSubmit,
  QuestionnaireTitle,
} from "@/components/ui/questionnaire";
import type { StructuredQuestion } from "@/lib/api";

/** The validator's planned questions as a quick-answer form (the Amplitude
 *  agent-setup pattern: numbered choices, "1 of N" pagination, a "Something
 *  else" free-text lane, Skip). Choices come structured from the engine — it
 *  computed them (the two Johns, the status enum, the scope split). Submitting
 *  COMPOSES A CHAT MESSAGE: answers always travel through the conversation,
 *  because the transcript is the engine's only state and provenance source.
 *  Dismissing (X) just means "I'll answer in chat instead". */
export default function QuestionForm({
  questions,
  onAnswer,
  disabled,
}: {
  questions: StructuredQuestion[];
  onAnswer: (text: string) => void;
  disabled: boolean;
}) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  // "form"-kind questions (capability 5's "one block" field form) don't fit
  // the Questionnaire's one-atomic-question-per-page pagination model — each
  // renders as its own dedicated multi-field block instead, submitted
  // independently. Everything else still goes through Questionnaire exactly
  // as before.
  const formQuestions = questions.filter((q) => q.kind === "form" && q.fields);
  const regularQuestions = questions.filter((q) => q.kind !== "form");

  return (
    <div className="space-y-3">
      {formQuestions.map((q) => (
        <FieldBlockForm key={q.slot} question={q} onAnswer={onAnswer} disabled={disabled} />
      ))}
      {regularQuestions.length > 0 && (
        <RegularQuestionForm
          questions={regularQuestions}
          onAnswer={onAnswer}
          disabled={disabled}
          onDismiss={() => setDismissed(true)}
        />
      )}
    </div>
  );
}

/** capability 5's "one block" native-action field form: every field (2
 *  required, 4 optional) as plain inputs in ONE form, submitting composes a
 *  SINGLE chat message naming whichever fields were filled ("List: X.
 *  Title: Y.") — the transcript is still the only state and provenance
 *  source, this is just a UI convenience for typing it out label by label. */
function FieldBlockForm({
  question,
  onAnswer,
  disabled,
}: {
  question: StructuredQuestion;
  onAnswer: (text: string) => void;
  disabled: boolean;
}) {
  const fields = question.fields ?? [];
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, f.value]))
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const parts = fields
      .map((f) => [f.label.replace(/\?$/, "").replace(/\(optional\)/i, "").trim(),
                  (values[f.key] ?? "").trim()])
      .filter(([, v]) => v)
      .map(([label, v]) => `${label}: ${v}`);
    if (parts.length) onAnswer(parts.join(". "));
  };

  return (
    <form
      onSubmit={submit}
      className="space-y-2.5 rounded-xl border border-hairline bg-card p-4"
    >
      <p className="text-[13.5px] font-semibold">{question.prompt}</p>
      {fields.map((f) => (
        <div key={f.key} className="flex items-center gap-2">
          <label className="w-40 shrink-0 text-[12px] text-ink-soft">
            {f.label.replace(/\?$/, "")}
            {f.required && <span className="text-destructive"> *</span>}
          </label>
          {f.kind === "choice" ? (
            <select
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              className="min-w-0 flex-1 rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-[12.5px] outline-none focus:border-ink-soft"
            >
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              className="min-w-0 flex-1 rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-[12.5px] outline-none focus:border-ink-soft"
            />
          )}
        </div>
      ))}
      <Button type="submit" size="sm" disabled={disabled}>
        Continue
      </Button>
    </form>
  );
}

function RegularQuestionForm({
  questions,
  onAnswer,
  disabled,
  onDismiss,
}: {
  questions: StructuredQuestion[];
  onAnswer: (text: string) => void;
  disabled: boolean;
  onDismiss: () => void;
}) {
  // unique per question — two questions may share one slot
  const fieldName = (q: StructuredQuestion, i: number) => `${q.slot}#${i}`;

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const parts: string[] = [];
    questions.forEach((q, i) => {
      const vals = fd
        .getAll(fieldName(q, i))
        .map((v) => String(v).trim())
        .filter(Boolean);
      if (vals.length) parts.push(vals.join(", "));
    });
    if (parts.length) onAnswer(parts.join(". "));
  };

  const multi = questions.length > 1;

  return (
    <div className="rounded-xl border border-hairline bg-card p-4">
      <Questionnaire onSubmit={submit} shortcuts="numbers">
        {questions.map((q, qi) => (
          // keyed by INDEX, not slot: one slot can carry two different
          // questions ("dara" unknown AND "john" ambiguous on the same
          // targets slot), and slot-keying silently rendered only one
          <QuestionnaireItem
            key={fieldName(q, qi)}
            name={fieldName(q, qi)}
            multiple={q.multiple}
          >
            <div className="flex items-start justify-between gap-3">
              <QuestionnaireTitle className="text-[13.5px] font-semibold">
                {q.prompt.replaceAll("**", "")}
              </QuestionnaireTitle>
              <span className="flex shrink-0 items-center gap-1">
                {multi && (
                  <>
                    <QuestionnairePrevious
                      variant="ghost"
                      size="sm"
                      className="size-7 min-h-0 p-0 text-muted-foreground"
                    >
                      ‹
                    </QuestionnairePrevious>
                    <QuestionnaireProgress className="min-w-0 text-[12px]" />
                    <QuestionnaireNext
                      variant="ghost"
                      size="sm"
                      className="size-7 min-h-0 p-0 text-muted-foreground"
                    >
                      ›
                    </QuestionnaireNext>
                  </>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="size-7 min-h-0 p-0 text-muted-foreground"
                  aria-label="Dismiss — answer in chat instead"
                  onClick={onDismiss}
                >
                  <X className="size-3.5" />
                </Button>
              </span>
            </div>
            {q.options.length > 0 && (
              <QuestionnaireChoices>
                {q.options.map((o) => (
                  <QuestionnaireChoice key={o.value} value={o.value}>
                    {o.label}
                  </QuestionnaireChoice>
                ))}
              </QuestionnaireChoices>
            )}
            <div className="flex items-center gap-2">
              {(q.allow_other || q.options.length === 0) && (
                <>
                  <PencilLine className="size-3.5 shrink-0 text-muted-foreground" />
                  <QuestionnaireInput
                    placeholder={
                      q.other_hint ||
                      (q.options.length ? "Something else" : "Type your answer")
                    }
                    className="min-w-0 flex-1"
                  />
                </>
              )}
              <span className="ms-auto flex shrink-0 gap-2">
                {multi && (
                  <QuestionnaireSkip variant="outline" size="sm">
                    Skip
                  </QuestionnaireSkip>
                )}
                <QuestionnaireSubmit size="sm" disabled={disabled}>
                  Answer
                </QuestionnaireSubmit>
              </span>
            </div>
          </QuestionnaireItem>
        ))}
      </Questionnaire>
    </div>
  );
}

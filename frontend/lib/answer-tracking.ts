import type { AnswerHelpers } from "@/lib/answer-helpers";

export const ANSWERED_BY = ["typed", "quick_reply", "date_picker"] as const;

export type AnsweredBy = (typeof ANSWERED_BY)[number];

export type Answer = {
  by: AnsweredBy;
  // Which button was tapped, counting from 1.
  position?: number;
};

export const TYPED: Answer = {
  by: "typed",
};

type Details = Record<string, string | number | boolean>;

type SentJob = {
  jobId: string;
  text: string;
};

export function offeredDetails(offered: AnswerHelpers): Details {
  const buttons = offered.quickReplies.length;
  const datePicker = offered.answerFormat === "date";

  return {
    quick_replies: buttons,
    date_picker: datePicker,
  };
}

export function sentDetails(job: SentJob, answer: Answer, offered: AnswerHelpers): Details {
  const onOffer = offeredDetails(offered);

  const details: Details = {
    job_id: job.jobId,
    chars: job.text.length,
    answered_by: answer.by,
    ...onOffer,
  };

  if (answer.position !== undefined) {
    details.position = answer.position;
  }

  return details;
}

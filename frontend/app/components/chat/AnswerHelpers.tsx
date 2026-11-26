import { useRef } from "react";

import DateAnswer from "@/app/components/chat/DateAnswer";
import QuickReplies from "@/app/components/chat/QuickReplies";
import type { AnswerHelpers as Helpers } from "@/lib/answer-helpers";
import type { Answer } from "@/lib/answer-tracking";

type AnswerHelpersProps = {
  helpers: Helpers;
  onAnswer: (text: string, answer: Answer) => void;
};

export default function AnswerHelpers({ helpers, onAnswer }: Readonly<AnswerHelpersProps>) {
  const answered = useRef(false);

  function answerOnce(text: string, answer: Answer) {
    if (answered.current) {
      return;
    }

    answered.current = true;
    onAnswer(text, answer);
  }

  function tapped(option: string, position: number) {
    answerOnce(option, {
      by: "quick_reply",
      position,
    });
  }

  function picked(date: string) {
    answerOnce(date, {
      by: "date_picker",
    });
  }

  const hasButtons = helpers.quickReplies.length > 0;
  const hasDatePicker = helpers.answerFormat === "date";

  return (
    <>
      {hasButtons && <QuickReplies options={helpers.quickReplies} onPick={tapped} />}

      {hasDatePicker && <DateAnswer onPick={picked} />}
    </>
  );
}

"use client";

import { type RefObject, useEffect, useRef } from "react";

import { type AnswerHelpers, offersHelp } from "@/lib/answer-helpers";

type Chat = {
  turns: number;
  pending: boolean;
  helpers: AnswerHelpers;
};

type Place = RefObject<HTMLDivElement | null>;

function scrollTo(place: Place, block: ScrollLogicalPosition) {
  const element = place.current;

  if (!element) {
    return;
  }

  element.scrollIntoView({
    behavior: "smooth",
    block,
  });
}

export function useChatFocus(chat: Chat, latest: Place, threadEnd: Place) {
  const { turns, pending } = chat;
  const offering = offersHelp(chat.helpers);
  const answeredByChoice = useRef(false);

  // With choices under it, keep the question itself on screen.
  useEffect(() => {
    if (offering) {
      scrollTo(latest, "start");
      return;
    }

    scrollTo(threadEnd, "end");
  }, [turns, pending, offering, latest, threadEnd]);

  // A chosen answer's button is gone, so focus moves to the next question.
  useEffect(() => {
    const question = latest.current;
    const chose = answeredByChoice.current;

    if (pending || !chose || !question) {
      return;
    }

    answeredByChoice.current = false;

    question.focus({
      preventScroll: true,
    });
  }, [turns, pending, latest]);

  return function choiceMade() {
    answeredByChoice.current = true;
  };
}

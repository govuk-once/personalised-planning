import { type AnswerHelpers, type Offer, offerOf } from "./answer-helpers.ts";
import {
  listOrEmpty,
  outputOf,
  recordOrEmpty,
  textOrNull,
} from "./reply-fields.ts";

export type ChatTurn = {
  message: string;
  life_event_ids: unknown[];
  collected_facts: Record<string, unknown>;
  outstanding: unknown[];
  complete: boolean;
  situation: string | null;
} & AnswerHelpers;

export type ChatReply = {
  turn: ChatTurn;
  offer: Offer;
};

export function chatReply(reply: unknown, quickReplies: boolean): ChatReply {
  const output = outputOf(reply);
  const message = textOrNull(output.message) ?? "";
  const complete = output.complete === true;

  const offer = offerOf(output, {
    complete,
    enabled: quickReplies,
  });

  const turn = {
    message,
    life_event_ids: listOrEmpty(output.life_event_ids),
    collected_facts: recordOrEmpty(output.collected_facts),
    outstanding: listOrEmpty(output.outstanding),
    complete,
    situation: textOrNull(output.situation),
    ...offer.shown,
  };

  return {
    turn,
    offer,
  };
}

export function chatTurn(reply: unknown): ChatTurn {
  const { turn } = chatReply(reply, true);

  return turn;
}

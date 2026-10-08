export const CLAIM = "SET #status = :running, #run = :run, #started = :now";
const STILL_STARTING = "(#status = :pending AND #created > :cutoff)";
const CLAIMED_BY_RUN = "(#status = :running AND #run = :run)";
export const CLAIMABLE = `${STILL_STARTING} OR ${CLAIMED_BY_RUN}`;

export const FINISH = "SET #status = :done, #parts = :parts, #finished = :now";
export const FINISHABLE = "#run = :run AND #status IN (:running, :done)";

export const FAIL = "SET #status = :failed, #error = :error, #finished = :now";
export const UNFINISHED = "#status IN (:pending, :running)";
export const PENDING = "#status = :pending";

export const CREATE_ONLY = "attribute_not_exists(item_key)";

import { defineBackend } from "@aws-amplify/backend";
import { linkBranchFirst } from "./jobs-backend/link-first";
import { JobsBackend } from "./jobs-backend/resource";
import { observeSessions } from "./observability/resource";

const backend = defineBackend({});

const stack = backend.createStack("JobsBackend");
const jobs = new JobsBackend(stack, "Backend");

linkBranchFirst(stack);
observeSessions(stack, jobs);

backend.addOutput({ custom: jobs.outputs });

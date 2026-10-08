import { defineBackend } from "@aws-amplify/backend";
import { JobsBackend } from "./jobs-backend/resource";

const backend = defineBackend({});

const jobs = new JobsBackend(backend.createStack("JobsBackend"), "Backend");

backend.addOutput({ custom: jobs.outputs });

import { defineBackend } from "@aws-amplify/backend";
import { PythonBackend } from "./python-backend/resource";

const backend = defineBackend({});

const python = new PythonBackend(backend.createStack("PythonBackend"), "Api");

backend.addOutput({ custom: { backendUrl: python.url } });

# AgentCore CDK app

This CDK app is managed by the AgentCore CLI. It deploys everything declared in `agentcore/agentcore.json` into AWS
through the `@aws/agentcore-cdk` constructs. It is two files:

- `bin/cdk.ts` — the entry point. It reads the project once (`readAgentCoreProject`), creates one stack per deployment
  target (`resolveTargetStacks`), and turns `agentcore.json` into the application's props (`transformAgentCoreJson`).
  Everything about how `agentcore.json` is interpreted lives in the library, so it changes with the library version, not
  with this file.
- `lib/cdk-stack.ts` — `AgentCoreStack`, which instantiates one `AgentCoreApplication`. This is the file you edit.

## To deploy a new agent version

```bash
agentcore build    # synthesizes the CloudFormation templates into agentcore/cdk/cdk.out
agentcore deploy   # synthesizes, then deploys the stack for the selected target
agentcore status   # reports the resources agentcore.json declares
```

`npm run build` compiles the app, and `npx cdk synth` / `npx cdk diff` work from this directory too.

If a runtime or harness is configured with an `executionRoleArn`, CDK cannot modify that imported role: every grant
emits a synth-time warning listing the permissions that were not attached, and the role must already carry them.

`agentcore status` reports only the resources `agentcore.json` declares; resources you add here are visible
through CloudFormation (`aws cloudformation describe-stack-resources`).

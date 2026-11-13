import type { Stack } from "aws-cdk-lib";

const BRANCH_LINKER = "AmplifyBranchLinker";

export function linkBranchFirst(stack: Stack): void {
  const linker = stack.nestedStackParent?.node.tryFindChild(BRANCH_LINKER);

  if (linker) {
    stack.nestedStackResource?.node.addDependency(linker);
  }
}

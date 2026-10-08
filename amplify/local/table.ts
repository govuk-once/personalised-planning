type Resource = {
  Type: string;
  Properties: any;
};

type Template = {
  Resources: Record<string, Resource>;
};

function isTable(resource: Resource): boolean {
  return resource.Type === "AWS::DynamoDB::Table";
}

export function tableOf(template: Template) {
  const resources = Object.entries(template.Resources);
  const [name, resource] = resources.find(([, each]) => isTable(each))!;

  const {
    KeySchema,
    AttributeDefinitions,
    BillingMode,
    TimeToLiveSpecification,
  } = resource.Properties;

  return {
    definition: {
      TableName: name,
      KeySchema,
      AttributeDefinitions,
      BillingMode,
    },
    ttlAttribute: TimeToLiveSpecification.AttributeName,
  };
}

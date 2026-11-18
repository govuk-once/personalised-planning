const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;

function cloudWatch(region: string): string {
  return `https://${region}.console.aws.amazon.com/cloudwatch/home?region=${region}`;
}

export function dashboardUrl(region: string, name: string): string {
  return `${cloudWatch(region)}#dashboards/dashboard/${name}`;
}

export function sessionTracesUrl(region: string, session: string): string {
  return `${cloudWatch(region)}#gen-ai-observability/agent-core/session/${session}`;
}

export function traceSearchUrl(region: string): string {
  return `${cloudWatch(region)}#xray:traces/query`;
}

export function traceMapUrl(region: string, group: string): string {
  const context = `context~(xrayGroup~'${group}~timeRange~(delta~${TWELVE_HOURS_MS}))`;

  return `${cloudWatch(region)}#xray:service-map/map?~(query~()~${context})`;
}

export function browserSessionsUrl(
  region: string,
  monitor: string,
  session: string
): string {
  const filter = {
    filters: [
      {
        propertyKey: "metadata.appSessionId",
        operator: "=",
        values: [session],
      },
    ],
    operation: "and",
  };
  const json = JSON.stringify(filter);
  const once = encodeURIComponent(json);
  const twice = encodeURIComponent(once);

  return `${cloudWatch(region)}#rum:dashboard/${monitor}?tab=sessions&rumFilters=${twice}`;
}

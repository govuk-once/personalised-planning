import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";

import {
  browserSessionsUrl,
  sessionTracesUrl,
  traceMapUrl,
  traceSearchUrl,
} from "./console-links";
import { browserQuery, SESSION } from "./session-queries";
import type { Site } from "./site";

const FULL_WIDTH = 24;

export type Table = {
  title: string;
  logGroups: string[];
  query: string[];
  height: number;
};

export function table(props: Table): cloudwatch.LogQueryWidget {
  return new cloudwatch.LogQueryWidget({
    title: props.title,
    logGroupNames: props.logGroups,
    queryLines: props.query,
    width: FULL_WIDTH,
    height: props.height,
  });
}

// A branch with no RUM monitor has no browser events to show.
export function browserTable(site: Site): cloudwatch.IWidget[] {
  if (!site.monitor) {
    return [];
  }

  const browser = table({
    title: "Browser",
    logGroups: [site.monitor.logGroup],
    query: browserQuery(),
    height: 8,
  });

  return [browser];
}

function link(label: string, url: string): string {
  return `[${label}](${url})`;
}

export function links(region: string, site: Site): cloudwatch.TextWidget {
  const traces = sessionTracesUrl(region, SESSION);
  const search = traceSearchUrl(region);
  const map = traceMapUrl(region, site.traceGroup);

  const all = [
    link("Traces", traces),
    link("Find a trace", search),
    link("Trace map", map),
  ];

  if (site.monitor) {
    const browsers = browserSessionsUrl(region, site.monitor.name, SESSION);
    const browserSessions = link("Browser sessions", browsers);

    all.push(browserSessions);
  }

  const line = all.join(" · ");

  return new cloudwatch.TextWidget({
    markdown: `## Links\n${line}`,
    width: FULL_WIDTH,
    height: 2,
  });
}

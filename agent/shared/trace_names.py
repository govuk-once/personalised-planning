"""Names the gateway for X-Ray traces"""

import os
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor

MCP_SEND = ["MCP", "send"]


class _GatewayName(SpanProcessor):
    def __init__(self, gateway: str):
        self.gateway = gateway

    def on_start(self, span, parent_context=None):
        words = span.name.split(" ")

        if words[:2] != MCP_SEND:
            return

        operation = words[2] if len(words) > 2 else "send"

        span.set_attribute("aws.remote.service", self.gateway)
        span.set_attribute("aws.remote.operation", operation)


def name_the_gateway() -> None:
    url = os.getenv("GRAPH_GATEWAY_URL", "")
    host = urlparse(url).hostname
    provider = trace.get_tracer_provider()

    if not host or not hasattr(provider, "add_span_processor"):
        return

    # The gateway's id is the first part of its address.
    gateway = host.split(".")[0]
    name = _GatewayName(gateway)

    provider.add_span_processor(name)

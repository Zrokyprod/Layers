# OpenTelemetry JSON Trace Ingestion

Point an OTLP HTTP exporter at Zroky's JSON trace endpoint:

```yaml
exporters:
  otlphttp/zroky:
    endpoint: https://api.zroky.com/v1/events/otlp
    encoding: json
    headers:
      X-Zroky-Project: <project-id>
      Authorization: Bearer <api-key>
```

The OTLP HTTP exporter appends `/v1/traces`, so the effective intake path is `/v1/events/otlp/v1/traces`.

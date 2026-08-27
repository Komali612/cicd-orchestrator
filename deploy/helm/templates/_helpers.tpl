{{- define "agent.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "agent.labels" -}}
app.kubernetes.io/name: {{ include "agent.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
